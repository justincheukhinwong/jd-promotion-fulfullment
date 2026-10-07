"""Check absorbed inference against explicit dummy-variable regression."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import statsmodels.api as sm
from src.models import fit_absorbed_model, fixed_effect_rank


class AbsorbedInferenceTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(918)
        n = 1400
        self.frame = pd.DataFrame({
            "product": rng.integers(0, 35, n).astype(str),
            "day": rng.integers(0, 9, n).astype(str),
            "is_bundle": rng.integers(0, 2, n),
            "depth": rng.uniform(0, 0.4, n),
        })
        self.frame["y"] = (-0.12 * self.frame.is_bundle + 0.3 * self.frame.depth
            + self.frame["product"].astype(int) / 50
            + self.frame.day.astype(int) / 30 + rng.normal(0, 0.2, n))

    def estimate(self):
        return fit_absorbed_model(self.frame, "y", ["is_bundle", "depth"],
                                  ["product", "day"], "product", "validation")

    def test_matches_explicit_dummy_ols(self):
        estimated, diagnostic = self.estimate()
        x = pd.concat([self.frame[["is_bundle", "depth"]],
                       pd.get_dummies(self.frame[["product", "day"]], drop_first=True)], axis=1)
        x = sm.add_constant(x.astype(float))
        explicit = sm.OLS(self.frame.y, x).fit(cov_type="cluster", use_t=True,
            cov_kwds={"groups": self.frame["product"], "use_correction": True,
                      "df_correction": True})
        self.assertEqual(diagnostic["parameter_rank"], np.linalg.matrix_rank(x))
        for row in estimated.itertuples():
            np.testing.assert_allclose(
                [row.coef, row.se, row.p_value, row.ci_low, row.ci_high],
                [explicit.params[row.term], explicit.bse[row.term], explicit.pvalues[row.term],
                 *explicit.conf_int().loc[row.term]], rtol=1e-6, atol=1e-9)

    def test_nested_effects_are_not_counted_twice(self):
        frame = pd.DataFrame({"sku": ["a", "a", "b", "b", "c", "c"],
                              "brand": ["x", "x", "x", "x", "y", "y"]})
        self.assertEqual(fixed_effect_rank(frame, ["sku", "brand"]), 3)

    def test_nonconvergence_stops_inference(self):
        with patch("src.models.residualize_multiway", return_value=(None, 200, False)):
            with self.assertRaisesRegex(RuntimeError, "did not converge"):
                self.estimate()


if __name__ == "__main__":
    unittest.main()
