"""Optional fairness-metrics tool (Fairlearn-backed).

This is the "surface facts, not verdicts" layer. Given a dataset and a protected
column, it computes group-disaggregated FACTS — base rates, and FPR/FNR if a
prediction column is provided — so the audit record can carry real numbers
instead of just a logged choice.

It does NOT, and cannot, certify fairness:
  - it only works when a dataset is actually accessible (the curated-dataset
    case, e.g. compas.csv); concealed/unavailable data -> no scan;
  - the base-rate disparity it reports is exactly what makes the impossibility
    theorem bite — but *which* disparity to accept is a human value judgment,
    not something this tool decides.

Kept out of core.py so the integrity core stays zero-dependency.
Install with: uv sync --extra fairness
"""
from __future__ import annotations


def fairness_scan(dataset_path: str, protected_col: str, label_col: str,
                  prediction_col: str | None = None,
                  positive_label: str = "1") -> dict:
    """Compute group-disaggregated FACTS for an auditable record."""
    import pandas as pd
    from fairlearn.metrics import (MetricFrame, selection_rate,
                                   false_positive_rate, false_negative_rate)

    df = pd.read_csv(dataset_path)
    pos = str(positive_label)
    y = (df[label_col].astype(str) == pos).astype(int)
    s = df[protected_col]

    out: dict = {"dataset": dataset_path, "protected": protected_col,
                 "label": label_col, "n_rows": int(len(df))}

    # Base rate of the positive label per group — the gap that drives the
    # impossibility theorem (you can't equalize calibration AND error rates
    # across groups when these differ).
    base = MetricFrame(metrics=selection_rate, y_true=y, y_pred=y,
                       sensitive_features=s)
    out["base_rate_by_group"] = {str(k): round(float(v), 3)
                                 for k, v in base.by_group.items()}
    out["base_rate_disparity"] = round(float(base.by_group.max()
                                              - base.by_group.min()), 3)

    # Group sizes (small groups => unreliable for that group, a real caveat).
    out["group_sizes"] = {str(k): int(v)
                          for k, v in s.value_counts().items()}

    # If predictions are available, the actual error-rate disparities.
    if prediction_col and prediction_col in df.columns:
        yhat = (df[prediction_col].astype(str) == pos).astype(int)
        mf = MetricFrame(metrics={"FPR": false_positive_rate,
                                  "FNR": false_negative_rate},
                         y_true=y, y_pred=yhat, sensitive_features=s)
        out["error_rates_by_group"] = {
            str(g): {"FPR": round(float(mf.by_group.loc[g, "FPR"]), 3),
                     "FNR": round(float(mf.by_group.loc[g, "FNR"]), 3)}
            for g in mf.by_group.index}
        out["fpr_disparity"] = round(float(mf.by_group["FPR"].max()
                                           - mf.by_group["FPR"].min()), 3)
        out["fnr_disparity"] = round(float(mf.by_group["FNR"].max()
                                           - mf.by_group["FNR"].min()), 3)

    parts = [f"base-rate disparity {out['base_rate_disparity']} across "
             f"{protected_col} groups {out['base_rate_by_group']}"]
    if "fpr_disparity" in out:
        parts.append(f"FPR disparity {out['fpr_disparity']}, "
                     f"FNR disparity {out['fnr_disparity']}")
    out["summary"] = ("; ".join(parts) + ". (Facts, not a verdict — choosing "
                      "which disparity to accept is a human value judgment.)")
    return out
