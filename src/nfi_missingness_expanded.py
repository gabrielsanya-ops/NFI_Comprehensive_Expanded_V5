"""Expanded missing-data diagnostics and strategy comparison (no leakage for ML folds)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def missingness_by_column(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    miss = df.isna().sum()
    out = pd.DataFrame(
        {
            "column": miss.index,
            "n_missing": miss.values,
            "pct_missing": (100.0 * miss.values / n) if n else np.nan,
            "dtype": [str(df[c].dtype) for c in miss.index],
        }
    ).sort_values("pct_missing", ascending=False)
    return out.reset_index(drop=True)


def classify_variable_types(df: pd.DataFrame, max_cat: int = 30) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c]
        kind = "other"
        if pd.api.types.is_bool_dtype(s):
            kind = "binary"
        elif pd.api.types.is_numeric_dtype(s):
            kind = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(s):
            kind = "datetime"
        else:
            nun = s.nunique(dropna=True)
            kind = "categorical" if nun <= max_cat else "text_or_high_card"
        rows.append({"column": c, "type_class": kind, "nunique": int(s.nunique(dropna=True))})
    return pd.DataFrame(rows)


def simple_imputation_benchmarks(df: pd.DataFrame, numeric_cols, random_state: int = 42) -> pd.DataFrame:
    """Compare complete-case n vs median-imputed means for numeric columns (descriptive only)."""
    rows = []
    for c in numeric_cols:
        s = pd.to_numeric(df[c], errors="coerce")
        cc = s.dropna()
        med = s.fillna(s.median())
        rows.append(
            {
                "column": c,
                "n_complete": int(cc.shape[0]),
                "pct_missing": float(100.0 * s.isna().mean()),
                "mean_complete_case": float(cc.mean()) if len(cc) else np.nan,
                "mean_median_imputed": float(med.mean()) if len(med) else np.nan,
                "abs_diff_means": float(abs(cc.mean() - med.mean())) if len(cc) else np.nan,
                "note": "DESCRIPTIVE_BENCHMARK_NOT_FOR_INFERENCE",
            }
        )
    return pd.DataFrame(rows)


def try_mice_numeric(df: pd.DataFrame, cols, max_iter: int = 5, random_state: int = 42) -> dict:
    """Optional MICE via sklearn IterativeImputer; skipped if unavailable or too sparse."""
    try:
        from sklearn.experimental import enable_iterative_imputer  # noqa: F401
        from sklearn.impute import IterativeImputer
    except Exception as e:
        return {"status": "skipped", "reason": str(e)}

    use = [c for c in cols if c in df.columns]
    X = df[use].apply(pd.to_numeric, errors="coerce")
    if X.shape[1] < 2 or X.notna().sum().sum() < 50:
        return {"status": "skipped", "reason": "insufficient numeric coverage for MICE"}
    imp = IterativeImputer(max_iter=max_iter, random_state=random_state)
    arr = imp.fit_transform(X)
    out = pd.DataFrame(arr, columns=use, index=X.index)
    return {"status": "ok", "imputed": out, "columns": use}
