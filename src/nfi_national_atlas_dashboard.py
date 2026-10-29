# -*- coding: utf-8 -*-
"""Dashboard-style national atlas (single Leaflet map + dynamic KPI strip).

Look-and-feel aligned with the NFI atlas mockup: header, thematic sidebar,
satellite basemap, floating basemap control, and a bottom infographic bar that
updates by theme and by region / governorate (province) filter.

All KPI numbers are computed from national_su_thematic_attributes (no invented values).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nfi_national_thematic_maps import NATIONAL_THEMES


def _json_safe(v):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if pd.isna(v):
        return None
    return v


def _theme_value_meta() -> dict[str, dict]:
    meta = {}
    for theme_id, title, value_col, kind, category, blurb in NATIONAL_THEMES:
        meta[theme_id] = {
            "id": theme_id,
            "title": title,
            "value_col": value_col,
            "kind": kind,
            "category": category,
            "blurb": blurb,
        }
    return meta


def _agg_block(df: pd.DataFrame) -> dict[str, Any]:
    """National / filtered KPI block from SU thematic rows (computed only)."""
    n = int(len(df))
    out: dict[str, Any] = {"n_su": n}
    if n == 0:
        return out

    def pct_true(col: str) -> float | None:
        if col not in df.columns:
            return None
        s = df[col]
        if s.dtype == object:
            s = s.map(lambda x: str(x).lower() in {"true", "1", "yes"})
        return float(100.0 * s.fillna(False).astype(bool).mean())

    def mean_num(col: str) -> float | None:
        if col not in df.columns:
            return None
        s = pd.to_numeric(df[col], errors="coerce")
        return float(s.mean()) if s.notna().any() else None

    def sum_num(col: str) -> float | None:
        if col not in df.columns:
            return None
        s = pd.to_numeric(df[col], errors="coerce")
        return float(s.sum()) if s.notna().any() else None

    out.update({
        "tree_presence_pct": pct_true("has_tree_record"),
        "shrub_presence_pct": pct_true("has_shrub_record"),
        "fire_presence_pct": pct_true("has_fire"),
        "deadwood_presence_pct": pct_true("has_deadwood"),
        "env_problem_pct": pct_true("has_env_problem"),
        "causative_agent_pct": pct_true("has_causative_agent"),
        "mean_dbh_cm": mean_num("mean_dbh_cm"),
        "mean_height_m": mean_num("mean_height_m"),
        "mean_n_trees": mean_num("n_trees"),
        "mean_n_species": mean_num("n_tree_species"),
        "sum_basal_m2": sum_num("sum_basal_m2"),
        "sum_volume_m3": sum_num("sum_volume_m3"),
        "sum_tree_agb_mg": sum_num("sum_tree_agb_mg"),
        "sum_tree_bgb_mg": sum_num("sum_tree_bgb_mg"),
        "sum_tree_carbon_mg": sum_num("sum_tree_carbon_mg"),
        "sum_tree_co2eq_mg": sum_num("sum_tree_co2eq_mg"),
        "sum_shrub_agb_mg": sum_num("sum_shrub_agb_mg"),
        "sum_shrub_carbon_mg": sum_num("sum_shrub_carbon_mg"),
        "sum_regen": sum_num("regen_count_sum"),
        "mean_stump_share": mean_num("stump_share"),
    })
    return out


def _admin_table(df: pd.DataFrame, col: str) -> list[dict]:
    if col not in df.columns:
        return []
    rows = []
    for name, g in df.groupby(col, dropna=False):
        if pd.isna(name) or str(name).strip() == "":
            continue
        block = _agg_block(g)
        block["name"] = str(name)
        if col == "governorate" and "region" in g.columns:
            # modal parent region
            reg = g["region"].dropna().astype(str)
            block["parent_region"] = reg.value_counts().index[0] if len(reg) else None
        rows.append(block)
    rows.sort(key=lambda r: (-r.get("n_su", 0), r.get("name", "")))
    return rows


def _slim_voronoi_fc(vor_fc: dict[str, Any], keep_cols: list[str]) -> dict[str, Any]:
    """Keep only theming properties on Voronoi features to limit HTML size."""
    keep = set(keep_cols) | {"SU_UID", "region", "governorate"}
    feats = []
    for f in vor_fc.get("features") or []:
        props = f.get("properties") or {}
        feats.append({
            "type": "Feature",
            "geometry": f.get("geometry"),
            "properties": {k: _json_safe(props.get(k)) for k in keep if k in props},
        })
    return {"type": "FeatureCollection", "features": feats}


def build_atlas_payload(
    themes_df: pd.DataFrame,
    catalog: pd.DataFrame | None = None,
    voronoi_fc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    theme_meta = _theme_value_meta()
    themes = []
    if catalog is not None and len(catalog):
        for _, r in catalog.iterrows():
            tid = str(r["theme_id"])
            base = theme_meta.get(tid, {})
            themes.append({
                "id": tid,
                "title": str(r.get("title") or base.get("title") or tid),
                "blurb": str(r.get("blurb") or base.get("blurb") or ""),
                "category": str(r.get("category") or base.get("category") or "Themes"),
                "value_col": base.get("value_col"),
                "kind": base.get("kind") or str(r.get("kind") or "continuous"),
            })
    else:
        themes = list(theme_meta.values())

    # Keep only fields needed for theming / filters / KPIs (smaller atlas HTML)
    keep_cols = {
        "SU_UID", "region", "governorate",
        "has_tree_record", "has_shrub_record", "has_fire", "has_deadwood",
        "has_env_problem", "has_causative_agent",
        "n_trees", "n_tree_species", "mean_dbh_cm", "mean_height_m",
        "sum_basal_m2", "sum_volume_m3",
        "sum_tree_agb_mg", "sum_tree_bgb_mg", "sum_tree_carbon_mg", "sum_tree_co2eq_mg",
        "n_shrubs", "sum_shrub_agb_mg", "sum_shrub_carbon_mg",
        "nat_lucs_mode", "tree_canopy_mode", "herbaceous_mode",
        "fire_type_mode", "env_category_mode", "causative_agent_mode",
        "tree_condition_mode", "crown_condition_mode",
        "regen_count_sum", "stump_share", "coord_confidence_mode",
    }
    keep_cols |= {t.get("value_col") for t in themes if t.get("value_col")}
    keep_cols = {c for c in keep_cols if c and c in themes_df.columns}

    features = []
    for _, row in themes_df.iterrows():
        lon, lat = row.get("lon_validated"), row.get("lat_validated")
        if pd.isna(lon) or pd.isna(lat):
            continue
        props = {c: _json_safe(row.get(c)) for c in keep_cols}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": props,
        })

    value_cols = [t.get("value_col") for t in themes if t.get("value_col")]
    vor_slim = None
    if voronoi_fc and voronoi_fc.get("features"):
        vor_slim = _slim_voronoi_fc(voronoi_fc, [c for c in value_cols if c])

    return {
        "meta": {
            "title": "KSA NFI National Atlas",
            "subtitle": "Forest and rangeland biomass and carbon monitoring (provisional sample metrics)",
            "n_su_total": int(len(themes_df)),
            "n_features_mapped": len(features),
            "n_voronoi_cells": len((vor_slim or {}).get("features") or []),
            "admin_levels": ["national", "region", "governorate"],
            "geometry_modes": ["points", "voronoi", "points_on_voronoi"],
            "note": (
                "Governorate is the province-level field from the SU master (su_group_gover_e). "
                "Voronoi / Thiessen polygons are nearest-neighbour influence zones for cartographic "
                "representation when an SU area frame is absent; points remain the sample locations."
            ),
        },
        "themes": themes,
        "national_kpis": _agg_block(themes_df),
        "by_region": _admin_table(themes_df, "region"),
        "by_governorate": _admin_table(themes_df, "governorate"),
        "geojson": {"type": "FeatureCollection", "features": features},
        "voronoi": vor_slim or {"type": "FeatureCollection", "features": []},
    }


def write_national_dashboard_atlas(
    themes_df: pd.DataFrame,
    out_dir: Path,
    catalog: pd.DataFrame | None = None,
    voronoi_fc: dict[str, Any] | None = None,
    country_fc: dict[str, Any] | None = None,
) -> Path:
    """Write dashboard atlas: index.html (+ embedded data) and atlas_data.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if voronoi_fc is None:
        try:
            from nfi_national_cartography import build_voronoi_geojson
            voronoi_fc = build_voronoi_geojson(themes_df)
        except Exception:
            voronoi_fc = {"type": "FeatureCollection", "features": []}
    if country_fc is None:
        try:
            from nfi_national_boundary import load_country, country_geojson
            country_fc = country_geojson(load_country())
        except Exception:
            country_fc = None
    payload = build_atlas_payload(themes_df, catalog=catalog, voronoi_fc=voronoi_fc)
    if country_fc is not None:
        payload["country"] = country_fc
        payload["meta"]["has_country_boundary"] = True
    data_path = out_dir / "atlas_data.json"
    raw = json.dumps(payload, ensure_ascii=False)
    data_path.write_text(raw, encoding="utf-8")

    # Prefer external JSON to keep index.html small on disk-constrained machines.
    # Fallback embed only a slim payload (points + country, no voronoi) for file:// use.
    index = out_dir / "index.html"
    slim = dict(payload)
    # Drop heavy voronoi from embedded copy; still available in atlas_data.json
    slim["voronoi"] = {"type": "FeatureCollection", "features": []}
    slim_raw = json.dumps(slim, ensure_ascii=False)
    html = _DASHBOARD_HTML.replace(
        "/*__ATLAS_DATA_PLACEHOLDER__*/",
        f"window.ATLAS_DATA = {slim_raw};",
    )
    index.write_text(html, encoding="utf-8")
    return index


_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>KSA NFI National Atlas</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root{
  --ink:#14201a; --muted:#5b6b63; --line:#d7e0da; --paper:#f4f7f5; --card:#ffffff;
  --forest:#1b5e20; --shadow:0 10px 30px rgba(20,32,26,.08);
}
*{box-sizing:border-box}
html,body{height:100%;margin:0;font-family:"IBM Plex Sans",Segoe UI,sans-serif;color:var(--ink);background:var(--paper)}
.shell{display:grid;grid-template-rows:58px 1fr 132px;height:100%}
.shell.fs-map{grid-template-rows:0 1fr 0}
.shell.fs-map header.app, .shell.fs-map .kpi-strip, .shell.fs-map aside.panel{display:none}
.shell.fs-map .workspace{grid-template-columns:1fr}
header.app{
  display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:0 18px;background:linear-gradient(90deg,#12351c,#1b5e20 55%,#246b3a);
  color:#f4faf5;box-shadow:var(--shadow);z-index:5;
}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.logo{width:34px;height:34px;border-radius:10px;background:rgba(255,255,255,.14);display:grid;place-items:center;font-size:18px}
.brand h1{margin:0;font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brand p{margin:2px 0 0;font-size:11px;opacity:.85}
nav.tabs{display:flex;gap:6px;flex-wrap:wrap}
nav.tabs button{border:0;background:transparent;color:#e8f5e9;padding:8px 12px;border-radius:999px;font-weight:600;font-size:12px;cursor:pointer}
nav.tabs button.active{background:rgba(255,255,255,.95);color:#14351c}
.workspace{display:grid;grid-template-columns:300px 1fr;min-height:0}
aside.panel{background:rgba(255,255,255,.92);backdrop-filter:blur(10px);border-right:1px solid var(--line);overflow:auto;padding:14px 12px 18px}
.panel h2{margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.panel .lead{font-size:12px;color:var(--muted);margin:0 0 12px;line-height:1.45}
.filters{display:grid;gap:8px;margin-bottom:12px}
.filters label{font-size:11px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px}
.filters select, .filters input{width:100%;border:1px solid var(--line);border-radius:10px;padding:8px 10px;background:#fff;font:inherit}
.cat{margin:14px 0 6px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.theme{width:100%;text-align:left;border:1px solid var(--line);background:#fff;border-radius:12px;padding:9px 10px;margin:0 0 7px;cursor:pointer;display:flex;gap:10px;align-items:flex-start}
.theme:hover{border-color:#9ccc9c}
.theme.active{border-color:var(--forest);box-shadow:0 0 0 2px rgba(27,94,32,.12);background:#f3faf4}
.theme .ico{width:28px;height:28px;border-radius:8px;background:#e8f5e9;display:grid;place-items:center;flex:0 0 auto;font-size:14px}
.theme strong{display:block;font-size:12.5px}
.theme span{display:block;font-size:11px;color:var(--muted);margin-top:2px;line-height:1.35}
.mapwrap{position:relative;min-height:0}
#map{position:absolute;inset:0;background:#0b1a12}
.float{
  position:absolute;z-index:650;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);
  border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:0;min-width:180px;user-select:none
}
.float .hd{
  cursor:move;padding:8px 12px;border-bottom:1px solid var(--line);font-size:12px;font-weight:700;
  display:flex;align-items:center;justify-content:space-between;gap:8px;background:linear-gradient(180deg,#f8faf8,#fff)
}
.float .hd .tools{display:flex;gap:4px}
.float .hd button{border:0;background:#eef2f0;border-radius:6px;width:22px;height:22px;cursor:pointer;font-size:11px;line-height:1}
.float .bd{padding:10px 12px;font-size:12px}
.float.basemap{top:14px;right:14px;width:220px}
.float.info{top:14px;left:58px;max-width:300px}
.float.legend{top:132px;left:58px;width:230px;max-height:42vh;overflow:auto}
.float.charts{bottom:18px;left:58px;width:300px;max-height:46vh;overflow:auto}
.float h3{margin:0 0 4px;font-size:13px}
.float p{margin:0;color:var(--muted);font-size:11.5px;line-height:1.4}
.float .row{display:flex;align-items:center;gap:8px;margin:5px 0}
.sw{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle;border:1px solid rgba(0,0,0,.15)}
.sw.sq{border-radius:3px}
.legend-scale{display:flex;align-items:flex-end;gap:10px;margin-top:8px}
.legend-scale .dot{border-radius:50%;background:#64748b;display:inline-block}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;background:#e8f5e9;color:#1b5e20;font-size:11px;font-weight:700}
.map-toolbar{
  position:absolute;top:14px;left:14px;z-index:700;display:flex;flex-direction:column;gap:6px
}
.map-toolbar button{
  width:34px;height:34px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.95);
  box-shadow:var(--shadow);cursor:pointer;font-size:14px
}
.kpi-strip{
  display:grid;grid-template-columns:repeat(8,minmax(110px,1fr));gap:10px;padding:12px 14px;
  background:linear-gradient(180deg,#ffffff,#f7faf8);border-top:1px solid var(--line);overflow:auto
}
.kpi{background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 12px;min-width:120px;box-shadow:0 4px 14px rgba(20,32,26,.04)}
.kpi .top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.kpi .label{font-size:11px;color:var(--muted);font-weight:600}
.kpi .value{font-size:20px;font-weight:800;margin-top:4px;letter-spacing:-.02em}
.kpi .unit{font-size:11px;color:var(--muted)}
.kpi .ico{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;font-size:14px}
#chartHist,#chartCat{width:100%!important;max-height:160px}
#chartNote .pct-list{margin-top:4px}
@media (max-width:1100px){
  .workspace{grid-template-columns:280px 1fr}
  .kpi-strip{grid-template-columns:repeat(4,minmax(120px,1fr))}
  .shell{grid-template-rows:58px 1fr 220px}
}
@media (max-width:820px){
  .workspace{grid-template-columns:1fr}
  aside.panel{display:none}
}
</style>
</head>
<body>
<div class="shell" id="shell">
  <header class="app">
    <div class="brand">
      <div class="logo">🌲</div>
      <div>
        <h1>KSA NFI National Atlas</h1>
        <p>Forest and rangeland biomass and carbon monitoring</p>
      </div>
    </div>
    <nav class="tabs" aria-label="Atlas sections">
      <button class="active" data-tab="map">Map</button>
      <button data-tab="analytics">Analytics</button>
      <button data-tab="reports">Reports</button>
      <button data-tab="about">About</button>
    </nav>
  </header>

  <div class="workspace">
    <aside class="panel">
      <h2>Atlas controls</h2>
      <p class="lead">Fixed class colours for categorical themes (land-cover style). Continuous themes use sequential ramps. Drag legend and charts; use fullscreen for presentation.</p>
      <div class="filters">
        <div>
          <label for="adminLevel">Admin level</label>
          <select id="adminLevel">
            <option value="national">National</option>
            <option value="region">Region</option>
            <option value="governorate">Governorate (province)</option>
          </select>
        </div>
        <div>
          <label for="adminName">Region / governorate</label>
          <select id="adminName"><option value="">All</option></select>
        </div>
        <div>
          <label for="searchBox">Search SU / place text</label>
          <input id="searchBox" placeholder="Search country, city or SU..."/>
        </div>
        <div>
          <label for="geomMode">Cartographic representation</label>
          <select id="geomMode">
            <option value="points">Point symbols (sample locations)</option>
            <option value="voronoi">Voronoi / Thiessen polygons</option>
            <option value="points_on_voronoi">Polygons + points overlay</option>
          </select>
        </div>
      </div>
      <div id="themeList"></div>
    </aside>

    <div class="mapwrap" id="mapwrap">
      <div id="map"></div>
      <div class="map-toolbar">
        <button type="button" id="btnFullscreen" title="Fullscreen map">⛶</button>
        <button type="button" id="btnToggleLegend" title="Toggle legend">▣</button>
        <button type="button" id="btnToggleCharts" title="Toggle charts">◔</button>
      </div>

      <div class="float info" id="themeInfo">
        <div class="hd" data-drag="themeInfo"><span>Theme</span><div class="tools"><button type="button" data-min="themeInfo">-</button></div></div>
        <div class="bd" id="themeInfoBd">
          <h3 id="themeTitle">Loading…</h3>
          <p id="themeBlurb"></p>
          <div style="margin-top:8px"><span class="badge" id="scopeBadge">National</span></div>
        </div>
      </div>

      <div class="float basemap" id="basemapPanel">
        <div class="hd" data-drag="basemapPanel"><span>Basemap</span><div class="tools"><button type="button" data-min="basemapPanel">-</button></div></div>
        <div class="bd" id="basemapPanelBd">
          <div class="row"><input type="radio" name="bm" id="bmEsri" checked/> <label for="bmEsri">Esri World Imagery</label></div>
          <div class="row"><input type="radio" name="bm" id="bmGoogle"/> <label for="bmGoogle">Google Satellite</label></div>
          <div class="row"><input type="radio" name="bm" id="bmHybrid"/> <label for="bmHybrid">Google Hybrid</label></div>
          <div class="row"><input type="checkbox" id="lblPlaces" checked/> <label for="lblPlaces">Countries and cities</label></div>
        </div>
      </div>

      <div class="float legend" id="legendPanel">
        <div class="hd" data-drag="legendPanel"><span>Legend</span><div class="tools"><button type="button" data-min="legendPanel">-</button></div></div>
        <div class="bd" id="legend"></div>
      </div>

      <div class="float charts" id="chartPanel">
        <div class="hd" data-drag="chartPanel"><span>Theme statistics</span><div class="tools"><button type="button" data-min="chartPanel">-</button></div></div>
        <div class="bd" id="chartPanelBd">
          <canvas id="chartHist" height="120"></canvas>
          <canvas id="chartCat" height="120" style="display:none"></canvas>
          <p id="chartNote" style="margin-top:6px;color:var(--muted);font-size:11px"></p>
        </div>
      </div>
    </div>
  </div>

  <section class="kpi-strip" id="kpiStrip" aria-label="Dynamic theme KPIs"></section>
</div>

<script>
const STATE = {
  data: null,
  themeId: null,
  adminLevel: 'national',
  adminName: '',
  geomMode: 'points',
  layer: null,
  layerPts: null,
  search: '',
  chartHist: null,
  chartCat: null,
  _vmax: 1,
  _vmin: 0,
};

const ICONS = {
  Frame:'🗺️', Gates:'🚪', Structure:'📐', Biodiversity:'🌿',
  'Biomass and carbon':'🌳', Shrubs:'🌾', 'Land use':'🗂️',
  'Vegetation cover':'🍃', Disturbance:'🔥', 'Deadwood and regen':'🪵',
  'Tree health':'❤️', 'Coordinate QA':'📍', Themes:'📊'
};

/* Cartographic palettes inspired by land-cover convention:
   green = living vegetation / agriculture; amber = shrub/range; tan = bare;
   blue = water; red = built-up / fire; brown = deadwood; purple = disease. */
const PAL = {
  vegYes:'#1b7f4e', vegNo:'#d1d5db',
  deadYes:'#6b4f3a', deadNo:'#e7e5e4',
  fireYes:'#c2410c', fireNo:'#e5e7eb',
  diseaseYes:'#7e22ce', diseaseNo:'#ede9fe',
  envYes:'#b45309', envNo:'#fef3c7',
  biomass:['#f7fcb9','#addd8e','#41ab5d','#006837'],
  structure:['#eff3ff','#bdd7ee','#6baed6','#08519c'],
  carbon:['#ffffcc','#a1dab4','#41b6c4','#225ea8'],
  warn:['#fff7bc','#fec44f','#d95f0e','#7f0000'],
  brown:['#efeee5','#d9c8b4','#a67c52','#5c4033'],
  purple:['#f3e8ff','#d8b4fe','#a855f7','#6b21a8'],
  canopy:['#e5e7eb','#c7e9c0','#74c476','#31a354','#006d2c','#00441b'],
  herb:['#e5e7eb','#ffffcc','#c2e699','#78c679','#31a354','#006837'],
};

/* Fixed class colours (land-cover style) for categorical themes */
const CLASS_COLORS = {
  // Land-cover style fixed colours (NFI nat_lucs classes; cartographic convention)
  land_use: {
    'Agricultural Land':'#1b5e20',
    'Forest':'#43a047',
    'Rangeland':'#f9a825',
    'Protected Area':'#00897b',
    'Oasis':'#66bb6a',
    'Valleys':'#cddc39',
    'Harrat':'#a1887f',
    'Sabkha':'#78909c',
    'Other':'#9e9e9e',
    'None':'#cbd5e1', 'nan':'#cbd5e1', 'NA':'#cbd5e1',
  },
  tree_canopy: {
    'No trees':'#e5e7eb',
    '< 5%':'#c7e9c0',
    '5-10 %':'#74c476',
    '10-40%':'#31a354',
    '40-70%':'#006d2c',
    '> 70%':'#00441b',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  herbaceous: {
    'No herbaceous':'#e5e7eb',
    '1-5 %':'#ffffd4',
    '6-10 %':'#fee391',
    '11-40%':'#fec44f',
    '41-70%':'#fe9929',
    '> 70%':'#cc4c02',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  tree_condition: {
    'Healthy':'#2e7d32',
    'Slightly affected':'#f9a825',
    'Severely affected':'#ef6c00',
    'Dead/Dying tree':'#5d4037',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  crown_condition: {
    'Healthy':'#2e7d32',
    'Declining health':'#f9a825',
    'Dying':'#ef6c00',
    'Dead':'#5d4037',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  fire_type: {
    'No evidence of fire':'#e5e7eb',
    'Surface fire':'#e65100',
    'Ground fire':'#bf360c',
    'Crown fire':'#b71c1c',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  causative_agent: {
    'Not applicable':'#e5e7eb',
    'Climate':'#0277bd',
    'Insects':'#6a1b9a',
    'Animals':'#ad1457',
    'Humans':'#c62828',
    'Dieback':'#4e342e',
    'Disease/Fungi':'#7b1fa2',
    'Other':'#78909c',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  env_category: {
    'No Environmental Problem':'#c8e6c9',
    'Erosion':'#ef6c00',
    'Overgrazing':'#f9a825',
    'Deforestation':'#5d4037',
    'Invasive species':'#8e24aa',
    'Other':'#90a4ae',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  coord_confidence: {
    'high':'#2e7d32',
    'medium':'#f9a825',
    'low':'#c62828',
    'None':'#cbd5e1', 'nan':'#cbd5e1',
  },
  region: {
    'Aseer':'#7c3aed', 'Asir':'#7c3aed',
    'Al Bahah':'#1d4ed8', 'Al Baha':'#1d4ed8',
    'Ar Riyad':'#16a34a',
    'Makkah Al Mukarramah':'#a16207',
    'Eastern Region':'#0891b2',
    'Jazan':'#db2777',
    'Najran':'#06b6d4',
    'Tabuk':'#ea580c',
    'Hail':'#4f46e5',
    'Northern Borders':'#64748b',
    'Al Jawf':'#0f766e',
    'Al Qaseem':'#ca8a04',
    'Al Madinah Al Munawwarah':'#be123c',
  },
};

function classColorMap(theme){
  const id = theme?.id || '';
  if(id==='land_use') return CLASS_COLORS.land_use;
  if(id==='tree_canopy') return CLASS_COLORS.tree_canopy;
  if(id==='herbaceous') return CLASS_COLORS.herbaceous;
  if(id==='tree_condition') return CLASS_COLORS.tree_condition;
  if(id==='crown_condition') return CLASS_COLORS.crown_condition;
  if(id==='fire_type') return CLASS_COLORS.fire_type;
  if(id==='causative_agent') return CLASS_COLORS.causative_agent;
  if(id==='env_category') return CLASS_COLORS.env_category;
  if(id==='coord_confidence') return CLASS_COLORS.coord_confidence;
  if(id==='region') return CLASS_COLORS.region;
  return null;
}

function orderedClassEntries(theme, counts){
  // Prefer fixed class order from CLASS_COLORS (land-cover style legend), then any extras by count
  const map = classColorMap(theme);
  const byLab = Object.fromEntries(counts);
  const out = [];
  const seen = new Set();
  if(map){
    Object.keys(map).forEach(k => {
      if(k==='nan' || k==='NA') return;
      if(byLab[k] != null){ out.push([k, byLab[k]]); seen.add(k); }
    });
  }
  counts.forEach(([k,n]) => { if(!seen.has(k)) out.push([k,n]); });
  return out;
}

function colorForClass(theme, raw){
  const key = (raw===null || raw===undefined || raw==='' || String(raw).toLowerCase()==='nan') ? 'nan' : String(raw);
  const map = classColorMap(theme);
  if(map && map[key]) return map[key];
  // fuzzy match (case / spacing)
  if(map){
    const hit = Object.keys(map).find(k => k.toLowerCase() === key.toLowerCase());
    if(hit) return map[hit];
  }
  // stable hash fallback (colourblind-safe-ish set; no green for damage themes)
  let hash = 0;
  for(let i=0;i<key.length;i++) hash = ((hash<<5)-hash)+key.charCodeAt(i);
  const fallback = ['#0072B2','#E69F00','#D55E00','#CC79A7','#56B4E9','#882255','#44AA99','#999999','#F0E442'];
  return fallback[Math.abs(hash) % fallback.length];
}

function paletteFor(theme){
  const id = theme?.id || '';
  const cat = theme?.category || '';
  if(id==='deadwood_presence') return {type:'binary', yes:PAL.deadYes, no:PAL.deadNo, ramp:PAL.brown, labelYes:'Deadwood present', labelNo:'No deadwood', legendTitle:'Deadwood'};
  if(id==='fire_presence') return {type:'binary', yes:PAL.fireYes, no:PAL.fireNo, ramp:PAL.warn, labelYes:'Fire evidence', labelNo:'No fire', legendTitle:'Fire'};
  if(id==='has_causative_agent') return {type:'binary', yes:PAL.diseaseYes, no:PAL.diseaseNo, ramp:PAL.purple, labelYes:'Agent recorded', labelNo:'Not recorded', legendTitle:'Causative agent'};
  if(id==='env_problem') return {type:'binary', yes:PAL.envYes, no:PAL.envNo, ramp:PAL.warn, labelYes:'Env. problem', labelNo:'None', legendTitle:'Environmental problem'};
  if(id==='tree_presence' || id==='shrub_presence') return {type:'binary', yes:PAL.vegYes, no:PAL.vegNo, ramp:PAL.biomass, labelYes:'Present', labelNo:'Absent', legendTitle: theme.title};
  if(id==='stump_share') return {type:'cont', ramp:PAL.brown, legendTitle:'Stump share'};
  if(id==='land_use' || id==='tree_canopy' || id==='herbaceous' || id==='tree_condition' || id==='crown_condition' || id==='fire_type' || id==='causative_agent' || id==='env_category' || id==='region' || id==='coord_confidence')
    return {type:'categorical', legendTitle: theme.title.replace(/ \(SU\).*/,'').replace(/^Modal /,'') + ' classes'};
  if(cat==='Biomass and carbon' || cat==='Shrubs') return {type:'cont', ramp:PAL.carbon, legendTitle: theme.title};
  if(cat==='Structure' || cat==='Biodiversity') return {type:'cont', ramp:PAL.structure, legendTitle: theme.title};
  if(cat==='Vegetation cover') return {type:'cont', ramp:PAL.canopy, legendTitle: theme.title};
  if(cat==='Disturbance' || cat==='Tree health') return {type:'cont', ramp:PAL.warn, legendTitle: theme.title};
  if(theme.kind==='categorical') return {type:'categorical', legendTitle: theme.title};
  if(theme.kind==='binary') return {type:'binary', yes:PAL.vegYes, no:PAL.vegNo, labelYes:'Yes', labelNo:'No', legendTitle: theme.title};
  return {type:'cont', ramp:PAL.structure, legendTitle: theme.title};
}

function rampColor(ramp, t){
  const i = Math.min(ramp.length-1, Math.max(0, Math.floor(t * (ramp.length-1) + 1e-9)));
  // blend between neighbouring stops
  const f = t * (ramp.length-1);
  const i0 = Math.floor(f), i1 = Math.min(ramp.length-1, i0+1);
  const u = f - i0;
  const hex = (h)=>{const n=parseInt(h.slice(1),16); return [(n>>16)&255,(n>>8)&255,n&255];};
  const a=hex(ramp[i0]), b=hex(ramp[i1]);
  const r=Math.round(a[0]*(1-u)+b[0]*u), g=Math.round(a[1]*(1-u)+b[1]*u), bl=Math.round(a[2]*(1-u)+b[2]*u);
  return `rgb(${r},${g},${bl})`;
}

function fmt(v, digits=1){
  if(v===null || v===undefined || Number.isNaN(v)) return '-';
  if(typeof v === 'number'){
    if(Math.abs(v) >= 1000) return v.toLocaleString(undefined,{maximumFractionDigits:digits});
    return v.toLocaleString(undefined,{maximumFractionDigits:digits});
  }
  return String(v);
}

function themeById(id){ return (STATE.data.themes || []).find(t => t.id === id); }

function filteredFeatures(){
  const feats = STATE.data.geojson.features || [];
  const level = STATE.adminLevel, name = STATE.adminName, q = (STATE.search || '').trim().toLowerCase();
  return feats.filter(f => {
    const p = f.properties || {};
    if(level === 'region' && name && String(p.region||'') !== name) return false;
    if(level === 'governorate' && name && String(p.governorate||'') !== name) return false;
    if(q){
      const blob = [p.SU_UID, p.region, p.governorate].join(' ').toLowerCase();
      if(!blob.includes(q)) return false;
    }
    return true;
  });
}

function filteredVoronoi(){
  const feats = (STATE.data.voronoi && STATE.data.voronoi.features) || [];
  const level = STATE.adminLevel, name = STATE.adminName, q = (STATE.search || '').trim().toLowerCase();
  return feats.filter(f => {
    const p = f.properties || {};
    if(level === 'region' && name && String(p.region||'') !== name) return false;
    if(level === 'governorate' && name && String(p.governorate||'') !== name) return false;
    if(q){
      const blob = [p.SU_UID, p.region, p.governorate].join(' ').toLowerCase();
      if(!blob.includes(q)) return false;
    }
    return true;
  });
}

function kpiSource(){
  if(STATE.adminLevel === 'region' && STATE.adminName){
    const row = (STATE.data.by_region||[]).find(r => r.name === STATE.adminName);
    if(row) return row;
  }
  if(STATE.adminLevel === 'governorate' && STATE.adminName){
    const row = (STATE.data.by_governorate||[]).find(r => r.name === STATE.adminName);
    if(row) return row;
  }
  const rows = filteredFeatures().map(f => f.properties);
  const n = rows.length;
  const pct = (col) => {
    const vals = rows.map(r => r[col]).filter(v => v!==null && v!==undefined);
    if(!vals.length) return null;
    return 100 * vals.filter(v => v===true || v==='True' || v===1).length / vals.length;
  };
  const mean = (col) => {
    const vals = rows.map(r => Number(r[col])).filter(v => Number.isFinite(v));
    if(!vals.length) return null;
    return vals.reduce((a,b)=>a+b,0)/vals.length;
  };
  const sum = (col) => {
    const vals = rows.map(r => Number(r[col])).filter(v => Number.isFinite(v));
    if(!vals.length) return null;
    return vals.reduce((a,b)=>a+b,0);
  };
  return {
    n_su: n,
    tree_presence_pct: pct('has_tree_record'),
    shrub_presence_pct: pct('has_shrub_record'),
    fire_presence_pct: pct('has_fire'),
    deadwood_presence_pct: pct('has_deadwood'),
    env_problem_pct: pct('has_env_problem'),
    causative_agent_pct: pct('has_causative_agent'),
    mean_dbh_cm: mean('mean_dbh_cm'),
    mean_height_m: mean('mean_height_m'),
    mean_n_trees: mean('n_trees'),
    mean_n_species: mean('n_tree_species'),
    sum_basal_m2: sum('sum_basal_m2'),
    sum_volume_m3: sum('sum_volume_m3'),
    sum_tree_agb_mg: sum('sum_tree_agb_mg'),
    sum_tree_bgb_mg: sum('sum_tree_bgb_mg'),
    sum_tree_carbon_mg: sum('sum_tree_carbon_mg'),
    sum_tree_co2eq_mg: sum('sum_tree_co2eq_mg'),
    sum_shrub_agb_mg: sum('sum_shrub_agb_mg'),
    sum_shrub_carbon_mg: sum('sum_shrub_carbon_mg'),
    sum_regen: sum('regen_count_sum'),
    mean_stump_share: mean('stump_share'),
  };
}

function cardsForTheme(theme, k){
  const base = [
    {label:'Total SU', value:fmt(k.n_su,0), unit:'Sample units in scope', ico:'📍', bg:'#e8f5e9'},
    {label:'Tree presence', value:fmt(k.tree_presence_pct,1)+'%', unit:'SUs with tree records', ico:'🌲', bg:'#e3f2fd'},
    {label:'Shrub presence', value:fmt(k.shrub_presence_pct,1)+'%', unit:'SUs with shrub records', ico:'🌾', bg:'#fff8e1'},
  ];
  const id = theme?.id || '';
  const extra = [];
  if(theme?.category==='Disturbance' || theme?.category==='Tree health' || theme?.category==='Deadwood and regen' ||
     ['fire_presence','deadwood_presence','causative_agent','has_causative_agent','stump_share'].includes(id)){
    extra.push(
      {label:'Fire present', value:fmt(k.fire_presence_pct,1)+'%', unit:'SUs with fire evidence', ico:'🔥', bg:'#ffebee'},
      {label:'Deadwood', value:fmt(k.deadwood_presence_pct,1)+'%', unit:'SUs with deadwood', ico:'🪵', bg:'#efebe9'},
      {label:'Agent recorded', value:fmt(k.causative_agent_pct,1)+'%', unit:'SUs with causative agent', ico:'🦠', bg:'#f3e8ff'},
      {label:'Env. problem', value:fmt(k.env_problem_pct,1)+'%', unit:'SUs with env. records', ico:'⚠️', bg:'#fff7ed'},
      {label:'Stump share', value:fmt((k.mean_stump_share||0)*100,1)+'%', unit:'mean of SU shares', ico:'🪓', bg:'#ffedd5'},
    );
  } else if(theme?.category==='Biomass and carbon' || theme?.category==='Shrubs'){
    extra.push(
      {label:'AGB (prov.)', value:fmt(k.sum_tree_agb_mg,1), unit:'Mg sum in scope', ico:'🌳', bg:'#e8f5e9'},
      {label:'Carbon (prov.)', value:fmt(k.sum_tree_carbon_mg,1), unit:'Mg sum in scope', ico:'⬛', bg:'#efebe9'},
      {label:'Shrub AGB', value:fmt(k.sum_shrub_agb_mg,1), unit:'Mg sum', ico:'🌾', bg:'#fff8e1'},
      {label:'Mean DBH', value:fmt(k.mean_dbh_cm,1), unit:'cm', ico:'📏', bg:'#e3f2fd'},
      {label:'Mean height', value:fmt(k.mean_height_m,1), unit:'m', ico:'📐', bg:'#f3e5f5'},
    );
  } else {
    extra.push(
      {label:'Mean DBH', value:fmt(k.mean_dbh_cm,1), unit:'cm', ico:'📏', bg:'#e3f2fd'},
      {label:'Mean height', value:fmt(k.mean_height_m,1), unit:'m', ico:'📐', bg:'#f3e5f5'},
      {label:'Basal area', value:fmt(k.sum_basal_m2,1), unit:'m² sum', ico:'🪵', bg:'#efebe9'},
      {label:'AGB (prov.)', value:fmt(k.sum_tree_agb_mg,1), unit:'Mg sum', ico:'🌳', bg:'#e8f5e9'},
      {label:'Mean trees / SU', value:fmt(k.mean_n_trees,1), unit:'count', ico:'🔢', bg:'#e8f5e9'},
    );
  }
  return base.concat(extra).slice(0,8);
}

function renderKpis(){
  const theme = themeById(STATE.themeId);
  const k = kpiSource();
  const cards = cardsForTheme(theme, k);
  document.getElementById('kpiStrip').innerHTML = cards.map(c => `
    <div class="kpi"><div class="top"><div class="label">${c.label}</div>
    <div class="ico" style="background:${c.bg}">${c.ico}</div></div>
    <div class="value">${c.value}</div><div class="unit">${c.unit}</div></div>`).join('');
  const scope = STATE.adminLevel === 'national' ? 'National'
    : (STATE.adminName ? `${STATE.adminLevel}: ${STATE.adminName}` : `${STATE.adminLevel}: all`);
  document.getElementById('scopeBadge').textContent = scope + ` · n=${fmt(k.n_su,0)} SU`;
}

function updateVmax(theme, feats){
  if(theme.kind !== 'continuous' || !theme.value_col){ STATE._vmax = 1; STATE._vmin = 0; return; }
  const vals = feats.map(f => Number(f.properties[theme.value_col])).filter(v => Number.isFinite(v)).sort((a,b)=>a-b);
  if(!vals.length){ STATE._vmax = 1; STATE._vmin = 0; return; }
  STATE._vmin = vals[0];
  STATE._vmax = vals[Math.min(vals.length-1, Math.floor(vals.length*0.95))] || 1;
  if(STATE._vmax <= STATE._vmin) STATE._vmax = STATE._vmin + 1e-9;
}

function colorFor(theme, props){
  const pal = paletteFor(theme);
  const col = theme.value_col;
  const kind = theme.kind;
  if(kind === 'binary'){
    const v = props[col];
    const yes = v===true || v==='True' || v===1;
    return yes ? pal.yes : pal.no;
  }
  if(kind === 'categorical'){
    return colorForClass(theme, props[col]);
  }
  if(kind === 'continuous'){
    const v = Number(props[col]);
    if(!Number.isFinite(v)) return '#94a3b8';
    const t = Math.max(0, Math.min(1, (v - STATE._vmin) / (STATE._vmax - STATE._vmin)));
    return rampColor(pal.ramp || PAL.structure, t);
  }
  return '#475569';
}

function classCounts(theme, feats){
  const col = theme.value_col;
  const counts = {};
  feats.forEach(f => {
    let v = f.properties[col];
    if(theme.kind==='binary'){
      const pal = paletteFor(theme);
      const yes = v===true || v==='True' || v===1;
      v = yes ? (pal.labelYes||'Yes') : (pal.labelNo||'No');
    } else {
      if(v===null || v===undefined || v==='' || String(v).toLowerCase()==='nan') v = 'No data';
      else v = String(v);
    }
    counts[v] = (counts[v]||0) + 1;
  });
  return Object.entries(counts).sort((a,b)=>b[1]-a[1]);
}

function radiusFor(theme, props){
  // Smaller base markers; continuous themes scale with value
  if(theme.kind === 'continuous' && theme.value_col){
    const v = Number(props[theme.value_col]);
    if(!Number.isFinite(v)) return 2.2;
    const t = Math.max(0, Math.min(1, (v - STATE._vmin) / (STATE._vmax - STATE._vmin)));
    return 2.0 + 4.5 * Math.sqrt(t); // ~2.0 to 6.5 px
  }
  if(theme.kind === 'binary'){
    const v = props[theme.value_col];
    const yes = v===true || v==='True' || v===1;
    return yes ? 3.2 : 2.2;
  }
  return 2.6;
}

function renderLegend(theme, feats){
  const el = document.getElementById('legend');
  const pal = paletteFor(theme);
  const title = pal.legendTitle || theme.title;
  const hd = document.querySelector('#legendPanel .hd span');
  if(hd) hd.textContent = (theme.kind === 'categorical') ? 'Classes' : 'Legend';
  let html = `<div style="font-weight:700;margin-bottom:8px">${title}</div>`;
  if(theme.kind === 'binary'){
    html += `<div style="margin:3px 0"><span class="sw" style="background:${pal.yes}"></span>${pal.labelYes||'Yes / present'}</div>
             <div style="margin:3px 0"><span class="sw" style="background:${pal.no}"></span>${pal.labelNo||'No / absent'}</div>`;
  } else if(theme.kind === 'continuous'){
    const ramp = pal.ramp || PAL.structure;
    html += `<div style="display:flex;height:12px;border-radius:6px;overflow:hidden;border:1px solid #cbd5e1;margin:6px 0">
      ${ramp.map(c=>`<div style="flex:1;background:${c}"></div>`).join('')}</div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:#64748b">
        <span>${fmt(STATE._vmin,2)}</span><span>${fmt(STATE._vmax,2)} (p95)</span></div>
      <div class="legend-scale">
        <span class="dot" style="width:8px;height:8px"></span><span style="font-size:10px">Low</span>
        <span class="dot" style="width:14px;height:14px"></span><span style="font-size:10px">High</span>
      </div>
      <div style="margin-top:6px;font-size:10px;color:#64748b">Marker size scales with value</div>`;
  } else {
    // Land-cover style class legend: fixed colour order + counts in view
    const raw = classCounts(theme, feats || []);
    const entries = orderedClassEntries(theme, raw).slice(0, 14);
    if(!entries.length){
      html += `<div style="font-size:11px;color:#64748b">No classes in current filter</div>`;
    } else {
      entries.forEach(([lab, n]) => {
        const c = colorForClass(theme, lab==='No data'?'nan':lab);
        html += `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:12px">
          <span class="sw" style="background:${c};flex:0 0 auto"></span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${lab}">${lab}</span>
        </div>`;
      });
      html += `<div style="margin-top:8px;font-size:10px;color:#64748b">Points: colour = class; size may vary with value</div>`;
    }
  }
  el.innerHTML = html;
}

function renderCharts(theme, feats){
  const note = document.getElementById('chartNote');
  const histEl = document.getElementById('chartHist');
  const catEl = document.getElementById('chartCat');
  if(STATE.chartHist){ STATE.chartHist.destroy(); STATE.chartHist=null; }
  if(STATE.chartCat){ STATE.chartCat.destroy(); STATE.chartCat=null; }

  const col = theme.value_col;
  if(!col){
    histEl.style.display='none'; catEl.style.display='none';
    note.textContent = 'No numeric/categorical field for this theme.';
    return;
  }
  const pal = paletteFor(theme);
  if(theme.kind === 'continuous'){
    histEl.style.display='block'; catEl.style.display='none';
    const vals = feats.map(f => Number(f.properties[col])).filter(v => Number.isFinite(v));
    if(vals.length < 5){ note.textContent='Too few values for histogram.'; return; }
    const bins = 12;
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const width = (hi-lo)/(bins||1) || 1;
    const counts = Array(bins).fill(0);
    vals.forEach(v => {
      let i = Math.floor((v-lo)/width);
      if(i>=bins) i=bins-1;
      counts[i]++;
    });
    const labels = counts.map((_,i)=> fmt(lo+i*width,1));
    STATE.chartHist = new Chart(histEl, {
      type:'bar',
      data:{labels, datasets:[{label:col, data:counts, backgroundColor: rampColor(pal.ramp||PAL.structure, 0.55), borderRadius:4}]},
      options:{plugins:{legend:{display:false}}, scales:{x:{ticks:{maxRotation:0, autoSkip:true, maxTicksLimit:6, font:{size:9}}}, y:{beginAtZero:true, ticks:{font:{size:9}}}}, maintainAspectRatio:false}
    });
    note.textContent = `Histogram of ${col} (n=${vals.length}). Mean=${fmt(vals.reduce((a,b)=>a+b,0)/vals.length,2)}.`;
  } else {
    histEl.style.display='none'; catEl.style.display='block';
    const raw = classCounts(theme, feats);
    // Stats by frequency (land-cover mockup); map colours stay fixed per class
    const byCount = [...raw].sort((a,b)=>b[1]-a[1]).slice(0, 10);
    const total = byCount.reduce((a,e)=>a+e[1], 0) || 1;
    const colors = byCount.map(([lab]) => {
      if(theme.kind==='binary'){
        return lab===(pal.labelYes||'Yes') ? pal.yes : pal.no;
      }
      return colorForClass(theme, lab==='No data'?'nan':lab);
    });
    STATE.chartCat = new Chart(catEl, {
      type:'doughnut',
      data:{labels:byCount.map(e=>e[0].slice(0,28)), datasets:[{data:byCount.map(e=>e[1]), backgroundColor:colors, borderWidth:1, borderColor:'#fff'}]},
      options:{
        cutout:'58%',
        plugins:{
          legend:{display:false},
          tooltip:{callbacks:{label:(ctx)=>{
            const n = ctx.parsed; const pct = 100*n/total;
            return ` ${ctx.label}: ${n} (${pct.toFixed(1)}%)`;
          }}}
        },
        maintainAspectRatio:false
      }
    });
    // Land-cover style percent list (by frequency)
    const list = byCount.map(([lab,n], i) => {
      const pctNum = 100*n/total;
      const pct = pctNum < 1 ? '<1' : pctNum.toFixed(0);
      const c = colors[i];
      return `<div style="display:flex;align-items:center;gap:6px;font-size:11px;margin:2px 0">
        <span class="sw" style="background:${c};width:10px;height:10px"></span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${lab}">${lab}</span>
        <b>${pct}%</b></div>`;
    }).join('');
    note.innerHTML = `<div class="pct-list" style="display:flex;gap:10px;align-items:flex-start">
      <div style="flex:0 0 auto;text-align:center;font-size:11px;color:#64748b;padding-top:4px"><b style="display:block;font-size:15px;color:#0f172a">${fmt(total,0)}</b>SU</div>
      <div style="flex:1;min-width:0">${list}</div>
    </div>`;
  }
}

function bindPopup(theme, feat, layer){
  const p = feat.properties || {};
  const val = theme.value_col ? p[theme.value_col] : '';
  layer.bindPopup(
    `<b>SU ${p.SU_UID??''}</b><br/>Region: ${p.region??'-'}<br/>Governorate: ${p.governorate??'-'}<br/>`+
    `${theme.title}: <b>${val===null||val===undefined?'-':val}</b>`
  );
}

function redrawLayer(){
  const theme = themeById(STATE.themeId);
  if(!theme) return;
  const pts = filteredFeatures();
  const vor = filteredVoronoi();
  updateVmax(theme, pts.length ? pts : vor);
  if(STATE.layer){ MAP.removeLayer(STATE.layer); STATE.layer = null; }
  if(STATE.layerPts){ MAP.removeLayer(STATE.layerPts); STATE.layerPts = null; }

  const mode = STATE.geomMode || 'points';
  const stylePoly = (feat) => {
    const c = colorFor(theme, feat.properties||{});
    return {color:'#ffffff', weight:0.35, fillColor:c, fillOpacity:0.7};
  };
  const pointLayer = (feat, latlng) => {
    const props = feat.properties||{};
    const c = colorFor(theme, props);
    const r = radiusFor(theme, props);
    return L.circleMarker(latlng, {
      radius: r,
      color: '#0f172a',
      fillColor: c,
      fillOpacity: 0.88,
      weight: 0.45
    });
  };

  if(mode === 'voronoi' || mode === 'points_on_voronoi'){
    if(vor.length){
      STATE.layer = L.geoJSON({type:'FeatureCollection', features:vor}, {
        style: stylePoly,
        onEachFeature: (feat, layer) => bindPopup(theme, feat, layer),
      }).addTo(MAP);
    }
  }
  if(mode === 'points' || mode === 'points_on_voronoi'){
    const target = (mode === 'points') ? 'layer' : 'layerPts';
    STATE[target] = L.geoJSON({type:'FeatureCollection', features:pts}, {
      pointToLayer: pointLayer,
      onEachFeature: (feat, layer) => bindPopup(theme, feat, layer),
    }).addTo(MAP);
  }

  const modeLabel = mode === 'voronoi' ? 'Voronoi / Thiessen'
    : (mode === 'points_on_voronoi' ? 'Polygons + points' : 'Points');
  document.getElementById('themeTitle').textContent = theme.title;
  document.getElementById('themeBlurb').textContent =
    (theme.blurb || '') + ` · Representation: ${modeLabel} · size varies with value`;
  renderLegend(theme, pts);
  renderCharts(theme, pts);
  renderKpis();
}

function fillThemeList(){
  const root = document.getElementById('themeList');
  const themes = STATE.data.themes || [];
  let html = '', last = null;
  themes.forEach(t => {
    if(t.kind === 'special_plots') return;
    if(t.category !== last){ html += `<div class="cat">${t.category}</div>`; last = t.category; }
    const ico = ICONS[t.category] || '📊';
    html += `<button class="theme" data-id="${t.id}">
      <div class="ico">${ico}</div>
      <div><strong>${t.title}</strong><span>${t.blurb||''}</span></div>
    </button>`;
  });
  root.innerHTML = html;
  root.querySelectorAll('.theme').forEach(btn => {
    btn.addEventListener('click', () => {
      root.querySelectorAll('.theme').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.themeId = btn.dataset.id;
      redrawLayer();
    });
  });
  const first = root.querySelector('.theme');
  if(first){ first.classList.add('active'); STATE.themeId = first.dataset.id; }
}

function fillAdminNames(){
  const sel = document.getElementById('adminName');
  const level = STATE.adminLevel;
  sel.innerHTML = '<option value="">All</option>';
  if(level === 'national'){ sel.disabled = true; return; }
  sel.disabled = false;
  const rows = level === 'region' ? (STATE.data.by_region||[]) : (STATE.data.by_governorate||[]);
  rows.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r.name;
    opt.textContent = `${r.name} (n=${r.n_su})`;
    sel.appendChild(opt);
  });
}

/* Drag panels */
function enableDrag(id){
  const el = document.getElementById(id);
  const hd = el.querySelector('.hd');
  let ox=0, oy=0, dragging=false;
  hd.addEventListener('pointerdown', (e) => {
    if(e.target.tagName === 'BUTTON') return;
    dragging = true;
    const rect = el.getBoundingClientRect();
    const parent = el.parentElement.getBoundingClientRect();
    ox = e.clientX - rect.left; oy = e.clientY - rect.top;
    el.style.right = 'auto'; el.style.bottom = 'auto';
    el.style.left = (rect.left - parent.left) + 'px';
    el.style.top = (rect.top - parent.top) + 'px';
    hd.setPointerCapture(e.pointerId);
  });
  hd.addEventListener('pointermove', (e) => {
    if(!dragging) return;
    const parent = el.parentElement.getBoundingClientRect();
    el.style.left = Math.max(0, e.clientX - parent.left - ox) + 'px';
    el.style.top = Math.max(0, e.clientY - parent.top - oy) + 'px';
  });
  hd.addEventListener('pointerup', () => { dragging=false; });
}
['themeInfo','basemapPanel','legendPanel','chartPanel'].forEach(enableDrag);
document.querySelectorAll('[data-min]').forEach(btn => {
  btn.addEventListener('click', () => {
    const id = btn.getAttribute('data-min');
    const bd = document.getElementById(id + 'Bd') || document.getElementById(id === 'legendPanel' ? 'legend' : id+'Bd');
    const target = id === 'legendPanel' ? document.getElementById('legend') : document.getElementById(id+'Bd');
    if(!target) return;
    target.style.display = target.style.display === 'none' ? '' : 'none';
  });
});

document.getElementById('btnToggleLegend').onclick = () => {
  const p = document.getElementById('legendPanel');
  p.style.display = p.style.display === 'none' ? '' : 'none';
};
document.getElementById('btnToggleCharts').onclick = () => {
  const p = document.getElementById('chartPanel');
  p.style.display = p.style.display === 'none' ? '' : 'none';
};
document.getElementById('btnFullscreen').onclick = () => {
  const wrap = document.getElementById('mapwrap');
  const shell = document.getElementById('shell');
  if(!document.fullscreenElement){
    wrap.requestFullscreen?.() || shell.classList.add('fs-map');
    setTimeout(()=>MAP.invalidateSize(), 200);
  } else {
    document.exitFullscreen?.();
  }
};
document.addEventListener('fullscreenchange', () => setTimeout(()=>MAP.invalidateSize(), 150));

const MAP = L.map('map', {zoomControl:true}).setView([23.5, 45.0], 6);
const layers = {
  esri: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {attribution:'Esri', maxZoom:19}),
  google: L.tileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', {attribution:'Google', maxZoom:20}),
  hybrid: L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {attribution:'Google', maxZoom:20}),
  places: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {attribution:'Esri', maxZoom:19, opacity:0.95}),
};
layers.esri.addTo(MAP);
layers.places.addTo(MAP);
let activeBm = layers.esri;
document.getElementById('bmEsri').onchange = () => { if(document.getElementById('bmEsri').checked){ MAP.removeLayer(activeBm); activeBm=layers.esri; activeBm.addTo(MAP);} };
document.getElementById('bmGoogle').onchange = () => { if(document.getElementById('bmGoogle').checked){ MAP.removeLayer(activeBm); activeBm=layers.google; activeBm.addTo(MAP);} };
document.getElementById('bmHybrid').onchange = () => { if(document.getElementById('bmHybrid').checked){ MAP.removeLayer(activeBm); activeBm=layers.hybrid; activeBm.addTo(MAP);} };
document.getElementById('lblPlaces').onchange = (e) => { e.target.checked ? layers.places.addTo(MAP) : MAP.removeLayer(layers.places); };

document.getElementById('adminLevel').addEventListener('change', (e) => {
  STATE.adminLevel = e.target.value; STATE.adminName = ''; fillAdminNames(); redrawLayer();
});
document.getElementById('adminName').addEventListener('change', (e) => { STATE.adminName = e.target.value; redrawLayer(); });
document.getElementById('searchBox').addEventListener('input', (e) => { STATE.search = e.target.value; redrawLayer(); });
document.getElementById('geomMode').addEventListener('change', (e) => { STATE.geomMode = e.target.value; redrawLayer(); });

document.querySelectorAll('nav.tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if(btn.dataset.tab === 'reports'){
      window.open('../documents/NFI_national_geopipeline_report.html', '_blank');
    } else if(btn.dataset.tab === 'about'){
      alert('KSA NFI National Atlas\\nSemantic colours: green=living vegetation; brown=deadwood/stumps; red/orange=fire; purple=disease/agents.\\nDrag legend and charts. Fullscreen via ⛶.');
    } else if(btn.dataset.tab === 'analytics'){
      const p = document.getElementById('chartPanel');
      p.style.display = '';
      p.scrollIntoView({block:'nearest'});
    }
  });
});

function boot(data){
  STATE.data = data;
  fillThemeList();
  fillAdminNames();
  if(data.country){
    L.geoJSON(data.country, {
      style: {color:'#f8fafc', weight:2.2, fillOpacity:0, opacity:0.95},
      interactive:false
    }).addTo(MAP);
    const cb = L.geoJSON(data.country).getBounds();
    if(cb.isValid()) MAP.fitBounds(cb.pad(0.04));
  }
  redrawLayer();
  if(!data.country){
    const feats = data.geojson.features || [];
    if(feats.length){
      const b = L.geoJSON(data.geojson).getBounds();
      if(b.isValid()) MAP.fitBounds(b.pad(0.05));
    }
  }
}
/*__ATLAS_DATA_PLACEHOLDER__*/
if(window.ATLAS_DATA){
  boot(window.ATLAS_DATA);
} else {
  fetch('atlas_data.json')
    .then(r => r.json())
    .then(boot)
    .catch(err => {
      document.getElementById('themeTitle').textContent = 'Failed to load atlas data';
      document.getElementById('themeBlurb').textContent = String(err);
    });
}
</script>
</body>
</html>
"""
