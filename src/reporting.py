"""Save compact, reproducible result tables."""
import re
import numpy as np
import pandas as pd
from IPython.display import display
from .config import TABLE_DIR

def record_table(name, frame, n=12, index=False):
    """Save the full table and preview a small number of rows."""
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_\-]+", "_", name)
    # Publish aggregate product labels rather than original hashed SKU identifiers.
    public = frame.copy()
    for column in ["primary_sku", "excluded_primary_sku"]:
        if column in public:
            if not hasattr(record_table, "sku_labels"):
                record_table.sku_labels = {}
            labels = record_table.sku_labels
            for sku in sorted(public[column].dropna().unique()):
                if sku not in labels:
                    labels[sku] = f"Product {len(labels) + 1:03d}"
            public[column] = public[column].map(labels)
    public.to_csv(TABLE_DIR / f"{name}.csv", index=index)
    display(public.head(min(n, 21)))

def format_bundle_estimates(results: pd.DataFrame) -> pd.DataFrame:
    '''Create a compact interpretation table for the bundle-minus-quantity term.'''
    if results.empty:
        return pd.DataFrame()
    out = results[results["term"].eq("is_bundle")].copy()
    out["estimate_scale"] = np.where(
        out["outcome"].isin(
            ["remote_any", "local_stockout_any"]
        ),
        "percentage points",
        "percent change in 1 + delivery hours",
    )
    binary = out["outcome"].isin(
        ["remote_any", "local_stockout_any"]
    )
    out["reported_estimate"] = np.where(
        binary,
        100 * out["coef"],
        100 * np.expm1(out["coef"]),
    )
    out["reported_ci_low"] = np.where(
        binary,
        100 * out["ci_low"],
        100 * np.expm1(out["ci_low"]),
    )
    out["reported_ci_high"] = np.where(
        binary,
        100 * out["ci_high"],
        100 * np.expm1(out["ci_high"]),
    )
    keep = [
        "model",
        "outcome",
        "reported_estimate",
        "reported_ci_low",
        "reported_ci_high",
        "estimate_scale",
        "p_value",
        "nobs",
        "n_clusters",
        "fixed_effects",
        "fe_converged",
    ]
    return out[keep].sort_values(["outcome", "model"])
