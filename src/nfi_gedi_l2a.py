# -*- coding: utf-8 -*-
"""
GEDI L2A (GEDI02_A) footprint helpers for NFI field-height comparison.

Primary LiDAR product for this project: NASA GEDI Level-2A Elevation and Height
Metrics (GEDI02_A). Meta CHM remains optional fallback only.

Typical workflow
----------------
1. Place exported footprints at ``H:/3.NFI/GEDIImages/gedi_l2a_footprints.parquet``
   (or CSV / GeoPackage), **or** point ``raw_dir`` at downloaded ``*.h5`` granules
   under ``H:/3.NFI/GEDIImages/raw``.
2. ``load_gedi_l2a`` → standardize columns → quality filter.
3. Spatially join nearest quality shots to NFI plots (≤30 m default).
4. Compare plot-level upper-canopy height (e.g. P95 of field trees) to RH98.
5. Optional interactive 3D: field stems vs GEDI L2A RH cylinders at footprint XY.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

GEDI_L2A_SHORT_NAME = "GEDI02_A"
GEDI_L2A_VERSION = "002"  # earthdata often lists 002; notebook may override
GEDI_PRODUCT_LABEL = "GEDI L2A (GEDI02_A) footprint RH metrics"

# Default on-disk storage (downloads + parsed footprint table)
GEDI_STORAGE_ROOT = Path(r"H:\3.NFI\GEDIImages")
GEDI_DEFAULT_RAW_DIR = GEDI_STORAGE_ROOT / "raw"
GEDI_DEFAULT_TABLE = GEDI_STORAGE_ROOT / "gedi_l2a_footprints.parquet"

# Beams commonly present in GEDI02_A HDF5
_GEDI_BEAMS = (
    "BEAM0000", "BEAM0001", "BEAM0010", "BEAM0011",
    "BEAM0101", "BEAM0110", "BEAM1000", "BEAM1011",
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def find_column(df: pd.DataFrame, names: list[str]) -> str | None:
    norms = {_norm(c): c for c in df.columns}
    for n in names:
        if _norm(n) in norms:
            return norms[_norm(n)]
    for c in df.columns:
        nc = _norm(c)
        if any(_norm(n) in nc for n in names):
            return c
    return None


def standardize_gedi_l2a(g: pd.DataFrame) -> pd.DataFrame:
    """Map common GEDI L2A / export names into a stable comparison schema."""
    candidates = {
        "shot_number": ["shot_number", "shotnumber", "shot_number_"],
        "latitude": ["lat_lowestmode", "latitude", "lat"],
        "longitude": ["lon_lowestmode", "longitude", "lon"],
        "elev_ground": ["elev_lowestmode", "elevation_lowestmode", "elev_ground"],
        "elev_highest": ["elev_highestreturn", "elevation_highestreturn", "elev_highest"],
        "rh95": ["rh95", "rh_95"],
        "rh98": ["rh98", "rh_98"],
        "rh100": ["rh100", "rh_100"],
        "quality_flag": ["quality_flag", "qualityflag"],
        "degrade_flag": ["degrade_flag", "degradeflag"],
        "sensitivity": ["sensitivity"],
        "delta_time": ["delta_time", "deltatime"],
        "beam": ["beam", "beamname", "BEAM"],
    }
    mapping = {}
    for std, opts in candidates.items():
        c = find_column(g, opts)
        if c and c != std:
            mapping[c] = std
    out = g.rename(columns=mapping).copy()
    if "latitude" not in out.columns or "longitude" not in out.columns:
        raise ValueError("GEDI L2A table lacks latitude/longitude (lat_lowestmode / lon_lowestmode).")
    for c in [
        "latitude", "longitude", "elev_ground", "elev_highest",
        "rh95", "rh98", "rh100", "sensitivity", "quality_flag", "degrade_flag",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out["lidar_product"] = GEDI_PRODUCT_LABEL
    return out


def quality_filter_gedi_l2a(
    g: pd.DataFrame,
    *,
    sensitivity_min: float = 0.90,
) -> pd.DataFrame:
    """Standard L2A quality gate: quality_flag==1, degrade_flag==0, sensitivity threshold."""
    keep = pd.Series(True, index=g.index)
    reasons = pd.Series("", index=g.index, dtype="string")
    if "quality_flag" in g.columns:
        bad = g["quality_flag"] != 1
        keep &= ~bad
        reasons.loc[bad] += "quality_flag;"
    if "degrade_flag" in g.columns:
        bad = g["degrade_flag"].fillna(1) != 0
        keep &= ~bad
        reasons.loc[bad] += "degrade_flag;"
    if "sensitivity" in g.columns:
        bad = g["sensitivity"] < float(sensitivity_min)
        keep &= ~bad
        reasons.loc[bad] += "low_sensitivity;"
    badxy = g["latitude"].isna() | g["longitude"].isna()
    keep &= ~badxy
    reasons.loc[badxy] += "bad_coordinate;"
    q = g.copy()
    q["gedi_quality_keep"] = keep
    q["gedi_quality_reason"] = reasons
    return q


def extract_gedi_l2a_h5(
    h5_path: Path,
    *,
    rh_indices: tuple[int, ...] = (95, 98, 100),
) -> pd.DataFrame:
    """
    Read one GEDI02_A HDF5 granule into a flat footprint table.

    RH metrics are taken from ``rh`` arrays at the requested percentiles
    (GEDI L2A stores RH0…RH100).
    """
    import h5py

    h5_path = Path(h5_path)
    rows: list[dict] = []
    with h5py.File(h5_path, "r") as f:
        beams = [b for b in _GEDI_BEAMS if b in f]
        if not beams:
            beams = [k for k in f.keys() if str(k).startswith("BEAM")]
        for beam in beams:
            g = f[beam]
            try:
                lat = np.asarray(g["lat_lowestmode"][:], dtype=float)
                lon = np.asarray(g["lon_lowestmode"][:], dtype=float)
            except KeyError:
                continue
            n = len(lat)
            rec = {
                "beam": np.full(n, beam),
                "latitude": lat,
                "longitude": lon,
            }
            for src, dst in [
                ("elev_lowestmode", "elev_ground"),
                ("elev_highestreturn", "elev_highest"),
                ("sensitivity", "sensitivity"),
                ("quality_flag", "quality_flag"),
                ("degrade_flag", "degrade_flag"),
                ("shot_number", "shot_number"),
                ("delta_time", "delta_time"),
            ]:
                if src in g:
                    rec[dst] = np.asarray(g[src][:], dtype=float)
            if "rh" in g:
                rh = np.asarray(g["rh"][:], dtype=float)
                # rh shape is typically (n_shots, 101)
                if rh.ndim == 2 and rh.shape[0] == n:
                    for idx in rh_indices:
                        if 0 <= idx < rh.shape[1]:
                            rec[f"rh{idx}"] = rh[:, idx]
                elif rh.ndim == 2 and rh.shape[1] == n:
                    for idx in rh_indices:
                        if 0 <= idx < rh.shape[0]:
                            rec[f"rh{idx}"] = rh[idx, :]
            # build row-wise without huge intermediate if possible
            df_beam = pd.DataFrame(rec)
            df_beam["source_granule"] = h5_path.name
            rows.append(df_beam)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def load_gedi_l2a_table(path: Path) -> pd.DataFrame | None:
    """Load a pre-exported GEDI L2A footprint table (parquet/csv/vector)."""
    path = Path(path)
    if not path.exists():
        return None
    suf = path.suffix.lower()
    if suf == ".parquet":
        g = pd.read_parquet(path)
    elif suf == ".csv":
        g = pd.read_csv(path)
    elif suf in {".gpkg", ".geojson", ".shp"}:
        import geopandas as gpd

        gg = gpd.read_file(path)
        if gg.crs is None:
            raise ValueError("GEDI vector file has no CRS.")
        gg = gg.to_crs(4326)
        g = pd.DataFrame(gg.drop(columns="geometry", errors="ignore"))
        g["longitude"] = gg.geometry.x.values
        g["latitude"] = gg.geometry.y.values
    else:
        raise ValueError(f"Unsupported GEDI L2A table format: {path.suffix}")
    return g


def load_gedi_l2a(
    *,
    table_path: Path | None = None,
    raw_dir: Path | None = None,
    sensitivity_min: float = 0.90,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict:
    """
    Load + standardize + quality-filter GEDI L2A footprints.

    Parameters
    ----------
    table_path : exported footprints (preferred for notebook speed)
    raw_dir : folder of GEDI02_A ``*.h5`` granules (parsed if table missing)
    bbox : optional (west, south, east, north) clip in WGS84
    """
    raw = None
    source = None
    if table_path and Path(table_path).exists():
        raw = load_gedi_l2a_table(Path(table_path))
        source = str(Path(table_path).resolve())
    elif raw_dir and Path(raw_dir).exists():
        parts = []
        for h5 in sorted(Path(raw_dir).glob("*.h5")):
            try:
                parts.append(extract_gedi_l2a_h5(h5))
            except Exception as e:
                print(f"  skip {h5.name}: {e}")
        if parts:
            raw = pd.concat(parts, ignore_index=True)
            source = str(Path(raw_dir).resolve())
    if raw is None or len(raw) == 0:
        return {
            "status": "MISSING",
            "product": GEDI_PRODUCT_LABEL,
            "message": (
                "No GEDI L2A footprints found. Place an export at "
                f"{GEDI_DEFAULT_TABLE} or download GEDI02_A "
                f"HDF5 granules into {GEDI_DEFAULT_RAW_DIR} and re-run."
            ),
            "all": pd.DataFrame(),
            "filtered": pd.DataFrame(),
            "source": None,
        }

    std = standardize_gedi_l2a(raw)
    if bbox is not None:
        w, s, e, n = bbox
        std = std.loc[
            std["longitude"].between(w, e) & std["latitude"].between(s, n)
        ].copy()
    q = quality_filter_gedi_l2a(std, sensitivity_min=sensitivity_min)
    filt = q.loc[q["gedi_quality_keep"]].copy()
    return {
        "status": "OK",
        "product": GEDI_PRODUCT_LABEL,
        "source": source,
        "all": q,
        "filtered": filt,
        "n_all": int(len(q)),
        "n_keep": int(len(filt)),
        "message": f"GEDI L2A loaded: {len(filt):,} quality shots of {len(q):,}.",
    }


def plot_field_vs_gedi_l2a_3d(
    *,
    trees: pd.DataFrame,
    gedi_filtered: pd.DataFrame,
    plot_df: pd.DataFrame | None = None,
    out_html: Path,
    max_distance_m: float = 60.0,
    height_col: str = "tree_height",
    gedi_rh_col: str = "rh98",
    max_trees: int = 400,
    max_gedi: int = 400,
) -> dict:
    """
    Interactive 3D scene: field tree stems vs nearby GEDI L2A RH98 spikes.

    Coordinates are projected to a local metres plane (approx. equirectangular
    around the plot cluster centroid) so the vertical axis is height in metres.
    """
    import plotly.graph_objects as go

    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)

    t = trees.copy()
    if height_col not in t.columns:
        return {"status": "SKIPPED", "reason": f"missing {height_col}"}
    # attach XY
    for c in ["lat_validated", "lon_validated"]:
        if c not in t.columns and plot_df is not None and "PLOT_UID" in t.columns and c in plot_df.columns:
            t = t.merge(plot_df[["PLOT_UID", c]].drop_duplicates("PLOT_UID"), on="PLOT_UID", how="left")
    if "lat_validated" not in t.columns or "lon_validated" not in t.columns:
        return {"status": "SKIPPED", "reason": "trees lack lat_validated/lon_validated"}

    t["_h"] = pd.to_numeric(t[height_col], errors="coerce")
    t["_lat"] = pd.to_numeric(t["lat_validated"], errors="coerce")
    t["_lon"] = pd.to_numeric(t["lon_validated"], errors="coerce")
    t = t.dropna(subset=["_h", "_lat", "_lon"])
    t = t.loc[(t["_h"] > 0) & (t["_h"] < 80)]
    if len(t) == 0:
        return {"status": "SKIPPED", "reason": "no valid field heights"}
    if len(t) > max_trees:
        t = t.sample(max_trees, random_state=42)

    g = gedi_filtered.copy()
    if gedi_rh_col not in g.columns:
        return {"status": "SKIPPED", "reason": f"GEDI missing {gedi_rh_col}"}
    g["_rh"] = pd.to_numeric(g[gedi_rh_col], errors="coerce")
    g["_lat"] = pd.to_numeric(g["latitude"], errors="coerce")
    g["_lon"] = pd.to_numeric(g["longitude"], errors="coerce")
    g = g.dropna(subset=["_rh", "_lat", "_lon"])
    g = g.loc[g["_rh"] > 0]
    if len(g) == 0:
        return {"status": "SKIPPED", "reason": "no valid GEDI RH"}

    # restrict GEDI to neighbourhood of field trees
    lat0 = float(t["_lat"].mean())
    lon0 = float(t["_lon"].mean())
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat0))

    def _xy(lat, lon):
        x = (lon - lon0) * m_per_deg_lon
        y = (lat - lat0) * m_per_deg_lat
        return x, y

    tx, ty = _xy(t["_lat"].to_numpy(), t["_lon"].to_numpy())
    gx, gy = _xy(g["_lat"].to_numpy(), g["_lon"].to_numpy())
    # keep GEDI within max_distance of any retained tree (coarse bbox then exact)
    pad = max_distance_m
    mask = (
        (gx >= tx.min() - pad) & (gx <= tx.max() + pad)
        & (gy >= ty.min() - pad) & (gy <= ty.max() + pad)
    )
    g = g.loc[mask].copy()
    gx, gy = gx[mask], gy[mask]
    if len(g) > max_gedi:
        idx = np.random.default_rng(42).choice(len(g), size=max_gedi, replace=False)
        g = g.iloc[idx]
        gx, gy = gx[idx], gy[idx]

    # Build stem segments for field trees (ground z=0 → height)
    stem_x, stem_y, stem_z = [], [], []
    for x, y, h in zip(tx, ty, t["_h"].to_numpy()):
        stem_x += [x, x, None]
        stem_y += [y, y, None]
        stem_z += [0.0, float(h), None]

    gedi_x, gedi_y, gedi_z = [], [], []
    for x, y, h in zip(gx, gy, g["_rh"].to_numpy()):
        gedi_x += [x, x, None]
        gedi_y += [y, y, None]
        gedi_z += [0.0, float(h), None]

    fig = go.Figure()
    fig.add_trace(go.Scatter3d(
        x=stem_x, y=stem_y, z=stem_z, mode="lines",
        line=dict(color="#166534", width=5),
        name="Field tree height (NFI)",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter3d(
        x=tx, y=ty, z=t["_h"].to_numpy(), mode="markers",
        marker=dict(size=3, color="#16a34a"),
        name="Field treetop",
        text=[f"h={h:.1f} m" for h in t["_h"]],
        hovertemplate="%{text}<extra>NFI</extra>",
    ))
    fig.add_trace(go.Scatter3d(
        x=gedi_x, y=gedi_y, z=gedi_z, mode="lines",
        line=dict(color="#c2410c", width=4),
        name=f"GEDI L2A {gedi_rh_col.upper()} footprint",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter3d(
        x=gx, y=gy, z=g["_rh"].to_numpy(), mode="markers",
        marker=dict(size=4, color="#ea580c", symbol="diamond"),
        name=f"GEDI {gedi_rh_col.upper()}",
        text=[f"RH={h:.1f} m" for h in g["_rh"]],
        hovertemplate="%{text}<extra>GEDI L2A</extra>",
    ))
    # ground plane hint
    fig.update_layout(
        title=(
            "Field tree heights vs GEDI L2A footprints (local metres plane)<br>"
            "<sup>Green = NFI stems · Orange = GEDI L2A RH · support mismatch is explicit</sup>"
        ),
        scene=dict(
            xaxis_title="East (m from cluster centre)",
            yaxis_title="North (m from cluster centre)",
            zaxis_title="Height (m)",
            aspectmode="data",
        ),
        margin=dict(l=0, r=0, t=60, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        template="plotly_white",
    )
    fig.write_html(str(out_html), include_plotlyjs="cdn")
    return {
        "status": "OK",
        "path": str(out_html),
        "n_trees": int(len(t)),
        "n_gedi": int(len(g)),
        "product": GEDI_PRODUCT_LABEL,
    }


def download_gedi_l2a_easy(
    bbox: tuple[float, float, float, float],
    *,
    out_table: Path = GEDI_DEFAULT_TABLE,
    raw_dir: Path = GEDI_DEFAULT_RAW_DIR,
    max_granules: int = 8,
    temporal: tuple[str, str] | None = ("2019-04-01", "2023-12-31"),
    force: bool = False,
    allow_interactive_login: bool = False,
    download_timeout_s: int = 1800,
) -> dict:
    """
    Easiest path: NASA Earthdata login → search GEDI02_A → download a few granules
    → parse beams to a footprint parquet for Section 15.

    Parameters
    ----------
    bbox : (west, south, east, north) in WGS84
    max_granules : keep the first download small (each L2A file is large)
    temporal : optional (start, end) ISO dates to shrink the search
    force : re-download / rebuild even if out_table already exists
    allow_interactive_login : if False (default), never prompt for username/password
        in a notebook kernel (that hang is what makes the cell look "running" overnight).
        Use netrc / EARTHDATA_USERNAME+PASSWORD, or set True only in an interactive terminal.
    download_timeout_s : soft guidance only; earthaccess itself has limited timeout control

    Returns
    -------
    dict with status, paths, n_rows, n_granules, message
    """
    out_table = Path(out_table)
    raw_dir = Path(raw_dir)
    out_table.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    if out_table.exists() and not force:
        try:
            n = len(pd.read_parquet(out_table))
        except Exception:
            n = -1
        return {
            "status": "EXISTS",
            "table": str(out_table.resolve()),
            "raw_dir": str(raw_dir.resolve()),
            "n_rows": int(n) if n >= 0 else None,
            "n_granules": len(list(raw_dir.glob("*.h5"))),
            "message": f"GEDI L2A table already present: {out_table} (set force=True to rebuild).",
        }

    try:
        import earthaccess
    except ImportError:
        return {
            "status": "NEED_PACKAGE",
            "message": "Install earthaccess first:  python -m pip install earthaccess",
        }

    # Login - NEVER block on interactive prompts unless explicitly allowed.
    # Interactive login inside Jupyter is the usual cause of overnight "running" cells.
    auth = None
    login_errors: list[str] = []
    for strategy in ("netrc", "environment"):
        try:
            auth = earthaccess.login(strategy=strategy, persist=True)
            if auth:
                print(f"  Earthdata login OK via {strategy}")
                break
        except Exception as e:
            login_errors.append(f"{strategy}: {e}")
            auth = None

    if not auth and allow_interactive_login:
        try:
            auth = earthaccess.login(strategy="interactive", persist=True)
        except Exception as e:
            login_errors.append(f"interactive: {e}")
            auth = None

    if not auth:
        hint = (
            "NASA Earthdata credentials are required (free: https://urs.earthdata.nasa.gov/).\n"
            "Do ONE of the following, then re-run:\n"
            "  1) Terminal (recommended):  python download_gedi_l2a.py\n"
            "     (will prompt once and save credentials)\n"
            "  2) Set env vars EARTHDATA_USERNAME and EARTHDATA_PASSWORD, then re-run Section 15\n"
            "  3) In a notebook cell (once): import earthaccess; "
            "earthaccess.login(strategy='interactive', persist=True)\n"
            "Notebook auto-download will NOT prompt interactively (avoids overnight hangs)."
        )
        if login_errors:
            hint += "\nDetails: " + " | ".join(login_errors[:3])
        return {"status": "NEED_LOGIN", "message": hint}

    west, south, east, north = [float(x) for x in bbox]
    search_kw: dict = {
        "short_name": GEDI_L2A_SHORT_NAME,
        "bounding_box": (west, south, east, north),
        "count": max(50, max_granules * 5),
    }
    if temporal:
        search_kw["temporal"] = (temporal[0], temporal[1])

    print("=" * 64)
    print("GEDI L2A easy download")
    print("=" * 64)
    print(f"  product : {GEDI_L2A_SHORT_NAME}")
    print(f"  bbox    : {west:.4f}, {south:.4f}, {east:.4f}, {north:.4f}")
    if temporal:
        print(f"  temporal: {temporal[0]} → {temporal[1]}")
    print(f"  cap     : {max_granules} granules  (each file can be several GB)")
    print(f"  note    : download may take a long time; prefer max_granules=2 for a first test")

    try:
        results = earthaccess.search_data(**search_kw)
    except Exception as e:
        return {"status": "SEARCH_FAILED", "message": f"CMR search failed: {e}"}

    if not results:
        return {
            "status": "EMPTY",
            "message": "No GEDI02_A granules found for this bbox/time window. Widen temporal or bbox.",
        }

    # Prefer granules that already look on-orbit / available; keep list short
    to_get = list(results)[: int(max_granules)]
    print(f"  found   : {len(results)} granules → downloading {len(to_get)}")

    try:
        # earthaccess download can take hours for L2A; print before/after so notebooks show progress
        import time as _time
        t0 = _time.time()
        print(f"  download start ({_time.strftime('%H:%M:%S')}) …")
        files = earthaccess.download(to_get, local_path=str(raw_dir))
        print(f"  download done in {(_time.time() - t0) / 60:.1f} min")
        _ = download_timeout_s  # reserved for future hard timeout wrapper
    except Exception as e:
        return {
            "status": "DOWNLOAD_FAILED",
            "message": (
                f"Download failed: {e}\n"
                "Confirm Earthdata account is linked to LP DAAC / NASA apps and retry."
            ),
            "n_search": len(results),
        }

    h5_files = sorted(raw_dir.glob("*.h5"))
    if not h5_files:
        # earthaccess may return paths as strings
        extra = []
        for f in files or []:
            p = Path(str(f))
            if p.suffix.lower() == ".h5" and p.exists():
                extra.append(p)
        h5_files = sorted(set(extra)) or h5_files

    if not h5_files:
        return {
            "status": "NO_H5",
            "message": f"Download finished but no *.h5 under {raw_dir}",
            "n_search": len(results),
        }

    parts = []
    for h5 in h5_files:
        try:
            print(f"  parsing : {h5.name} ({h5.stat().st_size / 1e9:.2f} GB) …")
            part = extract_gedi_l2a_h5(h5)
            if len(part):
                # clip to bbox early to shrink parquet
                part = part.loc[
                    part["longitude"].between(west, east)
                    & part["latitude"].between(south, north)
                ]
                parts.append(part)
                print(f"  parsed  : {h5.name} → {len(part):,} shots in bbox")
        except Exception as e:
            print(f"  skip    : {h5.name} ({e})")

    if not parts:
        return {
            "status": "PARSE_EMPTY",
            "message": "HDF5 files present but no footprints parsed inside the bbox.",
            "raw_dir": str(raw_dir.resolve()),
            "n_granules": len(h5_files),
        }

    table = pd.concat(parts, ignore_index=True)
    # drop exact duplicate shots if any
    if "shot_number" in table.columns:
        table = table.drop_duplicates(subset=["shot_number", "beam"], keep="first")
    table.to_parquet(out_table, index=False)
    print(f"  wrote   : {out_table} ({len(table):,} rows)")
    print("=" * 64)
    return {
        "status": "OK",
        "table": str(out_table.resolve()),
        "raw_dir": str(raw_dir.resolve()),
        "n_rows": int(len(table)),
        "n_granules": len(h5_files),
        "n_search": len(results),
        "message": (
            f"Downloaded {len(h5_files)} GEDI L2A granules and wrote "
            f"{len(table):,} footprints to {out_table.name}."
        ),
    }


def ensure_gedi_l2a_table(
    bbox: tuple[float, float, float, float],
    *,
    table_path: Path = GEDI_DEFAULT_TABLE,
    raw_dir: Path = GEDI_DEFAULT_RAW_DIR,
    max_granules: int = 8,
    auto_download: bool = True,
) -> dict:
    """
    Return a ready footprint table path. If missing and auto_download=True,
    run ``download_gedi_l2a_easy``.
    """
    table_path = Path(table_path)
    if table_path.exists():
        return {
            "status": "OK",
            "table": str(table_path.resolve()),
            "message": f"Using existing {table_path}",
            "downloaded": False,
        }
    if not auto_download:
        return {
            "status": "MISSING",
            "table": str(table_path),
            "message": "GEDI L2A table missing and auto_download=False.",
            "downloaded": False,
        }
    dl = download_gedi_l2a_easy(
        bbox,
        out_table=table_path,
        raw_dir=raw_dir,
        max_granules=max_granules,
        allow_interactive_login=False,
    )
    dl["downloaded"] = dl.get("status") == "OK"
    return dl
