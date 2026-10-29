# -*- coding: utf-8 -*-
"""KSA country / province boundaries for national map framing.

Uses Admin shapefiles (Country.shp, Provinces.shp). Maps are clipped or masked
to the national boundary and framed with free satellite basemap tiles
(Esri World Imagery / Google Satellite via contextily).

Province names are joined to NFI region labels via a documented alias table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# NFI SU master region_en -> Provinces.ADMIN_NA_1
REGION_TO_PROVINCE = {
    "Ar Riyad": "Ar Riyad",
    "Makkah Al Mukarramah": "Makkah Al Mukarramah",
    "Al Qaseem": "Al Qaseem",
    "Eastern Region": "Eastern Region",
    "Aseer": "Asir",
    "Asir": "Asir",
    "Tabuk": "Tabuk",
    "Hail": "Hail",
    "Northern Borders": "Northern Borders",
    "Jazan": "Jazan",
    "Najran": "Najran",
    "Al Bahah": "Al Baha",
    "Al Baha": "Al Baha",
    "Al Jawf": "Al Jawf",
    "Al Madinah Al Munawwarah": "Al Madinah Al Munawwarah",
}

ESRI_IMAGERY = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
GOOGLE_SAT = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"


def resolve_admin_dir(cfg: dict | None = None) -> Path:
    """Prefer config path, then project data/, then known workspace Admin folder."""
    candidates: list[Path] = []
    if cfg:
        gis = cfg.get("gis") or {}
        for key in ("admin_root", "country_admin_dir"):
            if gis.get(key):
                candidates.append(Path(gis[key]))
        paths = cfg.get("paths") or {}
        if paths.get("shapefiles_root"):
            candidates.append(Path(paths["shapefiles_root"]) / "Admin")
    # Relative to package / repo
    here = Path(__file__).resolve().parents[1]
    candidates.extend([
        here / "data" / "shapefile" / "Admin",
        Path(r"F:\1.KSA\31.WorkingGIS\shapefile\Admin"),
        Path("/content/drive/MyDrive/NFI/shapefile/Admin"),
    ])
    for c in candidates:
        if (c / "Country.shp").exists():
            return c
    raise FileNotFoundError(
        "Country.shp not found. Place Admin shapefiles under data/shapefile/Admin "
        "or set gis.admin_root in config.yaml."
    )


def load_country(admin_dir: Path | None = None, cfg: dict | None = None) -> gpd.GeoDataFrame:
    admin_dir = Path(admin_dir) if admin_dir else resolve_admin_dir(cfg)
    gdf = gpd.read_file(admin_dir / "Country.shp")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(4326)


def load_provinces(admin_dir: Path | None = None, cfg: dict | None = None) -> gpd.GeoDataFrame:
    admin_dir = Path(admin_dir) if admin_dir else resolve_admin_dir(cfg)
    gdf = gpd.read_file(admin_dir / "Provinces.shp")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    gdf = gdf.to_crs(4326)
    gdf["province_key"] = gdf["ADMIN_NA_1"].astype(str).str.strip()
    return gdf


def normalize_region_to_province(region: Any) -> str | None:
    if region is None or (isinstance(region, float) and np.isnan(region)):
        return None
    key = str(region).strip()
    return REGION_TO_PROVINCE.get(key, key)


def country_geojson(country: gpd.GeoDataFrame) -> dict:
    return country.__geo_interface__


def clip_points_to_country(df: pd.DataFrame, country: gpd.GeoDataFrame) -> pd.DataFrame:
    """Keep points that fall inside the national boundary."""
    use = df.loc[df["lon_validated"].notna() & df["lat_validated"].notna()].copy()
    if use.empty:
        return use
    pts = gpd.GeoDataFrame(
        use,
        geometry=gpd.points_from_xy(use["lon_validated"], use["lat_validated"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, country[["geometry"]], how="inner", predicate="within")
    return pd.DataFrame(joined.drop(columns=["geometry", "index_right"], errors="ignore"))


def add_satellite_basemap(ax, *, extent_gdf: gpd.GeoDataFrame, preferred: str = "esri") -> str:
    """Add free satellite tiles in Web Mercator; returns label used or empty."""
    try:
        import contextily as ctx
    except Exception:
        return ""
    web = extent_gdf.to_crs(3857)
    minx, miny, maxx, maxy = web.total_bounds
    pad_x = (maxx - minx) * 0.03
    pad_y = (maxy - miny) * 0.03
    ax.set_xlim(minx - pad_x, maxx + pad_x)
    ax.set_ylim(miny - pad_y, maxy + pad_y)
    sources = [ESRI_IMAGERY, GOOGLE_SAT] if preferred == "esri" else [GOOGLE_SAT, ESRI_IMAGERY]
    labels = ["Esri World Imagery", "Google Satellite"] if preferred == "esri" else ["Google Satellite", "Esri World Imagery"]
    for src, lab in zip(sources, labels):
        try:
            ctx.add_basemap(ax, source=src, attribution="Esri / Google", attribution_size=6, zoom="auto")
            return lab
        except Exception:
            continue
    return ""


def style_country_outline(ax, country_web: gpd.GeoDataFrame) -> None:
    country_web.boundary.plot(ax=ax, color="#f8fafc", linewidth=1.8, zorder=6)
    country_web.boundary.plot(ax=ax, color="#0f172a", linewidth=0.7, zorder=7)


def write_static_map_clipped(
    themes_df: pd.DataFrame,
    *,
    country: gpd.GeoDataFrame,
    value_col: str | None,
    title: str,
    out_path: Path,
    kind: str = "continuous",
    clip_points: bool = True,
) -> Path | None:
    """Point thematic map clipped to Country.shp with satellite basemap."""
    use = themes_df.copy()
    if clip_points:
        use = clip_points_to_country(use, country)
    use = use.loc[use["lon_validated"].notna() & use["lat_validated"].notna()]
    if value_col and value_col not in use.columns:
        return None
    if use.empty:
        return None

    pts = gpd.GeoDataFrame(
        use,
        geometry=gpd.points_from_xy(use["lon_validated"], use["lat_validated"]),
        crs="EPSG:4326",
    )
    fig, ax = plt.subplots(figsize=(8.5, 8.2), dpi=110)
    country_web = country.to_crs(3857)
    pts_web = pts.to_crs(3857)
    basemap = add_satellite_basemap(ax, extent_gdf=country)
    style_country_outline(ax, country_web)

    if kind == "binary":
        yes = pts_web[value_col].fillna(False).astype(bool) if value_col else pts_web.assign(**{value_col: False})[value_col]
        pts_web.loc[~yes].plot(ax=ax, markersize=8, color="#fb923c", alpha=0.75, edgecolor="white", linewidth=0.2, label="No", zorder=5)
        pts_web.loc[yes].plot(ax=ax, markersize=8, color="#22c55e", alpha=0.8, edgecolor="white", linewidth=0.2, label="Yes", zorder=5)
        ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    elif kind == "continuous":
        pts_web = pts_web.copy()
        pts_web["_val"] = pd.to_numeric(pts_web[value_col], errors="coerce")
        pts_web.plot(
            ax=ax, column="_val", cmap="YlGnBu", markersize=10, alpha=0.85,
            edgecolor="white", linewidth=0.15, legend=True, zorder=5,
            legend_kwds={"label": value_col, "shrink": 0.6},
        )
    elif kind == "categorical":
        pts_web.plot(
            ax=ax, column=value_col, cmap="tab20", categorical=True,
            markersize=9, alpha=0.85, edgecolor="white", linewidth=0.15, legend=False, zorder=5,
        )
    else:
        pts_web.plot(ax=ax, markersize=8, color="#38bdf8", alpha=0.8, edgecolor="white", linewidth=0.2, zorder=5)

    ax.set_axis_off()
    suffix = f" | {basemap}" if basemap else " | no basemap"
    ax.set_title(title + " (clipped to KSA Country.shp)" + suffix, fontsize=11, fontweight="bold")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    return out_path


def aggregate_by_province(themes_df: pd.DataFrame) -> pd.DataFrame:
    """Compute regional KPIs keyed to Provinces.ADMIN_NA_1."""
    df = themes_df.copy()
    df["province_key"] = df["region"].map(normalize_region_to_province)
    rows = []
    for key, g in df.groupby("province_key", dropna=False):
        if key is None or str(key).strip() == "" or str(key) == "nan":
            continue

        def pct(col: str) -> float | None:
            if col not in g.columns:
                return None
            s = g[col]
            if s.dtype == object:
                s = s.map(lambda x: str(x).lower() in {"true", "1", "yes"})
            return float(100.0 * s.fillna(False).astype(bool).mean())

        def mean_num(col: str) -> float | None:
            if col not in g.columns:
                return None
            s = pd.to_numeric(g[col], errors="coerce")
            return float(s.mean()) if s.notna().any() else None

        def sum_num(col: str) -> float | None:
            if col not in g.columns:
                return None
            s = pd.to_numeric(g[col], errors="coerce")
            return float(s.sum()) if s.notna().any() else None

        rows.append({
            "province_key": key,
            "n_su": int(len(g)),
            "tree_presence_pct": pct("has_tree_record"),
            "shrub_presence_pct": pct("has_shrub_record"),
            "fire_presence_pct": pct("has_fire"),
            "env_problem_pct": pct("has_env_problem"),
            "causative_agent_pct": pct("has_causative_agent"),
            "mean_dbh_cm": mean_num("mean_dbh_cm"),
            "mean_height_m": mean_num("mean_height_m"),
            "sum_tree_carbon_mg": sum_num("sum_tree_carbon_mg"),
            "sum_tree_agb_mg": sum_num("sum_tree_agb_mg"),
            "mean_n_trees": mean_num("n_trees"),
        })
    return pd.DataFrame(rows)


def write_regional_choropleths(
    themes_df: pd.DataFrame,
    provinces: gpd.GeoDataFrame,
    country: gpd.GeoDataFrame,
    out_dir: Path,
) -> dict[str, Path]:
    """Province polygons coloured by regional KPIs, framed by country + satellite."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    agg = aggregate_by_province(themes_df)
    gdf = provinces.merge(agg, on="province_key", how="left")
    specs = [
        ("n_su", "Number of SUs by province", "YlOrRd"),
        ("tree_presence_pct", "Tree presence % by province", "YlGn"),
        ("sum_tree_carbon_mg", "Provisional tree carbon sum (Mg) by province", "YlGnBu"),
        ("mean_dbh_cm", "Mean DBH (cm) by province", "PuBuGn"),
        ("fire_presence_pct", "Fire evidence % by province", "OrRd"),
        ("causative_agent_pct", "Causative agent recorded % by province", "Purples"),
    ]
    paths: dict[str, Path] = {}
    for col, title, cmap in specs:
        if col not in gdf.columns:
            continue
        fig, ax = plt.subplots(figsize=(8.5, 8.2), dpi=110)
        g_web = gdf.to_crs(3857)
        c_web = country.to_crs(3857)
        basemap = add_satellite_basemap(ax, extent_gdf=country)
        g_web.plot(
            ax=ax, column=col, cmap=cmap, linewidth=0.6, edgecolor="white",
            legend=True, missing_kwds={"color": "#64748b", "label": "No data"},
            legend_kwds={"label": col, "shrink": 0.55}, alpha=0.78, zorder=4,
        )
        style_country_outline(ax, c_web)
        # province labels
        for _, row in g_web.iterrows():
            if row.geometry is None or row.geometry.is_empty:
                continue
            c = row.geometry.representative_point()
            ax.text(c.x, c.y, str(row.get("province_key", ""))[:18], fontsize=6.5,
                    ha="center", va="center", color="#f8fafc",
                    path_effects=[], zorder=8,
                    bbox=dict(boxstyle="round,pad=0.15", facecolor="#0f172a", alpha=0.45, edgecolor="none"))
        ax.set_axis_off()
        suffix = f" | {basemap}" if basemap else ""
        ax.set_title(title + " (Provinces.shp)" + suffix, fontsize=11, fontweight="bold", color="#0f172a")
        fig.tight_layout()
        p = out_dir / f"regional_{col}.png"
        fig.savefig(p, dpi=130, bbox_inches="tight", facecolor="#f8fafc")
        plt.close(fig)
        paths[col] = p
    agg.to_csv(out_dir / "regional_province_kpis.csv", index=False)
    return paths


def attach_country_to_folium(m, country: gpd.GeoDataFrame) -> None:
    """Add country outline and fit map to national bounds."""
    import folium

    folium.GeoJson(
        country.__geo_interface__,
        name="KSA country boundary",
        style_function=lambda _f: {
            "color": "#f8fafc", "weight": 2.2, "fillOpacity": 0.0, "opacity": 0.95,
        },
    ).add_to(m)
    minx, miny, maxx, maxy = country.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]], padding=(12, 12))
