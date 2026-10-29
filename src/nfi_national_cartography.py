# -*- coding: utf-8 -*-
"""Scientific cartographic helpers: Voronoi influence polygons and hexbin surfaces.

Point samples remain authoritative. Voronoi (Thiessen) polygons assign each
location to the nearest SU; hexbins summarise mean/count in equal-area tiles.
Both are standard exploratory cartography when a complete SU area frame is absent.

References:
  Okabe, A., Boots, B., Sugihara, K., Chiu, S.N. (2000). Spatial Tessellations:
  Concepts and Applications of Voronoi Diagrams. Wiley.
  Carr, D.B., Olsen, A.R., White, D. (1992). Hexagon mosaic maps for display of
  univariate and bivariate geographical data. Cartography and Geographic
  Information Systems 19(4): 228-236.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _finite_xy(df: pd.DataFrame) -> pd.DataFrame:
    use = df.loc[df["lon_validated"].notna() & df["lat_validated"].notna()].copy()
    use["lon_validated"] = pd.to_numeric(use["lon_validated"], errors="coerce")
    use["lat_validated"] = pd.to_numeric(use["lat_validated"], errors="coerce")
    return use.dropna(subset=["lon_validated", "lat_validated"])


def _prop_json_safe(row: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in {"geometry"}:
            continue
        if pd.isna(v):
            out[k] = None
        elif isinstance(v, (np.bool_, bool)):
            out[k] = bool(v)
        elif isinstance(v, (np.integer, int)):
            out[k] = int(v)
        elif isinstance(v, (np.floating, float)):
            out[k] = float(v)
        else:
            out[k] = str(v)
    return out


def build_voronoi_geojson(themes_df: pd.DataFrame, *, max_cells: int = 4500) -> dict[str, Any]:
    """Thiessen polygons for SU points, clipped to a padded bounding box."""
    from shapely.geometry import MultiPoint, Point, box, mapping
    from shapely.ops import voronoi_diagram

    use = _finite_xy(themes_df)
    if len(use) < 4:
        return {"type": "FeatureCollection", "features": []}
    if len(use) > max_cells:
        use = use.sample(n=max_cells, random_state=42)

    coords = use[["lon_validated", "lat_validated"]].to_numpy(dtype=float)
    minx, miny = coords.min(axis=0)
    maxx, maxy = coords.max(axis=0)
    pad = 0.6
    bbox = box(minx - pad, miny - pad, maxx + pad, maxy + pad)
    mp = MultiPoint([Point(xy) for xy in coords])
    try:
        vd = voronoi_diagram(mp, envelope=bbox)
    except Exception:
        return {"type": "FeatureCollection", "features": []}

    su_xy = {
        str(uid): (float(xy[0]), float(xy[1]))
        for uid, xy in zip(use["SU_UID"].astype(str), coords)
    }
    props_by_uid = {
        str(r["SU_UID"]): _prop_json_safe(r)
        for _, r in use.iterrows()
    }

    features: list[dict] = []
    for poly in vd.geoms:
        if poly.is_empty:
            continue
        clipped = poly.intersection(bbox)
        if clipped.is_empty:
            continue
        c = clipped.centroid
        # nearest SU by squared distance
        best_uid, best_d = None, float("inf")
        for uid, (x, y) in su_xy.items():
            d = (c.x - x) ** 2 + (c.y - y) ** 2
            if d < best_d:
                best_d, best_uid = d, uid
        if best_uid is None:
            continue
        g = clipped.simplify(0.003, preserve_topology=True)
        if g.is_empty:
            continue
        geom = mapping(g)
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props_by_uid.get(best_uid, {"SU_UID": best_uid}),
        })
    return {"type": "FeatureCollection", "features": features}


def build_hex_geojson(
    themes_df: pd.DataFrame,
    value_col: str | None,
    *,
    gridsize: int = 28,
) -> dict[str, Any]:
    """Equal-area-style hex tiles coloured by count or mean of value_col."""
    use = _finite_xy(themes_df)
    if len(use) < 10:
        return {"type": "FeatureCollection", "features": []}

    x = use["lon_validated"].to_numpy(dtype=float)
    y = use["lat_validated"].to_numpy(dtype=float)
    if value_col and value_col in use.columns:
        C = pd.to_numeric(use[value_col], errors="coerce").to_numpy(dtype=float)
        reduce = np.nanmean
    else:
        C = np.ones(len(use), dtype=float)
        reduce = np.nansum

    # Use matplotlib hexbin internals via a throwaway axes
    fig, ax = plt.subplots(figsize=(2, 2))
    hb = ax.hexbin(x, y, C=C, reduce_C_function=reduce, gridsize=gridsize, mincnt=1)
    offsets = hb.get_offsets()
    values = hb.get_array()
    # reconstruct hex vertices from collection
    coll = hb
    paths = coll.get_paths()
    # After hexbin, paths[0] is the unit hex; offsets place them
    if not len(paths):
        plt.close(fig)
        return {"type": "FeatureCollection", "features": []}
    unit = paths[0].vertices  # closed ring in data units relative to offset
    features = []
    for (ox, oy), val in zip(offsets, values):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        ring = [[float(ox + vx), float(oy + vy)] for vx, vy in unit]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "hex_value": float(val),
                "value_col": value_col or "count",
                "n_hint": "hex aggregate",
            },
        })
    plt.close(fig)
    return {"type": "FeatureCollection", "features": features}


def write_hexbin_maps(
    themes_df: pd.DataFrame,
    out_dir: Path,
    specs: list[tuple[str, str, str]],
) -> dict[str, Path]:
    """Static hexbin maps: (theme_id, value_col, title)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    use = _finite_xy(themes_df)
    paths: dict[str, Path] = {}
    for theme_id, value_col, title in specs:
        if value_col not in use.columns:
            continue
        vals = pd.to_numeric(use[value_col], errors="coerce")
        m = vals.notna()
        if m.sum() < 10:
            continue
        fig, ax = plt.subplots(figsize=(9, 8), dpi=130)
        hb = ax.hexbin(
            use.loc[m, "lon_validated"],
            use.loc[m, "lat_validated"],
            C=vals[m],
            reduce_C_function=np.nanmean,
            gridsize=35,
            cmap="YlGnBu",
            mincnt=1,
            linewidths=0.15,
            edgecolors="#ffffff",
        )
        cb = plt.colorbar(hb, ax=ax)
        cb.set_label(f"hex mean of {value_col}")
        ax.scatter(
            use.loc[m, "lon_validated"], use.loc[m, "lat_validated"],
            s=2, c="#222222", alpha=0.15, zorder=3,
        )
        ax.set_title(title + " (hexbin mean + points)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        p = out_dir / f"hexbin_{theme_id}.png"
        fig.savefig(p, dpi=160)
        plt.close(fig)
        paths[theme_id] = p
    return paths


def write_voronoi_static_map(
    themes_df: pd.DataFrame,
    value_col: str,
    title: str,
    out_path: Path,
    kind: str = "continuous",
) -> Path | None:
    """Static choropleth of Voronoi cells for one attribute."""
    try:
        import geopandas as gpd
    except Exception:
        return None
    gj = build_voronoi_geojson(themes_df)
    if not gj["features"]:
        return None
    gdf = gpd.GeoDataFrame.from_features(gj, crs="EPSG:4326")
    if value_col not in gdf.columns:
        return None
    fig, ax = plt.subplots(figsize=(9, 8), dpi=130)
    if kind == "continuous":
        gdf.plot(
            column=value_col, cmap="YlGnBu", legend=True, ax=ax,
            edgecolor="white", linewidth=0.15, missing_kwds={"color": "#eeeeee"},
        )
    else:
        gdf.plot(
            column=value_col, cmap="tab20", legend=False, ax=ax,
            edgecolor="white", linewidth=0.15, categorical=True,
        )
    pts = _finite_xy(themes_df)
    ax.scatter(pts["lon_validated"], pts["lat_validated"], s=3, c="#111111", alpha=0.25, zorder=5)
    ax.set_title(title + " (Voronoi / Thiessen + points)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def write_cartographic_suite(themes_df: pd.DataFrame, out_root: Path) -> dict[str, Any]:
    """Write Voronoi GeoJSON, hex PNGs, and selected Voronoi static maps."""
    out_root = Path(out_root)
    carto = out_root / "maps" / "cartography"
    carto.mkdir(parents=True, exist_ok=True)
    vor = build_voronoi_geojson(themes_df)
    vor_path = carto / "su_voronoi_thiessen.geojson"
    import json
    vor_path.write_text(json.dumps(vor), encoding="utf-8")

    hex_specs = [
        ("sum_carbon", "sum_tree_carbon_mg", "Tree carbon (provisional)"),
        ("sum_agb", "sum_tree_agb_mg", "Tree AGB (provisional)"),
        ("mean_dbh", "mean_dbh_cm", "Mean DBH"),
        ("tree_count", "n_trees", "Tree count"),
        ("fire_presence", "has_fire", "Fire presence (0/1 mean)"),
    ]
    # binary as 0/1 for hex mean
    use = themes_df.copy()
    if "has_fire" in use.columns:
        use["has_fire"] = use["has_fire"].fillna(False).astype(bool).astype(int)
    hex_paths = write_hexbin_maps(use, carto / "hexbin", hex_specs)

    vor_pngs: dict[str, Path] = {}
    for theme_id, col, title, kind in [
        ("sum_carbon", "sum_tree_carbon_mg", "Tree carbon (provisional)", "continuous"),
        ("mean_dbh", "mean_dbh_cm", "Mean DBH", "continuous"),
        ("fire_presence", "has_fire", "Fire evidence", "categorical"),
        ("causative_agent", "causative_agent_mode", "Modal causative agent", "categorical"),
        ("tree_condition", "tree_condition_mode", "Modal tree condition", "categorical"),
    ]:
        if col not in themes_df.columns:
            continue
        p = write_voronoi_static_map(
            themes_df, col, title, carto / f"voronoi_{theme_id}.png", kind=kind,
        )
        if p:
            vor_pngs[theme_id] = p

    return {
        "voronoi_geojson": vor_path,
        "n_voronoi_cells": len(vor.get("features") or []),
        "hexbin_png": {k: str(v) for k, v in hex_paths.items()},
        "voronoi_png": {k: str(v) for k, v in vor_pngs.items()},
        "voronoi_fc": vor,
    }
