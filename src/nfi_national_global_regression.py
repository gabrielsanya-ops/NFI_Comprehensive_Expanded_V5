# -*- coding: utf-8 -*-
"""Regression of national NFI metrics against free global predictors.

Predictors (free, documented):
  1. Elevation from Open-Meteo elevation API (SRTM-based digital elevation).
     https://open-meteo.com/en/docs/elevation-api
  2. Meta / WRI High Resolution Canopy Height Maps v2 (optional subset),
     via nfi_lidar_global (Source Cooperative COGs).

Responses (provisional sample metrics from national thematic / biomass tables):
  mean_height_m, mean_dbh_cm, sum_tree_carbon_mg, sum_tree_agb_mg, n_trees

Ordinary least squares and Spearman correlations are reported. Numbers are
computed only from finite pairs; no invented coefficients.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


OPEN_METEO_ELEV_URL = "https://api.open-meteo.com/v1/elevation"
OPEN_METEO_CITATION = (
    "Zippenfenig, P. (2023). Open-Meteo.com Weather API. "
    "Elevation endpoint (SRTM-based). https://open-meteo.com/"
)
CHM_CITATION = (
    "Meta and World Resources Institute (2026). Version 2 High Resolution "
    "Canopy Height Maps (CHMv2). AWS Open Data / Source Cooperative."
)


def fetch_elevation_open_meteo(
    lons: np.ndarray,
    lats: np.ndarray,
    *,
    batch_size: int = 40,
    timeout: int = 60,
    pause_s: float = 1.2,
    max_retries: int = 4,
) -> np.ndarray:
    """Batch-query Open-Meteo elevation for lon/lat arrays (EPSG:4326)."""
    import time
    import requests

    elev = np.full(len(lons), np.nan, dtype=float)
    for i in range(0, len(lons), batch_size):
        sl = slice(i, i + batch_size)
        lon_s = ",".join(f"{float(x):.6f}" for x in lons[sl])
        lat_s = ",".join(f"{float(y):.6f}" for y in lats[sl])
        vals = []
        for attempt in range(max_retries):
            try:
                r = requests.get(
                    OPEN_METEO_ELEV_URL,
                    params={"longitude": lon_s, "latitude": lat_s},
                    timeout=timeout,
                )
                if r.status_code == 429:
                    time.sleep(pause_s * (attempt + 2))
                    continue
                r.raise_for_status()
                vals = r.json().get("elevation") or []
                break
            except Exception:
                time.sleep(pause_s * (attempt + 1))
        for j, v in enumerate(vals):
            if j >= (sl.stop - sl.start):
                break
            elev[i + j] = float(v) if v is not None else np.nan
        time.sleep(pause_s)
    return elev


def attach_elevation_to_su(
    themes_df: pd.DataFrame,
    *,
    tree_present_only: bool = True,
    max_points: int | None = 900,
    seed: int = 42,
) -> pd.DataFrame:
    use = themes_df.loc[
        themes_df["lon_validated"].notna() & themes_df["lat_validated"].notna()
    ].copy()
    if use.empty:
        use["elevation_m"] = pd.Series(dtype=float)
        return use
    if tree_present_only and "has_tree_record" in use.columns:
        treed = use.loc[use["has_tree_record"].fillna(False).astype(bool)]
        if len(treed) >= 30:
            use = treed
    if max_points is not None and len(use) > max_points:
        use = use.sample(n=max_points, random_state=seed)
    elev = fetch_elevation_open_meteo(
        use["lon_validated"].to_numpy(dtype=float),
        use["lat_validated"].to_numpy(dtype=float),
    )
    use["elevation_m"] = elev
    return use


def _ols_simple(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    """Simple OLS y ~ a + b x with R2, RMSE, Spearman (finite pairs only)."""
    m = x.notna() & y.notna()
    n = int(m.sum())
    out = {
        "n": n,
        "intercept": np.nan,
        "slope": np.nan,
        "r2": np.nan,
        "rmse": np.nan,
        "spearman": np.nan,
        "pearson": np.nan,
    }
    if n < 8:
        return out
    xv = x[m].to_numpy(dtype=float)
    yv = y[m].to_numpy(dtype=float)
    # polyfit degree 1
    b, a = np.polyfit(xv, yv, 1)  # y = b*x + a  (numpy returns highest power first)
    pred = a + b * xv
    ss_res = float(np.sum((yv - pred) ** 2))
    ss_tot = float(np.sum((yv - yv.mean()) ** 2))
    out["intercept"] = float(a)
    out["slope"] = float(b)
    out["r2"] = float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan
    out["rmse"] = float(np.sqrt(ss_res / n))
    out["spearman"] = float(pd.Series(xv).corr(pd.Series(yv), method="spearman"))
    out["pearson"] = float(pd.Series(xv).corr(pd.Series(yv), method="pearson"))
    return out


def run_elevation_regressions(su_elev: pd.DataFrame) -> pd.DataFrame:
    responses = [
        ("mean_height_m", "SU mean tree height (m)"),
        ("mean_dbh_cm", "SU mean DBH (cm)"),
        ("sum_tree_carbon_mg", "SU provisional tree carbon sum (Mg)"),
        ("sum_tree_agb_mg", "SU provisional tree AGB sum (Mg)"),
        ("n_trees", "SU tree count"),
    ]
    x = pd.to_numeric(su_elev.get("elevation_m"), errors="coerce")
    rows = []
    for col, label in responses:
        if col not in su_elev.columns:
            continue
        y = pd.to_numeric(su_elev[col], errors="coerce")
        # Prefer SUs with trees for structure/biomass responses
        if col in {"mean_height_m", "mean_dbh_cm", "sum_tree_carbon_mg", "sum_tree_agb_mg", "n_trees"}:
            if "has_tree_record" in su_elev.columns:
                mask = su_elev["has_tree_record"].fillna(False).astype(bool)
                stats = _ols_simple(x[mask], y[mask])
            else:
                stats = _ols_simple(x, y)
        else:
            stats = _ols_simple(x, y)
        stats.update({
            "response": col,
            "response_label": label,
            "predictor": "elevation_m",
            "predictor_source": "Open-Meteo elevation API (SRTM-based)",
        })
        rows.append(stats)
    return pd.DataFrame(rows)


def plot_regression_panels(
    su_elev: pd.DataFrame,
    metrics: pd.DataFrame,
    out_dir: Path,
) -> dict[str, Path]:
    import matplotlib.pyplot as plt
    from nfi_datascience import apply_plot_style, FANCY_PANEL_COLORS

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    x = pd.to_numeric(su_elev["elevation_m"], errors="coerce")
    for i, row in metrics.iterrows():
        col = row["response"]
        if col not in su_elev.columns:
            continue
        y = pd.to_numeric(su_elev[col], errors="coerce")
        if "has_tree_record" in su_elev.columns and col != "elevation_m":
            m = su_elev["has_tree_record"].fillna(False).astype(bool) & x.notna() & y.notna()
        else:
            m = x.notna() & y.notna()
        if m.sum() < 8:
            continue
        color = FANCY_PANEL_COLORS[int(i) % len(FANCY_PANEL_COLORS)]
        fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
        ax = axes[0]
        ax.scatter(x[m], y[m], s=22, c=color, alpha=0.55, edgecolors="white", linewidths=0.3)
        # regression line from fitted slope/intercept
        xs = np.linspace(float(x[m].min()), float(x[m].max()), 80)
        ax.plot(xs, row["intercept"] + row["slope"] * xs, color="#0f172a", lw=2.0, label="OLS fit")
        ax.set_xlabel("Elevation (m, Open-Meteo / SRTM)")
        ax.set_ylabel(row["response_label"])
        ax.set_title(
            f"{row['response_label']} vs elevation\n"
            f"n={int(row['n'])}  R²={row['r2']:.3f}  Spearman={row['spearman']:.3f}",
            fontsize=10,
        )
        ax.legend(fontsize=8)

        ax = axes[1]
        resid = y[m] - (row["intercept"] + row["slope"] * x[m])
        ax.hist(resid, bins=28, color=color, alpha=0.7, edgecolor="white", density=True)
        ax.axvline(0, color="#e11d48", ls="--", lw=1.5)
        ax.set_xlabel("Residual (observed minus fitted)")
        ax.set_title("Residual distribution")
        fig.suptitle("National NFI vs free global elevation", fontsize=12, fontweight="bold")
        fig.tight_layout()
        p = out_dir / f"reg_elev_vs_{col}.png"
        fig.savefig(p, dpi=170, bbox_inches="tight")
        plt.close(fig)
        paths[col] = p
    return paths


def maybe_attach_chm_subset(
    su_elev: pd.DataFrame,
    cache_dir: Path,
    *,
    max_points: int = 280,
    seed: int = 42,
) -> pd.DataFrame:
    """Sample Meta CHM at a subset of tree-present SU centroids (network-bound)."""
    try:
        from nfi_lidar_global import extract_meta_chm_at_plots
    except Exception:
        return su_elev
    use = su_elev.copy()
    if "has_tree_record" in use.columns:
        cand = use.loc[use["has_tree_record"].fillna(False).astype(bool)]
    else:
        cand = use
    cand = cand.loc[cand["lon_validated"].notna() & cand["lat_validated"].notna()]
    if len(cand) == 0:
        return use
    if len(cand) > max_points:
        cand = cand.sample(n=max_points, random_state=seed)
    try:
        chm = extract_meta_chm_at_plots(
            cand.rename(columns={"mean_height_m": "mean_height_m"}),
            cache_dir=cache_dir,
            lon_col="lon_validated",
            lat_col="lat_validated",
            half_win_px=5,
            progress_every=50,
        )
    except Exception as exc:
        use.attrs["chm_error"] = repr(exc)
        return use
    keep = ["SU_UID", "chm_center_m", "chm_window_p95_m", "chm_window_mean_m", "sample_ok"]
    keep = [c for c in keep if c in chm.columns]
    out = use.merge(chm[keep], on="SU_UID", how="left")
    return out


def run_chm_regressions(su_chm: pd.DataFrame) -> pd.DataFrame:
    if "chm_window_p95_m" not in su_chm.columns and "chm_center_m" not in su_chm.columns:
        return pd.DataFrame()
    pred_col = "chm_window_p95_m" if "chm_window_p95_m" in su_chm.columns else "chm_center_m"
    x = pd.to_numeric(su_chm[pred_col], errors="coerce")
    rows = []
    for col, label in [
        ("mean_height_m", "SU mean tree height (m)"),
        ("mean_dbh_cm", "SU mean DBH (cm)"),
        ("sum_tree_carbon_mg", "SU provisional tree carbon sum (Mg)"),
    ]:
        if col not in su_chm.columns:
            continue
        y = pd.to_numeric(su_chm[col], errors="coerce")
        stats = _ols_simple(x, y)
        stats.update({
            "response": col,
            "response_label": label,
            "predictor": pred_col,
            "predictor_source": "Meta/WRI CHMv2 (global canopy height)",
        })
        rows.append(stats)
    return pd.DataFrame(rows)


def plot_chm_regression_panels(su_chm: pd.DataFrame, metrics: pd.DataFrame, out_dir: Path) -> dict[str, Path]:
    import matplotlib.pyplot as plt
    from nfi_datascience import apply_plot_style, FANCY_PANEL_COLORS

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if metrics is None or metrics.empty:
        return {}
    pred = metrics.iloc[0]["predictor"]
    x = pd.to_numeric(su_chm[pred], errors="coerce")
    paths = {}
    for i, row in metrics.iterrows():
        col = row["response"]
        y = pd.to_numeric(su_chm[col], errors="coerce")
        m = x.notna() & y.notna()
        if m.sum() < 8:
            continue
        color = FANCY_PANEL_COLORS[int(i) % len(FANCY_PANEL_COLORS)]
        fig, ax = plt.subplots(figsize=(6.2, 5.0))
        ax.scatter(x[m], y[m], s=28, c=color, alpha=0.6, edgecolors="white", linewidths=0.3)
        xs = np.linspace(float(x[m].min()), float(x[m].max()), 60)
        ax.plot(xs, row["intercept"] + row["slope"] * xs, color="#0f172a", lw=2)
        ax.set_xlabel(f"{pred} (m)")
        ax.set_ylabel(row["response_label"])
        ax.set_title(
            f"{row['response_label']} vs Meta CHM\n"
            f"n={int(row['n'])}  R²={row['r2']:.3f}  Spearman={row['spearman']:.3f}"
        )
        fig.tight_layout()
        p = out_dir / f"reg_chm_vs_{col}.png"
        fig.savefig(p, dpi=170, bbox_inches="tight")
        plt.close(fig)
        paths[col] = p
    return paths


def produce_national_global_regressions(
    themes_df: pd.DataFrame,
    out_root: Path,
    *,
    sample_chm: bool = True,
    chm_max_points: int = 280,
) -> dict[str, Any]:
    out_root = Path(out_root)
    fig_dir = out_root / "figures" / "national_global_regression"
    audit = out_root / "audit"
    fig_dir.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)

    su_elev = attach_elevation_to_su(themes_df, tree_present_only=True, max_points=700)
    su_elev.to_csv(audit / "national_su_with_elevation.csv", index=False)
    elev_metrics = run_elevation_regressions(su_elev)
    elev_metrics.to_csv(audit / "regression_elevation_metrics.csv", index=False)
    elev_figs = plot_regression_panels(su_elev, elev_metrics, fig_dir / "elevation")

    chm_metrics = pd.DataFrame()
    chm_figs: dict[str, Path] = {}
    su_chm = su_elev
    if sample_chm:
        cache = out_root / "cache" / "meta_chm_v2"
        su_chm = maybe_attach_chm_subset(su_elev, cache, max_points=chm_max_points)
        su_chm.to_csv(audit / "national_su_with_elevation_chm.csv", index=False)
        chm_metrics = run_chm_regressions(su_chm)
        if len(chm_metrics):
            chm_metrics.to_csv(audit / "regression_chm_metrics.csv", index=False)
            chm_figs = plot_chm_regression_panels(su_chm, chm_metrics, fig_dir / "chm")

    citations = [OPEN_METEO_CITATION, CHM_CITATION]
    (audit / "global_predictor_citations.txt").write_text("\n".join(citations), encoding="utf-8")

    return {
        "su_elev": su_elev,
        "elev_metrics": elev_metrics,
        "elev_figs": elev_figs,
        "chm_metrics": chm_metrics,
        "chm_figs": chm_figs,
        "citations": citations,
    }
