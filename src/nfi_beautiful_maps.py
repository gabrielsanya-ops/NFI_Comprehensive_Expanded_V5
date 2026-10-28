# -*- coding: utf-8 -*-
"""
NFI-style beautiful interactive HTML maps (Folium).

Expanded to mirror the NCVC/FAO PDF atlas themes under
F:/1.KSA/1.Forest/10.NFI/4.Maps/pdf:

  TreeDensity, SpeciesDiversity, TreeHealth, DBH, VolPerTree, VolPerHa,
  Basal, AGB, BGB, TotalBiomass, Carbon (+ access, ownership, LUCC, stump).

Basemaps (no API key required):
  - OpenStreetMap
  - Esri World Imagery (free tile endpoint)
  - Google Satellite / Hybrid via mt*.google.com tile URLs (no API key;
    unofficial public tiles used by many Leaflet clients; may change ToS)

Flexible symbolization by theme: classified choropleth, continuous-like
quantile choropleth, categorical polygons, categorical points, graduated points.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Palettes / theme registry (aligned with poster PDF look)
# ---------------------------------------------------------------------------
DENSITY_COLORS = ["#d9f99d", "#86efac", "#22c55e", "#15803d", "#14532d"]
DIVERSITY_COLORS = ["#fde047", "#a5f3fc", "#86efac", "#65a30d", "#166534"]
DBH_COLORS = ["#fef3c7", "#fde68a", "#fbbf24", "#d97706", "#92400e"]
VOLUME_COLORS = ["#e0f2fe", "#7dd3fc", "#0ea5e9", "#0369a1", "#0c4a6e"]
BIOMASS_COLORS = ["#ecfccb", "#bef264", "#65a30d", "#3f6212", "#1a2e05"]
CARBON_COLORS = ["#f3e8ff", "#d8b4fe", "#a855f7", "#7e22ce", "#4c1d95"]
BASAL_COLORS = ["#ffedd5", "#fdba74", "#f97316", "#c2410c", "#7c2d12"]
ACCESS_COLORS = {
    "Inaccessible": "#f87171",
    "Bareland": "#e7e5e4",
    "Accessible": "#4ade80",
    "Other": "#94a3b8",
}
HEALTH_COLORS = {
    # Mapping Approach PDF p.8 - Tree health condition legend
    "Healthy": "#14532d",
    "Slightly affected": "#4ade80",
    "Not indicated": "#f9a8d4",
    "Severely affected": "#111827",
    "Dead/Dying tree": "#dc2626",
    # legacy aliases kept for older buckets
    "Dead/Dying": "#dc2626",
    "Damaged": "#ea580c",
    "Other": "#94a3b8",
}

# Office (red) vs Field (blue) - Mapping Approach PDF p.5
COORD_SOURCE_COLORS = {
    "Office": "#dc2626",
    "Field": "#2563eb",
    "Validated": "#0f766e",
}

# PDF-folder analogue -> atlas theme
# theme_id, title, value_col, palette, symbolization, layer_kind, pdf_analogue, category, blurb
ATLAS_THEMES = [
    # --- Coordinate QA first (Mapping Approach field↔office cross-check) ---
    ("coord_field_office", "FIELD VS OFFICE COORDINATES", None, COORD_SOURCE_COLORS,
     "coord_pairs", "plot_points",
     "MappingApproach.p5", "Coordinate QA",
     "Field GPS (blue) and office or database coordinates (red), with displacement links."),
    ("coord_displacement", "COORDINATE DISPLACEMENT", "coord_displacement_m",
     ["#ecfdf5", "#a7f3d0", "#34d399", "#f59e0b", "#dc2626"], "graduated_points", "plot_points",
     "MappingApproach.p5", "Coordinate QA",
     "Markers sized and coloured by field-to-office displacement in metres."),
    ("tree_density", "TREE DENSITY DISTRIBUTION", "density_trees_per_km2",
     ["#14532d", "#65a30d", "#facc15", "#f97316", "#b91c1c"], "choropleth_quantile", "su_poly",
     "1.TreeDensity", "Structure",
     "Quantile choropleth of trees per square kilometre, with an optional heat overlay."),
    ("species_diversity", "SPECIES DIVERSITY", "n_species", DIVERSITY_COLORS, "choropleth_quantile", "su_poly",
     "3.SpeciesDiversity", "Biodiversity",
     "Species richness by sampling unit, with an optional heat overlay."),
    ("tree_health_su", "TREE HEALTH BY SAMPLING UNIT", None, HEALTH_COLORS,
     "proportional_health", "su_points",
     "MappingApproach.p8", "Coordinate QA",
     "Proportional tree icons: colour shows health class, size and label show tree count."),
    ("tree_health", "TREE HEALTH", None, HEALTH_COLORS, "categorical_points", "tree_points",
     "5.TreeHealth", "Biodiversity",
     "Realistic tree icons by health class, with clusters and optional heat density."),
    ("dbh", "MEAN DBH BY SAMPLING UNIT", "mean_dbh_cm", DBH_COLORS, "choropleth_quantile", "su_poly",
     "6.DBH", "Structure", "Classed choropleth of mean diameter at breast height (cm)."),
    ("vol_per_tree", "VOLUME PER TREE (mean)", "mean_vol_tree_m3", VOLUME_COLORS, "choropleth_quantile", "su_poly",
     "7.VolPerTree", "Structure", "Mean volume per tree by sampling unit."),
    ("vol_per_ha", "VOLUME PER HECTARE (provisional)", "sum_vol_ha", VOLUME_COLORS, "choropleth_quantile", "su_poly",
     "8.VolPerHa", "Structure", "Provisional volume per hectare by sampling unit."),
    ("basal_area", "BASAL AREA (sum m2)", "sum_basal_m2", BASAL_COLORS, "choropleth_quantile", "su_poly",
     "9.Basal", "Structure", "Summed basal area by sampling unit."),
    ("agb", "ABOVE-GROUND BIOMASS (sum)", "sum_agb", BIOMASS_COLORS, "choropleth_quantile", "su_poly",
     "10.AGB", "Biomass & Carbon", "Above-ground biomass by sampling unit."),
    ("bgb", "BELOW-GROUND BIOMASS (sum)", "sum_bgb", BIOMASS_COLORS, "choropleth_quantile", "su_poly",
     "11.BGB", "Biomass & Carbon", "Below-ground biomass by sampling unit."),
    ("total_biomass", "TOTAL BIOMASS (sum)", "sum_total_biomass", BIOMASS_COLORS, "choropleth_quantile", "su_poly",
     "12.TotalBiomass", "Biomass & Carbon", "Total biomass by sampling unit."),
    ("carbon", "CARBON STOCK (sum)", "sum_carbon", CARBON_COLORS, "choropleth_quantile", "su_poly",
     "13.Carbon", "Biomass & Carbon", "Carbon stock by sampling unit."),
    ("tree_count", "TREE COUNT BY SAMPLING UNIT", "n_trees", DENSITY_COLORS, "choropleth_quantile", "su_poly",
     "1.TreeDensity", "Structure",
     "Absolute tree-record counts by sampling unit, with an optional heat overlay."),
    ("access", "PLOT ACCESSIBILITY", "access_class", ACCESS_COLORS, "categorical_poly", "su_poly",
     "access", "Access & Ownership", "Categorical polygon fill by access class."),
    ("ownership", "LAND OWNERSHIP", "owner_label", None, "categorical_poly", "su_poly",
     "ownership", "Access & Ownership", "Categorical ownership polygons."),
    ("lucc", "LAND USE / LAND COVER", "lucc_mode", None, "categorical_poly", "su_poly",
     "lucc", "Access & Ownership", "Modal land use and land cover class per sampling unit."),
    ("stump_share", "STUMP SHARE OF RECORDS", "stump_share",
     ["#fef9c3", "#fde047", "#eab308", "#ca8a04", "#854d0e"], "choropleth_quantile", "su_poly",
     "4.Deforestation", "Access & Ownership",
     "Stump share of records as a deforestation proxy."),
    ("species_points", "TREE SPECIES DISTRIBUTION", None, None, "categorical_points", "tree_points",
     "3.SpeciesDiversity", "Biodiversity",
     "Realistic tree icons by species (conifer or broadleaf), with clusters and heat density."),
    ("dbh_points", "DBH GRADUATED POINTS", "dbh_cm", DBH_COLORS, "graduated_points", "tree_points",
     "6.DBH", "Structure",
     "Tree icons sized by diameter at breast height, with clusters and heat density."),
]

def _make_su_uid(series: pd.Series) -> pd.Series:
    from nfi_audit import make_su_uid
    return make_su_uid(series)


# ---------------------------------------------------------------------------
# Basemaps (OSM + free satellite; Google tiles without API key)
# ---------------------------------------------------------------------------
def _map_summary_chart_b64(
    theme_id: str,
    *,
    trees: pd.DataFrame | None = None,
    su_metrics: pd.DataFrame | None = None,
    plot_df: pd.DataFrame | None = None,
) -> tuple[str, str] | None:
    """
    One compact chart (pie or bar) as base64 PNG for a map inset.
    Returns (title, data_uri) or None when a chart would add little value.
    """
    import base64
    import io
    import matplotlib.pyplot as plt

    title = ""
    fig = None
    try:
        if theme_id in {"tree_health", "tree_health_su"} and trees is not None:
            col = next((c for c in ["overall_tree_condition_label", "crown_condition_label"] if c in trees.columns), None)
            if not col:
                return None
            vc = trees[col].astype(str).value_counts().head(5)
            if len(vc) < 2:
                return None
            colors = [HEALTH_COLORS.get(str(k), "#94a3b8") for k in vc.index]
            # remap loose labels
            fig, ax = plt.subplots(figsize=(2.6, 2.6))
            ax.pie(vc.values, labels=[str(x)[:16] for x in vc.index], colors=colors,
                   autopct=lambda p: f"{p:.0f}%" if p >= 8 else "",
                   textprops={"fontsize": 7}, wedgeprops={"linewidth": 0.6, "edgecolor": "white"})
            ax.set_title("Health share", fontsize=9, fontweight="bold", pad=4)
            title = "Health share"

        elif theme_id in {"species_points", "species_diversity"} and trees is not None and "tree_species_scientific_name" in trees.columns:
            vc = trees["tree_species_scientific_name"].astype(str).value_counts().head(6)
            if len(vc) < 2:
                return None
            fig, ax = plt.subplots(figsize=(3.0, 2.4))
            labs = [str(x) if len(str(x)) <= 18 else str(x)[:16] + "…" for x in vc.index[::-1]]
            ax.barh(labs, vc.values[::-1], color="#0f766e", height=0.7)
            ax.set_xlabel("Count", fontsize=7)
            ax.tick_params(labelsize=7)
            ax.set_title("Top species", fontsize=9, fontweight="bold")
            title = "Top species"

        elif theme_id in {"access", "ownership", "lucc"} and su_metrics is not None:
            col = {"access": "access_class", "ownership": "owner_label", "lucc": "lucc_mode"}[theme_id]
            if col not in su_metrics.columns:
                return None
            vc = su_metrics[col].astype(str).value_counts().head(6)
            if len(vc) < 2:
                return None
            fig, ax = plt.subplots(figsize=(2.6, 2.6))
            ax.pie(vc.values, labels=[str(x)[:14] for x in vc.index],
                   autopct=lambda p: f"{p:.0f}%" if p >= 10 else "",
                   textprops={"fontsize": 7}, wedgeprops={"linewidth": 0.6, "edgecolor": "white"})
            ax.set_title(col.replace("_", " ").title(), fontsize=9, fontweight="bold")
            title = col.replace("_", " ").title()

        elif theme_id == "coord_field_office" and plot_df is not None and "coord_source" in plot_df.columns:
            vc = plot_df["coord_source"].astype(str).value_counts()
            if len(vc) < 1:
                return None
            fig, ax = plt.subplots(figsize=(2.6, 2.4))
            cols = [COORD_SOURCE_COLORS.get(str(k).title() if str(k) in ("field", "db") else str(k), "#64748b") for k in vc.index]
            # map db->Office, field->Field for colour
            paint = []
            for k in vc.index:
                kk = str(k).lower()
                paint.append(COORD_SOURCE_COLORS["Office"] if kk in {"db", "office"} else
                             COORD_SOURCE_COLORS["Field"] if kk == "field" else "#64748b")
            ax.bar([str(x) for x in vc.index], vc.values, color=paint)
            ax.set_ylabel("Plots", fontsize=7)
            ax.tick_params(labelsize=7)
            ax.set_title("Coordinate source", fontsize=9, fontweight="bold")
            title = "Coordinate source"

        elif theme_id in {"tree_density", "tree_count", "dbh"} and su_metrics is not None:
            col = {"tree_density": "density_trees_per_km2", "tree_count": "n_trees", "dbh": "mean_dbh_cm"}[theme_id]
            if col not in su_metrics.columns:
                return None
            v = pd.to_numeric(su_metrics[col], errors="coerce").dropna()
            if len(v) < 8:
                return None
            fig, ax = plt.subplots(figsize=(3.0, 2.3))
            ax.hist(v, bins=14, color="#1d4ed8", alpha=0.85, edgecolor="white", density=True)
            try:
                from scipy.stats import gaussian_kde
                xs = np.linspace(float(v.min()), float(v.max()), 120)
                ax.plot(xs, gaussian_kde(v)(xs), color="#0f172a", lw=1.4)
            except Exception:
                pass
            ax.set_xlabel(col.replace("_", " "), fontsize=7)
            ax.set_ylabel("Density", fontsize=7)
            ax.tick_params(labelsize=7)
            ax.set_title("Distribution", fontsize=9, fontweight="bold")
            title = "Distribution"
        else:
            return None

        if fig is None:
            return None
        fig.tight_layout(pad=0.3)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return title, f"data:image/png;base64,{b64}"
    except Exception:
        try:
            import matplotlib.pyplot as plt
            plt.close("all")
        except Exception:
            pass
        return None


def _add_chart_inset(m, theme_id: str, *, trees=None, su_metrics=None, plot_df=None) -> None:
    """Attach at most one small statistical inset (draggable) to avoid map clutter."""
    import folium

    packed = _map_summary_chart_b64(theme_id, trees=trees, su_metrics=su_metrics, plot_df=plot_df)
    if not packed:
        return
    title, uri = packed
    inner = f'<img src="{uri}" alt="{title}" style="width:100%;height:auto;display:block;border-radius:6px"/>'
    # Mid-left, below peel control, clear of legend (bottom-left)
    box = _panel_shell(
        inner, panel_id="nfi-chart", title=f"Summary · {title}",
        top="280px", left="12px", width="220px", accent="#e2e8f0", z=9995,
    )
    m.get_root().html.add_child(folium.Element(box))


def _add_basemaps(m, *, default: str = "imagery"):
    """
    Basemaps for notebook / HTML atlas (no paid API keys):
      Esri World Imagery, Google Satellite, Google Hybrid,
      plus Esri place-name / boundary reference overlays.
    """
    import folium

    layers = [
        ("Esri World Imagery",
         "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
         "Esri", default in {"imagery", "esri", "satellite"}),
        ("Google Satellite",
         "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
         "Google", default == "google"),
        ("Google Hybrid (named)",
         "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
         "Google", default == "hybrid"),
    ]
    for name, url, attr, show in layers:
        folium.TileLayer(
            tiles=url, attr=attr, name=name, max_zoom=20,
            control=True, show=show, overlay=False,
        ).add_to(m)

    # Country / city / place names over imagery (toggleable overlays)
    overlays = [
        ("Place names · countries & cities",
         "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/"
         "World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
         True),
        ("Place names · alternate",
         "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/"
         "World_Boundaries_and_Places_Alternate/MapServer/tile/{z}/{y}/{x}",
         False),
        ("Roads & transport labels",
         "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/"
         "World_Transportation/MapServer/tile/{z}/{y}/{x}",
         False),
    ]
    for name, url, show in overlays:
        folium.TileLayer(
            tiles=url, attr="Esri", name=name, max_zoom=19,
            overlay=True, control=True, show=show, opacity=0.95,
        ).add_to(m)
    return m


def _tree_icon_html(color: str, *, size: int = 22, kind: str = "broadleaf", label: str = "") -> str:
    """
    Near-realistic SVG tree pictogram (broadleaf / conifer / dead) tinted by ``color``.
    Used as Folium DivIcon content for health & species point maps.
    """
    color = color or "#166534"
    s = int(max(18, min(56, size)))
    trunk = "#5b3a29"
    if kind == "conifer":
        # Juniper / pine silhouette
        crown = (
            f'<polygon points="{s*0.5},{s*0.08} {s*0.18},{s*0.42} {s*0.82},{s*0.42}" fill="{color}"/>'
            f'<polygon points="{s*0.5},{s*0.22} {s*0.14},{s*0.58} {s*0.86},{s*0.58}" fill="{color}" opacity=".92"/>'
            f'<polygon points="{s*0.5},{s*0.38} {s*0.10},{s*0.74} {s*0.90},{s*0.74}" fill="{color}" opacity=".85"/>'
        )
    elif kind == "dead":
        crown = (
            f'<path d="M{s*0.5} {s*0.12} L{s*0.28} {s*0.34} M{s*0.5} {s*0.18} L{s*0.72} {s*0.36} '
            f'M{s*0.5} {s*0.28} L{s*0.22} {s*0.52} M{s*0.5} {s*0.30} L{s*0.78} {s*0.54}" '
            f'stroke="{color}" stroke-width="{max(1.5, s/18)}" fill="none" stroke-linecap="round"/>'
            f'<circle cx="{s*0.5}" cy="{s*0.14}" r="{s*0.06}" fill="{color}"/>'
        )
    else:
        # Broadleaf canopy with layered ellipses (Acacia-like)
        crown = (
            f'<ellipse cx="{s*0.50}" cy="{s*0.38}" rx="{s*0.38}" ry="{s*0.28}" fill="{color}" opacity=".95"/>'
            f'<ellipse cx="{s*0.34}" cy="{s*0.44}" rx="{s*0.22}" ry="{s*0.18}" fill="{color}" opacity=".88"/>'
            f'<ellipse cx="{s*0.66}" cy="{s*0.44}" rx="{s*0.22}" ry="{s*0.18}" fill="{color}" opacity=".88"/>'
            f'<ellipse cx="{s*0.50}" cy="{s*0.30}" rx="{s*0.20}" ry="{s*0.16}" fill="{color}"/>'
        )
    label_html = ""
    if label:
        label_html = (
            f'<div style="position:absolute;left:50%;bottom:-2px;transform:translateX(-50%);'
            f'background:rgba(15,23,42,.82);color:#fff;font:700 8px Segoe UI,Arial,sans-serif;'
            f'padding:0 3px;border-radius:3px;white-space:nowrap;">{label}</div>'
        )
    return (
        f'<div style="position:relative;width:{s}px;height:{s}px;line-height:0;">'
        f'<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}" xmlns="http://www.w3.org/2000/svg">'
        f'{crown}'
        f'<rect x="{s*0.44}" y="{s*0.68}" width="{s*0.12}" height="{s*0.26}" rx="{s*0.03}" fill="{trunk}"/>'
        f'<ellipse cx="{s*0.50}" cy="{s*0.94}" rx="{s*0.16}" ry="{s*0.04}" fill="{trunk}" opacity=".35"/>'
        f'</svg>{label_html}</div>'
    )


def _tree_kind_for_species(name: str) -> str:
    s = str(name or "").lower()
    if any(k in s for k in ("juniper", "pinus", "pine", "cupress", "cedrus", "conifer")):
        return "conifer"
    if any(k in s for k in ("dead", "dying", "stump")):
        return "dead"
    return "broadleaf"


def _tree_kind_for_health(label: str) -> str:
    s = str(label or "").lower()
    if any(k in s for k in ("dead", "dying")):
        return "dead"
    return "broadleaf"


def _add_heatmap_layer(m, latlons: list[list[float]], *, name: str = "Heat density", show: bool = False):
    """Kernel-style heat overlay (Folium HeatMap) for observation density."""
    if not latlons or len(latlons) < 5:
        return
    try:
        from folium.plugins import HeatMap
        HeatMap(
            latlons,
            name=name,
            min_opacity=0.25,
            max_zoom=14,
            radius=18,
            blur=22,
            gradient={0.2: "#0ea5e9", 0.45: "#22c55e", 0.7: "#eab308", 0.9: "#ef4444"},
            show=show,
        ).add_to(m)
    except Exception:
        pass


def _marker_cluster(name: str = "Clustered points", show: bool = True):
    from folium.plugins import MarkerCluster
    return MarkerCluster(
        name=name,
        show=show,
        options={
            "maxClusterRadius": 45,
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": False,
            "disableClusteringAtZoom": 15,
        },
    )


def _draggable_panels_js() -> str:
    """Shared JS: make .nfi-drag panels movable; keep them inside the viewport; avoid map pan while dragging."""
    return r"""
<script>
(function(){
  if (window.__nfiDragInit) return;
  window.__nfiDragInit = true;
  function clamp(v,a,b){return Math.max(a,Math.min(b,v));}
  function makeDraggable(el){
    if(!el || el.dataset.dragReady) return;
    el.dataset.dragReady = '1';
    el.style.position = 'fixed';
    el.style.cursor = 'default';
    var handle = el.querySelector('.nfi-drag-handle') || el;
    handle.style.cursor = 'move';
    var ox=0, oy=0, dragging=false;
    function onDown(e){
      if(e.target.closest('input,button,a,select,textarea,label')) return;
      dragging = true;
      var r = el.getBoundingClientRect();
      ox = (e.touches?e.touches[0].clientX:e.clientX) - r.left;
      oy = (e.touches?e.touches[0].clientY:e.clientY) - r.top;
      el.style.right = 'auto'; el.style.bottom = 'auto';
      el.style.left = r.left + 'px'; el.style.top = r.top + 'px';
      el.style.transform = 'none';
      el.classList.add('nfi-dragging');
      e.preventDefault(); e.stopPropagation();
    }
    function onMove(e){
      if(!dragging) return;
      var x = (e.touches?e.touches[0].clientX:e.clientX) - ox;
      var y = (e.touches?e.touches[0].clientY:e.clientY) - oy;
      var maxX = window.innerWidth - el.offsetWidth - 8;
      var maxY = window.innerHeight - el.offsetHeight - 8;
      el.style.left = clamp(x, 8, Math.max(8,maxX)) + 'px';
      el.style.top  = clamp(y, 8, Math.max(8,maxY)) + 'px';
      e.preventDefault(); e.stopPropagation();
    }
    function onUp(){ dragging=false; el.classList.remove('nfi-dragging'); }
    handle.addEventListener('mousedown', onDown);
    handle.addEventListener('touchstart', onDown, {passive:false});
    window.addEventListener('mousemove', onMove, {passive:false});
    window.addEventListener('touchmove', onMove, {passive:false});
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);
  }
  function deconflict(){
    var panels = Array.from(document.querySelectorAll('.nfi-drag'));
    // Simple cascade if two panels share nearly the same top-left
    panels.sort(function(a,b){
      return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
    });
    for(var i=0;i<panels.length;i++){
      for(var j=0;j<i;j++){
        var A=panels[i].getBoundingClientRect(), B=panels[j].getBoundingClientRect();
        var overlap = !(A.right<B.left+4 || A.left>B.right-4 || A.bottom<B.top+4 || A.top>B.bottom-4);
        if(overlap){
          panels[i].style.top = Math.min(window.innerHeight - A.height - 8, B.bottom + 10) + 'px';
          panels[i].style.bottom = 'auto';
          panels[i].style.transform = 'none';
        }
      }
    }
  }
  function boot(){
    document.querySelectorAll('.nfi-drag').forEach(makeDraggable);
    deconflict();
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 200);
  setTimeout(deconflict, 800);
})();
</script>
<style>
.nfi-drag{user-select:none; touch-action:none;}
.nfi-drag .nfi-drag-handle{cursor:move;}
.nfi-drag.nfi-dragging{opacity:.92; box-shadow:0 10px 28px rgba(0,0,0,.35)!important; z-index:10050!important;}
.nfi-drag .nfi-drag-hint{font-size:9px; opacity:.55; letter-spacing:.04em; text-transform:uppercase;}
.nfi-tree-icon{background:transparent!important;border:none!important;}
.leaflet-div-icon.nfi-tree-icon{background:transparent!important;border:none!important;}
</style>
"""


def _panel_shell(inner: str, *, panel_id: str, title: str, top=None, left=None, right=None, bottom=None,
                 width: str = "260px", accent: str = "#93c5fd", z: int = 9999) -> str:
    """Fixed chrome panel with drag handle; defaults placed to avoid mutual overlap."""
    pos = []
    if top is not None: pos.append(f"top:{top}")
    if left is not None: pos.append(f"left:{left}")
    if right is not None: pos.append(f"right:{right}")
    if bottom is not None: pos.append(f"bottom:{bottom}")
    pos_css = ";".join(pos)
    return f"""
    <div id="{panel_id}" class="nfi-drag" style="position:fixed;{pos_css};z-index:{z};
         background:rgba(15,23,42,.92);color:#e2e8f0;padding:0;border-radius:10px;
         font-family:Segoe UI,Arial,sans-serif;font-size:11px;width:{width};max-width:92vw;
         box-shadow:0 4px 14px rgba(0,0,0,.3);border:1px solid rgba(148,163,184,.4);
         max-height:46vh;display:flex;flex-direction:column;">
      <div class="nfi-drag-handle" style="padding:8px 10px 6px;border-bottom:1px solid rgba(148,163,184,.25);
           display:flex;justify-content:space-between;align-items:center;gap:8px;flex:0 0 auto;">
        <div style="font-weight:700;color:{accent};">{title}</div>
        <div class="nfi-drag-hint">drag</div>
      </div>
      <div style="padding:8px 10px 10px;overflow:auto;flex:1 1 auto;line-height:1.35;">{inner}</div>
    </div>
    """


def _add_cartographic_chrome(
    m,
    *,
    title: str,
    subtitle: str = "",
    legend_html: str = "",
    sources: str = "NFI cleansed tables, Asir SU GIS | Basemaps: Esri / Google",
    theme_id: str = "",
    pdf_analogue: str = "",
    locality_html: str = "",
) -> None:
    """Title, north arrow, legend, locality - all draggable, non-overlapping defaults."""
    import folium
    from folium.plugins import Fullscreen, MiniMap, MousePosition

    Fullscreen().add_to(m)
    try:
        MiniMap(
            tile_layer="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            toggle_display=True,
            position="bottomright",
            width=140,
            height=140,
            zoom_level_offset=-5,
        ).add_to(m)
    except Exception:
        try:
            inset = folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri", name="inset_esri", control=False,
            )
            MiniMap(tile_layer=inset, toggle_display=True, position="bottomright",
                    width=140, height=140, zoom_level_offset=-5).add_to(m)
        except Exception:
            pass

    MousePosition(
        position="bottomleft",
        separator=" | ",
        prefix="Lat/Lon:",
        lat_formatter="function(num) {return L.Util.formatNum(num, 5);}",
        lng_formatter="function(num) {return L.Util.formatNum(num, 5);}",
    ).add_to(m)

    today = date.today().isoformat()
    analogue = f"PDF analogue: {pdf_analogue}" if pdf_analogue else ""

    # Title bar - top centre (draggable)
    banner = f"""
    <div id="nfi-title" class="nfi-drag" style="position:fixed;top:10px;left:50%;transform:translateX(-50%);
         z-index:9999;background:linear-gradient(90deg,#111827 0%,#1f2937 100%);color:#f8fafc;
         padding:0;border-radius:10px;box-shadow:0 8px 24px rgba(15,23,42,.35);
         font-family:Segoe UI,Arial,sans-serif;text-align:center;min-width:420px;max-width:70vw;
         border:1px solid rgba(255,255,255,.12);">
      <div class="nfi-drag-handle" style="padding:8px 18px 4px;cursor:move;">
        <div style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;opacity:.7;">
          Kingdom of Saudi Arabia · NFI · GeoAI &nbsp;<span class="nfi-drag-hint">drag</span>
        </div>
        <div style="font-size:17px;font-weight:700;margin-top:2px;">{title}</div>
        <div style="font-size:11px;opacity:.88;margin-top:2px;">{subtitle}</div>
        <div style="font-size:10px;opacity:.65;margin-top:3px;">{analogue}</div>
      </div>
    </div>
    """

    # North - above minimap, clear of layer control (top-right)
    north = """
    <div id="nfi-north" class="nfi-drag" style="position:fixed;bottom:168px;right:280px;
         z-index:9998;background:rgba(255,255,255,.96);border:1px solid #334155;border-radius:10px;
         padding:8px 10px;text-align:center;font-family:Segoe UI,Arial,sans-serif;
         box-shadow:0 2px 10px rgba(0,0,0,.25);">
      <div class="nfi-drag-handle">
        <div style="font-size:26px;line-height:1;font-weight:700;color:#0f172a;">⬆</div>
        <div style="font-size:11px;font-weight:700;color:#0f172a;letter-spacing:.08em;">N</div>
        <div class="nfi-drag-hint" style="color:#64748b;">drag</div>
      </div>
    </div>
    """

    locality_box = ""
    if locality_html:
        # Bottom-right, stacked above the minimap so it never covers the layer control
        locality_box = _panel_shell(
            locality_html, panel_id="nfi-locality", title="Locality",
            bottom="168px", right="18px", width="250px", accent="#93c5fd", z=9997,
        )

    legend_inner = f"""
      {legend_html}
      <hr style="border:none;border-top:1px solid #475569;margin:8px 0;">
      <div style="opacity:.85;font-size:10px;">
        Scale bar · bottom-left &nbsp;|&nbsp; Minimap · bottom-right<br>
        Basemaps: Esri / Google Satellite / Google Hybrid<br>
        Toggle <b>Heat density</b> / <b>Clusters</b> in layer control<br>
        {sources}<br>
        Composed: {today} · theme={theme_id or 'custom'}
      </div>
    """
    # Legend bottom-left, above attribution / mouse position
    legend_box = _panel_shell(
        legend_inner, panel_id="nfi-legend", title="Legend",
        bottom="48px", left="12px", width="300px", accent="#bbf7d0", z=9996,
    )

    m.get_root().html.add_child(folium.Element(banner + north + locality_box + legend_box + _draggable_panels_js()))


def _add_opacity_peel_control(m, *, default_pct: int = 72) -> None:
    """Draggable layer-peel control (top-left, clear of title and legend)."""
    import folium

    map_name = m.get_name()
    default_pct = int(max(0, min(100, default_pct)))
    inner = f"""
      <label for="nfi-opacity" style="display:block;margin-bottom:4px;">
        Theme opacity: <span id="nfi-opacity-val">{default_pct}</span>%
      </label>
      <input id="nfi-opacity" type="range" min="0" max="100" value="{default_pct}"
             style="width:100%;accent-color:#9ca3af;">
      <div style="margin-top:8px;display:flex;gap:8px;align-items:center;">
        <input id="nfi-peel-basemap" type="checkbox">
        <label for="nfi-peel-basemap">Peel to basemap only</label>
      </div>
      <div style="opacity:.75;margin-top:6px;font-size:10px;">
        Fade thematic layers over Esri / Google imagery.
      </div>
    """
    box = _panel_shell(
        inner, panel_id="nfi-peel-box", title="Layer peel",
        top="118px", left="12px", width="220px", accent="#d1d5db", z=10000,
    )
    html = box + f"""
    <script>
    (function() {{
      function applyOpacity(o, peelOnly) {{
        var map = {map_name};
        if (!map) return;
        map.eachLayer(function(lyr) {{
          if (lyr instanceof L.TileLayer) return;
          var styleChild = function(child) {{
            if (!child || !child.setStyle) return;
            try {{
              if (peelOnly) {{
                child.setStyle({{fillOpacity: 0, opacity: 0}});
              }} else if (child instanceof L.CircleMarker) {{
                child.setStyle({{fillOpacity: o, opacity: Math.min(1, o + 0.15)}});
              }} else {{
                child.setStyle({{fillOpacity: o, opacity: Math.min(1, o + 0.2)}});
              }}
            }} catch (e) {{}}
          }};
          if (lyr instanceof L.LayerGroup || lyr instanceof L.FeatureGroup) {{
            lyr.eachLayer(styleChild);
          }} else {{
            styleChild(lyr);
          }}
        }});
      }}
      var slider = document.getElementById('nfi-opacity');
      var val = document.getElementById('nfi-opacity-val');
      var peel = document.getElementById('nfi-peel-basemap');
      function sync() {{
        var o = (+slider.value) / 100;
        val.textContent = slider.value;
        applyOpacity(o, peel.checked);
      }}
      if (slider) {{
        slider.addEventListener('input', sync);
        peel.addEventListener('change', sync);
        setTimeout(sync, 700);
      }}
    }})();
    </script>
    """
    m.get_root().html.add_child(folium.Element(html))


def _center_from_gdf(gdf):
    try:
        c = gdf.to_crs(4326).unary_union.centroid
        return [float(c.y), float(c.x)]
    except Exception:
        return [19.0, 42.5]


def _color_scale(values: pd.Series, palette: list[str]) -> tuple[list[float], list[str]]:
    v = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(v) == 0:
        return [0.0, 1.0], palette[:2]
    qs = np.unique(np.quantile(v, np.linspace(0, 1, len(palette) + 1)))
    if len(qs) < 2:
        qs = np.array([float(v.min()), float(v.max()) + 1e-6])
    return qs.tolist(), palette[: max(2, len(qs) - 1)]


def _bin_color(val, breaks, colors):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "#94a3b8"
    for i in range(len(colors)):
        lo = breaks[i]
        hi = breaks[i + 1] if i + 1 < len(breaks) else breaks[-1] + 1e9
        if lo <= val <= hi or (i == len(colors) - 1 and val >= lo):
            return colors[i]
    return colors[-1]


def _categorical_palette(levels: list[str]) -> dict[str, str]:
    import matplotlib
    import matplotlib.colors as mcolors

    n = max(len(levels), 1)
    try:
        cmap = matplotlib.colormaps.get_cmap("tab20").resampled(n)
    except Exception:
        import matplotlib.cm as cm
        cmap = cm.get_cmap("tab20", n)
    return {lev: mcolors.to_hex(cmap(i)) for i, lev in enumerate(levels)}


def _ensure_plot_xy(plot_df: pd.DataFrame | None, cfg: dict | None = None) -> pd.DataFrame | None:
    if plot_df is None or len(plot_df) == 0:
        return plot_df
    out = plot_df.copy()
    if {"lat_validated", "lon_validated"}.issubset(out.columns):
        return out
    try:
        from nfi_audit import plot_coordinate_qa, load_config
        cfg = cfg or load_config("config.yaml")
        qa = plot_coordinate_qa(out, cfg)
        if "PLOT_UID" in out.columns and "PLOT_UID" in qa.columns:
            add = qa[["PLOT_UID"] + [c for c in [
                "lat_validated", "lon_validated", "coord_source", "coord_confidence", "coord_displacement_m"
            ] if c in qa.columns]].drop_duplicates("PLOT_UID")
            out = out.drop(columns=[c for c in add.columns if c != "PLOT_UID" and c in out.columns], errors="ignore")
            out = out.merge(add, on="PLOT_UID", how="left")
            if {"lat_validated", "lon_validated"}.issubset(out.columns):
                return out
    except Exception:
        pass
    lat_c = next((c for c in [
        "lat_validated", "plot_info1_plot_coor1_y", "plot_info1_coor_db_y", "latitude", "lat"
    ] if c in out.columns), None)
    lon_c = next((c for c in [
        "lon_validated", "plot_info1_plot_coor1_x", "plot_info1_coor_db_x", "longitude", "lon"
    ] if c in out.columns), None)
    if lat_c and lon_c:
        out["lat_validated"] = pd.to_numeric(out[lat_c], errors="coerce")
        out["lon_validated"] = pd.to_numeric(out[lon_c], errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def build_su_map_metrics(
    trees: pd.DataFrame,
    asir_su,
    plot_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate tree / plot metrics to SU grain for choropleths."""
    su = asir_su.drop(columns="geometry", errors="ignore").copy()
    if "SU_UID" not in su.columns and "SU" in su.columns:
        su["SU_UID"] = _make_su_uid(su["SU"])
    su["SU_UID"] = _make_su_uid(su["SU_UID"])

    t = trees.copy()
    t["SU_UID"] = _make_su_uid(t["SU_UID"]) if "SU_UID" in t.columns else t.get("SU_UID")

    species_col = next(
        (c for c in ["tree_species_scientific_name", "species_scientific_name"] if c in t.columns), None
    )
    health_col = next(
        (c for c in ["overall_tree_condition_label", "crown_condition_label"] if c in t.columns), None
    )
    lucc_col = "lucc_label" if "lucc_label" in t.columns else None
    stump_col = "tree_or_stump_label" if "tree_or_stump_label" in t.columns else None

    metrics = t.groupby("SU_UID", dropna=False).size().rename("n_trees").reset_index()

    if species_col:
        sp = t.loc[t[species_col].notna()].groupby("SU_UID")[species_col].nunique().rename("n_species").reset_index()
        metrics = metrics.merge(sp, on="SU_UID", how="left")
    else:
        metrics["n_species"] = np.nan

    # Numeric engineering columns (raw or FV)
    num_specs = [
        ("mean_dbh_cm", "dbh_cm", "mean"),
        ("mean_height_m", "height_m", "mean"),
        ("mean_vol_tree_m3", "Vol/Tr", "mean"),
        ("sum_vol_tree_m3", "Vol/Tr", "sum"),
        ("sum_vol_ha", "Vol/Ha", "sum"),
        ("sum_basal_m2", "Basal area", "sum"),
        ("sum_agb", "AGB", "sum"),
        ("sum_bgb", "BGB", "sum"),
        ("sum_total_biomass", "Total_Biomass", "sum"),
        ("sum_carbon", "Carbon", "sum"),
    ]
    # also accept snake aliases
    alias = {
        "Vol/Tr": ["Vol/Tr", "vol_tree_m3"],
        "Vol/Ha": ["Vol/Ha", "vol_ha"],
        "Basal area": ["Basal area", "basal_area_m2"],
        "AGB": ["AGB", "agb"],
        "BGB": ["BGB", "bgb"],
        "Total_Biomass": ["Total_Biomass", "total_biomass"],
        "Carbon": ["Carbon", "carbon_ha_contrib"],
        "dbh_cm": ["dbh_cm", "tree_dbh"],
        "height_m": ["height_m", "tree_height"],
    }
    for out_name, src, how in num_specs:
        col = next((c for c in alias.get(src, [src]) if c in t.columns), None)
        if col is None:
            metrics[out_name] = np.nan
            continue
        s = pd.to_numeric(t[col], errors="coerce")
        tmp = t[["SU_UID"]].copy()
        tmp["_v"] = s
        if how == "mean":
            agg = tmp.groupby("SU_UID")["_v"].mean()
        else:
            agg = tmp.groupby("SU_UID")["_v"].sum()
        metrics = metrics.merge(agg.rename(out_name).reset_index(), on="SU_UID", how="left")

    if health_col:
        def _health_bucket(v):
            s = str(v).lower()
            if any(k in s for k in ("dead", "dying", "mort")):
                return "Dead/Dying"
            if any(k in s for k in ("health", "alive", "good", "live")):
                return "Healthy"
            if any(k in s for k in ("damag", "poor", "sick", "declin")):
                return "Damaged"
            return "Other"

        hh = t.copy()
        hh["_health"] = hh[health_col].map(_health_bucket)
        piv = hh.groupby(["SU_UID", "_health"]).size().unstack(fill_value=0).reset_index()
        metrics = metrics.merge(piv, on="SU_UID", how="left")

    if stump_col:
        st = t.copy()
        st["_is_stump"] = st[stump_col].astype(str).str.lower().eq("stump")
        share = st.groupby("SU_UID")["_is_stump"].mean().rename("stump_share").reset_index()
        metrics = metrics.merge(share, on="SU_UID", how="left")

    if lucc_col:
        mode_lucc = (
            t.groupby("SU_UID")[lucc_col]
            .agg(lambda s: s.dropna().astype(str).mode().iloc[0] if len(s.dropna()) else pd.NA)
            .rename("lucc_mode")
            .reset_index()
        )
        metrics = metrics.merge(mode_lucc, on="SU_UID", how="left")

    out = su.merge(metrics, on="SU_UID", how="left")
    for c in ["n_trees", "n_species"]:
        if c in out.columns:
            out[c] = out[c].fillna(0).astype(int)

    area = None
    for c in ["Area_H", "Area_H_attr", "area_h"]:
        if c in out.columns:
            area = pd.to_numeric(out[c], errors="coerce")
            break
    if area is not None:
        km2 = area / 100.0
        out["density_trees_per_km2"] = np.where(km2 > 0, out["n_trees"] / km2, np.nan)
    else:
        out["density_trees_per_km2"] = out["n_trees"].astype(float)

    if plot_df is not None:
        p = plot_df.copy()
        p["SU_UID"] = _make_su_uid(p["SU_UID"]) if "SU_UID" in p.columns else p.get("SU_UID")
        if "plot_info1_plot_access1_label" in p.columns:
            mode_access = (
                p.groupby("SU_UID")["plot_info1_plot_access1_label"]
                .agg(lambda s: s.dropna().astype(str).mode().iloc[0] if len(s.dropna()) else pd.NA)
                .rename("access_label")
                .reset_index()
            )
            out = out.merge(mode_access, on="SU_UID", how="left")
            out["access_class"] = out["access_label"].astype(str).map(
                lambda x: "Inaccessible"
                if "inaccessible" in x.lower() or "innaccessible" in x.lower()
                else ("Bareland" if "bare" in x.lower() else ("Accessible" if "access" in x.lower() else "Other"))
            )
        else:
            out["access_class"] = "Other"
        if "plot_info1_owner1_label" in p.columns:
            mode_own = (
                p.groupby("SU_UID")["plot_info1_owner1_label"]
                .agg(lambda s: s.dropna().astype(str).mode().iloc[0] if len(s.dropna()) else pd.NA)
                .rename("owner_label")
                .reset_index()
            )
            out = out.merge(mode_own, on="SU_UID", how="left")
    else:
        out["access_class"] = "Other"

    out["has_tree_record"] = out["n_trees"] > 0
    return out


# ---------------------------------------------------------------------------
# Symbolization engines
# ---------------------------------------------------------------------------
def _locality_info_html(su_metrics: pd.DataFrame | None, asir_su=None, grid=None) -> str:
    """Build a compact locality panel (country / region / governorate / SU counts)."""
    parts = [
        "<b>Country:</b> Kingdom of Saudi Arabia",
        "<b>Programme:</b> National Forest Inventory (NFI)",
        "<b>Analytical frame:</b> Asir SU grid (15/30 min)",
    ]
    src = None
    for cand in (su_metrics, asir_su, grid):
        if cand is None:
            continue
        try:
            df = cand.drop(columns="geometry", errors="ignore")
        except Exception:
            df = cand
        if hasattr(df, "columns"):
            src = df
            break
    if src is not None:
        reg_col = next((c for c in ["region", "reg_e"] if c in src.columns), None)
        gov_col = next((c for c in ["governorate", "gover_e"] if c in src.columns), None)
        if reg_col:
            regs = (
                src[reg_col].dropna().astype(str)
                .replace({"Aseer": "Asir", "Ar Riyad": "Ar Riyadh"})
                .value_counts()
            )
            top = ", ".join(f"{k} ({int(v)})" for k, v in regs.head(6).items())
            parts.append(f"<b>Regions (SU cells):</b> {top}")
        if gov_col:
            n_gov = int(src[gov_col].nunique(dropna=True))
            parts.append(f"<b>Governorates:</b> {n_gov}")
        if "SU_UID" in src.columns:
            parts.append(f"<b>Sampling units:</b> {int(src['SU_UID'].nunique())}")
        if "n_trees" in src.columns:
            parts.append(f"<b>Tree records (sum):</b> {int(pd.to_numeric(src['n_trees'], errors='coerce').fillna(0).sum()):,}")
    try:
        bb = (grid if grid is not None else asir_su).to_crs(4326).total_bounds
        parts.append(
            f"<b>Extent:</b> {bb[1]:.3f}-{bb[3]:.3f} N, {bb[0]:.3f}-{bb[2]:.3f} E"
        )
    except Exception:
        pass
    return "<br>".join(parts)


def render_nfi_map(
    *,
    asir_grid,
    asir_su,
    su_metrics: pd.DataFrame | None = None,
    trees: pd.DataFrame | None = None,
    plot_df: pd.DataFrame | None = None,
    theme_id: str,
    title: str,
    value_col: str | None,
    palette,
    symbolization: str,
    layer_kind: str,
    pdf_analogue: str = "",
    out_path: Path | None = None,
    basemap_default: str = "imagery",
    max_points: int = 8000,
    show_su_labels: bool = True,
) -> str:
    """
    Flexible map renderer.

    symbolization:
      - choropleth_quantile
      - categorical_poly
      - categorical_points (health / species)
      - graduated_points (size ~ value)
    """
    import folium

    grid = asir_grid.to_crs(4326).copy()
    if "SU_UID" not in grid.columns and "SU" in grid.columns:
        grid["SU_UID"] = _make_su_uid(grid["SU"])
    grid["SU_UID"] = _make_su_uid(grid["SU_UID"])
    su = asir_su.to_crs(4326)
    center = _center_from_gdf(grid)

    m = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
    _add_basemaps(m, default=basemap_default)

    # Boundary outline always available
    folium.GeoJson(
        su.__geo_interface__,
        name="SU points / universe",
        style_function=lambda f: {"fillOpacity": 0.0, "color": "#f8fafc", "weight": 1.0},
        show=False,
    ).add_to(m)

    legend_html = ""
    subtitle = f"Symbolization: {symbolization.replace('_', ' ')} | Layer: {layer_kind}"

    if symbolization == "choropleth_quantile" and layer_kind == "su_poly":
        if su_metrics is None or value_col is None or value_col not in su_metrics.columns:
            raise ValueError(f"Missing metric column for choropleth: {value_col}")
        palette = palette or DENSITY_COLORS
        mcols = list(dict.fromkeys(
            [c for c in ["SU_UID", value_col, "n_trees", "n_species", "access_class",
                         "reg_e", "gover_e", "has_tree_record"] if c in su_metrics.columns]
        ))
        drop_on_grid = [c for c in mcols if c != "SU_UID" and c in grid.columns]
        g = grid.drop(columns=drop_on_grid, errors="ignore").merge(
            su_metrics[mcols].drop_duplicates("SU_UID"), on="SU_UID", how="left"
        )
        vals = g[value_col]
        if isinstance(vals, pd.DataFrame):
            vals = vals.iloc[:, 0]
        vals = pd.to_numeric(vals, errors="coerce")
        breaks, colors = _color_scale(vals.loc[vals > 0], palette)

        def style_fn(feature):
            props = feature["properties"]
            v = props.get(value_col)
            access = str(props.get("access_class", ""))
            try:
                v = float(v) if v is not None else np.nan
            except Exception:
                v = np.nan
            if access == "Inaccessible" and (np.isnan(v) or v == 0):
                fill = ACCESS_COLORS["Inaccessible"]
            elif np.isnan(v) or v == 0:
                fill = ACCESS_COLORS["Bareland"]
            else:
                fill = _bin_color(v, breaks, colors)
            return {"fillColor": fill, "color": "#0f172a", "weight": 0.65, "fillOpacity": 0.74}

        tip_fields = [c for c in ["SU_UID", value_col, "n_trees", "n_species", "reg_e", "gover_e"] if c in g.columns]
        folium.GeoJson(
            g.__geo_interface__,
            name=title[:48],
            style_function=style_fn,
            tooltip=folium.GeoJsonTooltip(fields=tip_fields, aliases=tip_fields, sticky=True),
            highlight_function=lambda x: {"weight": 2.4, "color": "#fbbf24", "fillOpacity": 0.88},
        ).add_to(m)

        if show_su_labels:
            label_group = folium.FeatureGroup(name="SU value labels", show=True)
            try:
                cents = g.copy()
                cents["geometry"] = cents.geometry.centroid
                for _, row in cents.iterrows():
                    if row.geometry is None or row.geometry.is_empty:
                        continue
                    try:
                        v = float(row.get(value_col))
                        label = f"{v:.1f}" if abs(v) < 100 else f"{int(round(v))}"
                    except Exception:
                        continue
                    if not np.isfinite(v) or v == 0:
                        continue
                    folium.Marker(
                        [row.geometry.y, row.geometry.x],
                        icon=folium.DivIcon(
                            html=f"""<div style="background:rgba(255,255,255,.92);border:1px solid #14532d;
                            border-radius:999px;min-width:28px;height:28px;line-height:28px;padding:0 4px;
                            text-align:center;font-size:9px;font-weight:700;color:#14532d;">{label}</div>"""
                        ),
                    ).add_to(label_group)
            except Exception:
                pass
            label_group.add_to(m)

        items = [("Bareland / zero", ACCESS_COLORS["Bareland"]),
                 ("Inaccessible (no trees)", ACCESS_COLORS["Inaccessible"])]
        for i, col in enumerate(colors):
            lo, hi = breaks[i], breaks[min(i + 1, len(breaks) - 1)]
            items.append((f"{lo:.3g} - {hi:.3g}", col))
        legend_html = "<br>".join(
            f'<i style="background:{c};width:14px;height:14px;display:inline-block;margin-right:6px;border:1px solid #334155;"></i>{lab}'
            for lab, c in items
        )
        # Observation heat under density / count choropleths when tree points exist
        if theme_id in {"tree_density", "tree_count", "species_diversity"} and trees is not None:
            try:
                tt = trees.copy()
                pdf = _ensure_plot_xy(plot_df)
                if pdf is not None and {"PLOT_UID", "lat_validated", "lon_validated"}.issubset(pdf.columns):
                    tt = tt.drop(columns=["lat_validated", "lon_validated"], errors="ignore").merge(
                        pdf[["PLOT_UID", "lat_validated", "lon_validated"]].drop_duplicates("PLOT_UID"),
                        on="PLOT_UID", how="left",
                    )
                if {"lat_validated", "lon_validated"}.issubset(tt.columns):
                    pts = (
                        tt.assign(
                            _lat=pd.to_numeric(tt["lat_validated"], errors="coerce"),
                            _lon=pd.to_numeric(tt["lon_validated"], errors="coerce"),
                        )
                        .dropna(subset=["_lat", "_lon"])
                    )
                    if len(pts) > max_points:
                        pts = pts.sample(max_points, random_state=42)
                    _add_heatmap_layer(
                        m, pts[["_lat", "_lon"]].values.tolist(),
                        name="Heat density (tree observations)", show=False,
                    )
            except Exception:
                pass

    elif symbolization == "categorical_poly" and layer_kind == "su_poly":
        if su_metrics is None or value_col is None or value_col not in su_metrics.columns:
            raise ValueError(f"Missing categorical column: {value_col}")
        mcols = list(dict.fromkeys([c for c in ["SU_UID", value_col, "reg_e", "gover_e", "n_trees"] if c in su_metrics.columns]))
        drop_on_grid = [c for c in mcols if c != "SU_UID" and c in grid.columns]
        g = grid.drop(columns=drop_on_grid, errors="ignore").merge(
            su_metrics[mcols].drop_duplicates("SU_UID"), on="SU_UID", how="left"
        )
        levels = [str(x) for x in g[value_col].dropna().astype(str).value_counts().head(12).index.tolist()]
        if isinstance(palette, dict):
            colors = {k: palette.get(k, "#94a3b8") for k in levels}
            for k, v in palette.items():
                colors.setdefault(k, v)
        else:
            colors = _categorical_palette(levels)

        def style_fn(feature):
            lab = str(feature["properties"].get(value_col, "Other"))
            fill = colors.get(lab, "#94a3b8")
            return {"fillColor": fill, "color": "#0f172a", "weight": 0.65, "fillOpacity": 0.72}

        tip_fields = [c for c in ["SU_UID", value_col, "n_trees", "reg_e", "gover_e"] if c in g.columns]
        folium.GeoJson(
            g.__geo_interface__,
            name=title[:48],
            style_function=style_fn,
            tooltip=folium.GeoJsonTooltip(fields=tip_fields, aliases=tip_fields, sticky=True),
        ).add_to(m)
        legend_html = "<br>".join(
            f'<i style="background:{c};width:14px;height:14px;display:inline-block;margin-right:6px;border:1px solid #334155;"></i>{lab}'
            for lab, c in colors.items()
        )

    elif symbolization == "categorical_points" and layer_kind == "tree_points":
        if trees is None:
            raise ValueError("trees required for point symbolization")
        t = trees.copy()
        plot_df = _ensure_plot_xy(plot_df)
        if {"lat_validated", "lon_validated"}.issubset(t.columns):
            lat_c, lon_c = "lat_validated", "lon_validated"
        elif plot_df is not None and {"PLOT_UID", "lat_validated", "lon_validated"}.issubset(plot_df.columns):
            p = plot_df[["PLOT_UID", "lat_validated", "lon_validated"]].drop_duplicates("PLOT_UID")
            t = t.drop(columns=["lat_validated", "lon_validated"], errors="ignore").merge(p, on="PLOT_UID", how="left")
            lat_c, lon_c = "lat_validated", "lon_validated"
        else:
            raise ValueError("Need lat_validated/lon_validated for point maps")

        t["_lat"] = pd.to_numeric(t[lat_c], errors="coerce")
        t["_lon"] = pd.to_numeric(t[lon_c], errors="coerce")
        t = t.dropna(subset=["_lat", "_lon"])

        if theme_id == "tree_health":
            health_col = next(
                (c for c in ["overall_tree_condition_label", "crown_condition_label"] if c in t.columns), None
            )
            if health_col is None:
                raise ValueError("No health label column")

            def _bucket(v):
                s = str(v).lower()
                if any(k in s for k in ("dead", "dying", "mort")):
                    return "Dead/Dying tree"
                if "severe" in s:
                    return "Severely affected"
                if any(k in s for k in ("slight", "minor", "light")):
                    return "Slightly affected"
                if any(k in s for k in ("health", "alive", "good", "live")) and "not" not in s:
                    return "Healthy"
                if any(k in s for k in ("not indicated", "unknown", "n/a", "na", "none", "nan")):
                    return "Not indicated"
                if any(k in s for k in ("damag", "poor", "sick", "declin", "affect")):
                    return "Severely affected" if "severe" in s else "Slightly affected"
                return "Not indicated"

            t["_cat"] = t[health_col].map(_bucket)
            colors = palette if isinstance(palette, dict) else HEALTH_COLORS
            # Keep legend order like Mapping Approach p.8
            order = ["Healthy", "Slightly affected", "Not indicated", "Severely affected", "Dead/Dying tree"]
            colors = {k: colors.get(k, "#94a3b8") for k in order if k in set(t["_cat"])} | {
                k: v for k, v in colors.items() if k in set(t["_cat"]) and k not in order
            }
        else:
            sp_col = "tree_species_scientific_name"
            if sp_col not in t.columns:
                raise ValueError("species column missing")
            top = t[sp_col].value_counts().head(8).index.tolist()
            t["_cat"] = t[sp_col].where(t[sp_col].isin(top), other="Other")
            colors = _categorical_palette(top + ["Other"])

        if len(t) > max_points:
            t = t.sample(max_points, random_state=42)

        use_tree_icons = theme_id in {"tree_health", "species_points"}
        counts = t["_cat"].value_counts().to_dict()
        heat_pts = t[["_lat", "_lon"]].astype(float).values.tolist()

        # Clustered individual symbols (tree icons for health / species)
        cluster = _marker_cluster(
            name=("Tree icons · clustered" if use_tree_icons else "Points · clustered"),
            show=True,
        )
        for cls, color in colors.items():
            sub = t.loc[t["_cat"] == cls]
            if not len(sub):
                continue
            for _, row in sub.iterrows():
                popup = folium.Popup(
                    f"<b>{cls}</b><br>SU: {row.get('SU_UID','')}<br>"
                    f"{row.get('tree_species_scientific_name','')}",
                    max_width=280,
                )
                if use_tree_icons:
                    if theme_id == "tree_health":
                        kind = _tree_kind_for_health(cls)
                    else:
                        kind = _tree_kind_for_species(row.get("tree_species_scientific_name", cls))
                    icon = folium.DivIcon(
                        html=_tree_icon_html(color, size=20, kind=kind),
                        icon_size=(20, 20),
                        icon_anchor=(10, 18),
                        class_name="nfi-tree-icon",
                    )
                    folium.Marker(
                        [row["_lat"], row["_lon"]], icon=icon, popup=popup,
                    ).add_to(cluster)
                else:
                    folium.CircleMarker(
                        [row["_lat"], row["_lon"]],
                        radius=3.5, color=color, fill=True, fill_color=color,
                        fill_opacity=0.85, weight=0.4, popup=popup,
                    ).add_to(cluster)
        cluster.add_to(m)
        _add_heatmap_layer(m, heat_pts, name="Heat density (observations)", show=False)

        # Legend with mini tree icons for health/species
        if use_tree_icons:
            legend_bits = []
            for k, c in colors.items():
                if not counts.get(k, 0):
                    continue
                kind = _tree_kind_for_health(k) if theme_id == "tree_health" else _tree_kind_for_species(k)
                mini = _tree_icon_html(c, size=18, kind=kind)
                legend_bits.append(
                    f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0;">'
                    f'{mini}<span>{k} ({counts.get(k, 0)})</span></div>'
                )
            legend_html = "".join(legend_bits) + (
                "<div style='margin-top:6px;font-size:10px;opacity:.8'>"
                "Tree icons · toggle <b>Heat density</b> / zoom to uncluster</div>"
            )
        else:
            legend_html = "<br>".join(
                f'<i style="background:{c};width:12px;height:12px;display:inline-block;border-radius:50%;margin-right:6px;"></i>'
                f'{k} ({counts.get(k, 0)})'
                for k, c in colors.items() if counts.get(k, 0)
            )

    elif symbolization == "graduated_points" and layer_kind == "tree_points":
        if trees is None or value_col is None:
            raise ValueError("trees + value_col required for graduated points")
        t = trees.copy()
        plot_df = _ensure_plot_xy(plot_df)
        if {"lat_validated", "lon_validated"}.issubset(t.columns):
            lat_c, lon_c = "lat_validated", "lon_validated"
        elif plot_df is not None and {"PLOT_UID", "lat_validated", "lon_validated"}.issubset(plot_df.columns):
            p = plot_df[["PLOT_UID", "lat_validated", "lon_validated"]].drop_duplicates("PLOT_UID")
            t = t.drop(columns=["lat_validated", "lon_validated"], errors="ignore").merge(p, on="PLOT_UID", how="left")
            lat_c, lon_c = "lat_validated", "lon_validated"
        else:
            raise ValueError("Need coordinates for graduated points")

        # resolve value column aliases
        aliases = {
            "dbh_cm": ["dbh_cm", "tree_dbh"],
            "Vol/Tr": ["Vol/Tr", "vol_tree_m3"],
        }
        col = next((c for c in aliases.get(value_col, [value_col]) if c in t.columns), None)
        if col is None:
            raise ValueError(f"value column missing: {value_col}")
        t["_lat"] = pd.to_numeric(t[lat_c], errors="coerce")
        t["_lon"] = pd.to_numeric(t[lon_c], errors="coerce")
        t["_v"] = pd.to_numeric(t[col], errors="coerce")
        t = t.dropna(subset=["_lat", "_lon", "_v"])
        if len(t) > max_points:
            t = t.sample(max_points, random_state=42)
        palette = palette or DBH_COLORS
        breaks, colors = _color_scale(t["_v"], palette)
        vmin, vmax = float(t["_v"].min()), float(t["_v"].max())
        use_icons = theme_id in {"dbh_points"}
        cluster = _marker_cluster(name="DBH · clustered tree icons" if use_icons else "Graduated · clustered", show=True)
        heat_pts = []
        for _, row in t.iterrows():
            v = float(row["_v"])
            fill = _bin_color(v, breaks, colors)
            heat_pts.append([row["_lat"], row["_lon"]])
            popup = f"{col}={v:.2f}<br>SU {row.get('SU_UID','')}"
            if use_icons:
                # Size icon by DBH; conifer if Juniper etc.
                px = int(22 + 20 * ((v - vmin) / (vmax - vmin + 1e-9)))
                kind = _tree_kind_for_species(row.get("tree_species_scientific_name", ""))
                icon = folium.DivIcon(
                    html=_tree_icon_html(fill, size=px, kind=kind, label=f"{v:.0f}"),
                    icon_size=(px, px),
                    icon_anchor=(px // 2, px - 2),
                    class_name="nfi-tree-icon",
                )
                folium.Marker([row["_lat"], row["_lon"]], icon=icon, popup=popup).add_to(cluster)
            else:
                radius = 2.5 + 10.0 * ((v - vmin) / (vmax - vmin + 1e-9))
                folium.CircleMarker(
                    [row["_lat"], row["_lon"]],
                    radius=radius, color=fill, fill=True, fill_color=fill, fill_opacity=0.7, weight=0.3,
                    popup=popup,
                ).add_to(cluster)
        cluster.add_to(m)
        _add_heatmap_layer(m, heat_pts, name="Heat density (observations)", show=False)
        legend_html = (
            ("Tree icon size ~ " + col + "<br>") if use_icons else f"Marker size ~ {col}<br>"
        ) + "<br>".join(
            f'<i style="background:{c};width:14px;height:14px;display:inline-block;margin-right:6px;border:1px solid #334155;"></i>'
            f'{breaks[i]:.3g} - {breaks[min(i+1, len(breaks)-1)]:.3g}'
            for i, c in enumerate(colors)
        )

    elif symbolization == "coord_pairs" and layer_kind == "plot_points":
        # Mapping Approach p.5 - Field (blue) vs Office (red)
        plot_df = _ensure_plot_xy(plot_df)
        if plot_df is None:
            raise ValueError("plot_df required for field↔office coordinate map")
        p = plot_df.copy()
        for src, dst in [
            ("plot_info1_plot_coor1_x", "lon_field_orig"),
            ("plot_info1_plot_coor1_y", "lat_field_orig"),
            ("plot_info1_coor_db_x", "lon_db_orig"),
            ("plot_info1_coor_db_y", "lat_db_orig"),
        ]:
            if dst not in p.columns and src in p.columns:
                p[dst] = p[src]
        need = ["lon_field_orig", "lat_field_orig", "lon_db_orig", "lat_db_orig"]
        for c in need:
            if c not in p.columns:
                raise ValueError(f"Missing {c} for coord_pairs map")
            p[c] = pd.to_numeric(p[c], errors="coerce")
        colors = palette if isinstance(palette, dict) else COORD_SOURCE_COLORS
        links = folium.FeatureGroup(name="Field↔Office links", show=True)
        office_fg = folium.FeatureGroup(name="Office / DB coordinates", show=True)
        field_fg = folium.FeatureGroup(name="Field GPS coordinates", show=True)
        n_pair = 0
        for _, row in p.iterrows():
            of_ok = np.isfinite(row["lon_db_orig"]) and np.isfinite(row["lat_db_orig"])
            fi_ok = np.isfinite(row["lon_field_orig"]) and np.isfinite(row["lat_field_orig"])
            if of_ok:
                folium.CircleMarker(
                    [row["lat_db_orig"], row["lon_db_orig"]],
                    radius=4.5, color=colors.get("Office", "#dc2626"),
                    fill=True, fill_color=colors.get("Office", "#dc2626"),
                    fill_opacity=0.85, weight=0.5,
                    popup=f"Office<br>{row.get('PLOT_UID','')}",
                ).add_to(office_fg)
            if fi_ok:
                folium.CircleMarker(
                    [row["lat_field_orig"], row["lon_field_orig"]],
                    radius=4.5, color=colors.get("Field", "#2563eb"),
                    fill=True, fill_color=colors.get("Field", "#2563eb"),
                    fill_opacity=0.85, weight=0.5,
                    popup=f"Field<br>{row.get('PLOT_UID','')}",
                ).add_to(field_fg)
            if of_ok and fi_ok:
                n_pair += 1
                folium.PolyLine(
                    [[row["lat_db_orig"], row["lon_db_orig"]],
                     [row["lat_field_orig"], row["lon_field_orig"]]],
                    color="#64748b", weight=1.0, opacity=0.55,
                ).add_to(links)
        office_fg.add_to(m)
        field_fg.add_to(m)
        links.add_to(m)
        legend_html = (
            f'<i style="background:{colors.get("Office","#dc2626")};width:12px;height:12px;'
            f'display:inline-block;border-radius:50%;margin-right:6px;"></i>Office / DB<br>'
            f'<i style="background:{colors.get("Field","#2563eb")};width:12px;height:12px;'
            f'display:inline-block;border-radius:50%;margin-right:6px;"></i>Field GPS<br>'
            f'<span style="color:#64748b">|</span> Displacement link (n={n_pair})'
        )
        subtitle = f"Field↔office cross-check | paired plots={n_pair}"

    elif symbolization == "graduated_points" and layer_kind == "plot_points":
        plot_df = _ensure_plot_xy(plot_df)
        if plot_df is None:
            raise ValueError("plot_df required for displacement map")
        p = plot_df.copy()
        if "coord_displacement_m" not in p.columns:
            raise ValueError("coord_displacement_m missing - run plot_coordinate_qa first")
        if not {"lat_validated", "lon_validated"}.issubset(p.columns):
            raise ValueError("lat_validated/lon_validated required")
        p["_lat"] = pd.to_numeric(p["lat_validated"], errors="coerce")
        p["_lon"] = pd.to_numeric(p["lon_validated"], errors="coerce")
        p["_v"] = pd.to_numeric(p["coord_displacement_m"], errors="coerce")
        p = p.dropna(subset=["_lat", "_lon", "_v"])
        if p.empty:
            raise ValueError("No displacement values to map")
        palette = palette or ["#ecfdf5", "#a7f3d0", "#34d399", "#f59e0b", "#dc2626"]
        breaks, colors = _color_scale(p["_v"], palette)
        vmin, vmax = float(p["_v"].min()), float(p["_v"].max())
        fg = folium.FeatureGroup(name="Displacement (m)", show=True)
        for _, row in p.iterrows():
            v = float(row["_v"])
            radius = 3.0 + 12.0 * ((v - vmin) / (vmax - vmin + 1e-9))
            fill = _bin_color(v, breaks, colors)
            folium.CircleMarker(
                [row["_lat"], row["_lon"]],
                radius=radius, color=fill, fill=True, fill_color=fill,
                fill_opacity=0.75, weight=0.4,
                popup=f"Δ={v:.1f} m<br>{row.get('PLOT_UID','')}",
            ).add_to(fg)
        fg.add_to(m)
        legend_html = "Marker size ~ displacement (m)<br>" + "<br>".join(
            f'<i style="background:{c};width:14px;height:14px;display:inline-block;margin-right:6px;border:1px solid #334155;"></i>'
            f'{breaks[i]:.3g} - {breaks[min(i+1, len(breaks)-1)]:.3g} m'
            for i, c in enumerate(colors)
        )

    elif symbolization == "proportional_health" and layer_kind == "su_points":
        # Mapping Approach p.8 - proportional circles coloured by health, labelled with counts
        if trees is None:
            raise ValueError("trees required for proportional health map")
        t = trees.copy()
        health_col = next(
            (c for c in ["overall_tree_condition_label", "crown_condition_label"] if c in t.columns), None
        )
        if health_col is None or "SU_UID" not in t.columns:
            raise ValueError("Need health label + SU_UID")

        def _bucket(v):
            s = str(v).lower()
            if any(k in s for k in ("dead", "dying", "mort")):
                return "Dead/Dying tree"
            if "severe" in s:
                return "Severely affected"
            if any(k in s for k in ("slight", "minor", "light")):
                return "Slightly affected"
            if any(k in s for k in ("health", "alive", "good", "live")) and "not" not in s:
                return "Healthy"
            if any(k in s for k in ("not indicated", "unknown", "n/a", "na", "none", "nan")):
                return "Not indicated"
            if any(k in s for k in ("damag", "poor", "sick", "declin", "affect")):
                return "Slightly affected"
            return "Not indicated"

        t["_health"] = t[health_col].map(_bucket)
        t["SU_UID"] = _make_su_uid(t["SU_UID"])
        # Modal health + count per SU
        agg = (
            t.groupby("SU_UID")
            .agg(n_trees=("_health", "size"), health=("_health", lambda s: s.value_counts().index[0]))
            .reset_index()
        )
        g = asir_su.to_crs(4326).copy()
        if "SU_UID" not in g.columns and "SU" in g.columns:
            g["SU_UID"] = _make_su_uid(g["SU"])
        g["SU_UID"] = _make_su_uid(g["SU_UID"])
        # Prefer polygon centroids if grid provided
        grid_c = asir_grid.to_crs(4326).copy()
        if "SU_UID" not in grid_c.columns and "SU" in grid_c.columns:
            grid_c["SU_UID"] = _make_su_uid(grid_c["SU"])
        grid_c["SU_UID"] = _make_su_uid(grid_c["SU_UID"])
        cents = grid_c.copy()
        cents["geometry"] = cents.geometry.centroid
        cents = cents.merge(agg, on="SU_UID", how="inner")
        colors = palette if isinstance(palette, dict) else HEALTH_COLORS
        nmax = max(int(cents["n_trees"].max()), 1)
        fg = folium.FeatureGroup(name="Health · proportional tree symbols", show=True)
        for _, row in cents.iterrows():
            if row.geometry is None or row.geometry.is_empty:
                continue
            n = int(row["n_trees"])
            health = str(row["health"])
            col = colors.get(health, "#94a3b8")
            px = int(20 + 26 * (n / nmax) ** 0.5)
            kind = _tree_kind_for_health(health)
            html = _tree_icon_html(col, size=px, kind=kind, label=str(n))
            folium.Marker(
                [row.geometry.y, row.geometry.x],
                icon=folium.DivIcon(html=html, icon_size=(px, px), icon_anchor=(px // 2, px - 2),
                                   class_name="nfi-tree-icon"),
                popup=f"<b>{health}</b><br>SU {row['SU_UID']}<br>n={n}",
            ).add_to(fg)
        fg.add_to(m)
        order = ["Healthy", "Slightly affected", "Not indicated", "Severely affected", "Dead/Dying tree"]
        legend_html = "<b>Tree health condition</b><br>" + "".join(
            f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0;">'
            f'{_tree_icon_html(colors.get(k,"#94a3b8"), size=18, kind=_tree_kind_for_health(k))}'
            f'<span>{k}</span></div>'
            for k in order if k in colors
        ) + "<div style='font-size:10px;opacity:.8;margin-top:4px'>Icon size &amp; label = tree count at SU</div>"
        subtitle = "Mapping Approach p.8 · proportional tree icons by SU health"

    else:
        raise ValueError(f"Unsupported symbolization/layer: {symbolization}/{layer_kind}")

    _add_chart_inset(m, theme_id, trees=trees, su_metrics=su_metrics, plot_df=plot_df)
    _add_cartographic_chrome(
        m,
        title=title,
        subtitle=subtitle + f" | symbology={symbolization}",
        legend_html=legend_html,
        theme_id=theme_id,
        pdf_analogue=pdf_analogue,
        locality_html=_locality_info_html(su_metrics, asir_su=su, grid=grid),
    )
    folium.LayerControl(collapsed=False).add_to(m)
    _add_opacity_peel_control(m, default_pct=72)

    out_path = Path(out_path) if out_path else Path(f"html_{theme_id}.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return str(out_path)


# ---------------------------------------------------------------------------
# Atlas builder (PDF-parity theme set)
# ---------------------------------------------------------------------------
def build_beautiful_html_atlas(
    asir_grid,
    asir_su,
    trees: pd.DataFrame,
    plot_df: pd.DataFrame | None = None,
    out_dir: Path | None = None,
    *,
    basemap_default: str = "imagery",
    engineer_fv: bool = True,
    cfg: dict | None = None,
) -> dict:
    """
    Build an HTML atlas covering the main PDF map themes.
    Optionally engineers provisional FV metrics (DBH, Vol, AGB, Carbon, ...).
    """
    out_dir = Path(out_dir) if out_dir else Path("maps/html_atlas")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("BEAUTIFUL HTML ATLAS - NFI PDF-theme parity (interactive)")
    print("=" * 72)
    print(
        "Themes mirror F:/1.KSA/1.Forest/10.NFI/4.Maps/pdf\n"
        "Basemaps: Esri World Imagery, Google Satellite, Google Hybrid.\n"
        "Inset minimap uses Esri imagery (not Carto)."
    )

    trees_use = trees.copy()
    if engineer_fv:
        try:
            from nfi_audit import load_config
            from nfi_datascience import engineer_tree_volume_features_fv
            cfg = cfg or load_config("config.yaml")
            trees_use = engineer_tree_volume_features_fv(trees_use, cfg, trees_only=False)
            print("  FV engineering attached for DBH / Vol / AGB / Carbon maps")
        except Exception as e:
            print("  FV engineering skipped:", e)

    metrics = build_su_map_metrics(trees_use, asir_su, plot_df=plot_df)
    metrics.to_csv(out_dir / "su_map_metrics.csv", index=False)
    paths: dict = {"su_metrics_csv": str(out_dir / "su_map_metrics.csv")}

    for theme in ATLAS_THEMES:
        theme_id, title, value_col, palette, symbolization, layer_kind, pdf_analogue = theme[:7]
        out_path = out_dir / f"html_{theme_id}.html"
        try:
            # Skip choropleths when column entirely missing / all-null
            if symbolization.startswith("choropleth") and (value_col not in metrics.columns or metrics[value_col].notna().sum() == 0):
                paths[f"{theme_id}_skipped"] = f"no data for {value_col}"
                print(f"  skip {theme_id}: no data for {value_col}")
                continue
            if symbolization == "categorical_poly" and (value_col not in metrics.columns or metrics[value_col].notna().sum() == 0):
                paths[f"{theme_id}_skipped"] = f"no data for {value_col}"
                print(f"  skip {theme_id}: no data for {value_col}")
                continue

            p = render_nfi_map(
                asir_grid=asir_grid,
                asir_su=asir_su,
                su_metrics=metrics,
                trees=trees_use,
                plot_df=plot_df,
                theme_id=theme_id,
                title=title,
                value_col=value_col,
                palette=palette,
                symbolization=symbolization,
                layer_kind=layer_kind,
                pdf_analogue=pdf_analogue,
                out_path=out_path,
                basemap_default=basemap_default,
            )
            paths[theme_id] = p
            print(f"  {theme_id} -> {p}")
        except Exception as e:
            paths[f"{theme_id}_error"] = str(e)
            print(f"  {theme_id} skipped: {e}")

    index = _write_atlas_portal_index(out_dir, paths)
    paths["index"] = str(index)
    print("  index ->", paths["index"])
    print(f"  maps written: {sum(1 for k,v in paths.items() if k not in {'su_metrics_csv','index'} and isinstance(v,str) and str(v).endswith('.html'))}")
    print("=" * 72)
    return {"paths": paths, "su_metrics": metrics}


# Extra Leaflet grid-review maps (from interactive_asir_maps) registered into the portal
LEAFLET_ATLAS_META = {
    "su_labels": {
        "id": "leaflet_su_labels",
        "title": "Sampling-unit labels",
        "category": "Grid review",
        "symbology": "Interactive Leaflet",
        "blurb": "SU markers and labels on Esri/Google imagery. Zoom and click a marker for region, governorate and tree-presence.",
        "pdf": "grid",
    },
    "gate1": {
        "id": "leaflet_gate1",
        "title": "Gate 1 · tree-record presence",
        "category": "Grid review",
        "symbology": "Interactive Leaflet",
        "blurb": "Maroon = SU with tree records; orange = Gate 1 zero-tree SU. Zoom to review spatial pattern of presence.",
        "pdf": "gate1",
    },
    "area_h": {
        "id": "leaflet_area_h",
        "title": "Cell area (Area_H)",
        "category": "Grid review",
        "symbology": "Interactive Leaflet",
        "blurb": "Inventory cell Area_H joined by SU key (not Mercator-derived). Zoom to inspect individual cells.",
        "pdf": "area",
    },
    "by_region": {
        "id": "leaflet_by_region",
        "title": "Sampling units by region",
        "category": "Grid review",
        "symbology": "Interactive Leaflet",
        "blurb": "Grid cells coloured by administrative region. Use layer control for imagery/hybrid basemaps.",
        "pdf": "region",
    },
    "by_governorate": {
        "id": "leaflet_by_governorate",
        "title": "Sampling units by governorate",
        "category": "Grid review",
        "symbology": "Interactive Leaflet",
        "blurb": "Grid cells coloured by governorate. Zoom and pan to compare neighbouring administrations.",
        "pdf": "governorate",
    },
}


def attach_interactive_leaflet_to_atlas(atlas_dir: Path, imap_paths: dict) -> dict:
    """
    Copy interactive Leaflet HTML maps into the HTML atlas folder and rebuild index.html
    so they appear under the 'Grid review' branch of the portal tree.
    """
    import shutil

    atlas_dir = Path(atlas_dir)
    atlas_dir.mkdir(parents=True, exist_ok=True)
    paths: dict = {}
    # Preserve existing theme HTML already in the folder
    for p in atlas_dir.glob("html_*.html"):
        theme_id = p.stem.replace("html_", "", 1)
        paths[theme_id] = str(p)

    registered = {}
    for key, src in (imap_paths or {}).items():
        meta = LEAFLET_ATLAS_META.get(key)
        if not meta:
            # unknown key - still copy under a safe name
            theme_id = f"leaflet_{key}"
            meta = {
                "id": theme_id,
                "title": str(key).replace("_", " ").title(),
                "category": "Grid review",
                "symbology": "Interactive Leaflet",
                "blurb": "Interactive Leaflet map for grid review.",
                "pdf": key,
            }
        else:
            theme_id = meta["id"]
        src_p = Path(src)
        if not src_p.exists():
            continue
        dest = atlas_dir / f"html_{theme_id}.html"
        shutil.copy2(src_p, dest)
        paths[theme_id] = str(dest)
        registered[theme_id] = meta
        print(f"  atlas + {theme_id} <- {src_p.name}")

    index = _write_atlas_portal_index(atlas_dir, paths, extra_meta=registered)
    paths["index"] = str(index)
    print("  atlas index refreshed ->", paths["index"])
    return {"paths": paths, "registered": list(registered.keys()), "index": str(index)}


def _write_atlas_portal_index(out_dir: Path, paths: dict, extra_meta: dict | None = None) -> Path:
    """Professional split-pane atlas: theme tree (left) + live map iframe (right)."""
    from collections import OrderedDict

    maps_meta = []
    for theme in ATLAS_THEMES:
        theme_id, title, value_col, palette, symbolization, layer_kind, pdf_analogue, category, blurb = (
            theme if len(theme) >= 9 else (*theme, "All", theme[1])
        )
        p = paths.get(theme_id)
        if not p:
            continue
        sym_label = {
            "choropleth_quantile": "Choropleth",
            "categorical_poly": "Categorical polygons",
            "categorical_points": "Categorical points",
            "graduated_points": "Graduated points",
            "coord_pairs": "Field ↔ Office pairs",
            "proportional_health": "Proportional health symbols",
        }.get(symbolization, symbolization)
        maps_meta.append({
            "id": theme_id,
            "title": title.title() if title.isupper() else title,
            "file": Path(p).name,
            "category": category,
            "blurb": blurb,
            "symbology": sym_label,
            "pdf": pdf_analogue or "",
        })

    # Interactive Leaflet grid-review maps (copied into atlas)
    for theme_id, meta in (extra_meta or {}).items():
        p = paths.get(theme_id)
        if not p:
            continue
        maps_meta.append({
            "id": theme_id,
            "title": meta.get("title", theme_id),
            "file": Path(p).name,
            "category": meta.get("category", "Grid review"),
            "blurb": meta.get("blurb", ""),
            "symbology": meta.get("symbology", "Interactive Leaflet"),
            "pdf": meta.get("pdf", ""),
        })
    # Also pick up any html_leaflet_* already on disk without extra_meta
    for pth in Path(out_dir).glob("html_leaflet_*.html"):
        tid = pth.stem.replace("html_", "", 1)
        if any(m["id"] == tid for m in maps_meta):
            continue
        fallback = LEAFLET_ATLAS_META.get(tid.replace("leaflet_", "", 1), {})
        maps_meta.append({
            "id": tid,
            "title": fallback.get("title", tid.replace("_", " ").title()),
            "file": pth.name,
            "category": fallback.get("category", "Grid review"),
            "blurb": fallback.get("blurb", "Interactive Leaflet grid-review map."),
            "symbology": "Interactive Leaflet",
            "pdf": fallback.get("pdf", ""),
        })
        paths.setdefault(tid, str(pth))

    n = len(maps_meta)
    cat_order = ["Grid review", "Coordinate QA", "Structure", "Biomass & Carbon", "Biodiversity", "Access & Ownership"]
    by_cat: OrderedDict[str, list] = OrderedDict()
    for cat in cat_order:
        by_cat[cat] = [c for c in maps_meta if c["category"] == cat]
    for c in maps_meta:
        if c["category"] not in by_cat:
            by_cat.setdefault(c["category"], []).append(c)

    def esc(s: str) -> str:
        return (
            str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        )

    first = maps_meta[0] if maps_meta else None
    tree_blocks = []
    for cat, items in by_cat.items():
        if not items:
            continue
        leaves = []
        for c in items:
            leaves.append(f"""
            <li class="leaf">
              <button type="button" class="leaf-btn" id="nav-{esc(c['id'])}"
                data-id="{esc(c['id'])}" data-file="{esc(c['file'])}"
                data-title="{esc(c['title'])}" data-cat="{esc(c['category'])}"
                data-sym="{esc(c['symbology'])}" data-blurb="{esc(c['blurb'])}"
                data-text="{esc(c['title'] + ' ' + c['blurb'] + ' ' + c['id'] + ' ' + c['category'])}">
                <span class="leaf-rail" aria-hidden="true"></span>
                <span class="leaf-body">
                  <span class="leaf-name">{esc(c['title'])}</span>
                  <span class="leaf-meta">{esc(c['symbology'])}</span>
                </span>
              </button>
            </li>""")
        tree_blocks.append(f"""
        <details class="branch" open data-cat="{esc(cat)}">
          <summary class="branch-sum">
            <span class="chev" aria-hidden="true"></span>
            <span class="branch-name">{esc(cat)}</span>
            <span class="branch-count">{len(items)}</span>
          </summary>
          <ul class="leaves">{''.join(leaves)}</ul>
        </details>""")

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NFI Interactive Atlas</title>
<style>
:root {{
  --ink:#1a1d21;
  --muted:#6b7280;
  --line:#e5e7eb;
  --line-2:#d1d5db;
  --panel:#f7f8fa;
  --panel-2:#ffffff;
  --sidebar:#f3f4f6;
  --accent:#2f3b46;
  --accent-soft:#eef1f4;
  --active:#1f2937;
  --focus:#9ca3af;
  --shadow:0 1px 0 rgba(15,23,42,.04);
  --font:"Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}
* {{box-sizing:border-box}}
html, body {{height:100%; margin:0}}
body {{
  font-family:var(--font); color:var(--ink); background:#eceef1;
  display:flex; flex-direction:column; min-height:100vh;
}}
button {{font:inherit}}
.app-bar {{
  display:flex; align-items:center; justify-content:space-between; gap:16px;
  padding:10px 18px; background:#111827; color:#f9fafb;
  border-bottom:1px solid #0b1220; flex:0 0 auto;
}}
.brand {{display:flex; align-items:center; gap:12px; min-width:0}}
.mark {{
  width:28px; height:28px; border-radius:6px;
  background:linear-gradient(145deg,#4b5563,#111827);
  border:1px solid #6b7280; flex:0 0 auto;
}}
.brand-text {{min-width:0}}
.brand-text strong {{display:block; font-size:14px; letter-spacing:.02em}}
.brand-text span {{display:block; font-size:11px; color:#9ca3af; margin-top:1px}}
.bar-tools {{display:flex; align-items:center; gap:10px; flex-wrap:wrap}}
.search {{
  background:#1f2937; border:1px solid #374151; color:#e5e7eb;
  border-radius:6px; padding:8px 12px; min-width:210px; outline:none;
}}
.search:focus {{border-color:#9ca3af}}
.bar-meta {{font-size:12px; color:#9ca3af; white-space:nowrap}}
.workspace {{
  flex:1 1 auto; display:grid; grid-template-columns:300px minmax(0,1fr);
  min-height:0; height:calc(100vh - 53px);
}}
.sidebar {{
  background:var(--sidebar); border-right:1px solid var(--line-2);
  display:flex; flex-direction:column; min-height:0;
}}
.sidebar-head {{
  padding:14px 14px 10px; border-bottom:1px solid var(--line); flex:0 0 auto;
}}
.sidebar-head h1 {{margin:0; font-size:13px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:#374151}}
.sidebar-head p {{margin:6px 0 0; font-size:12px; color:var(--muted); line-height:1.4}}
.tree-scroll {{overflow:auto; padding:8px 8px 16px; flex:1 1 auto}}
.branch {{margin:0 0 4px; border:1px solid transparent; border-radius:8px}}
.branch-sum {{
  list-style:none; cursor:pointer; display:flex; align-items:center; gap:8px;
  padding:9px 10px; border-radius:8px; color:#111827; font-weight:650; font-size:13px;
  user-select:none;
}}
.branch-sum::-webkit-details-marker {{display:none}}
.branch-sum:hover {{background:#e5e7eb}}
.chev {{
  width:0; height:0; border-top:4px solid transparent; border-bottom:4px solid transparent;
  border-left:5px solid #6b7280; transition:transform .15s ease; flex:0 0 auto;
}}
details[open] > .branch-sum .chev {{transform:rotate(90deg)}}
.branch-name {{flex:1; min-width:0}}
.branch-count {{
  font-size:11px; color:#6b7280; background:#e5e7eb; border-radius:999px;
  padding:1px 7px; font-weight:600;
}}
.leaves {{list-style:none; margin:0; padding:0 0 6px 8px; border-left:1px solid #d1d5db; margin-left:14px}}
.leaf {{margin:0}}
.leaf-btn {{
  width:100%; text-align:left; border:0; background:transparent; cursor:pointer;
  display:flex; gap:8px; align-items:stretch; padding:7px 8px; border-radius:7px;
  color:inherit;
}}
.leaf-btn:hover {{background:#e5e7eb}}
.leaf-btn.active {{background:#fff; box-shadow:inset 0 0 0 1px #d1d5db, var(--shadow)}}
.leaf-btn.active .leaf-rail {{background:#111827}}
.leaf-rail {{width:2px; border-radius:2px; background:transparent; flex:0 0 auto; margin:2px 0}}
.leaf-body {{min-width:0; display:flex; flex-direction:column; gap:2px}}
.leaf-name {{font-size:13px; font-weight:600; color:#111827; line-height:1.25}}
.leaf-meta {{font-size:11px; color:var(--muted)}}
.viewer {{
  display:flex; flex-direction:column; min-width:0; min-height:0; background:#d1d5db;
}}
.viewer-bar {{
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding:10px 14px; background:var(--panel-2); border-bottom:1px solid var(--line-2);
  flex:0 0 auto;
}}
.viewer-title {{min-width:0}}
.viewer-title .crumb {{font-size:11px; color:var(--muted); letter-spacing:.04em; text-transform:uppercase}}
.viewer-title h2 {{margin:2px 0 0; font-size:16px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}}
.viewer-actions {{display:flex; gap:8px; flex-wrap:wrap}}
.btn {{
  appearance:none; border:1px solid var(--line-2); background:#fff; color:#111827;
  border-radius:6px; padding:7px 11px; font-size:12px; font-weight:600; cursor:pointer;
  text-decoration:none; display:inline-flex; align-items:center; gap:6px;
}}
.btn:hover {{background:#f3f4f6}}
.btn.primary {{background:#111827; color:#fff; border-color:#111827}}
.btn.primary:hover {{background:#374151}}
.frame-wrap {{
  flex:1 1 auto; min-height:0; position:relative; background:
    linear-gradient(45deg,#e5e7eb 25%,transparent 25%),
    linear-gradient(-45deg,#e5e7eb 25%,transparent 25%),
    linear-gradient(45deg,transparent 75%,#e5e7eb 75%),
    linear-gradient(-45deg,transparent 75%,#e5e7eb 75%);
  background-size:20px 20px; background-position:0 0,0 10px,10px -10px,-10px 0;
  background-color:#f3f4f6;
}}
#map-frame {{
  position:absolute; inset:0; width:100%; height:100%; border:0; background:#fff;
}}
.empty {{
  position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  color:var(--muted); font-size:14px; padding:24px; text-align:center;
}}
.desc {{
  flex:0 0 auto; padding:8px 14px 10px; background:#fff; border-top:1px solid var(--line);
  font-size:12px; color:#4b5563; line-height:1.45;
}}
@media (max-width:900px) {{
  .workspace {{grid-template-columns:1fr; height:auto}}
  .sidebar {{max-height:42vh; border-right:0; border-bottom:1px solid var(--line-2)}}
  .viewer {{min-height:58vh}}
  .frame-wrap {{min-height:52vh; position:relative}}
  #map-frame {{position:absolute}}
}}
</style></head><body>
<header class="app-bar">
  <div class="brand">
    <div class="mark" aria-hidden="true"></div>
    <div class="brand-text">
      <strong>NFI Interactive Atlas</strong>
      <span>Asir · thematic maps · Esri / Google basemaps</span>
    </div>
  </div>
  <div class="bar-tools">
    <input class="search" id="map-search" type="search" placeholder="Filter themes and maps…" autocomplete="off">
    <div class="bar-meta">{n} maps</div>
  </div>
</header>

<div class="workspace">
  <aside class="sidebar" aria-label="Theme tree">
    <div class="sidebar-head">
      <h1>Catalogue</h1>
      <p>Select a theme map. It opens in the viewer on this page.</p>
    </div>
    <div class="tree-scroll" id="tree-root">
      {''.join(tree_blocks) if tree_blocks else '<p style="padding:12px;color:#6b7280;font-size:13px">No maps found.</p>'}
    </div>
  </aside>

  <section class="viewer" aria-label="Map viewer">
    <div class="viewer-bar">
      <div class="viewer-title">
        <div class="crumb" id="view-crumb">NFI Atlas</div>
        <h2 id="view-title">Select a map</h2>
      </div>
      <div class="viewer-actions">
        <a class="btn" id="btn-newtab" href="#" target="_blank" rel="noopener">Open in new tab</a>
        <a class="btn primary" id="btn-data" href="su_map_metrics.csv" target="_blank" rel="noopener">Metrics CSV</a>
      </div>
    </div>
    <div class="frame-wrap">
      <div class="empty" id="empty-state">Choose a map from the tree on the left.</div>
      <iframe id="map-frame" title="Selected NFI map" hidden></iframe>
    </div>
    <div class="desc" id="view-desc">Basemaps: Esri World Imagery, Google Satellite, Google Hybrid. Layer peel and locality tools are on each map.</div>
  </section>
</div>

<script>
(function(){{
  const frame = document.getElementById('map-frame');
  const empty = document.getElementById('empty-state');
  const titleEl = document.getElementById('view-title');
  const crumbEl = document.getElementById('view-crumb');
  const descEl = document.getElementById('view-desc');
  const btnTab = document.getElementById('btn-newtab');
  const search = document.getElementById('map-search');
  const buttons = [...document.querySelectorAll('.leaf-btn')];
  const branches = [...document.querySelectorAll('.branch')];

  function selectMap(btn, pushHash) {{
    if (!btn) return;
    const file = btn.dataset.file;
    const id = btn.dataset.id;
    buttons.forEach(b => b.classList.toggle('active', b === btn));
    empty.hidden = true;
    frame.hidden = false;
    if (frame.getAttribute('src') !== file) frame.src = file;
    titleEl.textContent = btn.dataset.title || id;
    crumbEl.textContent = (btn.dataset.cat || 'Map') + ' · ' + (btn.dataset.sym || 'Theme');
    descEl.textContent = btn.dataset.blurb || '';
    btnTab.href = file;
    btnTab.style.visibility = 'visible';
    const branch = btn.closest('.branch');
    if (branch) branch.open = true;
    btn.scrollIntoView({{block:'nearest', behavior:'smooth'}});
    if (pushHash !== false) history.replaceState(null, '', '#' + id);
  }}

  buttons.forEach(btn => btn.addEventListener('click', () => selectMap(btn, true)));

  function applyFilter() {{
    const q = (search.value || '').toLowerCase().trim();
    buttons.forEach(btn => {{
      const text = (btn.dataset.text || btn.textContent || '').toLowerCase();
      const ok = !q || text.includes(q);
      btn.closest('.leaf').style.display = ok ? '' : 'none';
    }});
    branches.forEach(br => {{
      const visible = [...br.querySelectorAll('.leaf')].some(li => li.style.display !== 'none');
      br.style.display = visible ? '' : 'none';
      if (visible && q) br.open = true;
    }});
  }}
  search.addEventListener('input', applyFilter);

  function boot() {{
    const hash = (location.hash || '').replace(/^#/, '');
    let btn = hash ? document.getElementById('nav-' + hash) : null;
    if (!btn) btn = buttons[0] || null;
    if (btn) selectMap(btn, !hash);
    else btnTab.style.visibility = 'hidden';
  }}
  window.addEventListener('hashchange', () => {{
    const hash = (location.hash || '').replace(/^#/, '');
    const btn = document.getElementById('nav-' + hash);
    if (btn) selectMap(btn, false);
  }});
  boot();
}})();
</script>
</body></html>
"""
    index = Path(out_dir) / "index.html"
    index.write_text(html, encoding="utf-8")
    return index


# Backwards-compatible aliases used by older notebook cells
def beautiful_metric_choropleth(asir_grid, su_metrics, *, value_col, title, subtitle="", out_path=None,
                                palette=None, legend_caption="", zero_as_bare=True):
    return render_nfi_map(
        asir_grid=asir_grid, asir_su=asir_grid, su_metrics=su_metrics, trees=None, plot_df=None,
        theme_id="custom", title=title, value_col=value_col, palette=palette or DENSITY_COLORS,
        symbolization="choropleth_quantile", layer_kind="su_poly",
        pdf_analogue=legend_caption or subtitle, out_path=out_path,
    )


def beautiful_tree_health_map(trees, asir_su, plot_df=None, *, out_path=None, title="TREE HEALTH",
                              subtitle="", max_points=8000):
    return render_nfi_map(
        asir_grid=asir_su, asir_su=asir_su, su_metrics=None, trees=trees, plot_df=plot_df,
        theme_id="tree_health", title=title, value_col=None, palette=HEALTH_COLORS,
        symbolization="categorical_points", layer_kind="tree_points",
        pdf_analogue="5.TreeHealth", out_path=out_path, max_points=max_points,
    )


def beautiful_species_points_map(trees, asir_su, plot_df=None, *, out_path=None, top_n=8,
                                 max_points=8000, title="TREE SPECIES DISTRIBUTION"):
    return render_nfi_map(
        asir_grid=asir_su, asir_su=asir_su, su_metrics=None, trees=trees, plot_df=plot_df,
        theme_id="species_points", title=title, value_col=None, palette=None,
        symbolization="categorical_points", layer_kind="tree_points",
        pdf_analogue="3.SpeciesDiversity", out_path=out_path, max_points=max_points,
    )
