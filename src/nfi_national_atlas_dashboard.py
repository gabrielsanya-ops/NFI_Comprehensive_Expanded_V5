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

    features = []
    for _, row in themes_df.iterrows():
        lon, lat = row.get("lon_validated"), row.get("lat_validated")
        if pd.isna(lon) or pd.isna(lat):
            continue
        props = {c: _json_safe(row.get(c)) for c in themes_df.columns}
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
    payload = build_atlas_payload(themes_df, catalog=catalog, voronoi_fc=voronoi_fc)
    data_path = out_dir / "atlas_data.json"
    raw = json.dumps(payload, ensure_ascii=False)
    data_path.write_text(raw, encoding="utf-8")

    # Embed JSON so file:// open works without a local web server / CORS issues
    index = out_dir / "index.html"
    html = _DASHBOARD_HTML.replace(
        "/*__ATLAS_DATA_PLACEHOLDER__*/",
        f"window.ATLAS_DATA = {raw};",
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
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root{
  --ink:#14201a; --muted:#5b6b63; --line:#d7e0da; --paper:#f4f7f5; --card:#ffffff;
  --forest:#1b5e20; --forest2:#2e7d32; --accent:#0e7c66; --warn:#d97706;
  --shadow:0 10px 30px rgba(20,32,26,.08);
}
*{box-sizing:border-box}
html,body{height:100%;margin:0;font-family:"IBM Plex Sans",Segoe UI,sans-serif;color:var(--ink);background:var(--paper)}
.shell{display:grid;grid-template-rows:58px 1fr 132px;height:100%}
header.app{
  display:flex;align-items:center;justify-content:space-between;gap:16px;
  padding:0 18px;background:linear-gradient(90deg,#12351c,#1b5e20 55%,#246b3a);
  color:#f4faf5;box-shadow:var(--shadow);z-index:5;
}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.logo{
  width:34px;height:34px;border-radius:10px;background:rgba(255,255,255,.14);
  display:grid;place-items:center;font-size:18px
}
.brand h1{margin:0;font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brand p{margin:2px 0 0;font-size:11px;opacity:.85}
nav.tabs{display:flex;gap:6px;flex-wrap:wrap}
nav.tabs button{
  border:0;background:transparent;color:#e8f5e9;padding:8px 12px;border-radius:999px;
  font-weight:600;font-size:12px;cursor:pointer
}
nav.tabs button.active{background:rgba(255,255,255,.95);color:#14351c}
.workspace{display:grid;grid-template-columns:320px 1fr;min-height:0}
aside.panel{
  background:rgba(255,255,255,.92);backdrop-filter:blur(10px);border-right:1px solid var(--line);
  overflow:auto;padding:14px 12px 18px
}
.panel h2{margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.panel .lead{font-size:12px;color:var(--muted);margin:0 0 12px;line-height:1.45}
.filters{display:grid;gap:8px;margin-bottom:12px}
.filters label{font-size:11px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px}
.filters select, .filters input{
  width:100%;border:1px solid var(--line);border-radius:10px;padding:8px 10px;background:#fff;font:inherit
}
.cat{margin:14px 0 6px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.theme{
  width:100%;text-align:left;border:1px solid var(--line);background:#fff;border-radius:12px;
  padding:9px 10px;margin:0 0 7px;cursor:pointer;display:flex;gap:10px;align-items:flex-start
}
.theme:hover{border-color:#9ccc9c}
.theme.active{border-color:var(--forest);box-shadow:0 0 0 2px rgba(27,94,32,.12);background:#f3faf4}
.theme .ico{
  width:28px;height:28px;border-radius:8px;background:#e8f5e9;display:grid;place-items:center;flex:0 0 auto;font-size:14px
}
.theme strong{display:block;font-size:12.5px}
.theme span{display:block;font-size:11px;color:var(--muted);margin-top:2px;line-height:1.35}
.mapwrap{position:relative;min-height:0}
#map{position:absolute;inset:0;background:#0b1a12}
.float{
  position:absolute;z-index:500;background:rgba(255,255,255,.94);backdrop-filter:blur(8px);
  border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:10px 12px
}
.float.basemap{top:14px;right:14px;width:210px;font-size:12px}
.float.info{top:14px;left:58px;max-width:340px}
.float h3{margin:0 0 4px;font-size:13px}
.float p{margin:0;color:var(--muted);font-size:11.5px;line-height:1.4}
.float .row{display:flex;align-items:center;gap:8px;margin:5px 0}
.kpi-strip{
  display:grid;grid-template-columns:repeat(8,minmax(110px,1fr));gap:10px;padding:12px 14px;
  background:linear-gradient(180deg,#ffffff,#f7faf8);border-top:1px solid var(--line);overflow:auto
}
.kpi{
  background:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 12px;min-width:120px;
  box-shadow:0 4px 14px rgba(20,32,26,.04)
}
.kpi .top{display:flex;align-items:center;justify-content:space-between;gap:8px}
.kpi .label{font-size:11px;color:var(--muted);font-weight:600}
.kpi .value{font-size:20px;font-weight:800;margin-top:4px;letter-spacing:-.02em}
.kpi .unit{font-size:11px;color:var(--muted)}
.kpi .ico{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;font-size:14px}
.badge{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;background:#e8f5e9;color:#1b5e20;font-size:11px;font-weight:700}
.legend{position:absolute;bottom:18px;right:14px;z-index:500;background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:12px;padding:8px 10px;font-size:11px}
.legend .sw{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:middle}
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
<div class="shell">
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
      <p class="lead">Select a thematic layer. KPIs below the map update for the current theme and admin filter (national, region, or governorate / province).</p>
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

    <div class="mapwrap">
      <div id="map"></div>
      <div class="float info" id="themeInfo">
        <h3 id="themeTitle">Loading…</h3>
        <p id="themeBlurb"></p>
        <div style="margin-top:8px"><span class="badge" id="scopeBadge">National</span></div>
      </div>
      <div class="float basemap">
        <strong>Basemap</strong>
        <div class="row"><input type="radio" name="bm" id="bmEsri" checked/> <label for="bmEsri">Esri World Imagery</label></div>
        <div class="row"><input type="radio" name="bm" id="bmGoogle"/> <label for="bmGoogle">Google Satellite</label></div>
        <div class="row"><input type="radio" name="bm" id="bmHybrid"/> <label for="bmHybrid">Google Hybrid</label></div>
        <div class="row"><input type="checkbox" id="lblPlaces" checked/> <label for="lblPlaces">Countries and cities</label></div>
      </div>
      <div class="legend" id="legend"></div>
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
};

const ICONS = {
  Frame:'🗺️', Gates:'🚪', Structure:'📐', Biodiversity:'🌿',
  'Biomass and carbon':'🌳', Shrubs:'🌾', 'Land use':'🗂️',
  'Vegetation cover':'🍃', Disturbance:'🔥', 'Deadwood and regen':'🪵',
  'Tree health':'❤️', 'Coordinate QA':'📍', Themes:'📊'
};

function fmt(v, digits=1){
  if(v===null || v===undefined || Number.isNaN(v)) return '-';
  if(typeof v === 'number'){
    if(Math.abs(v) >= 1000) return v.toLocaleString(undefined,{maximumFractionDigits:digits});
    return v.toLocaleString(undefined,{maximumFractionDigits:digits});
  }
  return String(v);
}

function themeById(id){
  return (STATE.data.themes || []).find(t => t.id === id);
}

function filteredFeatures(){
  const feats = STATE.data.geojson.features || [];
  const level = STATE.adminLevel;
  const name = STATE.adminName;
  const q = (STATE.search || '').trim().toLowerCase();
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
  // Prefer pre-aggregated admin tables when filtering by one admin unit
  if(STATE.adminLevel === 'region' && STATE.adminName){
    const row = (STATE.data.by_region||[]).find(r => r.name === STATE.adminName);
    if(row) return row;
  }
  if(STATE.adminLevel === 'governorate' && STATE.adminName){
    const row = (STATE.data.by_governorate||[]).find(r => r.name === STATE.adminName);
    if(row) return row;
  }
  // Otherwise recompute from currently filtered features (includes search)
  const feats = filteredFeatures();
  const rows = feats.map(f => f.properties);
  const n = rows.length;
  const pct = (col) => {
    const vals = rows.map(r => r[col]).filter(v => v!==null && v!==undefined);
    if(!vals.length) return null;
    const t = vals.filter(v => v===true || v==='True' || v===1).length;
    return 100 * t / vals.length;
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
  // Always show scope size + theme-relevant metrics (computed)
  const base = [
    {label:'Total SU', value:fmt(k.n_su,0), unit:'Sample units in scope', ico:'📍', bg:'#e8f5e9'},
    {label:'Tree presence', value:fmt(k.tree_presence_pct,1)+'%', unit:'SUs with tree records', ico:'🌲', bg:'#e3f2fd'},
    {label:'Shrub presence', value:fmt(k.shrub_presence_pct,1)+'%', unit:'SUs with shrub records', ico:'🌾', bg:'#fff8e1'},
  ];
  const id = theme?.id || '';
  const extra = [];
  if(['mean_dbh','tree_count','mean_height','sum_basal','sum_volume','stump_share','species_richness'].includes(id) || theme?.category==='Structure' || theme?.category==='Biodiversity'){
    extra.push(
      {label:'Mean DBH', value:fmt(k.mean_dbh_cm,1), unit:'cm (SU mean of means)', ico:'📏', bg:'#e3f2fd'},
      {label:'Mean height', value:fmt(k.mean_height_m,1), unit:'m (SU mean of means)', ico:'📐', bg:'#f3e5f5'},
      {label:'Basal area', value:fmt(k.sum_basal_m2,1), unit:'m² sum in scope', ico:'🪵', bg:'#efebe9'},
      {label:'Volume (prov.)', value:fmt(k.sum_volume_m3,1), unit:'m³ sum in scope', ico:'📦', bg:'#e8eaf6'},
      {label:'Mean trees / SU', value:fmt(k.mean_n_trees,1), unit:'where trees present', ico:'🔢', bg:'#e8f5e9'},
    );
  } else if(theme?.category==='Biomass and carbon' || ['sum_agb','sum_bgb','sum_carbon','sum_co2eq'].includes(id)){
    extra.push(
      {label:'AGB (prov.)', value:fmt(k.sum_tree_agb_mg,1), unit:'Mg sum in scope', ico:'🌳', bg:'#e8f5e9'},
      {label:'BGB (prov.)', value:fmt(k.sum_tree_bgb_mg,1), unit:'Mg sum in scope', ico:'🌱', bg:'#f1f8e9'},
      {label:'Carbon (prov.)', value:fmt(k.sum_tree_carbon_mg,1), unit:'Mg sum in scope', ico:'⬛', bg:'#efebe9'},
      {label:'CO₂eq (prov.)', value:fmt(k.sum_tree_co2eq_mg,1), unit:'Mg sum in scope', ico:'☁️', bg:'#e3f2fd'},
      {label:'Mean DBH', value:fmt(k.mean_dbh_cm,1), unit:'cm', ico:'📏', bg:'#e3f2fd'},
    );
  } else if(theme?.category==='Shrubs'){
    extra.push(
      {label:'Shrub AGB', value:fmt(k.sum_shrub_agb_mg,1), unit:'Mg sum in scope', ico:'🌾', bg:'#fff8e1'},
      {label:'Shrub carbon', value:fmt(k.sum_shrub_carbon_mg,1), unit:'Mg sum in scope', ico:'⬛', bg:'#efebe9'},
      {label:'Tree presence', value:fmt(k.tree_presence_pct,1)+'%', unit:'context', ico:'🌲', bg:'#e8f5e9'},
      {label:'Mean height', value:fmt(k.mean_height_m,1), unit:'m trees', ico:'📐', bg:'#f3e5f5'},
      {label:'Regen sum', value:fmt(k.sum_regen,0), unit:'count field sum', ico:'🌱', bg:'#e8f5e9'},
    );
  } else if(theme?.category==='Disturbance' || theme?.category==='Tree health' || ['fire_presence','fire_type','env_problem','env_category','causative_agent','has_causative_agent','tree_condition','crown_condition'].includes(id)){
    extra.push(
      {label:'Fire present', value:fmt(k.fire_presence_pct,1)+'%', unit:'SUs with fire evidence', ico:'🔥', bg:'#ffebee'},
      {label:'Env. problem', value:fmt(k.env_problem_pct,1)+'%', unit:'SUs with env. records', ico:'⚠️', bg:'#fff3e0'},
      {label:'Agent recorded', value:fmt(k.causative_agent_pct,1)+'%', unit:'SUs with causative agent', ico:'🦠', bg:'#fce4ec'},
      {label:'Deadwood', value:fmt(k.deadwood_presence_pct,1)+'%', unit:'SUs with deadwood', ico:'🪵', bg:'#efebe9'},
      {label:'Stump share', value:fmt((k.mean_stump_share||0)*100,1)+'%', unit:'mean of SU shares', ico:'🪓', bg:'#fff8e1'},
    );
  } else if(theme?.category==='Deadwood and regen'){
    extra.push(
      {label:'Deadwood', value:fmt(k.deadwood_presence_pct,1)+'%', unit:'SUs with deadwood', ico:'🪵', bg:'#efebe9'},
      {label:'Regen sum', value:fmt(k.sum_regen,0), unit:'count field sum', ico:'🌱', bg:'#e8f5e9'},
      {label:'Shrub presence', value:fmt(k.shrub_presence_pct,1)+'%', unit:'context', ico:'🌾', bg:'#fff8e1'},
      {label:'Tree presence', value:fmt(k.tree_presence_pct,1)+'%', unit:'context', ico:'🌲', bg:'#e8f5e9'},
      {label:'Carbon (prov.)', value:fmt(k.sum_tree_carbon_mg,1), unit:'Mg sum', ico:'⬛', bg:'#efebe9'},
    );
  } else {
    extra.push(
      {label:'Mean DBH', value:fmt(k.mean_dbh_cm,1), unit:'cm', ico:'📏', bg:'#e3f2fd'},
      {label:'Mean height', value:fmt(k.mean_height_m,1), unit:'m', ico:'📐', bg:'#f3e5f5'},
      {label:'Basal area', value:fmt(k.sum_basal_m2,1), unit:'m² sum', ico:'🪵', bg:'#efebe9'},
      {label:'Volume (prov.)', value:fmt(k.sum_volume_m3,1), unit:'m³ sum', ico:'📦', bg:'#e8eaf6'},
      {label:'AGB (prov.)', value:fmt(k.sum_tree_agb_mg,1), unit:'Mg sum', ico:'🌳', bg:'#e8f5e9'},
    );
  }
  return base.concat(extra).slice(0,8);
}

function renderKpis(){
  const theme = themeById(STATE.themeId);
  const k = kpiSource();
  const cards = cardsForTheme(theme, k);
  const el = document.getElementById('kpiStrip');
  el.innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="top">
        <div class="label">${c.label}</div>
        <div class="ico" style="background:${c.bg}">${c.ico}</div>
      </div>
      <div class="value">${c.value}</div>
      <div class="unit">${c.unit}</div>
    </div>`).join('');
  const scope = STATE.adminLevel === 'national' ? 'National'
    : (STATE.adminName ? `${STATE.adminLevel}: ${STATE.adminName}` : `${STATE.adminLevel}: all`);
  document.getElementById('scopeBadge').textContent = scope + ` · n=${fmt(k.n_su,0)} SU`;
}

function colorFor(theme, props){
  const col = theme.value_col;
  const kind = theme.kind;
  if(kind === 'binary'){
    const v = props[col];
    const yes = v===true || v==='True' || v===1;
    return yes ? '#2e7d32' : '#ef6c00';
  }
  if(kind === 'categorical'){
    const raw = String(props[col] ?? 'NA');
    let hash = 0;
    for(let i=0;i<raw.length;i++) hash = ((hash<<5)-hash)+raw.charCodeAt(i);
    const palette = ['#0072B2','#E69F00','#009E73','#D55E00','#CC79A7','#56B4E9','#F0E442','#882255','#44AA99','#117733'];
    return palette[Math.abs(hash)%palette.length];
  }
  if(kind === 'continuous'){
    const v = Number(props[col]);
    if(!Number.isFinite(v)) return '#9e9e9e';
    // relative colour needs vmax; approximate with log-ish bins on value itself
    const t = Math.max(0, Math.min(1, v / (STATE._vmax || 1)));
    if(t > 0.75) return '#08306b';
    if(t > 0.5) return '#2171b5';
    if(t > 0.25) return '#6baed6';
    return '#c6dbef';
  }
  return '#1b5e20';
}

function updateVmax(theme, feats){
  if(theme.kind !== 'continuous' || !theme.value_col){ STATE._vmax = 1; return; }
  const vals = feats.map(f => Number(f.properties[theme.value_col])).filter(v => Number.isFinite(v) && v>0).sort((a,b)=>a-b);
  if(!vals.length){ STATE._vmax = 1; return; }
  const idx = Math.min(vals.length-1, Math.floor(vals.length*0.95));
  STATE._vmax = vals[idx] || 1;
}

function renderLegend(theme){
  const el = document.getElementById('legend');
  if(theme.kind === 'binary'){
    el.innerHTML = `<div><span class="sw" style="background:#2e7d32"></span>Yes / present</div>
                    <div><span class="sw" style="background:#ef6c00"></span>No / absent</div>`;
  } else if(theme.kind === 'continuous'){
    el.innerHTML = `<div><b>${theme.title}</b></div>
      <div><span class="sw" style="background:#c6dbef"></span>Low</div>
      <div><span class="sw" style="background:#6baed6"></span>Mid</div>
      <div><span class="sw" style="background:#2171b5"></span>High</div>
      <div><span class="sw" style="background:#08306b"></span>Top ~5%</div>`;
  } else {
    el.innerHTML = `<div><b>${theme.title}</b></div><div>Categorical colours by class</div>`;
  }
}

function filteredVoronoi(){
  const feats = (STATE.data.voronoi && STATE.data.voronoi.features) || [];
  const level = STATE.adminLevel;
  const name = STATE.adminName;
  const q = (STATE.search || '').trim().toLowerCase();
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
    return {color:'#ffffff', weight:0.4, fillColor:c, fillOpacity:0.72};
  };
  const pointLayer = (feat, latlng) => {
    const c = colorFor(theme, feat.properties||{});
    return L.circleMarker(latlng, {
      radius: theme.kind==='continuous' ? 4 : 4.5,
      color: c, fillColor: c, fillOpacity: 0.85, weight: 0.6
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
    (theme.blurb || '') + ` · Representation: ${modeLabel}`;
  renderLegend(theme);
  renderKpis();
}

function fillThemeList(){
  const root = document.getElementById('themeList');
  const themes = STATE.data.themes || [];
  let html = '';
  let last = null;
  themes.forEach(t => {
    if(t.kind === 'special_plots') return; // single-map dashboard uses SU points for all themes
    if(t.category !== last){
      html += `<div class="cat">${t.category}</div>`;
      last = t.category;
    }
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
  if(first){
    first.classList.add('active');
    STATE.themeId = first.dataset.id;
  }
}

function fillAdminNames(){
  const sel = document.getElementById('adminName');
  const level = STATE.adminLevel;
  sel.innerHTML = '<option value="">All</option>';
  if(level === 'national'){
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  const rows = level === 'region' ? (STATE.data.by_region||[]) : (STATE.data.by_governorate||[]);
  rows.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r.name;
    opt.textContent = `${r.name} (n=${r.n_su})`;
    sel.appendChild(opt);
  });
}

// Map init
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
  STATE.adminLevel = e.target.value;
  STATE.adminName = '';
  fillAdminNames();
  redrawLayer();
});
document.getElementById('adminName').addEventListener('change', (e) => {
  STATE.adminName = e.target.value;
  redrawLayer();
});
document.getElementById('searchBox').addEventListener('input', (e) => {
  STATE.search = e.target.value;
  redrawLayer();
});
document.getElementById('geomMode').addEventListener('change', (e) => {
  STATE.geomMode = e.target.value;
  redrawLayer();
});

document.querySelectorAll('nav.tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav.tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if(btn.dataset.tab === 'reports'){
      window.open('../documents/NFI_national_geopipeline_report.html', '_blank');
    } else if(btn.dataset.tab === 'about'){
      alert('KSA NFI National Atlas\\nProvisional sample metrics from the national tabular universe.\\nAdmin levels: National, Region, Governorate (province).\\nNumbers are computed from atlas_data.json only.');
    } else if(btn.dataset.tab === 'analytics'){
      const k = kpiSource();
      alert('Analytics snapshot (current scope)\\nSU: '+k.n_su+'\\nTree presence %: '+fmt(k.tree_presence_pct,1)+'\\nShrub presence %: '+fmt(k.shrub_presence_pct,1)+'\\nMean DBH: '+fmt(k.mean_dbh_cm,1)+'\\nAGB sum Mg: '+fmt(k.sum_tree_agb_mg,1));
    }
  });
});

function boot(data){
  STATE.data = data;
  fillThemeList();
  fillAdminNames();
  redrawLayer();
  const feats = data.geojson.features || [];
  if(feats.length){
    const b = L.geoJSON(data.geojson).getBounds();
    if(b.isValid()) MAP.fitBounds(b.pad(0.05));
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
