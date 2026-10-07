"""Absorbed OLS with primary-SKU clustered inference."""
from __future__ import annotations
from typing import Sequence, Tuple, Dict
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.sparse import csr_matrix, hstack
from scipy.stats import t as student_t
from statsmodels.stats.sandwich_covariance import cov_cluster
from .data import clean_category
from .config import (MAX_MODEL_ROWS, RANDOM_SEED, MIN_MODEL_ROWS, MIN_CLUSTERS,
                     FE_TOL, FE_MAX_ITER, MODEL_FE, OUTCOMES)

def fixed_effect_rank(frame, columns):
    """Count the joint dummy-space rank, including disconnected or nested effects."""
    blocks = []
    for column in columns:
        codes, levels = pd.factorize(frame[column], sort=True)
        blocks.append(csr_matrix((np.ones(len(frame)), (np.arange(len(frame)), codes)),
                                 shape=(len(frame), len(levels))))
    dummy = hstack(blocks, format="csr")
    # Normalize before ranking the small Gram matrix to avoid scale-driven rank loss.
    norms = np.sqrt(np.asarray(dummy.power(2).sum(axis=0)).ravel())
    dummy = dummy.multiply(1 / norms)
    gram = (dummy.T @ dummy).toarray()
    return int(np.linalg.matrix_rank(gram, hermitian=True))

def sample_model_rows(df: pd.DataFrame) -> pd.DataFrame:
    '''Apply the optional model-row cap with a reproducible random sample.'''
    if MAX_MODEL_ROWS is not None and len(df) > MAX_MODEL_ROWS:
        return df.sample(
            n=MAX_MODEL_ROWS,
            random_state=RANDOM_SEED,
        ).copy()
    return df.copy()


def residualize_multiway(
    df: pd.DataFrame,
    value_cols: Sequence[str],
    fe_cols: Sequence[str],
    tol: float = FE_TOL,
    max_iter: int = FE_MAX_ITER,
) -> Tuple[pd.DataFrame, int, bool]:
    '''Residualize numeric columns against several categorical fixed effects.'''
    z = df[list(value_cols)].astype(float).copy()
    z -= z.mean()
    converged = False

    for iteration in range(1, max_iter + 1):
        max_change = 0.0
        for fe in fe_cols:
            group_means = z.groupby(
                df[fe], observed=True, sort=False
            ).transform("mean")
            max_change = max(
                max_change,
                float(
                    np.nanmax(
                        np.abs(group_means.to_numpy())
                    )
                ),
            )
            z -= group_means
        if max_change < tol:
            converged = True
            break
    return z, iteration, converged


def fit_absorbed_model(
    df: pd.DataFrame,
    outcome: str,
    x_cols: Sequence[str],
    fe_cols: Sequence[str],
    cluster_col: str,
    model_name: str,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    '''Fit an OLS/LPM after absorbing fixed effects and cluster by primary SKU.'''
    needed = list(
        dict.fromkeys(
            [outcome] + list(x_cols) + list(fe_cols) + [cluster_col]
        )
    )
    d = df[needed].replace([np.inf, -np.inf], np.nan).copy()
    d = d.dropna(subset=[outcome] + list(x_cols)).copy()
    for col in list(fe_cols) + [cluster_col]:
        d[col] = clean_category(d[col])
    d = sample_model_rows(d)

    n_clusters = d[cluster_col].nunique()
    diagnostics = {
        "model": model_name,
        "outcome": outcome,
        "nobs": len(d),
        "n_clusters": n_clusters,
        "fixed_effects": ", ".join(fe_cols),
        "x_columns": ", ".join(x_cols),
        "status": "not_run",
    }
    if len(d) < MIN_MODEL_ROWS:
        diagnostics["status"] = "too_few_rows"
        return pd.DataFrame(), diagnostics
    if n_clusters < MIN_CLUSTERS:
        diagnostics["status"] = "too_few_clusters"
        return pd.DataFrame(), diagnostics

    residualized, iterations, converged = residualize_multiway(
        d,
        [outcome] + list(x_cols),
        fe_cols,
    )
    if not converged:
        raise RuntimeError(f"Fixed effects did not converge: {model_name}")
    y = residualized[outcome]
    x = residualized[list(x_cols)]
    varying = x.columns[
        x.var(ddof=0).fillna(0).gt(1e-14)
    ].tolist()
    diagnostics.update(
        {
            "fe_iterations": iterations,
            "fe_converged": converged,
            "status": "ok",
        }
    )
    if "is_bundle" not in varying:
        diagnostics["status"] = "no_within_fe_promo_variation"
        return pd.DataFrame(), diagnostics

    if np.linalg.matrix_rank(x[varying].to_numpy()) != len(varying):
        raise ValueError(f"Collinear residualized regressors: {model_name}")
    result = sm.OLS(y, x[varying], hasconst=False).fit()
    fe_rank = fixed_effect_rank(d, fe_cols)
    parameter_rank = fe_rank + len(varying)
    if len(d) <= parameter_rank:
        raise ValueError("Insufficient residual degrees of freedom.")
    # CR1 includes absorbed parameters; inference uses G - 1 cluster degrees of freedom.
    covariance = cov_cluster(result, d[cluster_col], use_correction=False)
    correction = n_clusters / (n_clusters - 1) * (len(d) - 1) / (len(d) - parameter_rank)
    standard_errors = np.sqrt(np.diag(covariance) * correction)
    critical = student_t.ppf(0.975, df=n_clusters - 1)
    diagnostics.update(fe_rank=fe_rank, parameter_rank=parameter_rank,
                       cluster_df=n_clusters - 1, covariance="CR1, full parameter rank")

    rows = []
    for i, term in enumerate(varying):
        beta = float(result.params[term])
        se = float(standard_errors[i])
        p_value = float(2 * student_t.sf(abs(beta / se), df=n_clusters - 1))
        rows.append(
            {
                "model": model_name,
                "outcome": outcome,
                "term": term,
                "coef": beta,
                "se": se,
                "ci_low": beta - critical * se,
                "ci_high": beta + critical * se,
                "p_value": p_value,
                "nobs": int(result.nobs),
                "n_clusters": n_clusters,
                "r2_within": float(result.rsquared),
                "fixed_effects": ", ".join(fe_cols),
                "fe_iterations": iterations,
                "fe_converged": converged,
            }
        )
    return pd.DataFrame(rows), diagnostics



def eligible_outcome_sample(
    panel: pd.DataFrame,
    outcome: str,
) -> pd.DataFrame:
    '''Return the valid rows for one outcome.'''
    if outcome == "log_delivery_hours":
        return panel[
            panel["jd_logistics"].eq(1)
            & panel["log_delivery_hours"].notna()
        ].copy()
    if outcome == "local_stockout_any":
        return panel[panel[outcome].notna()].copy()
    return panel.copy()


def estimate_family(
    panel: pd.DataFrame,
    family: str,
    x_cols: Sequence[str],
    fe_cols: Sequence[str] = MODEL_FE,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    '''Estimate all three outcomes for one sample/specification.'''
    result_parts = []
    diagnostics = []

    for outcome in OUTCOMES:
        outcome_panel = eligible_outcome_sample(panel, outcome)
        estimates, diagnostic = fit_absorbed_model(
            outcome_panel,
            outcome=outcome,
            x_cols=x_cols,
            fe_cols=fe_cols,
            cluster_col="primary_sku",
            model_name=f"{family}_{outcome}",
        )
        if not estimates.empty:
            result_parts.append(estimates)
        diagnostics.append(diagnostic)

    results = (
        pd.concat(result_parts, ignore_index=True)
        if result_parts
        else pd.DataFrame()
    )
    return results, pd.DataFrame(diagnostics)
