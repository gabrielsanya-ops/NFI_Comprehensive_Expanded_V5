# -*- coding: utf-8 -*-
"""National-wide remote height evidence for the entire Kingdom (not Asir-only).

Primary free wall-to-wall alternatives to footprint GEDI for KSA NFI:
  1. Meta / WRI High Resolution Canopy Height Maps v2 (global COGs)
  2. Open-Meteo elevation (SRTM-based) at national SU centroids

Policy (aligned with End-to-End workflow):
  - Compare disparities only; never overwrite field tree_height.
  - Imputation OFF for remote → field.
  - Coverage is the full national SU master (all regions).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nfi_lidar_global import PRODUCT_CITATION as CHM_CITATION
from nfi_lidar_global import PRODUCT_NAME as CHM_PRODUCT
from nfi_lidar_global import extract_meta_chm_at_plots
from nfi_national_global_regression import OPEN_METEO_CITATION, fetch_elevation_open_meteo


def load_national_su_points(out_root: Path, cfg: dict | None = None) -> pd.DataFrame:
    """Load national SU centroids for the entire Kingdom."""
    path = Path(out_root) / "validated" / "national_su_thematic_attributes.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run the national thematic/atlas stage first "
            "so all-region SU centroids exist."
        )
    df = pd.read_csv(path)
    need = ["SU_UID", "lon_validated", "lat_validated"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise KeyError(f"national_su_thematic_attributes missing columns: {missing}")
    df = df.dropna(subset=["lon_validated", "lat_validated"]).copy()
    df["lon_validated"] = pd.to_numeric(df["lon_validated"], errors="coerce")
    df["lat_validated"] = pd.to_numeric(df["lat_validated"], errors="coerce")
    df = df.dropna(subset=["lon_validated", "lat_validated"])
    df = df[df["lat_validated"].between(-90, 90) & df["lon_validated"].between(-180, 180)]
    return df.reset_index(drop=True)


def _fetch_elevation_opentopodata(
    lons: np.ndarray,
    lats: np.ndarray,
    *,
    batch_size: int = 100,
    pause_s: float = 0.35,
    dataset: str = "srtm30m",
) -> np.ndarray:
    """National terrain heights via OpenTopoData SRTM30m (wall-to-wall)."""
    import time
    import requests

    elev = np.full(len(lons), np.nan, dtype=float)
    url = f"https://api.opentopodata.org/v1/{dataset}"
    for i in range(0, len(lons), batch_size):
        sl = slice(i, i + batch_size)
        locs = "|".join(f"{float(lat):.6f},{float(lon):.6f}" for lon, lat in zip(lons[sl], lats[sl]))
        try:
            r = requests.get(url, params={"locations": locs}, timeout=90)
            if r.status_code == 429:
                time.sleep(2.0)
                r = requests.get(url, params={"locations": locs}, timeout=90)
            r.raise_for_status()
            results = r.json().get("results") or []
            for j, rec in enumerate(results):
                if j >= (sl.stop - sl.start):
                    break
                v = rec.get("elevation")
                elev[i + j] = float(v) if v is not None else np.nan
        except Exception:
            # leave NaNs for this batch
            pass
        if (i // batch_size) % 5 == 0:
            print(f"  elevation progress {min(i + batch_size, len(lons))}/{len(lons)}")
        time.sleep(pause_s)
    return elev


def attach_national_elevation(su_df: pd.DataFrame, *, pause_s: float = 0.35) -> pd.DataFrame:
    """Wall-to-wall elevation for every national SU (OpenTopoData SRTM30m, fallback Open-Meteo)."""
    out = su_df.copy()
    lons = out["lon_validated"].to_numpy(dtype=float)
    lats = out["lat_validated"].to_numpy(dtype=float)
    elev = _fetch_elevation_opentopodata(lons, lats, pause_s=pause_s)
    source = (
        "OpenTopoData SRTM30m API (Jarvis et al. / CGIAR SRTM). "
        "https://www.opentopodata.org/"
    )
    if int(np.isfinite(elev).sum()) < max(50, int(0.2 * len(elev))):
        print("OpenTopoData sparse; falling back to Open-Meteo elevation...")
        elev = fetch_elevation_open_meteo(lons, lats, batch_size=40, pause_s=max(pause_s, 1.0))
        source = OPEN_METEO_CITATION
    out["elevation_m_open_meteo"] = elev  # keep column name for downstream continuity
    out["elevation_m"] = elev
    out["elevation_source"] = source
    return out


def sample_national_meta_chm(
    su_df: pd.DataFrame,
    cache_dir: Path,
    *,
    progress_every: int = 50,
    workers: int = 8,
) -> pd.DataFrame:
    """Meta CHMv2 at national SU centroids (all regions), parallel by COG tile."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import geopandas as gpd
    from shapely.geometry import Point

    from nfi_lidar_global import _env_for_cog, _sample_cog_point_and_window, load_meta_tiles

    pts = su_df.copy()
    if "PLOT_UID" not in pts.columns:
        pts["PLOT_UID"] = pts["SU_UID"].astype(str) + "-SU_CENTROID"
    pts["lon_validated"] = pd.to_numeric(pts["lon_validated"], errors="coerce")
    pts["lat_validated"] = pd.to_numeric(pts["lat_validated"], errors="coerce")
    pts = pts.dropna(subset=["lon_validated", "lat_validated"]).reset_index(drop=True)

    _env_for_cog()
    tiles = load_meta_tiles(cache_dir)
    gdf = gpd.GeoDataFrame(
        pts,
        geometry=[Point(xy) for xy in zip(pts["lon_validated"], pts["lat_validated"])],
        crs=4326,
    )
    joined = gpd.sjoin(
        gdf, tiles[["quadkey", "cog_url", "geometry"]], how="left", predicate="intersects"
    )
    joined = joined[~joined.index.duplicated(keep="first")]

    groups = list(joined.groupby("cog_url", dropna=False))
    print(f"Sampling Meta CHM v2 at {len(joined)} SUs across {len(groups)} tiles (workers={workers})...")

    def _one_group(item):
        cog_url, grp = item
        rows = []
        if pd.isna(cog_url) or cog_url is None:
            for _, r in grp.iterrows():
                rows.append({
                    "PLOT_UID": r.get("PLOT_UID"),
                    "SU_UID": r.get("SU_UID"),
                    "lon_validated": float(r["lon_validated"]),
                    "lat_validated": float(r["lat_validated"]),
                    "chm_product": CHM_PRODUCT,
                    "quadkey": None,
                    "chm_center_m": np.nan,
                    "chm_window_max_m": np.nan,
                    "chm_window_mean_m": np.nan,
                    "chm_window_p95_m": np.nan,
                    "cog_url": None,
                    "sample_ok": False,
                    "error": "NO_TILE",
                })
            return rows
        for _, r in grp.iterrows():
            sample = _sample_cog_point_and_window(
                str(cog_url), float(r["lon_validated"]), float(r["lat_validated"]), half_win_px=7
            )
            rows.append({
                "PLOT_UID": r.get("PLOT_UID"),
                "SU_UID": r.get("SU_UID"),
                "lon_validated": float(r["lon_validated"]),
                "lat_validated": float(r["lat_validated"]),
                "chm_product": CHM_PRODUCT,
                "quadkey": r.get("quadkey"),
                "cog_url": cog_url,
                **sample,
            })
        return rows

    results = []
    done_groups = 0
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futs = [pool.submit(_one_group, g) for g in groups]
        for fut in as_completed(futs):
            results.extend(fut.result())
            done_groups += 1
            if progress_every and done_groups % max(1, progress_every // 5) == 0:
                print(f"  CHM tiles done {done_groups}/{len(groups)}")

    out = pd.DataFrame(results)
    if "mean_height_m" in pts.columns:
        out = out.merge(pts[["SU_UID", "mean_height_m"]], on="SU_UID", how="left")
        out["field_minus_chm_center"] = pd.to_numeric(out["mean_height_m"], errors="coerce") - pd.to_numeric(
            out["chm_center_m"], errors="coerce"
        )
        out["field_minus_chm_p95"] = pd.to_numeric(out["mean_height_m"], errors="coerce") - pd.to_numeric(
            out["chm_window_p95_m"], errors="coerce"
        )
    return out


def disparity_summary(joined: pd.DataFrame) -> dict[str, Any]:
    """Numeric disparity stats where field height and CHM both finite."""
    work = joined.copy()
    if "mean_height_m" not in work.columns:
        return {"n_paired": 0, "note": "No field mean_height_m on SU table."}
    field = pd.to_numeric(work["mean_height_m"], errors="coerce")
    chm = pd.to_numeric(work.get("chm_window_p95_m", work.get("chm_center_m")), errors="coerce")
    pair = work.loc[field.notna() & chm.notna() & (field > 0)].copy()
    if pair.empty:
        return {"n_paired": 0, "note": "No overlapping field height and CHM values."}
    delta = field.loc[pair.index] - chm.loc[pair.index]
    by_region = None
    if "region" in pair.columns:
        tmp = pair.assign(_field=field.loc[pair.index], _chm=chm.loc[pair.index])
        tmp["_delta"] = tmp["_field"] - tmp["_chm"]
        by_region = (
            tmp.groupby("region", dropna=False)
            .agg(
                n_paired=("_delta", "size"),
                mae_m=("_delta", lambda s: float(np.mean(np.abs(s)))),
                bias_m=("_delta", "mean"),
                field_mean_m=("_field", "mean"),
                chm_mean_m=("_chm", "mean"),
            )
            .reset_index()
        )
        by_region["mae_m"] = by_region["mae_m"].round(3)
        by_region["bias_m"] = by_region["bias_m"].round(3)
        by_region["field_mean_m"] = by_region["field_mean_m"].round(3)
        by_region["chm_mean_m"] = by_region["chm_mean_m"].round(3)
    return {
        "n_paired": int(len(pair)),
        "mae_m": round(float(np.mean(np.abs(delta))), 3),
        "bias_field_minus_chm_m": round(float(delta.mean()), 3),
        "spearman_r": round(float(pd.Series(field.loc[pair.index]).corr(pd.Series(chm.loc[pair.index]), method="spearman")), 4)
        if len(pair) >= 3
        else None,
        "by_region": by_region,
    }


def run_national_remote_height_evidence(
    out_root: Path,
    *,
    cache_dir: Path | None = None,
    sample_chm: bool = True,
    sample_elevation: bool = True,
    max_chm_points: int | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Build Kingdom-wide remote height evidence package.

    Parameters
    ----------
    max_chm_points :
        Optional cap for CHM network sampling. ``None`` = all national SUs with coords.
        Stratification by region is applied when capping so no province is dropped.
    """
    out_root = Path(out_root)
    cache_dir = Path(cache_dir) if cache_dir else out_root / "cache" / "meta_chm_v2"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (out_root / "validated").mkdir(parents=True, exist_ok=True)
    (out_root / "audit").mkdir(parents=True, exist_ok=True)
    (out_root / "logs").mkdir(parents=True, exist_ok=True)

    su = load_national_su_points(out_root)
    n_regions = int(su["region"].nunique()) if "region" in su.columns else None

    # Optional stratified cap (still national, all regions represented)
    chm_input = su
    if sample_chm and max_chm_points is not None and len(su) > max_chm_points:
        if "region" in su.columns:
            parts = []
            regions = su["region"].fillna("UNKNOWN").unique().tolist()
            per = max(1, max_chm_points // max(1, len(regions)))
            rng = np.random.RandomState(seed)
            for reg, g in su.fillna({"region": "UNKNOWN"}).groupby("region"):
                take = min(len(g), per)
                # prefer tree-present when available
                if "has_tree_record" in g.columns and g["has_tree_record"].fillna(False).any():
                    treed = g.loc[g["has_tree_record"].fillna(False).astype(bool)]
                    other = g.loc[~g["has_tree_record"].fillna(False).astype(bool)]
                    n_t = min(len(treed), max(1, take // 2))
                    n_o = min(len(other), take - n_t)
                    parts.append(pd.concat([
                        treed.sample(n=n_t, random_state=seed) if n_t else treed.head(0),
                        other.sample(n=n_o, random_state=seed) if n_o else other.head(0),
                    ], ignore_index=True))
                else:
                    parts.append(g.sample(n=take, random_state=int(rng.randint(0, 10_000))))
            chm_input = pd.concat(parts, ignore_index=True)
            if len(chm_input) > max_chm_points:
                chm_input = chm_input.sample(n=max_chm_points, random_state=seed)
        else:
            chm_input = su.sample(n=max_chm_points, random_state=seed)

    elev_df = None
    if sample_elevation:
        print(f"National elevation (SRTM via OpenTopoData) for {len(su)} SUs across {n_regions} regions...")
        elev_df = attach_national_elevation(su)
        elev_path = out_root / "validated" / "national_su_elevation_open_meteo.csv"
        elev_df.to_csv(elev_path, index=False)
    else:
        elev_path = out_root / "validated" / "national_su_elevation_open_meteo.csv"

    chm_df = None
    chm_path = out_root / "validated" / "national_su_meta_chm_v2.csv"
    if sample_chm:
        print(
            f"National Meta CHMv2 sampling for {len(chm_input)} SUs "
            f"(regions={chm_input['region'].nunique() if 'region' in chm_input.columns else 'n/a'})..."
        )
        chm_df = sample_national_meta_chm(chm_input, cache_dir=cache_dir)
        # bring region / field height from input
        meta_cols = [c for c in ["SU_UID", "region", "mean_height_m", "has_tree_record", "n_trees"] if c in chm_input.columns]
        chm_df = chm_df.merge(chm_input[meta_cols].drop_duplicates("SU_UID"), on="SU_UID", how="left", suffixes=("", "_su"))
        if "mean_height_m_su" in chm_df.columns and "mean_height_m" in chm_df.columns:
            chm_df["mean_height_m"] = chm_df["mean_height_m"].fillna(chm_df["mean_height_m_su"])
        chm_df.to_csv(chm_path, index=False)

    # Join elevation onto CHM table when both exist
    joined = None
    if chm_df is not None:
        joined = chm_df.copy()
        if elev_df is not None:
            joined = joined.merge(
                elev_df[["SU_UID", "elevation_m_open_meteo"]],
                on="SU_UID",
                how="left",
            )
        disp = disparity_summary(joined)
        if isinstance(disp.get("by_region"), pd.DataFrame):
            disp["by_region"].to_csv(
                out_root / "audit" / "national_chm_field_disparity_by_region.csv", index=False
            )
            disp_serializable = {k: v for k, v in disp.items() if k != "by_region"}
            disp_serializable["n_regions_in_disparity"] = int(len(disp["by_region"]))
        else:
            disp_serializable = disp
    else:
        disp_serializable = {"n_paired": 0, "note": "CHM not sampled this run."}

    n_chm_ok = int(chm_df["sample_ok"].fillna(False).sum()) if chm_df is not None and "sample_ok" in chm_df.columns else 0
    n_elev_ok = int(elev_df["elevation_m_open_meteo"].notna().sum()) if elev_df is not None else 0

    evidence_adequate = (n_chm_ok >= 100) or (n_elev_ok >= 500)
    report = {
        "scope": "national_entire_kingdom",
        "asir_only": False,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_su_with_coords": int(len(su)),
        "n_regions": n_regions,
        "products": [
            {
                "name": CHM_PRODUCT,
                "role": "wall_to_wall_canopy_height_alternative_to_GEDI_footprints",
                "citation": CHM_CITATION,
                "n_sampled": int(len(chm_df)) if chm_df is not None else 0,
                "n_sample_ok": n_chm_ok,
                "path": str(chm_path) if chm_path.exists() else None,
            },
            {
                "name": "OpenTopoData_SRTM30m",
                "role": "wall_to_wall_terrain_covariate",
                "citation": (
                    elev_df["elevation_source"].iloc[0]
                    if elev_df is not None and "elevation_source" in elev_df.columns and len(elev_df)
                    else OPEN_METEO_CITATION
                ),
                "n_sampled": int(len(elev_df)) if elev_df is not None else 0,
                "n_sample_ok": n_elev_ok,
                "path": str(elev_path) if elev_path.exists() else None,
            },
        ],
        "gedi_footprints": {
            "required_for_national_evidence": False,
            "note": "GEDI is footprint-based and sparse; national wall-to-wall evidence uses Meta CHMv2 + elevation.",
        },
        "field_overwrite": False,
        "imputation": "OFF",
        "evidence_adequate": evidence_adequate,
        "disparity": disp_serializable,
    }
    (out_root / "logs" / "national_remote_height_evidence.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (out_root / "audit" / "lidar_evidence_gate.json").write_text(
        json.dumps(
            {
                "step": 15,
                "scope": "national_entire_kingdom",
                "product": "Meta_CHMv2 + Open-Meteo elevation (national alternatives to GEDI)",
                "evidence_adequate": evidence_adequate,
                "found_paths": [p["path"] for p in report["products"] if p.get("path")],
                "imputation": "OFF",
                "field_overwrite": False,
                "n_chm_ok": n_chm_ok,
                "n_elev_ok": n_elev_ok,
                "n_regions": n_regions,
                "log": str(out_root / "logs" / "national_remote_height_evidence.json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report
