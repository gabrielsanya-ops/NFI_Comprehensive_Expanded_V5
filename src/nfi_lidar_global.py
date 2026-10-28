# -*- coding: utf-8 -*-
"""
Sample free global canopy-height (LiDAR-informed) products at NFI plots
and compare with field-recorded tree heights using tabular AI models.

Primary product (currently offered, free, global):
  Meta / WRI High Resolution Canopy Height Maps v2 (DINOv3), via Source Cooperative
  tile index + COGs:
    https://data.source.coop/tge-labs/meta-chm-v2/tiles.parquet
    https://data.source.coop/tge-labs/meta-chm-v2/chm/{quadkey}.tif

Note: This is satellite-ML canopy height fused with LiDAR reference (not raw ALS
point clouds). Still the practical free global height layer for plot comparison.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

TILE_INDEX_URL = "https://data.source.coop/tge-labs/meta-chm-v2/tiles.parquet"
PRODUCT_NAME = "Meta_WRI_CHMv2_DINOv3_global"
PRODUCT_CITATION = (
    "Meta and World Resources Institute (2026). Version 2 High Resolution "
    "Canopy Height Maps (CHMv2). AWS Open Data / Source Cooperative."
)


def _env_for_cog():
    os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.tiff")


def ensure_meta_tile_index(cache_dir: Path) -> Path:
    import requests

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "meta_chm_v2_tiles.parquet"
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    r = requests.get(TILE_INDEX_URL, timeout=180)
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def load_meta_tiles(cache_dir: Path):
    import geopandas as gpd

    path = ensure_meta_tile_index(cache_dir)
    return gpd.read_parquet(path)


def _sample_cog_point_and_window(cog_url: str, lon: float, lat: float, half_win_px: int = 7) -> dict:
    """Sample center pixel + local max/mean/p95 in a small window (handles GPS/tree offset)."""
    import rasterio
    from pyproj import Transformer
    from rasterio.windows import Window

    _env_for_cog()
    out = {
        "chm_center_m": np.nan,
        "chm_window_max_m": np.nan,
        "chm_window_mean_m": np.nan,
        "chm_window_p95_m": np.nan,
        "cog_url": cog_url,
        "sample_ok": False,
        "error": None,
    }
    try:
        with rasterio.Env(GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES"):
            with rasterio.open(cog_url) as ds:
                tr = Transformer.from_crs(4326, ds.crs, always_xy=True)
                x, y = tr.transform(float(lon), float(lat))
                row, col = ds.index(x, y)
                center = list(ds.sample([(x, y)]))[0][0]
                if center is None or (isinstance(center, float) and np.isnan(center)):
                    center = np.nan
                # window
                r0 = max(0, row - half_win_px)
                c0 = max(0, col - half_win_px)
                h = min(ds.height - r0, 2 * half_win_px + 1)
                w = min(ds.width - c0, 2 * half_win_px + 1)
                win = Window(c0, r0, w, h)
                arr = ds.read(1, window=win).astype("float64")
                nodata = ds.nodata
                if nodata is not None:
                    arr = np.where(arr == nodata, np.nan, arr)
                arr = np.where(arr < 0, np.nan, arr)
                out["chm_center_m"] = float(center) if np.isfinite(center) else np.nan
                if np.isfinite(arr).any():
                    out["chm_window_max_m"] = float(np.nanmax(arr))
                    out["chm_window_mean_m"] = float(np.nanmean(arr))
                    out["chm_window_p95_m"] = float(np.nanpercentile(arr, 95))
                out["sample_ok"] = True
    except Exception as e:
        out["error"] = repr(e)
    return out


def extract_meta_chm_at_plots(
    plot_df: pd.DataFrame,
    cache_dir: Path,
    lon_col: str = "lon_validated",
    lat_col: str = "lat_validated",
    half_win_px: int = 7,
    progress_every: int = 25,
) -> pd.DataFrame:
    """
    Attach Meta CHM v2 heights to each plot with valid coordinates.
    Groups points by tile so each COG is opened once (much faster).
    """
    import geopandas as gpd
    import rasterio
    from shapely.geometry import Point
    from pyproj import Transformer
    from rasterio.windows import Window

    _env_for_cog()
    tiles = load_meta_tiles(cache_dir)
    df = plot_df.copy()
    # After GEDI sjoin the plot table can carry duplicate lat/lon names; zip() then
    # iterates column labels (strings) and Point() raises float('lon_validated').
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")].copy()
    if lon_col not in df.columns or lat_col not in df.columns:
        raise KeyError(
            f"Meta CHM needs '{lon_col}' and '{lat_col}'. Present: {list(df.columns)[:40]}"
        )
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df = df.dropna(subset=[lon_col, lat_col]).reset_index(drop=True)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(xy) for xy in zip(df[lon_col].tolist(), df[lat_col].tolist())],
        crs=4326,
    )
    # spatial join to tiles
    joined = gpd.sjoin(gdf, tiles[["quadkey", "cog_url", "geometry"]], how="left", predicate="intersects")
    # if multiple matches, keep first
    joined = joined[~joined.index.duplicated(keep="first")]

    results = []
    grouped = joined.groupby("cog_url", dropna=False)
    n_groups = joined["cog_url"].nunique(dropna=True)
    print(f"Sampling Meta CHM v2 at {len(joined)} plots across {n_groups} tiles...")

    done = 0
    for cog_url, grp in grouped:
        base_cols = {
            "PLOT_UID": grp.get("PLOT_UID"),
            "SU_UID": grp.get("SU_UID"),
            lon_col: grp[lon_col].values,
            lat_col: grp[lat_col].values,
            "mean_height_m": grp["mean_height_m"].values if "mean_height_m" in grp.columns else np.nan,
            "n_trees": grp["n_trees"].values if "n_trees" in grp.columns else np.nan,
            "chm_product": PRODUCT_NAME,
            "quadkey": grp["quadkey"].values if "quadkey" in grp.columns else None,
        }
        if pd.isna(cog_url) or cog_url is None:
            for i in range(len(grp)):
                results.append({
                    "PLOT_UID": grp.iloc[i].get("PLOT_UID"),
                    "SU_UID": grp.iloc[i].get("SU_UID"),
                    lon_col: float(grp.iloc[i][lon_col]),
                    lat_col: float(grp.iloc[i][lat_col]),
                    "mean_height_m": grp.iloc[i].get("mean_height_m"),
                    "n_trees": grp.iloc[i].get("n_trees"),
                    "chm_product": PRODUCT_NAME,
                    "quadkey": None,
                    "chm_center_m": np.nan,
                    "chm_window_max_m": np.nan,
                    "chm_window_mean_m": np.nan,
                    "chm_window_p95_m": np.nan,
                    "cog_url": None,
                    "sample_ok": False,
                    "error": "NO_TILE",
                })
            continue

        try:
            with rasterio.Env(GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES"):
                with rasterio.open(str(cog_url)) as ds:
                    tr = Transformer.from_crs(4326, ds.crs, always_xy=True)
                    for _, r in grp.iterrows():
                        lon, lat = float(r[lon_col]), float(r[lat_col])
                        x, y = tr.transform(lon, lat)
                        row, col = ds.index(x, y)
                        center = list(ds.sample([(x, y)]))[0][0]
                        r0 = max(0, row - half_win_px)
                        c0 = max(0, col - half_win_px)
                        h = min(ds.height - r0, 2 * half_win_px + 1)
                        w = min(ds.width - c0, 2 * half_win_px + 1)
                        arr = ds.read(1, window=Window(c0, r0, w, h)).astype("float64")
                        if ds.nodata is not None:
                            arr = np.where(arr == ds.nodata, np.nan, arr)
                        arr = np.where(arr < 0, np.nan, arr)
                        rec = {
                            "PLOT_UID": r.get("PLOT_UID"),
                            "SU_UID": r.get("SU_UID"),
                            lon_col: lon,
                            lat_col: lat,
                            "mean_height_m": r.get("mean_height_m"),
                            "n_trees": r.get("n_trees"),
                            "chm_product": PRODUCT_NAME,
                            "quadkey": r.get("quadkey"),
                            "cog_url": cog_url,
                            "chm_center_m": float(center) if center is not None and np.isfinite(center) else np.nan,
                            "sample_ok": True,
                            "error": None,
                        }
                        if np.isfinite(arr).any():
                            rec["chm_window_max_m"] = float(np.nanmax(arr))
                            rec["chm_window_mean_m"] = float(np.nanmean(arr))
                            rec["chm_window_p95_m"] = float(np.nanpercentile(arr, 95))
                        else:
                            rec["chm_window_max_m"] = np.nan
                            rec["chm_window_mean_m"] = np.nan
                            rec["chm_window_p95_m"] = np.nan
                        results.append(rec)
                        done += 1
                        if progress_every and done % progress_every == 0:
                            print(f"  CHM sampled {done}/{len(joined)}")
        except Exception as e:
            for _, r in grp.iterrows():
                results.append({
                    "PLOT_UID": r.get("PLOT_UID"),
                    "SU_UID": r.get("SU_UID"),
                    lon_col: float(r[lon_col]),
                    lat_col: float(r[lat_col]),
                    "mean_height_m": r.get("mean_height_m"),
                    "n_trees": r.get("n_trees"),
                    "chm_product": PRODUCT_NAME,
                    "quadkey": r.get("quadkey"),
                    "cog_url": cog_url,
                    "chm_center_m": np.nan,
                    "chm_window_max_m": np.nan,
                    "chm_window_mean_m": np.nan,
                    "chm_window_p95_m": np.nan,
                    "sample_ok": False,
                    "error": repr(e),
                })

    out = pd.DataFrame(results)
    if "mean_height_m" in out.columns:
        out["field_minus_chm_center"] = pd.to_numeric(out["mean_height_m"], errors="coerce") - pd.to_numeric(
            out["chm_center_m"], errors="coerce"
        )
        out["field_minus_chm_p95"] = pd.to_numeric(out["mean_height_m"], errors="coerce") - pd.to_numeric(
            out["chm_window_p95_m"], errors="coerce"
        )
    return out


def height_comparison_summary(joined: pd.DataFrame) -> pd.DataFrame:
    from nfi_datascience import regression_metrics

    rows = []
    field = pd.to_numeric(joined.get("mean_height_m"), errors="coerce")
    for name, col in [
        ("chm_center_m", "chm_center_m"),
        ("chm_window_p95_m", "chm_window_p95_m"),
        ("chm_window_max_m", "chm_window_max_m"),
    ]:
        if col not in joined.columns:
            continue
        pred = pd.to_numeric(joined[col], errors="coerce")
        m = regression_metrics(field, pred)
        m["comparison"] = f"field_mean_height vs {name}"
        m["n_finite_pairs"] = int((field.notna() & pred.notna()).sum())
        m["spearman"] = float(field.corr(pred, method="spearman")) if m["n_finite_pairs"] > 2 else np.nan
        rows.append(m)
    return pd.DataFrame(rows)


def plot_field_vs_chm(joined: pd.DataFrame, out_dir: Path) -> dict:
    import matplotlib.pyplot as plt
    from nfi_datascience import apply_plot_style, PALETTE

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    field = pd.to_numeric(joined["mean_height_m"], errors="coerce")
    for label, col in [
        ("center", "chm_center_m"),
        ("window_p95", "chm_window_p95_m"),
        ("window_max", "chm_window_max_m"),
    ]:
        if col not in joined.columns:
            continue
        chm = pd.to_numeric(joined[col], errors="coerce")
        mask = field.notna() & chm.notna()
        if mask.sum() < 5:
            continue
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        ax = axes[0]
        ax.scatter(field[mask], chm[mask], s=28, c=PALETTE["steel"], alpha=0.7, edgecolors="white", linewidths=0.4)
        lo = float(np.nanmin([field[mask].min(), chm[mask].min()]))
        hi = float(np.nanmax([field[mask].max(), chm[mask].max()]))
        ax.plot([lo, hi], [lo, hi], color=PALETTE["rose"], ls="--", lw=1.6, label="1:1")
        ax.set_xlabel("Field mean tree height (m)")
        ax.set_ylabel(f"Global CHM {label} (m)")
        ax.set_title(f"NFI field height vs Meta CHM v2 ({label})")
        ax.legend()

        ax = axes[1]
        resid = chm[mask] - field[mask]
        ax.hist(resid, bins=25, color=PALETTE["teal"], edgecolor="white", alpha=0.9, density=True)
        try:
            from scipy.stats import gaussian_kde
            xs = np.linspace(float(resid.min()), float(resid.max()), 120)
            ax.plot(xs, gaussian_kde(resid)(xs), color="#0f172a", lw=1.5)
        except Exception:
            pass
        ax.axvline(0, color=PALETTE["rose"], ls="--")
        ax.set_xlabel("CHM minus field (m)")
        ax.set_title(f"Residual KDE ({label})")
        fig.tight_layout()
        p = out_dir / f"field_vs_chm_{label}.png"
        fig.savefig(p, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths[label] = str(p)
    return paths


def plot_field_lidar_comparison_board(
    *,
    trees: pd.DataFrame,
    plot_df: pd.DataFrame | None = None,
    gedi_compare: pd.DataFrame | None = None,
    chm_joined: pd.DataFrame | None = None,
    out_dir: Path,
    gedi_height_col: str = "rh98",
) -> dict:
    """
    Field tree height and plot elevation versus LiDAR-informed products.

    Always draws field height (and elevation when present). When GEDI or Meta CHM
    pairs exist, adds scatter, residual KDE, and Bland-Altman panels.
    """
    import matplotlib.pyplot as plt
    from nfi_datascience import apply_plot_style, PALETTE

    apply_plot_style()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict = {}
    narrative = []

    # --- Field height distribution (always) ---
    hcol = next((c for c in ["tree_height", "height_m", "tree_height_m"] if c in trees.columns), None)
    if hcol:
        h = pd.to_numeric(trees[hcol], errors="coerce").dropna()
        h = h.loc[(h > 0) & (h < 80)]
        if len(h) >= 10:
            fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
            axes[0].hist(h, bins=30, color=PALETTE.get("steel", "#3b82f6"), edgecolor="white", alpha=0.9, density=True)
            try:
                from scipy.stats import gaussian_kde
                xs = np.linspace(float(h.min()), float(h.max()), 160)
                axes[0].plot(xs, gaussian_kde(h)(xs), color="#0f172a", lw=1.6)
            except Exception:
                pass
            axes[0].set_xlabel("Field tree height (m)")
            axes[0].set_ylabel("Density")
            axes[0].set_title("Field-measured tree heights")
            axes[1].boxplot(h, vert=True, patch_artist=True,
                            boxprops=dict(facecolor="#bfdbfe"), medianprops=dict(color="#1e3a8a"))
            axes[1].set_ylabel("Height (m)")
            axes[1].set_title(f"n={len(h):,}  median={h.median():.1f} m")
            fig.suptitle("NFI field tree height summary", fontsize=12, fontweight="bold")
            fig.tight_layout()
            p = out_dir / "field_tree_height_summary.png"
            fig.savefig(p, dpi=180, bbox_inches="tight")
            plt.close(fig)
            paths["field_height_summary"] = str(p)
            narrative.append(f"Field heights: n={len(h):,}, median={h.median():.1f} m.")

    # --- Field / plot elevation summary ---
    elev = None
    if plot_df is not None:
        ecol = next((c for c in ["elevation", "elev", "altitude", "nfi_elevation_m", "plot_elevation"] if c in plot_df.columns), None)
        if ecol:
            elev = pd.to_numeric(plot_df[ecol], errors="coerce").dropna()
    if elev is not None and len(elev) >= 10:
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        ax.hist(elev, bins=28, color="#78716c", edgecolor="white", alpha=0.9, density=True)
        try:
            from scipy.stats import gaussian_kde
            xs = np.linspace(float(elev.min()), float(elev.max()), 160)
            ax.plot(xs, gaussian_kde(elev)(xs), color="#0f172a", lw=1.6)
        except Exception:
            pass
        ax.set_xlabel("Plot elevation (m)")
        ax.set_ylabel("Density")
        ax.set_title(f"Field or database plot elevation (n={len(elev):,})")
        fig.tight_layout()
        p = out_dir / "field_plot_elevation_summary.png"
        fig.savefig(p, dpi=180, bbox_inches="tight")
        plt.close(fig)
        paths["field_elevation_summary"] = str(p)
        narrative.append(f"Plot elevation: n={len(elev):,}, median={elev.median():.0f} m.")

    # Field boards stay steel/blue; GEDI boards use amber so they read as a different product.
    GEDI_POINT = "#c2410c"   # burnt orange - GEDI pairs
    GEDI_RESID = "#ea580c"   # brighter orange - residual hist
    GEDI_BA = "#9a3412"      # deeper orange - Bland-Altman

    def _pair_board(x, y, *, xlab, ylab, title, stem, point_c=None, resid_c=None, ba_c=None):
        mask = x.notna() & y.notna()
        if mask.sum() < 5:
            return None
        xx, yy = x[mask].astype(float), y[mask].astype(float)
        point_c = point_c or PALETTE.get("steel", "#3b82f6")
        resid_c = resid_c or PALETTE.get("teal", "#14b8a6")
        ba_c = ba_c or "#6366f1"
        fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.0))
        ax = axes[0]
        ax.scatter(xx, yy, s=26, alpha=0.65, c=point_c, edgecolors="white", linewidths=0.35)
        lo = float(min(xx.min(), yy.min())); hi = float(max(xx.max(), yy.max()))
        ax.plot([lo, hi], [lo, hi], ls="--", color=PALETTE.get("rose", "#e11d48"), lw=1.5, label="1:1")
        ax.set_xlabel(xlab); ax.set_ylabel(ylab); ax.set_title("Scatter"); ax.legend(fontsize=8)
        ax = axes[1]
        resid = yy - xx
        ax.hist(resid, bins=22, color=resid_c, edgecolor="white", density=True, alpha=0.9)
        try:
            from scipy.stats import gaussian_kde
            xs = np.linspace(float(resid.min()), float(resid.max()), 120)
            ax.plot(xs, gaussian_kde(resid)(xs), color="#0f172a", lw=1.5)
        except Exception:
            pass
        ax.axvline(0, color=PALETTE.get("rose", "#e11d48"), ls="--")
        ax.set_xlabel("Remote minus field"); ax.set_title("Residual KDE")
        ax = axes[2]
        mean_pair = (xx + yy) / 2
        ax.scatter(mean_pair, resid, s=22, alpha=0.6, c=ba_c, edgecolors="white", linewidths=0.3)
        mdiff, sd = float(resid.mean()), float(resid.std(ddof=1)) if len(resid) > 1 else 0.0
        ax.axhline(mdiff, color="#0f172a")
        ax.axhline(mdiff + 1.96 * sd, color="#64748b", ls="--")
        ax.axhline(mdiff - 1.96 * sd, color="#64748b", ls="--")
        ax.set_xlabel("Pair mean"); ax.set_ylabel("Difference"); ax.set_title("Bland-Altman")
        fig.suptitle(title, fontsize=12, fontweight="bold")
        fig.tight_layout()
        p = out_dir / f"{stem}.png"
        fig.savefig(p, dpi=180, bbox_inches="tight")
        plt.close(fig)
        return str(p), int(mask.sum()), mdiff

    # --- GEDI height & elevation ---
    if gedi_compare is not None and len(gedi_compare):
        g = gedi_compare.copy()
        _gedi_colors = dict(point_c=GEDI_POINT, resid_c=GEDI_RESID, ba_c=GEDI_BA)
        if "nfi_height_p95" in g.columns and gedi_height_col in g.columns:
            out = _pair_board(
                pd.to_numeric(g["nfi_height_p95"], errors="coerce"),
                pd.to_numeric(g[gedi_height_col], errors="coerce"),
                xlab="NFI plot height P95 (m)",
                ylab=f"GEDI {gedi_height_col.upper()} (m)",
                title="Field upper-canopy height vs GEDI",
                stem="field_vs_gedi_height_board",
                **_gedi_colors,
            )
            if out:
                paths["gedi_height_board"], n, bias = out
                narrative.append(f"GEDI height pairs: n={n}, mean bias (GEDI-NFI)={bias:.2f} m.")
        if "nfi_elevation_m" in g.columns and "elev_ground" in g.columns:
            out = _pair_board(
                pd.to_numeric(g["nfi_elevation_m"], errors="coerce"),
                pd.to_numeric(g["elev_ground"], errors="coerce"),
                xlab="NFI plot elevation (m)",
                ylab="GEDI ground elevation (m)",
                title="Field or database elevation vs GEDI ground",
                stem="field_vs_gedi_elevation_board",
                **_gedi_colors,
            )
            if out:
                paths["gedi_elevation_board"], n, bias = out
                narrative.append(f"GEDI elevation pairs: n={n}, mean bias={bias:.1f} m.")

    # --- Meta CHM height ---
    if chm_joined is not None and len(chm_joined) and "mean_height_m" in chm_joined.columns:
        chm_paths = plot_field_vs_chm(chm_joined, out_dir / "chm")
        paths.update({f"chm_{k}": v for k, v in chm_paths.items()})
        if chm_paths:
            narrative.append(f"Meta CHM comparison figures: {len(chm_paths)}.")

    if not any(k.startswith("gedi_") or k.startswith("chm_") for k in paths):
        narrative.append(
            "No paired LiDAR product was available yet. Field height and elevation graphs are shown; "
            "add GEDI footprints or run Meta CHM sampling to unlock paired comparison boards."
        )

    return {
        "paths": paths,
        "narrative": " ".join(narrative),
        "out_dir": str(out_dir),
    }


def train_height_models_field_vs_chm(joined: pd.DataFrame, out_dir: Path, random_state: int = 42) -> dict:
    """
    Predict field mean_height_m from global CHM features (+ location)
    with SU-grouped 70/15/15 train/val/test.
    """
    from nfi_datascience import train_val_test_models

    df = joined.copy()
    # engineer features expected by train_val_test_models-like API  -  reuse with custom features
    need = ["mean_height_m", "lon_validated", "lat_validated", "SU_UID", "PLOT_UID"]
    for c in need:
        if c not in df.columns:
            return {"status": "SKIPPED", "reason": f"missing {c}"}

    # temporarily map CHM cols into the feature set via a thin wrapper
    feat = df.dropna(subset=["mean_height_m", "lon_validated", "lat_validated", "SU_UID"]).copy()
    # create aliases so existing trainer can be adapted
    for src, dst in [
        ("chm_window_p95_m", "n_trees"),          # reuse slot carefully  -  better custom trainer
    ]:
        pass

    return _train_height_custom(feat, out_dir, random_state=random_state)


def _train_height_custom(df: pd.DataFrame, out_dir: Path, random_state: int = 42) -> dict:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from nfi_datascience import (
        make_train_val_test_by_group, regression_metrics, plot_split_overview,
        plot_model_diagnostics, plot_metrics_comparison, plot_feature_importance,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    feature_cols = [c for c in [
        "lon_validated", "lat_validated",
        "chm_center_m", "chm_window_p95_m", "chm_window_max_m", "chm_window_mean_m",
        "n_trees",
    ] if c in df.columns]
    target = "mean_height_m"
    d = df.dropna(subset=[target, "SU_UID"] + [c for c in feature_cols if c.startswith("chm_") or c in ("lon_validated", "lat_validated")]).copy()
    # require at least one CHM signal
    chm_cols = [c for c in feature_cols if c.startswith("chm_")]
    if chm_cols:
        d = d.loc[d[chm_cols].notna().any(axis=1)].copy()
    if len(d) < 80:
        return {"status": "SKIPPED", "reason": f"insufficient rows ({len(d)})"}

    d = make_train_val_test_by_group(d, group_col="SU_UID", train_frac=0.70, val_frac=0.15, random_state=random_state)
    split_paths = plot_split_overview(d, target, out_dir / "splits")

    X = d[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    y = pd.to_numeric(d[target], errors="coerce")
    models = {
        "RandomForest": RandomForestRegressor(n_estimators=300, random_state=random_state, n_jobs=-1, min_samples_leaf=2),
        "GradientBoosting": GradientBoostingRegressor(random_state=random_state),
        "MLPRegressor": Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=500, random_state=random_state, early_stopping=True)),
        ]),
    }

    metric_rows, diag_paths, importance = [], {}, None
    tr = d["split"] == "train"
    for name, model in models.items():
        model.fit(X.loc[tr], y.loc[tr])
        for sp in ["train", "val", "test"]:
            msk = d["split"] == sp
            pred = model.predict(X.loc[msk])
            m = regression_metrics(y.loc[msk], pred)
            m.update({"model": name, "split_set": sp, "features": "|".join(feature_cols)})
            metric_rows.append(m)
            if sp in {"val", "test"}:
                diag_paths[f"{name}_{sp}"] = str(plot_model_diagnostics(
                    y.loc[msk], pred, sp, name, out_dir / f"diag_{name}_{sp}.png"
                ))
        if hasattr(model, "feature_importances_"):
            importance = pd.DataFrame({"feature": feature_cols, "importance": model.feature_importances_, "model": name})

    metrics = pd.DataFrame(metric_rows)
    metrics_plot = plot_metrics_comparison(metrics, out_dir / "metrics_by_split.png")
    imp_path = None
    if importance is not None:
        imp_path = plot_feature_importance(importance, out_dir / "feature_importance.png", "Height model feature importance")

    best = metrics.loc[metrics.split_set == "val"].sort_values("RMSE").iloc[0]["model"]
    return {
        "status": "OK",
        "metrics": metrics,
        "data_with_split": d,
        "best_model_by_val_RMSE": best,
        "feature_importance": importance,
        "feature_cols": feature_cols,
        "plot_paths": {**split_paths, "metrics_by_split": str(metrics_plot),
                       "feature_importance": str(imp_path) if imp_path else None, **diag_paths},
        "product": PRODUCT_NAME,
        "citation": PRODUCT_CITATION,
        "n_train": int((d.split == "train").sum()),
        "n_val": int((d.split == "val").sum()),
        "n_test": int((d.split == "test").sum()),
    }
