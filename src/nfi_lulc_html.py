"""National LULC Validation analyses restored/expanded from the HTML report assets.

Source of truth for methods: PROCESS_AND_VALIDATION.md and LULC_VALIDATION_REPORT.html
under F:/1.KSA/1.Forest/10.NFI/10.LULC_Validation.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_lulc_validated(path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def lulc_key_numbers(df: pd.DataFrame) -> dict:
    n = len(df)
    vt = df["validation_true"] if "validation_true" in df.columns else None
    accepted = int(vt.sum()) if vt is not None else None
    forest_in = int(df["inside_forest_reserved"].sum()) if "inside_forest_reserved" in df.columns else None
    final = df["final_lulc"] if "final_lulc" in df.columns else df.get("New LCU")
    n_forest = int((final.astype(str).str.lower() == "forest").sum()) if final is not None else None
    return {
        "n_rows": n,
        "n_su": int(df["su_no"].nunique()) if "su_no" in df.columns else None,
        "accepted_true": accepted,
        "updated_false": (n - accepted) if accepted is not None else None,
        "accepted_pct": round(100.0 * accepted / n, 1) if accepted and n else None,
        "inside_forest_reserved": forest_in,
        "final_lulc_forest": n_forest,
        "n_final_classes": int(final.nunique()) if final is not None else None,
    }


def validation_rule_counts(df: pd.DataFrame) -> pd.DataFrame:
    col = "validation_rule" if "validation_rule" in df.columns else None
    if col is None:
        return pd.DataFrame()
    out = df[col].value_counts(dropna=False).rename("rows").to_frame()
    out["percent"] = (100.0 * out["rows"] / len(df)).round(1)
    return out


def final_lulc_distribution(df: pd.DataFrame) -> pd.DataFrame:
    col = "final_lulc" if "final_lulc" in df.columns else "New LCU"
    out = df[col].value_counts(dropna=False).rename("rows").to_frame()
    out["percent"] = (100.0 * out["rows"] / len(df)).round(1)
    return out


def load_confusion_csv(path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def compute_oa_from_confusion(cm: pd.DataFrame) -> dict:
    """Best-effort OA if confusion is square counts with labels in index/columns."""
    if cm.empty:
        return {"oa": np.nan, "note": "empty"}
    # If first column is a label column, set index
    if cm.shape[1] and not np.issubdtype(cm.iloc[:, 0].dtype, np.number):
        cm = cm.set_index(cm.columns[0])
    arr = cm.select_dtypes(include=[np.number]).to_numpy(dtype=float)
    if arr.size == 0:
        return {"oa": np.nan, "note": "no numeric"}
    total = arr.sum()
    diag = np.trace(arr) if arr.shape[0] == arr.shape[1] else np.nan
    oa = float(diag / total) if total and np.isfinite(diag) else np.nan
    return {"oa": oa, "n": int(total), "shape": list(arr.shape)}


def plot_validation_true_false(df: pd.DataFrame, out_path=None):
    if "validation_true" not in df.columns:
        return None
    counts = df["validation_true"].value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(6, 4), dpi=140)
    labels = ["Updated Final LULC (False)", "Field kept (True)"]
    vals = [int(counts.get(False, 0)), int(counts.get(True, 0))]
    ax.bar(labels, vals, color=["#ef6c00", "#2e7d32"])
    ax.set_ylabel("Rows")
    ax.set_title("LULC Validation: accepted vs updated (national)")
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=200)
    return fig


def plot_final_lulc_bars(dist: pd.DataFrame, out_path=None, top_n: int = 15):
    d = dist.head(top_n)
    fig, ax = plt.subplots(figsize=(9, 5), dpi=140)
    ax.barh(d.index.astype(str)[::-1], d["rows"].values[::-1], color="#1f4e79")
    ax.set_xlabel("Rows")
    ax.set_title(f"Final LULC distribution (top {top_n})")
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=200)
    return fig


def plot_national_points(df: pd.DataFrame, out_path=None):
    lon = "lon" if "lon" in df.columns else None
    lat = "lat" if "lat" in df.columns else None
    if not lon or not lat:
        return None
    # unique plots
    pts = df.drop_duplicates(["su_no", "plot_no"]) if {"su_no", "plot_no"}.issubset(df.columns) else df
    x = pd.to_numeric(pts[lon], errors="coerce")
    y = pd.to_numeric(pts[lat], errors="coerce")
    m = x.notna() & y.notna()
    fig, ax = plt.subplots(figsize=(9, 8), dpi=140)
    if "validation_true" in pts.columns:
        for flag, color, lab in [(True, "#2e7d32", "Accepted"), (False, "#c62828", "Updated")]:
            sub = m & (pts["validation_true"] == flag)
            ax.scatter(x[sub], y[sub], s=4, c=color, alpha=0.35, label=lab)
        ax.legend(markerscale=3)
    else:
        ax.scatter(x[m], y[m], s=4, c="#0b3d0b", alpha=0.35)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("National office-plot locations (LULC Validation)\nCRS: WGS84")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    if out_path:
        fig.savefig(out_path, dpi=200)
    return fig


def forest_priority_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarise Final Forest by reserve/access flags when columns exist."""
    final = df["final_lulc"] if "final_lulc" in df.columns else None
    if final is None:
        return pd.DataFrame()
    is_forest = final.astype(str).str.lower().eq("forest")
    rows = [{"metric": "final_lulc_forest", "value": int(is_forest.sum())}]
    if "inside_forest_reserved" in df.columns:
        rows.append(
            {
                "metric": "forest_inside_reserve",
                "value": int((is_forest & df["inside_forest_reserved"].astype(bool)).sum()),
            }
        )
        rows.append(
            {
                "metric": "forest_outside_reserve",
                "value": int((is_forest & ~df["inside_forest_reserved"].astype(bool)).sum()),
            }
        )
    if "is_inaccessible" in df.columns:
        rows.append(
            {
                "metric": "forest_and_inaccessible",
                "value": int((is_forest & df["is_inaccessible"].astype(bool)).sum()),
            }
        )
    return pd.DataFrame(rows)
