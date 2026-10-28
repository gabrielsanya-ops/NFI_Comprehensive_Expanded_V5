# -*- coding: utf-8 -*-
"""
Exploratory analysis, feature engineering, integrity scorecards, and
SU-grouped tabular supervised learning for KSA NFI / Asir case study.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# EDA
# ---------------------------------------------------------------------------

def missingness_report(df: pd.DataFrame, source: str = "") -> pd.DataFrame:
    rows = []
    n = len(df)
    for c in df.columns:
        null_n = int(df[c].isna().sum())
        rows.append({
            "source": source,
            "column": c,
            "dtype": str(df[c].dtype),
            "n": n,
            "null_n": null_n,
            "null_pct": round(100 * null_n / n, 3) if n else 0.0,
            "non_null": n - null_n,
            "unique_n": int(df[c].nunique(dropna=True)),
        })
    return pd.DataFrame(rows).sort_values("null_pct", ascending=False)


def univariate_numeric(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    if cols is None:
        cols = [c for c in df.select_dtypes(include=[np.number]).columns]
    rows = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({
            "variable": c,
            "n": int(s.notna().sum()),
            "mean": float(s.mean()) if s.notna().any() else np.nan,
            "std": float(s.std()) if s.notna().any() else np.nan,
            "min": float(s.min()) if s.notna().any() else np.nan,
            "p25": float(s.quantile(0.25)) if s.notna().any() else np.nan,
            "median": float(s.median()) if s.notna().any() else np.nan,
            "p75": float(s.quantile(0.75)) if s.notna().any() else np.nan,
            "max": float(s.max()) if s.notna().any() else np.nan,
            "skew": float(s.skew()) if s.notna().sum() > 2 else np.nan,
            "mean_median_gap": float(s.mean() - s.median()) if s.notna().any() else np.nan,
        })
    return pd.DataFrame(rows)


def outlier_iqr_flags(df: pd.DataFrame, cols: list[str], k: float = 1.5) -> pd.DataFrame:
    """Flag IQR outliers; never auto-delete rows in the NFI audit workflow."""
    flags = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - k * iqr, q3 + k * iqr
        mask = s.notna() & ((s < lo) | (s > hi))
        for idx in df.index[mask]:
            flags.append({
                "row_index": idx,
                "variable": c,
                "value": float(s.loc[idx]),
                "fence_lo": float(lo),
                "fence_hi": float(hi),
                "disposition": "FLAGGED_NOT_DELETED",
            })
    return pd.DataFrame(flags)


def bivariate_numeric(df: pd.DataFrame, cols: list[str], method: str = "spearman") -> pd.DataFrame:
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = sub.corr(method=method)
    rows = []
    for i, a in enumerate(corr.columns):
        for j, b in enumerate(corr.columns):
            if j <= i:
                continue
            rows.append({"var_a": a, "var_b": b, "method": method, "corr": float(corr.loc[a, b])})
    return pd.DataFrame(rows).sort_values("corr", key=lambda s: s.abs(), ascending=False)


def univariate_categorical(df: pd.DataFrame, cols: list[str], top_n: int = 15) -> pd.DataFrame:
    """Frequency tables for categorical fields."""
    rows = []
    n = len(df)
    for c in cols:
        if c not in df.columns:
            continue
        vc = df[c].astype(str).replace({"nan": pd.NA, "None": pd.NA, "<NA>": pd.NA}).dropna().value_counts()
        for rank, (val, cnt) in enumerate(vc.head(top_n).items(), start=1):
            rows.append({
                "variable": c,
                "rank": rank,
                "level": val,
                "n": int(cnt),
                "pct": round(100 * cnt / n, 3) if n else 0.0,
                "n_levels_total": int(vc.shape[0]),
            })
    return pd.DataFrame(rows)


def bivariate_cat_numeric(
    df: pd.DataFrame,
    cat_col: str,
    num_col: str,
    top_levels: int = 12,
) -> pd.DataFrame:
    """Group numeric summaries by category (box-plot companion table)."""
    if cat_col not in df.columns or num_col not in df.columns:
        return pd.DataFrame()
    d = df[[cat_col, num_col]].copy()
    d[num_col] = pd.to_numeric(d[num_col], errors="coerce")
    d[cat_col] = d[cat_col].astype(str)
    top = d[cat_col].value_counts().head(top_levels).index
    d = d.loc[d[cat_col].isin(top)]
    g = d.groupby(cat_col, dropna=False)[num_col]
    out = g.agg(
        n="count", mean="mean", median="median", std="std",
        p25=lambda s: s.quantile(0.25), p75=lambda s: s.quantile(0.75),
    ).reset_index()
    out["num_variable"] = num_col
    out["cat_variable"] = cat_col
    return out.sort_values("n", ascending=False)


# NFI-FV workbook constants (provisional tree equations; not SU-cased)
FV_FORM_FACTOR = 0.65
FV_PLOT_AREA_HA_ASSUMED = 0.1  # Vol/Ha = Vol/Tr * 10 in NFI-FV.xlsx


def engineer_tree_volume_features_fv(
    trees: pd.DataFrame,
    cfg: dict,
    trees_only: bool = True,
) -> pd.DataFrame:
    """
    Tree-grain engineering matching NFI-FV.xlsx formulas.
    Does NOT aggregate to SU. Vol_ha_contrib is per-tree contribution under
    assumed plot area 0.1 ha (flagged provisional).
    """
    cols = cfg["columns"]
    t = trees.copy()
    if trees_only and "tree_or_stump_label" in t.columns:
        t = t.loc[t["tree_or_stump_label"].astype(str).str.lower().eq("tree")].copy()
    elif trees_only and "tree_or_stump" in t.columns:
        # common numeric code 1 = Tree in older exports
        t = t.loc[t["tree_or_stump"].astype(str).isin(["1", "Tree"])].copy()

    dbh_cm = pd.to_numeric(t[cols["dbh"]], errors="coerce")
    ht = pd.to_numeric(t[cols["height"]], errors="coerce")
    t["dbh_cm"] = dbh_cm
    t["height_m"] = ht
    t["dbh_m"] = dbh_cm / 100.0
    t["basal_area_m2"] = (t["dbh_m"] ** 2) * 0.785
    t["vol_tree_m3"] = t["height_m"] * t["basal_area_m2"] * FV_FORM_FACTOR
    t["vol_ha_contrib"] = t["vol_tree_m3"] / FV_PLOT_AREA_HA_ASSUMED
    t["agb_ha_contrib"] = t["vol_ha_contrib"] * 0.6 * 2.0
    t["bgb_ha_contrib"] = t["agb_ha_contrib"] * 0.28
    t["total_biomass_ha_contrib"] = t["agb_ha_contrib"] + t["bgb_ha_contrib"]
    t["carbon_ha_contrib"] = t["total_biomass_ha_contrib"] * 0.47
    t["bgb_mokany_ha_contrib"] = 0.489 * (t["agb_ha_contrib"].clip(lower=0) ** 0.89)
    # NFI-FV.xlsx column aliases (tree grain; not SU-cased)
    t["DBH(m)"] = t["dbh_m"]
    t["Basal area"] = t["basal_area_m2"]
    t["Vol/Tr"] = t["vol_tree_m3"]
    t["Vol/Ha"] = t["vol_ha_contrib"]
    t["AGB"] = t["agb_ha_contrib"]
    t["BGB"] = t["bgb_ha_contrib"]
    t["Total_Biomass"] = t["total_biomass_ha_contrib"]
    t["Carbon"] = t["carbon_ha_contrib"]
    t["BGB_Mokany"] = t["bgb_mokany_ha_contrib"]
    t["fv_plot_area_ha_assumed"] = FV_PLOT_AREA_HA_ASSUMED
    t["fv_equation_status"] = "PROVISIONAL_TREE_GRAIN_MATCHES_NFI_FV"
    t["eligible_volume"] = t["dbh_cm"].notna() & t["height_m"].notna() & (t["dbh_cm"] > 0) & (t["height_m"] > 0)
    return t


FV_DELIVERABLE_COLS = [
    "DBH(m)", "Basal area", "Vol/Tr", "Vol/Ha", "AGB", "BGB",
    "Total_Biomass", "Carbon", "BGB_Mokany",
]


def fv_deliverable_frame(trees_fv: pd.DataFrame) -> pd.DataFrame:
    """Tree-level NFI-FV metric columns with keys for audit export."""
    key_cols = [c for c in [
        "SU_UID", "PLOT_UID", "PLOT_ID", "tree_species_scientific_name",
        "tree_or_stump_label", "dbh_cm", "height_m", "eligible_volume",
        "fv_equation_status", "fv_plot_area_ha_assumed",
    ] if c in trees_fv.columns]
    cols = key_cols + [c for c in FV_DELIVERABLE_COLS if c in trees_fv.columns]
    return trees_fv[cols].copy()


def eda_readout_numeric(uni: pd.DataFrame, skew_heavy: float = 1.0) -> pd.DataFrame:
    """Generate concise numeric distribution notes from univariate summaries."""
    rows = []
    for _, r in uni.iterrows():
        notes = []
        if pd.notna(r.get("skew")) and abs(r["skew"]) >= skew_heavy:
            notes.append(f"heavy_skew_{'right' if r['skew'] > 0 else 'left'}")
        if pd.notna(r.get("mean_median_gap")) and abs(r["mean_median_gap"]) > 0.1 * max(abs(r.get("median") or 0), 1e-9):
            notes.append("mean_median_gap_suggests_skew_or_outliers")
        if pd.notna(r.get("max")) and pd.notna(r.get("p75")) and r["max"] > 3 * max(r["p75"], 1e-9):
            notes.append("extreme_max_vs_p75_check_outliers")
        rows.append({
            "variable": r["variable"],
            "n": r.get("n"),
            "skew": r.get("skew"),
            "mean_median_gap": r.get("mean_median_gap"),
            "readout": "; ".join(notes) if notes else "distribution_ok_for_first_pass",
        })
    return pd.DataFrame(rows)


def eda_readout_bivariate(biv: pd.DataFrame, strong: float = 0.7, weak: float = 0.3) -> pd.DataFrame:
    """Flag strong / weak numeric associations for methods notes."""
    if biv is None or len(biv) == 0:
        return pd.DataFrame()
    out = biv.copy()
    out["abs_corr"] = out["corr"].abs()
    out["readout"] = np.where(
        out["abs_corr"] >= strong, "strong_association_review_collinearity",
        np.where(out["abs_corr"] < weak, "weak_association", "moderate_association"),
    )
    return out.sort_values("abs_corr", ascending=False)


def plot_ecdf(df: pd.DataFrame, cols: list[str], out_path: Path, title: str = "Empirical CDF"):
    import matplotlib.pyplot as plt

    apply_plot_style()
    cols = [c for c in cols if c in df.columns][:6]
    if not cols:
        return None
    n = len(cols)
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 3.6), squeeze=False)
    for ax, c in zip(axes[0], cols):
        s = pd.to_numeric(df[c], errors="coerce").dropna().sort_values()
        if s.empty:
            ax.set_visible(False)
            continue
        y = np.arange(1, len(s) + 1) / len(s)
        ax.plot(s.values, y, color=PALETTE["steel"], lw=1.8)
        ax.set_title(c, fontsize=10)
        ax.set_xlabel(c)
        ax.set_ylabel("F(x)")
    fig.suptitle(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_scatter_matrix(df: pd.DataFrame, cols: list[str], out_path: Path, title: str = "Scatter matrix"):
    import matplotlib.pyplot as plt

    apply_plot_style()
    cols = [c for c in cols if c in df.columns][:5]
    if len(cols) < 2:
        return None
    sub = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(sub) < 10:
        return None
    # subsample for speed
    if len(sub) > 2500:
        sub = sub.sample(2500, random_state=42)
    n = len(cols)
    fig, axes = plt.subplots(n, n, figsize=(2.4 * n, 2.4 * n))
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            ax = axes[i, j]
            if i == j:
                ax.hist(sub[a], bins=30, color=PALETTE["teal"], alpha=0.85, edgecolor="white")
            else:
                ax.scatter(sub[b], sub[a], s=6, alpha=0.35, c=PALETTE["steel"], edgecolors="none")
            if i == n - 1:
                ax.set_xlabel(b, fontsize=8)
            else:
                ax.set_xticklabels([])
            if j == 0:
                ax.set_ylabel(a, fontsize=8)
            else:
                ax.set_yticklabels([])
    fig.suptitle(title, fontsize=12, fontweight="bold")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_grouped_boxplots(
    df: pd.DataFrame,
    cat_col: str,
    num_col: str,
    out_path: Path,
    top_levels: int = 10,
    title: str | None = None,
):
    import matplotlib.pyplot as plt

    apply_plot_style()
    if cat_col not in df.columns or num_col not in df.columns:
        return None
    d = df[[cat_col, num_col]].copy()
    d[num_col] = pd.to_numeric(d[num_col], errors="coerce")
    d = d.dropna()
    top = d[cat_col].astype(str).value_counts().head(top_levels).index.tolist()
    d = d.loc[d[cat_col].astype(str).isin(top)]
    if d.empty:
        return None
    order = top
    data = [d.loc[d[cat_col].astype(str) == lev, num_col].values for lev in order]
    fig, ax = plt.subplots(figsize=(max(7, 0.7 * len(order)), 4.5))
    bp = ax.boxplot(data, tick_labels=[str(x)[:18] for x in order], patch_artist=True, showfliers=True)
    for box in bp["boxes"]:
        box.set(facecolor=PALETTE["steel"], alpha=0.55)
    ax.set_xlabel(cat_col)
    ax.set_ylabel(num_col)
    ax.set_title(title or f"{num_col} by {cat_col}")
    plt.xticks(rotation=35, ha="right")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_categorical_bars(df: pd.DataFrame, col: str, out_path: Path, top_n: int = 15, title: str | None = None):
    import matplotlib.pyplot as plt

    apply_plot_style()
    if col not in df.columns:
        return None
    vc = df[col].astype(str).value_counts().head(top_n)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(vc.index.astype(str)[::-1], vc.values[::-1], color=PALETTE["teal"], height=0.7)
    ax.set_xlabel("Count")
    ax.set_title(title or f"Categorical distribution: {col}")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


FANCY_PANEL_COLORS = [
    "#7c3aed", "#0ea5e9", "#f59e0b", "#10b981", "#ec4899", "#6366f1",
    "#14b8a6", "#f97316", "#8b5cf6", "#06b6d4",
]


def plot_categorical_grid(
    df: pd.DataFrame,
    cols: list[str],
    out_path: Path,
    *,
    top_n: int = 10,
    ncols: int = 2,
    title: str = "Categorical distributions",
    skip_redundant_vernacular: bool = True,
) -> Path | None:
    """
    Compact multi-panel categorical board (one figure).
    Drops vernacular_name when scientific_name is also plotted (same rank order).
    Each panel uses a distinct accent colour.
    """
    import matplotlib.pyplot as plt
    from matplotlib import colors as mcolors

    apply_plot_style()
    use = [c for c in cols if c in df.columns]
    if skip_redundant_vernacular and "tree_species_scientific_name" in use:
        use = [c for c in use if c != "tree_species_vernacular_name"]
    use = use[:6]
    if not use:
        return None

    n = len(use)
    ncols = min(ncols, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(4.6 * ncols, 2.85 * nrows),
        layout="constrained",
    )
    axes = np.atleast_1d(axes).ravel()

    for i, col in enumerate(use):
        ax = axes[i]
        vc = df[col].astype(str).value_counts(dropna=False).head(top_n)
        labs = [str(x) if len(str(x)) <= 28 else str(x)[:25] + "…" for x in vc.index.astype(str)[::-1]]
        vals = vc.values[::-1]
        base = FANCY_PANEL_COLORS[i % len(FANCY_PANEL_COLORS)]
        # light→dark ramp within the panel
        ramp = [mcolors.to_hex(mcolors.to_rgba(base, alpha=0.45 + 0.55 * (j + 1) / max(len(vals), 1)))
                for j in range(len(vals))]
        # solid colour bars with slight luminance variation
        cmap = mcolors.LinearSegmentedColormap.from_list(f"cat{i}", ["#f8fafc", base])
        bar_cols = [cmap(0.35 + 0.65 * (j + 1) / max(len(vals), 1)) for j in range(len(vals))]
        ax.barh(labs, vals, color=bar_cols, height=0.72, edgecolor="white", linewidth=0.5)
        ax.set_title(col.replace("_", " "), fontsize=9.5, fontweight="bold", color=base, loc="left")
        ax.tick_params(axis="y", labelsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax.set_xlabel("Count", fontsize=7.5)
        for yi, v in enumerate(vals):
            ax.text(v + max(vals) * 0.015, yi, f"{int(v):,}", va="center", fontsize=6.5, color=PALETTE["slate"])
        ax.set_xlim(0, max(vals) * 1.22 if len(vals) else 1)

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle(title, fontsize=12, fontweight="bold")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def eda_limitations_nfi() -> pd.DataFrame:
    """Documented EDA and modelling limits for this Asir workflow."""
    return pd.DataFrame([
        {"limitation": "plot_area_ha missing", "impact": "stems/ha and true Vol/ha blocked", "mitigation": "use provisional 0.1 ha only with PROVISIONAL flag"},
        {"limitation": "SU-cased pivot of tree metrics", "impact": "misreads mean DBH / carbon as SU attributes", "mitigation": "keep tree / plot / SU grains separate"},
        {"limitation": "generic FV biomass constants", "impact": "AGB/Carbon not species-allometric", "mitigation": "treat as interim until species equations approved"},
        {"limitation": "Gate1/2 field classes open", "impact": "zero-tree SUs unresolved", "mitigation": "do not impute tree absence as confirmed zero"},
        {"limitation": "stumps and trees <3 m", "impact": "inflate counts / zero volume rows", "mitigation": "trees-only filter for volume EDA"},
    ])

PALETTE = {
    "ink": "#1b2838",
    "steel": "#2f6f8f",
    "teal": "#1f8a70",
    "amber": "#d97706",
    "rose": "#b91c1c",
    "slate": "#64748b",
    "bg": "#f4f7fb",
    "panel": "#ffffff",
    "grid": "#d9e2ec",
    "train": "#2f6f8f",
    "val": "#1f8a70",
    "test": "#d97706",
    "curve": "#0ea5e9",
    "curve2": "#a855f7",
    "curve3": "#f59e0b",
}

# Match the Asir grid region legend colours used on the static map
REGION_COLORS = {
    "Al Bahah": "#1d4ed8",
    "Ar Riyad": "#16a34a",
    "Ar Riyadh": "#16a34a",
    "Aseer": "#7c3aed",
    "Asir": "#7c3aed",
    "Jazan": "#db2777",
    "Makkah Al Mukarramah": "#a16207",
    "Najran": "#06b6d4",
}


def region_color(name: str) -> str:
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return PALETTE["slate"]
    key = str(name).strip()
    return REGION_COLORS.get(key, PALETTE["steel"])


def apply_plot_style():
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "figure.facecolor": PALETTE["bg"],
        "axes.facecolor": PALETTE["panel"],
        "axes.edgecolor": "#334155",
        "axes.labelcolor": PALETTE["ink"],
        "xtick.color": PALETTE["ink"],
        "ytick.color": PALETTE["ink"],
        "text.color": PALETTE["ink"],
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "axes.titleweight": "bold",
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": PALETTE["grid"],
        "grid.linewidth": 0.9,
        "grid.alpha": 0.95,
        "grid.linestyle": "--",
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "lines.linewidth": 2.2,
        "patch.linewidth": 0.6,
    })


def plot_region_su_dashboard(
    by_region: pd.DataFrame,
    out_dir: Path,
    *,
    region_col: str = "region",
    su_col: str = "n_su",
    title: str = "Sampling units (SU) by administrative region",
) -> dict:
    """
    Compact non-map SU board for the Asir-grid regions - one row of panels:
      counts (once) | share curve | tree-present vs Gate-1 composition.
    Colours match the cartography legend. No duplicate bar/lollipop pair.
    """
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = by_region.copy()
    if region_col not in df.columns:
        region_col = "reg_e" if "reg_e" in df.columns else df.columns[0]
    if su_col not in df.columns:
        for c in ("n_su", "SU_count", "count"):
            if c in df.columns:
                su_col = c
                break
    df = df.dropna(subset=[region_col]).copy()
    df[su_col] = pd.to_numeric(df[su_col], errors="coerce").fillna(0).astype(int)
    df = df.sort_values(su_col, ascending=True)
    colors = [region_color(r) for r in df[region_col]]
    total = int(df[su_col].sum()) or 1
    y = np.arange(len(df))
    labels = df[region_col].astype(str).tolist()
    share = (df[su_col] / total).values

    with_trees_col = next((c for c in ("n_with_trees", "n_su_with_trees") if c in df.columns), None)
    gate_col = next((c for c in ("n_gate1_zero_tree_su", "n_gate1") if c in df.columns), None)
    has_comp = bool(with_trees_col and gate_col)

    n_panels = 3 if has_comp else 2
    width_ratios = [1.15, 0.95, 1.15] if has_comp else [1.2, 1.0]
    fig, axes = plt.subplots(
        1, n_panels,
        figsize=(12.8 if has_comp else 9.6, 3.55),
        gridspec_kw={"width_ratios": width_ratios},
        layout="constrained",
    )
    if n_panels == 2:
        axes = list(axes)

    # --- Panel 1: SU counts (single representation) ---
    ax = axes[0]
    ax.barh(y, df[su_col].values, color=colors, height=0.62, edgecolor="white", linewidth=0.8, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("SU count", fontsize=8)
    ax.set_title("Counts by region", fontsize=10, fontweight="bold", loc="left")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
    ax.tick_params(axis="x", labelsize=7.5)
    xmax = max(df[su_col]) if len(df) else 1
    for i, v in enumerate(df[su_col].values):
        ax.text(
            v + xmax * 0.02, i, f"{int(v)} ({100 * v / total:.0f}%)",
            va="center", fontsize=7.5, color=PALETTE["ink"], fontweight="bold",
        )
    ax.set_xlim(0, xmax * 1.28)

    # --- Panel 2: share curve ---
    ax = axes[1]
    x = np.arange(len(df))
    ax.fill_between(x, share, color=PALETTE["curve"], alpha=0.16, zorder=1)
    ax.plot(
        x, share, color=PALETTE["curve"], lw=2.0, marker="o", markersize=6,
        markerfacecolor="white", markeredgewidth=1.6, markeredgecolor=PALETTE["curve2"], zorder=3,
    )
    for i, (s, col) in enumerate(zip(share, colors)):
        ax.scatter([i], [s], s=55, c=[col], zorder=4, edgecolors="white", linewidths=0.8)
        ax.text(i, s + max(share) * 0.04, f"{100 * s:.0f}%", ha="center", fontsize=7, color=PALETTE["ink"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
    ax.set_ylabel("Share", fontsize=8)
    ax.set_title("Regional share", fontsize=10, fontweight="bold", loc="left")
    ax.set_ylim(0, max(share) * 1.28 if len(share) else 1)
    ax.tick_params(axis="y", labelsize=7.5)

    # --- Panel 3: composition ---
    if has_comp:
        ax = axes[2]
        left = df[with_trees_col].astype(float).values
        right = df[gate_col].astype(float).values
        ax.barh(y, left, color=colors, height=0.62, edgecolor="white", label="With trees", zorder=3)
        ax.barh(
            y, right, left=left, color="#cbd5e1", height=0.62, edgecolor="white",
            label="Gate 1 zero-tree", zorder=3,
        )
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("Sampling units", fontsize=8)
        ax.set_title("Trees vs Gate 1 zeros", fontsize=10, fontweight="bold", loc="left")
        ax.legend(loc="lower right", fontsize=7, frameon=False)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        ax.tick_params(axis="x", labelsize=7.5)

    fig.suptitle(title, fontsize=11.5, fontweight="bold")
    p = out_dir / "region_su_dashboard_row.png"
    fig.savefig(p, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return {"su_dashboard_row": str(p)}


def plot_missingness_bars(miss_df: pd.DataFrame, out_path: Path, top_n: int = 20, title: str = "Missingness"):
    """Legacy single-panel bars; prefer plot_missingness_pair / plot_missingness_profile."""
    import matplotlib.pyplot as plt
    from matplotlib import cm

    apply_plot_style()
    d = miss_df.head(top_n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, max(3.0, 0.28 * len(d))))
    cmap = plt.colormaps.get_cmap("plasma") if hasattr(plt, "colormaps") else cm.get_cmap("plasma")
    norm = plt.Normalize(0, 100)
    colors = cmap(norm(d["null_pct"].astype(float).values))
    ax.barh(d["column"].astype(str), d["null_pct"], color=colors, height=0.72, edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Missing %")
    ax.set_title(title)
    for y, v in enumerate(d["null_pct"]):
        ax.text(v + 0.4, y, f"{v:.1f}%", va="center", fontsize=7.5, color=PALETTE["slate"])
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_missingness_pair(
    miss_a: pd.DataFrame,
    miss_b: pd.DataFrame,
    out_path: Path,
    *,
    title_a: str = "Trees",
    title_b: str = "Plots",
    top_n: int = 12,
    title: str = "Missingness · trees vs plots",
) -> Path:
    """Compact side-by-side missingness bars with a plasma severity ramp."""
    import matplotlib.pyplot as plt
    from matplotlib import cm
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    apply_plot_style()
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), layout="constrained", sharex=False)
    cmap = plt.colormaps.get_cmap("plasma") if hasattr(plt, "colormaps") else cm.get_cmap("plasma")
    norm = plt.Normalize(0, 100)

    for ax, miss, ttl, accent in (
        (axes[0], miss_a, title_a, "#7c3aed"),
        (axes[1], miss_b, title_b, "#0ea5e9"),
    ):
        d = miss.sort_values("null_pct", ascending=False).head(top_n).iloc[::-1]
        labs = [str(c) if len(str(c)) <= 30 else str(c)[:27] + "…" for c in d["column"]]
        cols = cmap(norm(d["null_pct"].astype(float).values))
        ax.barh(labs, d["null_pct"], color=cols, height=0.7, edgecolor="white", linewidth=0.35)
        ax.axvline(5, color="#fbbf24", ls="--", lw=0.9, alpha=0.8)
        ax.axvline(20, color="#f43f5e", ls="--", lw=0.9, alpha=0.8)
        ax.set_xlabel("Missing %", fontsize=8)
        ax.set_title(ttl, fontsize=11, fontweight="bold", color=accent, loc="left")
        ax.tick_params(axis="y", labelsize=7)
        ax.tick_params(axis="x", labelsize=7.5)
        ax.set_xlim(0, 108)
        for yi, v in enumerate(d["null_pct"]):
            ax.text(min(float(v) + 1.2, 100), yi, f"{v:.0f}%", va="center", fontsize=6.5, color=PALETTE["ink"])

    # shared colour strip
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cax = inset_axes(axes[1], width="55%", height="4%", loc="lower right", borderpad=1.2)
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("Missing %", fontsize=7)
    cb.ax.tick_params(labelsize=6)

    fig.suptitle(title, fontsize=12, fontweight="bold")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_missingness_profile(
    df: pd.DataFrame | None = None,
    miss_df: pd.DataFrame | None = None,
    out_path: Path | None = None,
    *,
    top_n: int = 18,
    title: str = "Missingness profile",
    source_label: str = "",
    sample_rows: int = 120,
    seed: int = 42,
) -> Path:
    """
    Publication-style missingness dashboard for data-science EDA:
      (1) ranked severity bars for the most incomplete columns,
      (2) column-count by completeness band,
      (3) binary missingness matrix (sampled rows × top incomplete fields).
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import FancyBboxPatch

    apply_plot_style()
    if miss_df is None:
        if df is None:
            raise ValueError("Provide df or miss_df")
        miss_df = missingness_report(df, source=source_label or "")
    miss = miss_df.copy()
    if "null_pct" not in miss.columns:
        raise ValueError("miss_df must include null_pct")

    n_cols = len(miss)
    n_rows = int(miss["n"].iloc[0]) if "n" in miss.columns and len(miss) else (len(df) if df is not None else 0)
    complete = int((miss["null_pct"] <= 0).sum())
    low = int(((miss["null_pct"] > 0) & (miss["null_pct"] <= 5)).sum())
    mid = int(((miss["null_pct"] > 5) & (miss["null_pct"] <= 20)).sum())
    high = int((miss["null_pct"] > 20).sum())
    mean_miss = float(miss["null_pct"].mean()) if len(miss) else 0.0

    d = miss.sort_values("null_pct", ascending=False).head(top_n).iloc[::-1]
    band_colors = {
        "complete": "#15803d",
        "low": PALETTE["teal"],
        "moderate": PALETTE["amber"],
        "high": PALETTE["rose"],
    }

    def _bar_color(v: float) -> str:
        if v > 20:
            return band_colors["high"]
        if v > 5:
            return band_colors["moderate"]
        if v > 0:
            return band_colors["low"]
        return band_colors["complete"]

    fig = plt.figure(figsize=(13.2, 8.4))
    gs = fig.add_gridspec(
        2, 2, width_ratios=[1.55, 1.0], height_ratios=[1.15, 1.0],
        hspace=0.32, wspace=0.28,
    )
    ax_bar = fig.add_subplot(gs[:, 0])
    ax_band = fig.add_subplot(gs[0, 1])
    ax_mat = fig.add_subplot(gs[1, 1])

    # --- ranked bars ---
    y = np.arange(len(d))
    colors = [_bar_color(float(v)) for v in d["null_pct"]]
    ax_bar.barh(y, d["null_pct"], color=colors, height=0.72, edgecolor="white", linewidth=0.6, zorder=3)
    ax_bar.axvline(5, color=PALETTE["amber"], ls="--", lw=1.1, alpha=0.85, zorder=2)
    ax_bar.axvline(20, color=PALETTE["rose"], ls="--", lw=1.1, alpha=0.85, zorder=2)
    ax_bar.set_yticks(y)
    labels = [str(c) if len(str(c)) <= 34 else str(c)[:31] + "…" for c in d["column"]]
    ax_bar.set_yticklabels(labels, fontsize=8.5)
    ax_bar.set_xlabel("Missing values (%)")
    ax_bar.set_xlim(0, max(100.0, float(d["null_pct"].max()) * 1.18) if len(d) else 100)
    subtitle = source_label or (str(miss["source"].iloc[0]) if "source" in miss.columns and len(miss) else "")
    ax_bar.set_title(
        f"{title}" + (f"  ·  {subtitle}" if subtitle else ""),
        fontsize=13, fontweight="bold", loc="left", pad=10,
    )
    for yi, (pct, nn) in enumerate(zip(d["null_pct"], d.get("null_n", [None] * len(d)))):
        tag = f"{pct:.1f}%"
        if nn is not None and pd.notna(nn):
            tag = f"{pct:.1f}%  (n={int(nn):,})"
        ax_bar.text(float(pct) + 0.8, yi, tag, va="center", fontsize=7.5, color=PALETTE["slate"])
    ax_bar.text(
        0.98, 0.02,
        "dashed lines: 5% / 20% severity thresholds",
        transform=ax_bar.transAxes, ha="right", va="bottom",
        fontsize=7.5, color=PALETTE["slate"], style="italic",
    )

    # --- completeness bands ---
    bands = ["Complete\n(0%)", "Low\n(0-5%]", "Moderate\n(5-20%]", "High\n(>20%)"]
    counts = [complete, low, mid, high]
    bcols = [band_colors["complete"], band_colors["low"], band_colors["moderate"], band_colors["high"]]
    xpos = np.arange(len(bands))
    bars = ax_band.bar(xpos, counts, color=bcols, width=0.72, edgecolor="white", linewidth=0.8, zorder=3)
    ax_band.set_xticks(xpos)
    ax_band.set_xticklabels(bands, fontsize=8)
    ax_band.set_ylabel("Number of columns")
    ax_band.set_title("Columns by missingness band", fontsize=11, fontweight="bold", loc="left")
    for b, c in zip(bars, counts):
        if c:
            ax_band.text(b.get_x() + b.get_width() / 2, c + 0.15, str(c), ha="center", va="bottom",
                         fontsize=9, fontweight="bold", color=PALETTE["ink"])
    ax_band.set_ylim(0, max(counts) * 1.25 + 0.5 if any(counts) else 1)

    # KPI strip as annotation box on band panel
    kpi = (
        f"{n_rows:,} rows · {n_cols} columns\n"
        f"mean missing {mean_miss:.1f}% · complete cols {complete}/{n_cols}"
    )
    ax_band.text(
        0.02, 0.98, kpi, transform=ax_band.transAxes, va="top", ha="left",
        fontsize=8, color=PALETTE["ink"],
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#eef2ff", edgecolor="#c7d2fe", alpha=0.95),
    )

    # --- binary matrix ---
    ax_mat.set_title("Sample missingness matrix (1 = missing)", fontsize=11, fontweight="bold", loc="left")
    if df is not None and len(d):
        cols = d["column"].astype(str).tolist()[::-1]  # high-missing at top
        cols = [c for c in cols if c in df.columns]
        if cols:
            n_take = min(sample_rows, len(df))
            sample = df[cols].sample(n=n_take, random_state=seed) if len(df) > n_take else df[cols]
            mat = sample.isna().astype(int).to_numpy().T  # columns × rows
            cmap = ListedColormap(["#e2e8f0", PALETTE["rose"]])
            ax_mat.imshow(mat, aspect="auto", interpolation="nearest", cmap=cmap, vmin=0, vmax=1)
            ax_mat.set_yticks(range(len(cols)))
            ax_mat.set_yticklabels(
                [c if len(c) <= 28 else c[:25] + "…" for c in cols], fontsize=7.5
            )
            ax_mat.set_xlabel(f"Sampled rows (n={len(sample):,})", fontsize=8)
            ax_mat.set_xticks([])
            # legend swatches
            ax_mat.scatter([], [], c="#e2e8f0", s=60, marker="s", label="Present", edgecolors="#94a3b8")
            ax_mat.scatter([], [], c=PALETTE["rose"], s=60, marker="s", label="Missing")
            ax_mat.legend(loc="upper right", fontsize=7, frameon=True, fancybox=True)
        else:
            ax_mat.text(0.5, 0.5, "No overlapping columns for matrix", ha="center", va="center",
                        transform=ax_mat.transAxes, color=PALETTE["slate"])
            ax_mat.axis("off")
    else:
        ax_mat.text(
            0.5, 0.5,
            "Pass the source DataFrame to render\nthe row × column missingness matrix",
            ha="center", va="center", transform=ax_mat.transAxes, color=PALETTE["slate"], fontsize=9,
        )
        ax_mat.set_xticks([])
        ax_mat.set_yticks([])

    # footer branding strip
    fig.patches.append(
        FancyBboxPatch(
            (0.01, 0.01), 0.98, 0.035, transform=fig.transFigure,
            boxstyle="round,pad=0.004,rounding_size=0.008",
            facecolor="#0f172a", edgecolor="none", zorder=0,
        )
    )
    fig.text(
        0.5, 0.027,
        "NFI GeoAI · missingness profile  ·  red = high risk for modelling / legends  ·  sources unchanged",
        ha="center", va="center", color="#e2e8f0", fontsize=7.5, zorder=1,
    )

    out_path = Path(out_path) if out_path else Path("missingness_profile.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_univariate_grid(df: pd.DataFrame, cols: list[str], out_path: Path, title: str = "Univariate"):
    import matplotlib.pyplot as plt

    apply_plot_style()
    n = len(cols)
    if n == 0:
        return None
    ncols = min(3, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 3.5 * nrows))
    axes = np.array(axes).reshape(-1)
    for ax, c in zip(axes, cols):
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        ax.hist(s, bins=28, color=PALETTE["steel"], alpha=0.88, edgecolor="white", linewidth=0.6)
        if len(s):
            ax.axvline(s.median(), color=PALETTE["amber"], ls="--", lw=1.8, label="median")
            ax.axvline(s.mean(), color=PALETTE["rose"], ls=":", lw=1.8, label="mean")
        ax.set_title(c, fontsize=10)
        ax.legend(fontsize=7, loc="upper right")
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_boxplots(df: pd.DataFrame, cols: list[str], out_path: Path, title: str = "Boxplots"):
    import matplotlib.pyplot as plt

    apply_plot_style()
    n = len(cols)
    if not n:
        return None
    fig, axes = plt.subplots(1, n, figsize=(3.2 * n, 4.2))
    if n == 1:
        axes = [axes]
    for ax, c in zip(axes, cols):
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        bp = ax.boxplot(s, patch_artist=True, widths=0.55,
                        boxprops=dict(facecolor=PALETTE["steel"], alpha=0.75, edgecolor=PALETTE["ink"]),
                        medianprops=dict(color=PALETTE["amber"], linewidth=2),
                        whiskerprops=dict(color=PALETTE["ink"]),
                        capprops=dict(color=PALETTE["ink"]),
                        flierprops=dict(marker="o", markersize=3, alpha=0.35, markerfacecolor=PALETTE["rose"]))
        ax.set_title(c, fontsize=10)
        ax.set_xticks([])
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_corr_heatmap(df: pd.DataFrame, cols: list[str], out_path: Path, method: str = "spearman"):
    import matplotlib.pyplot as plt

    apply_plot_style()
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = sub.corr(method=method)
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(corr, cmap="magma", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=40, ha="right", fontsize=7.5)
    ax.set_yticklabels(cols, fontsize=7.5)
    for i in range(len(cols)):
        for j in range(len(cols)):
            val = corr.iloc[i, j]
            ax.text(
                j, i, f"{val:.2f}", ha="center", va="center", fontsize=7,
                color="white" if abs(val) > 0.45 else PALETTE["ink"],
            )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(f"Bivariate {method.title()} correlations")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_corr_pair(
    df: pd.DataFrame,
    cols: list[str],
    out_path: Path,
    *,
    title: str = "Bivariate correlations · Spearman vs Pearson",
) -> Path | None:
    """Side-by-side Spearman / Pearson heatmaps in one compact figure (magma)."""
    import matplotlib.pyplot as plt

    apply_plot_style()
    use = [c for c in cols if c in df.columns]
    if len(use) < 2:
        return None
    sub = df[use].apply(pd.to_numeric, errors="coerce")
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), layout="constrained")
    last_im = None
    for ax, method, accent in (
        (axes[0], "spearman", "#7c3aed"),
        (axes[1], "pearson", "#ea580c"),
    ):
        corr = sub.corr(method=method)
        last_im = ax.imshow(corr, cmap="magma", vmin=-1, vmax=1)
        ax.set_xticks(range(len(use)))
        ax.set_yticks(range(len(use)))
        ax.set_xticklabels(use, rotation=40, ha="right", fontsize=7)
        ax.set_yticklabels(use, fontsize=7)
        for i in range(len(use)):
            for j in range(len(use)):
                val = float(corr.iloc[i, j])
                ax.text(
                    j, i, f"{val:.2f}", ha="center", va="center", fontsize=6.5,
                    color="white" if abs(val) > 0.45 else "#fde68a",
                )
        ax.set_title(method.title(), fontsize=11, fontweight="bold", color=accent, loc="left")

    cbar = fig.colorbar(last_im, ax=axes, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(labelsize=7)
    cbar.set_label("r", fontsize=8)
    fig.suptitle(title, fontsize=12, fontweight="bold")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_old_vs_new_bars(score: pd.DataFrame, out_path: Path):
    import matplotlib.pyplot as plt

    apply_plot_style()
    fig, ax = plt.subplots(figsize=(7.5, 4))
    colors = [PALETTE["rose"], PALETTE["teal"]]
    bars = ax.bar(score["method"], score["integrity_score_pct"], color=colors, width=0.55, edgecolor="white")
    ax.set_ylabel("Integrity score %")
    ax.set_title("OLD clip/pivot vs NEW anti-clip long-form")
    ax.set_ylim(0, 115)
    for b, v in zip(bars, score["integrity_score_pct"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 3, f"{v:.0f}%", ha="center", fontweight="bold")
    plt.xticks(rotation=12, ha="right")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Modelling protocol + diagnostics
# ---------------------------------------------------------------------------

def ai_integration_roadmap() -> pd.DataFrame:
    """Backwards-compatible alias for modelling_protocol_table()."""
    return modelling_protocol_table()


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) == 0:
        return {"n": 0}
    err = y_pred - y_true
    rmse = float(np.sqrt(np.mean(err**2)))
    mae = float(np.mean(np.abs(err)))
    bias = float(np.mean(err))
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y_true - y_true.mean())**2))
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    rel_rmse = float(100 * rmse / np.mean(np.abs(y_true))) if np.mean(np.abs(y_true)) else np.nan
    return {
        "n": int(len(y_true)), "RMSE": rmse, "MAE": mae, "bias": bias,
        "R2": r2, "relRMSE_pct": rel_rmse,
    }


def make_train_val_test_by_group(
    df: pd.DataFrame,
    group_col: str = "SU_UID",
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    random_state: int = 42,
) -> pd.DataFrame:
    """Assign each group wholly to train, val, or test (spatial/leakage-safe). Default 70/15/15."""
    rng = np.random.default_rng(random_state)
    out = df.copy()
    groups = out[group_col].astype(str).unique()
    rng.shuffle(groups)
    n = len(groups)
    n_train = int(round(n * train_frac))
    n_val = int(round(n * val_frac))
    # remainder goes to test (≈15%)
    train_g = set(groups[:n_train])
    val_g = set(groups[n_train:n_train + n_val])
    test_g = set(groups[n_train + n_val:])

    def _lab(g):
        g = str(g)
        if g in train_g:
            return "train"
        if g in val_g:
            return "val"
        return "test"

    out["split"] = out[group_col].map(_lab)
    return out


def plot_split_overview(df: pd.DataFrame, target: str, out_dir: Path) -> dict:
    """Fancy train/val/test diagnostic plots."""
    import matplotlib.pyplot as plt

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    order = ["train", "val", "test"]
    colors = [PALETTE["train"], PALETTE["val"], PALETTE["test"]]

    # counts
    fig, ax = plt.subplots(figsize=(7, 4))
    counts = df["split"].value_counts().reindex(order).fillna(0)
    bars = ax.bar(order, counts.values, color=colors, width=0.55, edgecolor="white")
    ax.set_title("Train / validation / test sample sizes (SU-grouped)")
    ax.set_ylabel("Plots")
    for b, v in zip(bars, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, v + max(counts.values) * 0.02, int(v),
                ha="center", fontweight="bold")
    fig.tight_layout()
    p1 = out_dir / "split_counts.png"
    fig.savefig(p1, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths["counts"] = str(p1)

    # target distributions
    fig, ax = plt.subplots(figsize=(8, 4.5))
    data = [pd.to_numeric(df.loc[df.split == s, target], errors="coerce").dropna() for s in order]
    parts = ax.violinplot(data, positions=range(3), showmeans=False, showmedians=True, showextrema=True)
    for i, b in enumerate(parts["bodies"]):
        b.set_facecolor(colors[i])
        b.set_alpha(0.75)
        b.set_edgecolor(PALETTE["ink"])
    parts["cmedians"].set_color(PALETTE["ink"])
    ax.set_xticks(range(3))
    ax.set_xticklabels(order)
    ax.set_ylabel(target)
    ax.set_title(f"Target distribution by split: {target}")
    fig.tight_layout()
    p2 = out_dir / "split_target_violin.png"
    fig.savefig(p2, dpi=180, bbox_inches="tight")
    plt.close(fig)
    paths["target_violin"] = str(p2)

    # map of splits if coords exist
    if {"lon_validated", "lat_validated"}.issubset(df.columns):
        fig, ax = plt.subplots(figsize=(8.5, 7.5))
        for s, col in zip(order, colors):
            sub = df.loc[df.split == s].dropna(subset=["lon_validated", "lat_validated"])
            ax.scatter(sub["lon_validated"], sub["lat_validated"], s=18, c=col, alpha=0.75,
                       edgecolors="white", linewidths=0.3, label=s)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title("Spatial train / val / test assignment (by SU group)")
        ax.legend(title="split")
        fig.tight_layout()
        p3 = out_dir / "split_spatial_map.png"
        fig.savefig(p3, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths["spatial_map"] = str(p3)

    return paths


def plot_model_diagnostics(y_true, y_pred, split_name: str, model_name: str, out_path: Path):
    import matplotlib.pyplot as plt

    apply_plot_style()
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    resid = y_pred - y_true
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))

    ax = axes[0]
    ax.scatter(y_true, y_pred, s=22, c=PALETTE["steel"], alpha=0.65, edgecolors="white", linewidths=0.4)
    lo = np.nanmin([y_true.min(), y_pred.min()])
    hi = np.nanmax([y_true.max(), y_pred.max()])
    ax.plot([lo, hi], [lo, hi], color=PALETTE["rose"], ls="--", lw=1.6, label="1:1")
    ax.set_xlabel("Observed")
    ax.set_ylabel("Predicted")
    ax.set_title(f"{model_name}  -  {split_name}: predicted vs observed")
    ax.legend()

    ax = axes[1]
    ax.scatter(y_pred, resid, s=22, c=PALETTE["teal"], alpha=0.65, edgecolors="white", linewidths=0.4)
    ax.axhline(0, color=PALETTE["rose"], ls="--", lw=1.4)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Residual (pred - obs)")
    ax.set_title(f"{model_name}  -  {split_name}: residuals")

    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_metrics_comparison(metrics_df: pd.DataFrame, out_path: Path):
    import matplotlib.pyplot as plt

    apply_plot_style()
    metric_cols = [c for c in ["RMSE", "MAE", "R2"] if c in metrics_df.columns]
    splits = ["train", "val", "test"]
    models = list(metrics_df["model"].unique())
    model_colors = [PALETTE["steel"], PALETTE["teal"], PALETTE["amber"], PALETTE["rose"]]
    fig, axes = plt.subplots(1, len(metric_cols), figsize=(4.6 * len(metric_cols), 4.4))
    if len(metric_cols) == 1:
        axes = [axes]
    x = np.arange(len(splits))
    width = 0.8 / max(len(models), 1)
    for ax, metric in zip(axes, metric_cols):
        for i, model in enumerate(models):
            vals = []
            for sp in splits:
                row = metrics_df.loc[(metrics_df.model == model) & (metrics_df.split_set == sp)]
                vals.append(float(row[metric].iloc[0]) if len(row) else np.nan)
            ax.bar(x + i * width - 0.4 + width / 2, vals, width=width * 0.92,
                   label=model, color=model_colors[i % len(model_colors)], alpha=0.92,
                   edgecolor="white")
        ax.set_xticks(x)
        ax.set_xticklabels(splits)
        ax.set_title(metric)
        ax.legend(fontsize=7, loc="best")
    fig.suptitle("Model metrics by train / val / test", fontsize=13, fontweight="bold")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_feature_importance(importances: pd.DataFrame, out_path: Path, title: str = "Feature importance"):
    import matplotlib.pyplot as plt

    apply_plot_style()
    d = importances.sort_values("importance").tail(12)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(d["feature"], d["importance"], color=PALETTE["steel"], height=0.7)
    ax.set_xlabel("Importance")
    ax.set_title(title)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path


def train_val_test_models(
    plot_feat: pd.DataFrame,
    target: str = "mean_dbh_cm",
    group_col: str = "SU_UID",
    out_dir: Path | None = None,
    random_state: int = 42,
) -> dict:
    """
    SU-grouped 70/15/15 tabular modelling (RF, GBM, MLP) with residual, loss, and confusion diagnostics.
    """
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    out_dir = Path(out_dir) if out_dir else Path("figures/tvt")
    out_dir.mkdir(parents=True, exist_ok=True)

    need = [target, "lon_validated", "lat_validated", group_col]
    df = plot_feat.dropna(subset=need).copy()
    df = df.loc[pd.to_numeric(df[target], errors="coerce").notna()].copy()
    if len(df) < 80:
        return {"status": "SKIPPED", "reason": f"insufficient rows ({len(df)})"}

    feature_cols = [c for c in ["lon_validated", "lat_validated", "n_trees", "mean_height_m", "n_species"]
                    if c in df.columns]
    df = make_train_val_test_by_group(
        df, group_col=group_col, train_frac=0.70, val_frac=0.15, random_state=random_state
    )
    split_paths = plot_split_overview(df, target, out_dir / "splits")

    X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = pd.to_numeric(df[target], errors="coerce")

    models = {
        "RandomForest": RandomForestRegressor(
            n_estimators=300, random_state=random_state, n_jobs=-1, min_samples_leaf=2
        ),
        "GradientBoosting": GradientBoostingRegressor(random_state=random_state),
        "MLPRegressor": Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPRegressor(
                hidden_layer_sizes=(64, 32), max_iter=500,
                random_state=random_state, early_stopping=True, validation_fraction=0.15,
            )),
        ]),
    }

    metric_rows = []
    pred_frames = []
    diag_paths = {}
    importance = None

    tr_mask = df["split"] == "train"
    Xtr, ytr = X.loc[tr_mask], y.loc[tr_mask]

    for name, model in models.items():
        model.fit(Xtr, ytr)
        for split_name in ["train", "val", "test"]:
            msk = df["split"] == split_name
            Xs, ys = X.loc[msk], y.loc[msk]
            pred = model.predict(Xs)
            m = regression_metrics(ys, pred)
            m["model"] = name
            m["split_set"] = split_name
            m["features"] = "|".join(feature_cols)
            metric_rows.append(m)
            pred_frames.append(pd.DataFrame({
                "PLOT_UID": df.loc[msk, "PLOT_UID"].values if "PLOT_UID" in df.columns else np.arange(msk.sum()),
                "split": split_name,
                "model": name,
                "y_true": ys.values,
                "y_pred": pred,
                "residual": pred - ys.values,
            }))
            if split_name in {"val", "test"}:
                p = plot_model_diagnostics(
                    ys, pred, split_name, name,
                    out_dir / f"diag_{name}_{split_name}.png",
                )
                diag_paths[f"{name}_{split_name}"] = str(p)

        # feature importance for tree models
        if hasattr(model, "feature_importances_"):
            importance = pd.DataFrame({
                "feature": feature_cols,
                "importance": model.feature_importances_,
                "model": name,
            })

        if name == "MLPRegressor":
            mlp_est = model.named_steps["mlp"]
            loss_p = plot_mlp_loss_curve(
                mlp_est, out_dir / "mlp_loss_curve.png",
                title="MLPRegressor training loss (StandardScaler on train features)",
            )
            if loss_p:
                diag_paths["mlp_loss_curve"] = str(loss_p)

    # DBH quartile classes -> confusion matrix on test (classification companion)
    try:
        df["dbh_bin"] = pd.qcut(y, q=4, labels=["Q1_low", "Q2", "Q3", "Q4_high"], duplicates="drop")
    except ValueError:
        df["dbh_bin"] = pd.cut(y, bins=4, labels=["B1", "B2", "B3", "B4"])
    y_bin = df["dbh_bin"]
    ok_bin = y_bin.notna()
    if ok_bin.sum() >= 80 and y_bin.nunique() >= 2:
        from sklearn.ensemble import RandomForestClassifier
        clf = RandomForestClassifier(
            n_estimators=200, random_state=random_state, n_jobs=-1, min_samples_leaf=2
        )
        clf.fit(X.loc[tr_mask & ok_bin], y_bin.loc[tr_mask & ok_bin])
        te = (df["split"] == "test") & ok_bin
        if te.sum() >= 10:
            y_true_c = y_bin.loc[te]
            y_pred_c = clf.predict(X.loc[te])
            labels = list(y_bin.dropna().unique())
            order = [x for x in ["Q1_low", "Q2", "Q3", "Q4_high", "B1", "B2", "B3", "B4"] if x in labels]
            labels = order if order else labels
            cm_path, _cm = plot_confusion_matrix(
                y_true_c, y_pred_c, labels,
                out_dir / "confusion_matrix_dbh_bins_test.png",
                title="Test-set confusion matrix: mean DBH quartile classes (RandomForest)",
            )
            diag_paths["confusion_matrix_dbh_bins"] = str(cm_path)

    metrics = pd.DataFrame(metric_rows)
    preds = pd.concat(pred_frames, ignore_index=True)
    metrics_plot = plot_metrics_comparison(metrics, out_dir / "metrics_by_split.png")
    imp_path = None
    if importance is not None:
        imp_path = plot_feature_importance(
            importance, out_dir / "feature_importance_rf.png",
            title="RandomForest feature importance",
        )

    # best by val RMSE
    val = metrics.loc[metrics.split_set == "val"].sort_values("RMSE")
    best = val.iloc[0]["model"] if len(val) else None

    return {
        "status": "OK",
        "data_with_split": df,
        "metrics": metrics,
        "predictions": preds,
        "best_model_by_val_RMSE": best,
        "feature_importance": importance,
        "normalization": normalization_policy(),
        "plot_paths": {
            **split_paths,
            "metrics_by_split": str(metrics_plot),
            "feature_importance": str(imp_path) if imp_path else None,
            **diag_paths,
        },
        "feature_cols": feature_cols,
        "target": target,
        "n_train": int(tr_mask.sum()),
        "n_val": int((df.split == "val").sum()),
        "n_test": int((df.split == "test").sum()),
    }


# Backwards-compatible alias
def prototype_mlp_spatial(plot_feat, target="mean_dbh_cm", group_col="SU_UID", random_state=42):
    res = train_val_test_models(plot_feat, target=target, group_col=group_col, random_state=random_state)
    if res.get("status") != "OK":
        return res
    return {
        "status": "OK",
        "metrics": res["metrics"],
        "n_train": res["n_train"],
        "n_test": res["n_test"],
        "plot_paths": res["plot_paths"],
        "best_model_by_val_RMSE": res["best_model_by_val_RMSE"],
    }


def engineer_plot_tree_features(trees: pd.DataFrame, plot_df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cols = cfg["columns"]
    t = trees.copy()
    t["_dbh"] = pd.to_numeric(t[cols["dbh"]], errors="coerce")
    t["_ht"] = pd.to_numeric(t[cols["height"]], errors="coerce")
    g = t.groupby("PLOT_UID", dropna=False)
    feat = g.agg(
        n_trees=("_dbh", "size"),
        mean_dbh_cm=("_dbh", "mean"),
        median_dbh_cm=("_dbh", "median"),
        max_dbh_cm=("_dbh", "max"),
        mean_height_m=("_ht", "mean"),
        median_height_m=("_ht", "median"),
        n_species=("tree_species_scientific_name", "nunique")
        if "tree_species_scientific_name" in t.columns else ("_dbh", "size"),
    ).reset_index()
    keep = [c for c in [
        "PLOT_UID", "SU_UID", "PLOT_ID", "lon_validated", "lat_validated",
        "coord_source", "coord_confidence",
    ] if c in plot_df.columns]
    out = plot_df[keep].drop_duplicates("PLOT_UID").merge(feat, on="PLOT_UID", how="left")
    for c in ["n_trees", "n_species"]:
        if c in out.columns:
            out[c] = out[c].fillna(0)
    out["stems_per_ha"] = np.nan
    out["stems_per_ha_status"] = "BLOCKED_NO_PLOT_AREA_HA"
    return out


# ---------------------------------------------------------------------------
# Old vs new method  -  data accuracy / integrity comparison
# ---------------------------------------------------------------------------

def compare_old_vs_new_method(asir_su, trees: pd.DataFrame, longform: pd.DataFrame, gate_targets: dict) -> pd.DataFrame:
    """
    Quantify integrity/accuracy of OLD (clip/inner-join/pivot-drop) vs
    NEW (anti-clip LEFT + long-form lattice) against baked Gate targets.
    """
    from nfi_audit import make_su_uid

    universe = set(make_su_uid(asir_su["SU_UID"]).astype(str))
    tree_su = set(make_su_uid(trees.loc[trees["SU_UID"].astype(str).isin(universe), "SU_UID"]))
    old_retained = universe & tree_su
    old_lost = universe - tree_su

    # Old pivot-like: only plots that appear in trees
    old_plots = set(
        trees.loc[trees["SU_UID"].astype(str).isin(universe), "PLOT_UID"].astype(str)
    )
    new_plots = set(longform["PLOT_UID"].astype(str))
    new_zero_kept = int((~longform["has_tree_record"]).sum()) if "has_tree_record" in longform.columns else 0

    rows = [
        {
            "metric": "su_universe_complete",
            "old_clip_inner": len(old_retained) == gate_targets["total_sus"],
            "new_anticlip_longform": len(universe) == gate_targets["total_sus"],
            "old_value": len(old_retained),
            "new_value": len(universe),
            "target": gate_targets["total_sus"],
            "winner": "NEW",
        },
        {
            "metric": "gate1_sus_recoverable_for_validation",
            "old_clip_inner": False,
            "new_anticlip_longform": len(old_lost) == gate_targets["sus_no_trees"],
            "old_value": 0,
            "new_value": len(old_lost),
            "target": gate_targets["sus_no_trees"],
            "winner": "NEW",
        },
        {
            "metric": "expected_plot_lattice_rows",
            "old_clip_inner": len(old_plots) == gate_targets["expected_plots"],
            "new_anticlip_longform": len(new_plots) == gate_targets["expected_plots"],
            "old_value": len(old_plots),
            "new_value": len(new_plots),
            "target": gate_targets["expected_plots"],
            "winner": "NEW",
        },
        {
            "metric": "zero_tree_plot_cells_visible",
            "old_clip_inner": False,
            "new_anticlip_longform": new_zero_kept == (
                gate_targets["expected_plots"] - gate_targets["plots_with_trees"]
            ),
            "old_value": 0,
            "new_value": new_zero_kept,
            "target": gate_targets["expected_plots"] - gate_targets["plots_with_trees"],
            "winner": "NEW",
        },
        {
            "metric": "false_zero_tree_risk_if_absence_treated_as_zero",
            "old_clip_inner": True,   # high risk  -  lost SUs invisible
            "new_anticlip_longform": False,  # flagged for Gate1/2 instead
            "old_value": 1,
            "new_value": 0,
            "target": 0,
            "winner": "NEW",
        },
        {
            "metric": "plots_with_trees_recovered",
            "old_clip_inner": len(old_plots) == gate_targets["plots_with_trees"],
            "new_anticlip_longform": int(longform["has_tree_record"].sum()) == gate_targets["plots_with_trees"]
            if "has_tree_record" in longform.columns else False,
            "old_value": len(old_plots),
            "new_value": int(longform["has_tree_record"].sum()) if "has_tree_record" in longform.columns else None,
            "target": gate_targets["plots_with_trees"],
            "winner": "TIE" if len(old_plots) == int(longform.get("has_tree_record", pd.Series(dtype=bool)).sum()) else "NEW",
        },
    ]
    if "Area_H_attr" in longform.columns:
        area_ok = int(longform["Area_H_attr"].notna().sum())
        rows.append({
            "metric": "Area_H_attached_without_clip",
            "old_clip_inner": False,
            "new_anticlip_longform": area_ok == len(longform),
            "old_value": None,
            "new_value": area_ok,
            "target": len(longform),
            "winner": "NEW",
        })
    out = pd.DataFrame(rows)
    out["new_matches_target"] = out.apply(
        lambda r: (r["new_value"] == r["target"]) if pd.notna(r["new_value"]) else False, axis=1
    )
    return out


def accuracy_scorecard(comparison: pd.DataFrame) -> pd.DataFrame:
    """Compact scorecard: % of integrity metrics won by each method."""
    n = len(comparison)
    return pd.DataFrame([{
        "method": "OLD_clip_inner_pivot",
        "metrics_matching_gate_targets": int(comparison["old_clip_inner"].sum())
        if comparison["old_clip_inner"].dtype == bool
        else None,
        "wins": int((comparison["winner"] == "OLD").sum()),
        "integrity_score_pct": round(100 * int((comparison["winner"] == "OLD").sum()) / n, 1),
        "note": "Invisible Gate1 SUs; zeros dropped; high false-zero risk",
    }, {
        "method": "NEW_anticlip_longform_keyjoin",
        "metrics_matching_gate_targets": int(comparison["new_matches_target"].sum()),
        "wins": int((comparison["winner"].isin(["NEW", "TIE"])).sum()),
        "integrity_score_pct": round(100 * int((comparison["winner"].isin(["NEW", "TIE"])).sum()) / n, 1),
        "note": "Full universe; Gate templates; Area_H by key; zeros retained",
    }])


def modelling_protocol_table() -> pd.DataFrame:
    """Supervised learning stages used in this notebook (tabular GeoAI)."""
    return pd.DataFrame([
        {
            "stage": "A_data_foundation",
            "method": "EDA, gates, lexical QA, integrity scorecard",
            "ready_now": True,
            "metrics": "Gate targets, missingness %, outlier flags, integrity score",
            "note": "Prerequisite for modelling",
        },
        {
            "stage": "B_su_grouped_holdout",
            "method": "RandomForest / GradientBoosting / MLPRegressor",
            "ready_now": "Prototype allowed; prefer after Gate 1/2 field sign-off",
            "metrics": "RMSE, MAE, R2, bias, relRMSE; MLP loss curve; confusion matrix for binned classes",
            "note": "70/15/15 by SU_UID to block plot-level leakage",
        },
        {
            "stage": "C_spatial_cv",
            "method": "GroupKFold by SU or governorate",
            "ready_now": "WITH B",
            "metrics": "Fold-wise RMSE/MAE + residual plots",
            "note": "Model selection protocol",
        },
        {
            "stage": "D_blocked_biomass",
            "method": "Biomass and carbon estimation",
            "ready_now": False,
            "metrics": "Blocked until plot_area_ha, allometrics, and design weights exist",
            "note": "Explicitly blocked",
        },
    ])


def normalization_policy() -> pd.DataFrame:
    """
    Where feature normalization / scaling is required in the final analysis.
    Tree ensembles do not need it; distance-based and neural models do.
    """
    return pd.DataFrame([
        {
            "step": "EDA and gate tables",
            "normalize": False,
            "method": "none",
            "reason": "Counts and rates must stay in native units for audit against Gate targets.",
        },
        {
            "step": "RandomForest / GradientBoosting regression",
            "normalize": False,
            "method": "none",
            "reason": "Split-based learners are scale-invariant; keep lon/lat/DBH/height in physical units.",
        },
        {
            "step": "MLPRegressor (plot-level regression)",
            "normalize": True,
            "method": "StandardScaler fit on TRAIN only, applied to val/test",
            "reason": "Gradient descent is sensitive to feature scale; pipeline already wraps scaler.",
        },
        {
            "step": "MLP / logistic classification of tree-presence or DBH bins",
            "normalize": True,
            "method": "StandardScaler fit on TRAIN only",
            "reason": "Same as MLP regression; prevents lon/lat dominating DBH features.",
        },
        {
            "step": "Correlation heatmaps / IQR outlier fences",
            "normalize": False,
            "method": "none (Spearman is rank-based; IQR uses native units)",
            "reason": "Interpretability of biological thresholds.",
        },
        {
            "step": "stems/ha and biomass",
            "normalize": "BLOCKED",
            "method": "N/A",
            "reason": "plot_area_ha missing; do not invent areas to normalize stem counts.",
        },
        {
            "step": "CHM vs field height comparison",
            "normalize": False,
            "method": "compare metres to metres; optional residual plots",
            "reason": "Both height sources are already in metres.",
        },
    ])


def plot_confusion_matrix(y_true, y_pred, labels, out_path: Path, title: str = "Confusion matrix"):
    import matplotlib.pyplot as plt
    from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

    apply_plot_style()
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    ConfusionMatrixDisplay(cm, display_labels=labels).plot(
        ax=ax, cmap="Blues", colorbar=True, values_format="d"
    )
    ax.set_title(title)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path, cm


def plot_mlp_loss_curve(mlp_est, out_path: Path, title: str = "MLP training loss curve"):
    """Plot sklearn MLPRegressor loss_curve_ (and validation_scores_ if present)."""
    import matplotlib.pyplot as plt

    apply_plot_style()
    if not hasattr(mlp_est, "loss_curve_"):
        return None
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(mlp_est.loss_curve_, color=PALETTE["steel"], lw=2.0, label="Training loss")
    if hasattr(mlp_est, "validation_scores_") and mlp_est.validation_scores_ is not None:
        vs = np.asarray(mlp_est.validation_scores_, dtype=float)
        ax2 = ax.twinx()
        ax2.plot(vs, color=PALETTE["amber"], lw=1.8, label="Validation score")
        ax2.set_ylabel("Validation score")
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2, loc="best")
    else:
        ax.legend(loc="best")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.set_title(title)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out_path

# ---------------------------------------------------------------------------
# Extended statistical figure pack (FV metrics + field attributes)
# ---------------------------------------------------------------------------

TREE_ATTR_COLS = [
    "tree_or_stump_label",
    "tree_species_scientific_name",
    "tree_species_vernacular_name",
    "tree_species_language_code",
    "lucc_label",
    "stem_quality_label",
    "crown_condition_label",
    "overall_tree_condition_label",
    "causative_agent_label[1]",
    "causative_agent_label[2]",
    "decomposition_status_label",
    "years_since_cut_label",
]

PLOT_ATTR_COLS = [
    "plot_info1_plot_access1_label",
    "plot_info1_owner1_label",
    "coord_source",
    "coord_confidence",
]

# Extra plot descriptors turned into presence / effort flags for graphs
PLOT_PRESENCE_FLAG_SPECS = [
    ("notes2", "has_field_notes"),
    ("plot_info1_plot_access1_qualifier", "has_access_qualifier"),
    ("plot_info1_owner1_qualifier", "has_owner_qualifier"),
]


def attach_plot_attributes_to_trees(trees: pd.DataFrame, plots: pd.DataFrame) -> pd.DataFrame:
    """Join plot accessibility / ownership / coord trust onto tree rows by PLOT_UID."""
    cols = [c for c in ["PLOT_UID"] + PLOT_ATTR_COLS if c in plots.columns]
    if "PLOT_UID" not in cols:
        return trees.copy()
    p = plots[cols].drop_duplicates("PLOT_UID")
    return trees.merge(p, on="PLOT_UID", how="left", suffixes=("", "_plot"))


def enrich_plot_presence_flags(plot_df: pd.DataFrame) -> pd.DataFrame:
    """Add binary presence flags for free-text / qualifier columns used in graphs."""
    out = plot_df.copy()
    for src, flag in PLOT_PRESENCE_FLAG_SPECS:
        if src not in out.columns:
            continue
        s = out[src]
        out[flag] = s.notna() & ~s.astype(str).str.strip().isin(["", "nan", "None", "<NA>"])
    return out


def plot_metric_distribution_suite(
    df: pd.DataFrame,
    cols: list[str],
    out_dir: Path,
    prefix: str = "fv",
    max_strip: int = 2000,
) -> dict:
    """For each numeric metric: histogram+KDE, boxplot, violin, strip/bubble panel."""
    import matplotlib.pyplot as plt
    try:
        import seaborn as sns
    except ImportError:
        sns = None

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    cols = [c for c in cols if c in df.columns]
    for col in cols:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < 5:
            continue
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(col))
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.2))

        ax = axes[0, 0]
        ax.hist(s, bins=40, color=PALETTE["steel"], alpha=0.55, edgecolor="white", density=True, zorder=2)
        if sns is not None:
            sns.kdeplot(
                x=s, ax=ax, color=PALETTE["curve2"], lw=2.4, fill=True,
                alpha=0.22, warn_singular=False, zorder=3,
            )
            sns.kdeplot(x=s, ax=ax, color=PALETTE["curve"], lw=2.6, warn_singular=False, zorder=4)
        ax.axvline(s.median(), color=PALETTE["amber"], ls="--", lw=1.8, label="median", zorder=5)
        ax.axvline(s.mean(), color=PALETTE["rose"], ls=":", lw=1.8, label="mean", zorder=5)
        ax.legend(loc="upper right", fontsize=8)
        ax.set_title(f"{col}: histogram + density curve")
        ax.set_xlabel(col)


        ax = axes[0, 1]
        bp = ax.boxplot(s.values, vert=True, patch_artist=True, widths=0.45)
        for box in bp["boxes"]:
            box.set(facecolor=PALETTE["teal"], alpha=0.65)
        ax.set_title(f"{col}: boxplot")
        ax.set_ylabel(col)

        ax = axes[1, 0]
        parts = ax.violinplot(s.values, positions=[0], showmeans=True, showmedians=True, showextrema=True)
        for b in parts["bodies"]:
            b.set_facecolor(PALETTE["amber"])
            b.set_alpha(0.7)
        ax.set_xticks([0])
        ax.set_xticklabels([str(col)[:24]])
        ax.set_title(f"{col}: violin")

        ax = axes[1, 1]
        sample = s.sample(min(len(s), max_strip), random_state=42)
        rng = np.random.default_rng(42)
        x = rng.normal(0, 0.08, size=len(sample))
        sizes = 12 + 40 * (sample - sample.min()) / (sample.max() - sample.min() + 1e-12)
        ax.scatter(x, sample.values, s=sizes, alpha=0.35, c=PALETTE["steel"], edgecolors="none")
        ax.set_xticks([0])
        ax.set_xticklabels(["strip / bubble"])
        ax.set_ylabel(col)
        ax.set_title(f"{col}: strip (marker size ~ value)")

        fig.suptitle(f"Distribution suite: {col}", fontsize=13, fontweight="bold")
        fig.tight_layout()
        path = out_dir / f"{prefix}_dist_{safe}.png"
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        paths[col] = str(path)
    return paths


def plot_attribute_count_dashboard(
    df: pd.DataFrame,
    cols: list[str],
    out_path: Path,
    title: str = "Field attribute frequencies",
    top_n: int = 12,
) -> Path | None:
    import matplotlib.pyplot as plt
    from matplotlib import colors as mcolors

    apply_plot_style()
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return None
    n = len(cols)
    ncols = min(2, n)
    nrows = int(np.ceil(n / ncols))
    # Tall panels + constrained layout keep figure/panel titles from colliding
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(6.4 * ncols, 3.7 * nrows + 0.9),
        squeeze=False,
        layout="constrained",
    )
    fancy = list(FANCY_PANEL_COLORS)
    # Multi-hue accents so each bar can pick a distinct colour (not just a single tint)
    rainbow = [
        "#7c3aed", "#2563eb", "#0ea5e9", "#14b8a6", "#10b981", "#84cc16",
        "#eab308", "#f59e0b", "#f97316", "#ef4444", "#ec4899", "#a855f7",
    ]
    for i, col in enumerate(cols):
        ax = axes[i // ncols][i % ncols]
        vc = df[col].astype(str).replace({"nan": np.nan, "None": np.nan, "<NA>": np.nan}).dropna()
        vc = vc.value_counts().head(top_n)
        labs = [str(x) if len(str(x)) <= 32 else str(x)[:29] + "…" for x in vc.index.astype(str)[::-1]]
        vals = vc.values[::-1]
        base = fancy[i % len(fancy)]
        # Mix panel accent with a rainbow so bars are vividly multi-coloured
        bar_cols = []
        for j in range(len(vals)):
            hue = rainbow[(i + j) % len(rainbow)]
            cmap = mcolors.LinearSegmentedColormap.from_list(f"attr{i}_{j}", ["#ffffff", hue, base])
            bar_cols.append(cmap(0.55 + 0.40 * (j + 1) / max(len(vals), 1)))
        ax.barh(labs, vals, color=bar_cols, height=0.68, edgecolor="white", linewidth=0.55, alpha=0.95)
        pretty = str(col).replace("_", " ")
        if len(pretty) > 42:
            pretty = pretty[:39] + "…"
        ax.set_title(pretty, fontsize=9.5, fontweight="bold", color=base, loc="left", pad=8)
        ax.set_xlabel("Count", fontsize=8, labelpad=4)
        ax.tick_params(axis="y", labelsize=7.5, pad=2)
        ax.tick_params(axis="x", labelsize=7.5)
        xmax = float(max(vals)) if len(vals) else 1.0
        for yi, v in enumerate(vals):
            ax.text(v + xmax * 0.015, yi, f"{int(v):,}", va="center", fontsize=6.5, color=PALETTE["slate"])
        ax.set_xlim(0, xmax * 1.28)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    for j in range(len(cols), nrows * ncols):
        axes[j // ncols][j % ncols].set_visible(False)
    fig.suptitle(title, fontsize=12.5, fontweight="bold", y=1.02)
    try:
        fig.set_constrained_layout_pads(w_pad=0.10, h_pad=0.22, hspace=0.22, wspace=0.10)
    except Exception:
        pass
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=180, bbox_inches="tight", pad_inches=0.35)
    plt.close(fig)
    return out_path


def plot_metric_by_category_suite(
    df: pd.DataFrame,
    num_col: str,
    cat_col: str,
    out_path: Path,
    top_levels: int = 8,
    title: str | None = None,
) -> Path | None:
    """Box + violin + swarm/strip of a metric by attribute."""
    import matplotlib.pyplot as plt
    try:
        import seaborn as sns
    except ImportError:
        sns = None

    apply_plot_style()
    if num_col not in df.columns or cat_col not in df.columns:
        return None
    d = df[[cat_col, num_col]].copy()
    d[num_col] = pd.to_numeric(d[num_col], errors="coerce")
    d[cat_col] = d[cat_col].astype(str)
    d = d.replace({"nan": np.nan}).dropna()
    if d.empty:
        return None
    top = d[cat_col].value_counts().head(top_levels).index.tolist()
    d = d.loc[d[cat_col].isin(top)]
    order = top
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.6))

    if sns is not None:
        sns.boxplot(data=d, x=cat_col, y=num_col, order=order, ax=axes[0], color=PALETTE["steel"])
        sns.violinplot(data=d, x=cat_col, y=num_col, order=order, ax=axes[1], color=PALETTE["teal"], cut=0)
        plot_df = d.sample(min(len(d), 1800), random_state=42) if len(d) > 1800 else d
        sns.stripplot(
            data=plot_df, x=cat_col, y=num_col, order=order, ax=axes[2],
            size=2.8, alpha=0.4, color=PALETTE["amber"], jitter=0.28,
        )
        axes[2].set_title("Strip / bubbles")
        axes[0].set_title("Box")
        axes[1].set_title("Violin")
    else:
        data = [d.loc[d[cat_col] == lev, num_col].values for lev in order]
        axes[0].boxplot(data, tick_labels=[str(x)[:14] for x in order], patch_artist=True)
        axes[0].set_title("Box")
        axes[1].violinplot(data, showmeans=True, showmedians=True)
        axes[1].set_xticks(range(1, len(order) + 1))
        axes[1].set_xticklabels([str(x)[:14] for x in order], rotation=30, ha="right")
        axes[1].set_title("Violin")
        axes[2].set_visible(False)

    for ax in axes:
        if ax.get_visible():
            ax.tick_params(axis="x", rotation=32)
            for lbl in ax.get_xticklabels():
                lbl.set_ha("right")
            ax.set_xlabel("")
            ax.set_ylabel(num_col)
    fig.suptitle(title or f"{num_col} by {cat_col}", fontsize=12, fontweight="bold")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_species_bubble_map(
    df: pd.DataFrame,
    out_path: Path,
    species_col: str = "tree_species_scientific_name",
    size_col: str = "Basal area",
    top_n: int = 12,
) -> Path | None:
    """Bubble chart: species mean DBH vs rank; size = count; colour = mean basal area."""
    import matplotlib.pyplot as plt

    apply_plot_style()
    if size_col not in df.columns and "basal_area_m2" in df.columns:
        size_col = "basal_area_m2"
    need = [species_col, "dbh_cm", size_col]
    if any(c not in df.columns for c in need):
        return None
    d = df[need].copy()
    d["dbh_cm"] = pd.to_numeric(d["dbh_cm"], errors="coerce")
    d[size_col] = pd.to_numeric(d[size_col], errors="coerce")
    d[species_col] = d[species_col].astype(str)
    d = d.dropna()
    top = d[species_col].value_counts().head(top_n).index
    d = d.loc[d[species_col].isin(top)]
    g = d.groupby(species_col).agg(
        n=("dbh_cm", "size"),
        mean_dbh=("dbh_cm", "mean"),
        mean_ba=(size_col, "mean"),
    ).reset_index().sort_values("n", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    sc = ax.scatter(
        g["mean_dbh"], np.arange(len(g)),
        s=80 + 8 * g["n"],
        c=g["mean_ba"], cmap="YlGn",
        alpha=0.85, edgecolors="#1b2838", linewidths=0.4,
    )
    ax.set_yticks(np.arange(len(g)))
    ax.set_yticklabels(g[species_col].astype(str).str.slice(0, 28))
    ax.set_xlabel("Mean DBH (cm)")
    ax.set_title("Species bubbles: x = mean DBH, size = stem count, colour = mean basal area")
    cb = fig.colorbar(sc, ax=ax, shrink=0.8)
    cb.set_label(f"Mean {size_col}")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_stump_vs_tree_compare(
    df: pd.DataFrame,
    out_path: Path,
    label_col: str = "tree_or_stump_label",
) -> Path | None:
    """Side-by-side counts and DBH violins for Tree vs Stump."""
    import matplotlib.pyplot as plt

    apply_plot_style()
    if label_col not in df.columns:
        return None
    d = df.copy()
    d[label_col] = d[label_col].astype(str)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    vc = d[label_col].value_counts()
    colors = [PALETTE["teal"], PALETTE["rose"], PALETTE["amber"], PALETTE["steel"]]
    axes[0].bar(vc.index.astype(str), vc.values, color=colors[: len(vc)], width=0.55)
    axes[0].set_title("Tree vs stump counts")
    axes[0].set_ylabel("Records")
    if "dbh_cm" in d.columns:
        groups, labels = [], []
        for lab in vc.index:
            s = pd.to_numeric(d.loc[d[label_col] == lab, "dbh_cm"], errors="coerce").dropna()
            if len(s):
                groups.append(s.values)
                labels.append(str(lab))
        if groups:
            parts = axes[1].violinplot(groups, showmeans=True, showmedians=True)
            for b in parts["bodies"]:
                b.set_facecolor(PALETTE["steel"])
                b.set_alpha(0.7)
            axes[1].set_xticks(range(1, len(labels) + 1))
            axes[1].set_xticklabels(labels)
            axes[1].set_ylabel("DBH (cm)")
            axes[1].set_title("DBH by tree / stump class")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out_path


def build_asir_statistical_figure_pack(
    trees_fv: pd.DataFrame,
    plot_df: pd.DataFrame | None = None,
    out_dir: Path | None = None,
) -> dict:
    """
    Statistical figure pack for Asir trees:
    FV metric distribution suites; accessibility/ownership; condition;
    causative agents; decomposition; species (scientific + vernacular);
    language codes; stump comparisons; coord trust; qualifier/notes flags;
    metric-by-attribute box/violin/swarm panels.
    """
    out_dir = Path(out_dir) if out_dir else Path("figures/stat_pack")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict = {}

    df = trees_fv.copy()
    plot_enriched = enrich_plot_presence_flags(plot_df) if plot_df is not None else None
    if plot_enriched is not None:
        df = attach_plot_attributes_to_trees(df, plot_enriched)

    fv_cols = [c for c in FV_DELIVERABLE_COLS if c in df.columns]
    elig = df.loc[df["eligible_volume"]] if "eligible_volume" in df.columns else df
    paths["fv_distributions"] = plot_metric_distribution_suite(
        elig, fv_cols, out_dir / "fv_distributions", prefix="fv",
    )

    # Tree descriptive frequencies - skip the four already shown in categorical_grid.png
    # (stump/species/language/LUCC) and vernacular (own chart below).
    _cat_grid_overlap = {
        "tree_or_stump_label",
        "tree_species_scientific_name",
        "tree_species_language_code",
        "lucc_label",
        "tree_species_vernacular_name",
    }
    tree_attrs_dash = [
        c for c in TREE_ATTR_COLS
        if c in df.columns and c not in _cat_grid_overlap
    ]
    p1 = plot_attribute_count_dashboard(
        df, tree_attrs_dash, out_dir / "tree_attribute_frequencies.png",
        title="Tree attributes: condition, agents, decomposition, years since cut",
    )
    if p1:
        paths["tree_attributes"] = str(p1)

    plot_attrs = [c for c in PLOT_ATTR_COLS if c in (plot_enriched.columns if plot_enriched is not None else df.columns)]
    if plot_attrs and plot_enriched is not None:
        p2 = plot_attribute_count_dashboard(
            plot_enriched, plot_attrs, out_dir / "plot_access_ownership.png",
            title="Plot accessibility, ownership, and coordinate trust",
        )
        if p2:
            paths["plot_access_ownership"] = str(p2)
    elif plot_attrs:
        base = df.drop_duplicates("PLOT_UID") if "PLOT_UID" in df.columns else df
        p2 = plot_attribute_count_dashboard(
            base, plot_attrs, out_dir / "plot_access_ownership.png",
            title="Plot accessibility, ownership, and coordinate trust",
        )
        if p2:
            paths["plot_access_ownership"] = str(p2)

    p3 = plot_stump_vs_tree_compare(df, out_dir / "stump_vs_tree.png")
    if p3:
        paths["stump_vs_tree"] = str(p3)

    p4 = plot_species_bubble_map(df, out_dir / "species_bubbles.png")
    if p4:
        paths["species_bubbles"] = str(p4)

    if "tree_species_vernacular_name" in df.columns:
        vern = df.loc[
            df["tree_species_vernacular_name"].notna()
            & ~df["tree_species_vernacular_name"].astype(str).isin(["", "nan", "None"])
        ]
        if len(vern):
            p_v = plot_attribute_count_dashboard(
                vern, ["tree_species_vernacular_name"],
                out_dir / "vernacular_name_top.png",
                title="Top vernacular species names (field language)",
                top_n=15,
            )
            if p_v:
                paths["vernacular_names"] = str(p_v)

    if "tree_species_language_code" in df.columns:
        lang = df.loc[
            df["tree_species_language_code"].notna()
            & ~df["tree_species_language_code"].astype(str).isin(["", "nan", "None", "<NA>"])
        ]
        if len(lang):
            p_l = plot_attribute_count_dashboard(
                lang, ["tree_species_language_code"],
                out_dir / "species_language_codes.png",
                title="Species language codes (after derived cleaning)",
                top_n=10,
            )
            if p_l:
                paths["language_codes"] = str(p_l)

    cross = []
    # Focused cross-panels (avoid combinatorial explosion)
    cross_specs = [
        ("dbh_cm", "lucc_label"),
        ("dbh_cm", "overall_tree_condition_label"),
        ("dbh_cm", "causative_agent_label[1]"),
        ("dbh_cm", "stem_quality_label"),
        ("dbh_cm", "crown_condition_label"),
        ("dbh_cm", "plot_info1_plot_access1_label"),
        ("dbh_cm", "plot_info1_owner1_label"),
        ("dbh_cm", "tree_species_scientific_name"),
        ("dbh_cm", "tree_or_stump_label"),
        ("dbh_cm", "decomposition_status_label"),
        ("dbh_cm", "years_since_cut_label"),
        ("dbh_cm", "coord_source"),
        ("Vol/Tr", "lucc_label"),
        ("Vol/Tr", "overall_tree_condition_label"),
        ("Vol/Tr", "tree_species_scientific_name"),
        ("Vol/Tr", "plot_info1_plot_access1_label"),
        ("Basal area", "lucc_label"),
        ("Basal area", "stem_quality_label"),
        ("Basal area", "plot_info1_owner1_label"),
        ("Carbon", "lucc_label"),
        ("Carbon", "overall_tree_condition_label"),
        ("Carbon", "plot_info1_owner1_label"),
        ("Carbon", "crown_condition_label"),
    ]
    for num, cat in cross_specs:
        if cat in df.columns and num in df.columns:
            top = 10 if "species" in cat else 8
            safe_c = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cat)[:40]
            safe_n = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in num)
            pp = plot_metric_by_category_suite(
                df, num, cat, out_dir / f"byattr_{safe_n}__{safe_c}.png",
                top_levels=top, title=f"{num} by {cat}",
            )
            if pp:
                cross.append(str(pp))
    paths["metric_by_attribute"] = cross

    if "causative_agent_label[1]" in df.columns:
        agent = df["causative_agent_label[1]"].astype(str)
        sub = df.loc[agent.notna() & ~agent.isin(["nan", "None", "Not applicable"])]
        if len(sub):
            p5 = plot_attribute_count_dashboard(
                sub, ["causative_agent_label[1]"],
                out_dir / "causative_agents_detail.png",
                title="Causative agents (excluding not applicable / missing)",
                top_n=10,
            )
            if p5:
                paths["causative_agents"] = str(p5)
            if "dbh_cm" in sub.columns:
                p6 = plot_metric_by_category_suite(
                    sub, "dbh_cm", "causative_agent_label[1]",
                    out_dir / "dbh_by_causative_agent.png",
                    title="DBH by causative agent (including insects)",
                )
                if p6:
                    paths["dbh_by_agent"] = str(p6)

    if "causative_agent_label[2]" in df.columns:
        a2 = df["causative_agent_label[2]"].astype(str)
        sub2 = df.loc[a2.notna() & ~a2.isin(["nan", "None", "Not applicable", ""])]
        if len(sub2):
            p5b = plot_attribute_count_dashboard(
                sub2, ["causative_agent_label[2]"],
                out_dir / "causative_agents_secondary.png",
                title="Secondary causative agents",
                top_n=10,
            )
            if p5b:
                paths["causative_agents_secondary"] = str(p5b)

    if "decomposition_status_label" in df.columns:
        decomp = df.loc[df["decomposition_status_label"].notna()]
        decomp = decomp.loc[~decomp["decomposition_status_label"].astype(str).isin(["nan", "None"])]
        if len(decomp):
            p7 = plot_attribute_count_dashboard(
                decomp, ["decomposition_status_label"],
                out_dir / "decomposition_status.png",
                title="Decomposition status",
            )
            if p7:
                paths["decomposition"] = str(p7)

    if "years_since_cut_label" in df.columns:
        ysc = df.loc[df["years_since_cut_label"].notna()]
        ysc = ysc.loc[~ysc["years_since_cut_label"].astype(str).isin(["nan", "None"])]
        if len(ysc):
            p8 = plot_attribute_count_dashboard(
                ysc, ["years_since_cut_label"],
                out_dir / "years_since_cut.png",
                title="Years since cut (stump / harvest context)",
            )
            if p8:
                paths["years_since_cut"] = str(p8)

    if plot_enriched is not None:
        flag_cols = [f for _, f in PLOT_PRESENCE_FLAG_SPECS if f in plot_enriched.columns]
        if flag_cols:
            p9 = plot_attribute_count_dashboard(
                plot_enriched, flag_cols,
                out_dir / "plot_notes_and_qualifiers.png",
                title="Plot notes and qualifier presence (access / ownership / notes2)",
            )
            if p9:
                paths["plot_notes_and_qualifiers"] = str(p9)

        if "has_field_notes" in plot_enriched.columns:
            if "plot_info1_plot_access1_label" in plot_enriched.columns:
                p10 = plot_attribute_count_dashboard(
                    plot_enriched.loc[plot_enriched["has_field_notes"]],
                    ["plot_info1_plot_access1_label"],
                    out_dir / "notes_by_access.png",
                    title="Plots with field notes: accessibility profile",
                )
                if p10:
                    paths["notes_by_access"] = str(p10)
            if "plot_info1_owner1_label" in plot_enriched.columns:
                p11 = plot_attribute_count_dashboard(
                    plot_enriched.loc[plot_enriched["has_field_notes"]],
                    ["plot_info1_owner1_label"],
                    out_dir / "notes_by_ownership.png",
                    title="Plots with field notes: ownership profile",
                )
                if p11:
                    paths["notes_by_ownership"] = str(p11)

        if "coord_displacement_m" in plot_enriched.columns and "plot_info1_plot_access1_label" in plot_enriched.columns:
            p12 = plot_metric_by_category_suite(
                plot_enriched, "coord_displacement_m", "plot_info1_plot_access1_label",
                out_dir / "coord_displacement_by_access.png",
                title="Coordinate displacement (m) by accessibility",
            )
            if p12:
                paths["coord_displacement_by_access"] = str(p12)

        if "time_record1_days_no" in plot_enriched.columns:
            days = pd.to_numeric(plot_enriched["time_record1_days_no"], errors="coerce")
            tmp = plot_enriched.copy()
            tmp["_survey_days"] = days
            if days.notna().sum() >= 5:
                p13 = plot_metric_distribution_suite(
                    tmp, ["_survey_days"], out_dir / "survey_effort_days", prefix="effort",
                )
                if p13:
                    paths["survey_effort_days"] = p13

        if "stem_quality_label" in df.columns and "crown_condition_label" in df.columns:
            # Condition co-occurrence heat-style counts via grouped bars already covered;
            # add bole height if present as a structural descriptor.
            pass

    if "tree_bole_height" in df.columns:
        bole = df.copy()
        bole["tree_bole_height"] = pd.to_numeric(bole["tree_bole_height"], errors="coerce")
        if bole["tree_bole_height"].notna().sum() >= 5:
            p14 = plot_metric_distribution_suite(
                bole, ["tree_bole_height"], out_dir / "bole_height", prefix="bole",
            )
            if p14:
                paths["bole_height"] = p14
            if "tree_or_stump_label" in bole.columns:
                p15 = plot_metric_by_category_suite(
                    bole, "tree_bole_height", "tree_or_stump_label",
                    out_dir / "bole_height_by_stump.png",
                    title="Bole height by tree / stump",
                )
                if p15:
                    paths["bole_height_by_stump"] = str(p15)

    return paths


# ---------------------------------------------------------------------------
# Field vs office coordinate cross-check (Mapping Approach PDF, p.5)
# ---------------------------------------------------------------------------

def field_vs_office_coordinate_crosscheck(
    plot_df: pd.DataFrame,
    out_dir: Path,
    *,
    title: str = "Field data verification and cross checking",
) -> dict:
    """
    Reproduce the Mapping Approach (FAO/NCVC) field↔office coordinate QA:

      • scatter of Field vs Office with trend lines (Office=red, Field=blue)
      • overlapping histograms + KDE for X (lon) and Y (lat)
      • paired t-tests on X and Y
      • MANOVA on (x,y) by source
      • Moran's I on displacement when PySAL / libpysal is available

    Expects columns from ``plot_coordinate_qa``:
      lon_field_orig, lat_field_orig, lon_db_orig, lat_db_orig
      (falls back to plot_info1_plot_coor1_* / plot_info1_coor_db_*).
    """
    import matplotlib.pyplot as plt
    from matplotlib import colors as mcolors

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    d = plot_df.copy()
    rename = {
        "plot_info1_plot_coor1_x": "lon_field_orig",
        "plot_info1_plot_coor1_y": "lat_field_orig",
        "plot_info1_coor_db_x": "lon_db_orig",
        "plot_info1_coor_db_y": "lat_db_orig",
    }
    for src, dst in rename.items():
        if dst not in d.columns and src in d.columns:
            d[dst] = d[src]

    need = ["lon_field_orig", "lat_field_orig", "lon_db_orig", "lat_db_orig"]
    miss = [c for c in need if c not in d.columns]
    if miss:
        return {"ok": False, "error": f"missing columns: {miss}"}

    for c in need:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    both = d.dropna(subset=need).copy()
    if both.empty:
        return {"ok": False, "error": "no paired field/office coordinates"}

    # Long form for MANOVA / hist overlays
    field_pts = both[["lon_field_orig", "lat_field_orig"]].rename(
        columns={"lon_field_orig": "x", "lat_field_orig": "y"}
    )
    field_pts["source"] = "Field"
    office_pts = both[["lon_db_orig", "lat_db_orig"]].rename(
        columns={"lon_db_orig": "x", "lat_db_orig": "y"}
    )
    office_pts["source"] = "Office"
    long = pd.concat([field_pts, office_pts], ignore_index=True)

    # Displacement (m) - same approx as plot_coordinate_qa
    dlon = (both["lon_field_orig"] - both["lon_db_orig"]) * 111000 * np.cos(
        np.radians(both["lat_db_orig"].fillna(23))
    )
    dlat = (both["lat_field_orig"] - both["lat_db_orig"]) * 111000
    both["displacement_m"] = np.sqrt(dlon**2 + dlat**2)

    # --- Stats ---
    from scipy import stats as scipy_stats

    tx = scipy_stats.ttest_rel(both["lon_field_orig"], both["lon_db_orig"], nan_policy="omit")
    ty = scipy_stats.ttest_rel(both["lat_field_orig"], both["lat_db_orig"], nan_policy="omit")

    manova_p = np.nan
    manova_note = "MANOVA unavailable"
    try:
        from statsmodels.multivariate.manova import MANOVA
        mv = long.copy()
        mv["source"] = mv["source"].astype("category")
        res = MANOVA.from_formula("x + y ~ source", data=mv).mv_test()
        # Wilks lambda p-value for source
        tab = res.results.get("source")
        if tab is not None:
            # tab.summary_frame or similar
            try:
                sf = tab["stat"]
                manova_p = float(sf.loc["Wilks' lambda", "Pr > F"])
            except Exception:
                try:
                    manova_p = float(np.asarray(tab.summary())[-1][-1])
                except Exception:
                    manova_p = np.nan
            manova_note = (
                f"MANOVA Wilks p ≈ {manova_p:.4f}. High p → no significant multivariate "
                "difference between Field and Office (x,y)."
                if np.isfinite(manova_p)
                else "MANOVA ran but p-value could not be parsed."
            )
    except Exception as e:
        manova_note = f"MANOVA skipped ({type(e).__name__}: {e})"

    moran_i, moran_p, moran_note = np.nan, np.nan, "Moran's I skipped (optional dependency)"
    try:
        from libpysal.weights import Queen
        from esda.moran import Moran
        import geopandas as gpd
        from shapely.geometry import Point

        g = gpd.GeoDataFrame(
            both,
            geometry=[Point(xy) for xy in zip(both["lon_db_orig"], both["lat_db_orig"])],
            crs=4326,
        )
        if len(g) >= 30:
            w = Queen.from_dataframe(g)
            w.transform = "r"
            mi = Moran(g["displacement_m"].fillna(0).values, w)
            moran_i, moran_p = float(mi.I), float(mi.p_sim)
            moran_note = (
                f"Moran's I = {moran_i:.4f}, p = {moran_p:.4g}. "
                "Values near 1 indicate strong positive spatial clustering of displacement."
            )
        else:
            moran_note = "Moran's I needs ≥30 paired points."
    except Exception as e:
        moran_note = f"Moran's I skipped ({type(e).__name__})"

    stats_tbl = pd.DataFrame([
        {"test": "Paired t-test X (lon Field-Office)", "statistic": float(tx.statistic), "p_value": float(tx.pvalue)},
        {"test": "Paired t-test Y (lat Field-Office)", "statistic": float(ty.statistic), "p_value": float(ty.pvalue)},
        {"test": "MANOVA (x,y ~ source)", "statistic": np.nan, "p_value": manova_p},
        {"test": "Moran's I (displacement)", "statistic": moran_i, "p_value": moran_p},
        {"test": "n paired plots", "statistic": float(len(both)), "p_value": np.nan},
        {"test": "median displacement_m", "statistic": float(both["displacement_m"].median()), "p_value": np.nan},
        {"test": "p95 displacement_m", "statistic": float(both["displacement_m"].quantile(0.95)), "p_value": np.nan},
    ])
    stats_path = out_dir / "field_vs_office_coord_stats.csv"
    stats_tbl.to_csv(stats_path, index=False)
    both_path = out_dir / "field_vs_office_coord_pairs.csv"
    both.to_csv(both_path, index=False)

    # --- Figure board (PDF p.5 layout) ---
    OFFICE, FIELD = "#dc2626", "#2563eb"
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.6), layout="constrained")

    # Left: scatter lon vs lat by source with OLS trend
    ax = axes[0]
    for src, col, lon_c, lat_c in [
        ("Office", OFFICE, "lon_db_orig", "lat_db_orig"),
        ("Field", FIELD, "lon_field_orig", "lat_field_orig"),
    ]:
        x = both[lon_c].values
        y = both[lat_c].values
        ax.scatter(x, y, s=12, alpha=0.45, c=col, label=src, edgecolors="none")
        if len(x) >= 3:
            coef = np.polyfit(x, y, 1)
            xs = np.linspace(np.nanmin(x), np.nanmax(x), 80)
            ax.plot(xs, coef[0] * xs + coef[1], color=col, lw=1.8, alpha=0.9)
    ax.set_xlabel("X (longitude)")
    ax.set_ylabel("Y (latitude)")
    ax.set_title("Scatter by DataSource", fontsize=10, fontweight="bold")
    ax.legend(frameon=False, fontsize=8)

    # Centre / right: overlapping histograms
    for ax, colname, lab in [
        (axes[1], "x", "Histogram of X: Office vs Field"),
        (axes[2], "y", "Histogram of Y: Office vs Field"),
    ]:
        for src, col in [("Office", OFFICE), ("Field", FIELD)]:
            vals = long.loc[long["source"] == src, colname].values
            ax.hist(vals, bins=28, density=False, alpha=0.45, color=col, label=src, edgecolor="white")
            try:
                from scipy.stats import gaussian_kde
                if len(vals) >= 8:
                    xs = np.linspace(np.nanmin(vals), np.nanmax(vals), 200)
                    kde = gaussian_kde(vals)
                    # scale KDE to count-ish height
                    scale = len(vals) * (xs.max() - xs.min()) / 28
                    ax.plot(xs, kde(xs) * scale, color=col, lw=1.6)
            except Exception:
                pass
        ax.set_title(lab, fontsize=10, fontweight="bold")
        ax.set_xlabel(colname.upper())
        ax.set_ylabel("Count")
        ax.legend(frameon=False, fontsize=8)

    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig_path = out_dir / "field_vs_office_coord_crosscheck.png"
    fig.savefig(fig_path, dpi=180, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)

    narrative = (
        f"Paired t-test X: t={tx.statistic:.4f}, p={tx.pvalue:.4g}. "
        f"Paired t-test Y: t={ty.statistic:.4f}, p={ty.pvalue:.4g}. "
        f"{manova_note} {moran_note} "
        f"Median field↔office displacement = {both['displacement_m'].median():.1f} m "
        f"(n={len(both)} paired plots)."
    )

    return {
        "ok": True,
        "n_paired": int(len(both)),
        "figure": str(fig_path),
        "stats_csv": str(stats_path),
        "pairs_csv": str(both_path),
        "stats": stats_tbl,
        "pairs": both,
        "narrative": narrative,
        "t_x": tx,
        "t_y": ty,
        "manova_p": manova_p,
        "moran_i": moran_i,
        "moran_p": moran_p,
    }

