# -*- coding: utf-8 -*-
"""Area appropriation, long-form anti-pivot joins, static and interactive maps."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EQUAL_AREA_CRS_DEFAULT = "EPSG:32637"  # WGS84 / UTM 37N (western KSA belt)


def _keys():
    from nfi_audit import expected_plot_universe, make_su_uid
    return expected_plot_universe, make_su_uid


def area_appropriation_audit(asir_grid, cfg: dict | None = None, equal_area_crs: str = EQUAL_AREA_CRS_DEFAULT) -> dict:
    """
    Handle SU-cell area safely for NFI review.

    Rules:
    - Grid attribute Area_H is the inventory cell area label; attach by SU_UID, never by clip.
    - Do NOT use Web Mercator (EPSG:3857) geometry.area for official ha (systematic bias).
    - Optional equal-area check (UTM) is QA only; discrepancies are flagged, not auto-fixed.
    - Plot-level plot_area_ha is MISSING in cleansed sources -> stems/ha and expansion BLOCKED.
    - Never apportion Area_H down to plots by naive /5 without a documented design rule.
    """
    _, make_su_uid = _keys()
    g = asir_grid.copy()
    if "SU_UID" not in g.columns:
        key = (cfg or {}).get("gis", {}).get("asir_grid_key", "SU")
        g["SU_UID"] = make_su_uid(g[key])
    g["Area_H_attr"] = pd.to_numeric(g.get("Area_H"), errors="coerce")

    g_ea = g.to_crs(equal_area_crs)
    g["Area_H_equal_area_recalc"] = g_ea.geometry.area / 10000.0
    g["area_delta_ha"] = g["Area_H_equal_area_recalc"] - g["Area_H_attr"]
    g["area_rel_pct"] = np.where(
        g["Area_H_attr"].abs() > 1e-6,
        100 * g["area_delta_ha"] / g["Area_H_attr"],
        np.nan,
    )

    crs_s = str(asir_grid.crs)
    if "3857" in crs_s:
        g_m = asir_grid.copy()
        g["Area_H_mercator_WRONG"] = g_m.geometry.area / 10000.0
        g["mercator_bias_ha"] = g["Area_H_mercator_WRONG"] - g["Area_H_attr"]
    else:
        g["Area_H_mercator_WRONG"] = np.nan
        g["mercator_bias_ha"] = np.nan

    summary = pd.DataFrame([{
        "n_cells": len(g),
        "Area_H_attr_sum": float(g["Area_H_attr"].sum()),
        "Area_H_attr_median": float(g["Area_H_attr"].median()),
        "equal_area_recalc_sum": float(g["Area_H_equal_area_recalc"].sum()),
        "median_abs_delta_ha_vs_attr": float(g["area_delta_ha"].abs().median()),
        "median_abs_mercator_bias_ha": (
            float(g["mercator_bias_ha"].abs().median())
            if g["mercator_bias_ha"].notna().any() else None
        ),
        "plot_area_ha_in_source": False,
        "stems_per_ha_status": "BLOCKED",
        "design_expansion_status": "BLOCKED",
        "appropriation_rule": (
            "Attach Area_H by SU_UID left-join; never clip-then-recompute; "
            "never pivot-drop zero SUs"
        ),
    }])

    policy = pd.DataFrame([
        {"rule": "master_area_field", "value": "Area_H on Asir_Grid_15_30_Final", "action": "USE_AS_ATTRIBUTE"},
        {"rule": "web_mercator_geometry_area", "value": "EPSG:3857", "action": "FORBIDDEN_FOR_HA"},
        {"rule": "equal_area_recompute", "value": equal_area_crs, "action": "QA_ONLY_FLAG_DELTAS"},
        {"rule": "plot_area_ha", "value": "not in cleansed Excel", "action": "BLOCK_STEMS_PER_HA"},
        {"rule": "naive_Area_H_div_5_plots", "value": "undocumented", "action": "FORBIDDEN_WITHOUT_DESIGN_NOTE"},
        {"rule": "clip_then_sum_area", "value": "loses Gate1 SUs + corrupts denominators", "action": "FORBIDDEN"},
        {"rule": "attach_area_by_key", "value": "SU_UID left join", "action": "REQUIRED"},
    ])
    return {"grid_area": g, "summary": summary, "policy": policy}


def longform_su_plot_tree_presence(asir_su, trees: pd.DataFrame, plots_per_su: int = 5, sep: str = "-") -> pd.DataFrame:
    """Long-form lattice + left join (keeps zero cells that pivots drop)."""
    expected_plot_universe, make_su_uid = _keys()
    universe = make_su_uid(asir_su["SU_UID"]).astype(str)
    base = expected_plot_universe(set(universe), plots_per_su, sep)
    if "gover_e" in asir_su.columns:
        gov = dict(zip(make_su_uid(asir_su["SU_UID"]), asir_su["gover_e"]))
        reg = (
            dict(zip(make_su_uid(asir_su["SU_UID"]), asir_su["reg_e"]))
            if "reg_e" in asir_su.columns else {}
        )
        base["governorate"] = base["SU_UID"].map(gov)
        base["region"] = base["SU_UID"].map(reg)
    tc = trees.groupby("PLOT_UID", dropna=False).size().rename("n_tree_records").reset_index()
    tc["PLOT_UID"] = tc["PLOT_UID"].astype(str)
    out = base.merge(tc, on="PLOT_UID", how="left")
    out["n_tree_records"] = out["n_tree_records"].fillna(0).astype(int)
    out["has_tree_record"] = out["n_tree_records"] > 0
    return out


def attach_grid_area_by_key(df: pd.DataFrame, grid_area_gdf, su_col: str = "SU_UID") -> pd.DataFrame:
    """Attribute-join Area_H; no spatial clip required."""
    _, make_su_uid = _keys()
    g = grid_area_gdf.copy()
    if "SU_UID" not in g.columns:
        g["SU_UID"] = make_su_uid(g["SU"])
    if "Area_H_attr" not in g.columns:
        g["Area_H_attr"] = pd.to_numeric(g["Area_H"], errors="coerce")
    area = g[["SU_UID", "Area_H_attr"]].drop_duplicates("SU_UID")
    out = df.copy()
    out[su_col] = make_su_uid(out[su_col])
    return out.merge(area, left_on=su_col, right_on="SU_UID", how="left", suffixes=("", "_area"))


def region_governorate_summaries(longform: pd.DataFrame, su_tree_gdf) -> dict:
    """Roll-ups for review maps from long-form data."""
    su = su_tree_gdf.drop(columns="geometry", errors="ignore").copy()
    by_reg = (
        su.groupby("reg_e", dropna=False)
        .agg(n_su=("SU_UID", "nunique"), n_with_trees=("has_tree_record", "sum"))
        .reset_index()
    )
    by_reg["n_gate1"] = by_reg["n_su"] - by_reg["n_with_trees"]
    by_gov = (
        su.groupby(["reg_e", "gover_e"], dropna=False)
        .agg(n_su=("SU_UID", "nunique"), n_with_trees=("has_tree_record", "sum"))
        .reset_index()
    )
    by_gov["n_gate1"] = by_gov["n_su"] - by_gov["n_with_trees"]
    plot_by_gov = (
        longform.groupby(["region", "governorate"], dropna=False)
        .agg(
            expected_plots=("PLOT_UID", "count"),
            plots_with_trees=("has_tree_record", "sum"),
            tree_records=("n_tree_records", "sum"),
        )
        .reset_index()
    )
    return {"by_region": by_reg, "by_governorate": by_gov, "plots_by_governorate": plot_by_gov}


def _add_free_basemaps(m):
    """Leaflet basemaps: Esri imagery + Google Satellite/Hybrid + place-name overlays."""
    import folium

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Esri World Imagery",
        max_zoom=19,
        control=True,
        show=True,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Satellite",
        max_zoom=20,
        control=True,
        show=False,
    ).add_to(m)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google",
        name="Google Hybrid (named)",
        max_zoom=20,
        control=True,
        show=False,
    ).add_to(m)
    # Country / city names over imagery
    folium.TileLayer(
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/"
            "World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Esri",
        name="Place names · countries & cities",
        max_zoom=19,
        overlay=True,
        control=True,
        show=True,
        opacity=0.95,
    ).add_to(m)
    return m


def interactive_asir_maps(asir_grid, asir_su, su_tree=None, out_dir: Path | None = None) -> dict:
    """
    Interactive Leaflet maps with SU labels and free imagery basemaps.
    Writes HTML under out_dir; returns paths for notebook embedding.
    """
    import folium
    from folium.features import GeoJsonTooltip, DivIcon

    out_dir = Path(out_dir) if out_dir else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    print("=" * 72)
    print("CARTOGRAPHY STORY - interactive maps with basemaps")
    print("=" * 72)
    print(
        "Each HTML map starts with tiles=None, then loads basemap layers:\n"
        "  - Esri World Imagery\n"
        "  - Google Satellite\n"
        "  - Google Hybrid\n"
        "Use the layer control to switch basemaps while inspecting SU labels."
    )
    print()

    grid = asir_grid.to_crs(4326).copy()
    su = asir_su.to_crs(4326).copy()
    if "SU_UID" not in su.columns and "SU" in su.columns:
        from nfi_audit import make_su_uid
        su["SU_UID"] = make_su_uid(su["SU"])
    if "SU_UID" in su.columns:
        su["SU_UID"] = su["SU_UID"].astype(str)
    if "SU_UID" not in grid.columns and "SU" in grid.columns:
        from nfi_audit import make_su_uid
        grid["SU_UID"] = make_su_uid(grid["SU"]).astype(str)
    elif "SU_UID" in grid.columns:
        grid["SU_UID"] = grid["SU_UID"].astype(str)

    bounds = grid.total_bounds
    center = [float((bounds[1] + bounds[3]) / 2), float((bounds[0] + bounds[2]) / 2)]

    m1 = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
    _add_free_basemaps(m1)
    tip_fields = [c for c in ["SU_UID", "SU", "reg_e", "gover_e", "Area_H"] if c in grid.columns][:5]
    tip_aliases = {
        "SU_UID": "SU_UID", "SU": "SU raw", "reg_e": "Region",
        "gover_e": "Governorate", "Area_H": "Area_H (ha)",
    }
    folium.GeoJson(
        grid.__geo_interface__,
        name="SU analytical grid",
        style_function=lambda _f: {
            "color": "#1b4f72", "weight": 0.6, "fillOpacity": 0.05, "fillColor": "#5dade2",
        },
        tooltip=GeoJsonTooltip(
            fields=tip_fields,
            aliases=[tip_aliases.get(f, f) for f in tip_fields],
        ),
    ).add_to(m1)

    label_group = folium.FeatureGroup(name="SU_UID labels", show=True)
    pts = su_tree.to_crs(4326).copy() if su_tree is not None else su
    if "SU_UID" in pts.columns:
        pts["SU_UID"] = pts["SU_UID"].astype(str)
    step = 1 if len(pts) <= 500 else 2
    for i, (_, row) in enumerate(pts.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        y, x = geom.y, geom.x
        has_t = None
        if "has_tree_record" in row.index and pd.notna(row.get("has_tree_record")):
            has_t = bool(row["has_tree_record"])
        color = "#1f8a70" if has_t else ("#d97706" if has_t is False else "#2f6f8f")
        folium.CircleMarker(
            location=[y, x],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>SU_UID:</b> {row.get('SU_UID')}<br>"
                f"<b>Region:</b> {row.get('reg_e', '')}<br>"
                f"<b>Governorate:</b> {row.get('gover_e', '')}<br>"
                f"<b>Trees:</b> {has_t}",
                max_width=280,
            ),
            tooltip=f"SU {row.get('SU_UID')}",
        ).add_to(label_group)
        if i % step == 0:
            folium.Marker(
                location=[y, x],
                icon=DivIcon(
                    icon_size=(60, 14),
                    icon_anchor=(0, 0),
                    html=(
                        f'<div style="font-size:9px;font-weight:700;color:#1b2838;'
                        f'text-shadow:0 0 3px #fff,0 0 3px #fff;">{row.get("SU_UID")}</div>'
                    ),
                ),
            ).add_to(label_group)
    label_group.add_to(m1)
    folium.LayerControl(collapsed=False).add_to(m1)
    m1.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,253,248,0.92);'
        'padding:8px 12px;border:1px solid #1b2838;border-radius:4px;font-family:Segoe UI,sans-serif;">'
        "<b>Asir NFI sampling units on free satellite imagery</b><br>"
        "<span style='font-size:12px'>SU_UID labels | Esri / Google basemaps | click markers for attributes</span>"
        "</div>"
    ))
    p1 = out_dir / "interactive_asir_su_labels.html"
    m1.save(str(p1))
    paths["su_labels"] = str(p1)

    if su_tree is not None and "has_tree_record" in su_tree.columns:
        m2 = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
        _add_free_basemaps(m2)
        folium.GeoJson(
            grid.__geo_interface__,
            name="Analytical grid",
            style_function=lambda _f: {
                "color": "#566573", "weight": 0.4, "fillOpacity": 0.02, "fillColor": "#aab7b8",
            },
        ).add_to(m2)
        st = su_tree.to_crs(4326).copy()
        st["SU_UID"] = st["SU_UID"].astype(str)
        g_yes = folium.FeatureGroup(name="Has tree records", show=True)
        g_no = folium.FeatureGroup(name="Gate 1: no tree records", show=True)
        for _, row in st.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            target = g_yes if bool(row["has_tree_record"]) else g_no
            col = "#8B1E1E" if row["has_tree_record"] else "#E67E22"
            folium.CircleMarker(
                [geom.y, geom.x], radius=5, color=col, fill=True, fill_opacity=0.9,
                tooltip=f"SU {row['SU_UID']}",
                popup=f"SU_UID={row['SU_UID']}<br>has_tree_record={row['has_tree_record']}",
            ).add_to(target)
            folium.Marker(
                [geom.y, geom.x],
                icon=DivIcon(
                    icon_size=(52, 12), icon_anchor=(0, 0),
                    html=(
                        f'<div style="font-size:8px;font-weight:700;color:#111;'
                        f'text-shadow:0 0 2px #fff">{row["SU_UID"]}</div>'
                    ),
                ),
            ).add_to(target)
        g_yes.add_to(m2)
        g_no.add_to(m2)
        folium.LayerControl(collapsed=False).add_to(m2)
        m2.get_root().html.add_child(folium.Element(
            '<div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,253,248,0.92);'
            'padding:8px 12px;border:1px solid #1b2838;border-radius:4px;">'
            "<b>Gate 1 spatial review: tree-record presence by SU</b><br>"
            "<span style='font-size:12px'>Maroon = has trees | Orange = no tree records (anti-clip universe retained)</span>"
            "</div>"
        ))
        p2 = out_dir / "interactive_gate1_su_status.html"
        m2.save(str(p2))
        paths["gate1"] = str(p2)

    if "Area_H" in grid.columns:
        m3 = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
        _add_free_basemaps(m3)
        tip_f = [c for c in ["SU_UID", "SU", "Area_H", "reg_e", "gover_e"] if c in grid.columns]
        area_vals = pd.to_numeric(grid["Area_H"], errors="coerce")
        a_min = float(area_vals.quantile(0.05)) if area_vals.notna().any() else 0.0
        a_max = float(area_vals.quantile(0.95)) if area_vals.notna().any() else 1.0
        if a_max <= a_min:
            a_max = a_min + 1.0

        def _area_color(feature):
            v = feature["properties"].get("Area_H")
            try:
                x = float(v)
            except (TypeError, ValueError):
                return "#d4d4d4"
            t = max(0.0, min(1.0, (x - a_min) / (a_max - a_min)))
            # light yellow -> deep blue
            r = int(254 - t * 200)
            gcol = int(243 - t * 100)
            b = int(199 + t * 56)
            return f"#{r:02x}{gcol:02x}{b:02x}"

        folium.GeoJson(
            grid.__geo_interface__,
            name="Grid cells (Area_H)",
            style_function=lambda f: {
                "fillColor": _area_color(f), "color": "#fff", "weight": 0.4, "fillOpacity": 0.65,
            },
            tooltip=GeoJsonTooltip(
                fields=tip_f,
                aliases=["SU_UID", "SU", "Area_H (ha)", "Region", "Governorate"][: len(tip_f)],
            ),
        ).add_to(m3)
        folium.LayerControl(collapsed=False).add_to(m3)
        m3.get_root().html.add_child(folium.Element(
            '<div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,253,248,0.92);'
            'padding:8px 12px;border:1px solid #1b2838;border-radius:4px;">'
            "<b>Asir inventory cell area (Area_H attribute)</b><br>"
            "<span style='font-size:12px'>Zoom to inspect cells. Area_H is joined by SU key (not Mercator-derived).</span>"
            "</div>"
        ))
        p3 = out_dir / "interactive_area_h.html"
        m3.save(str(p3))
        paths["area_h"] = str(p3)

    # Categorical choropleths: region and governorate (interactive replacements for static PNGs)
    _cat_palette = [
        "#7c3aed", "#a16207", "#06b6d4", "#db2777", "#1d4ed8", "#16a34a",
        "#f97316", "#64748b", "#0e7490", "#be123c", "#4d7c0f", "#9333ea",
    ]
    for col, key, title, blurb in [
        ("reg_e", "by_region", "Sampling units by region",
         "Each grid cell coloured by administrative region (reg_e). Zoom and click for SU attributes."),
        ("gover_e", "by_governorate", "Sampling units by governorate",
         "Each grid cell coloured by governorate (gover_e). Use layer control to switch basemaps."),
    ]:
        if col not in grid.columns:
            continue
        cats = [c for c in sorted(grid[col].dropna().astype(str).unique())]
        cmap = {c: _cat_palette[i % len(_cat_palette)] for i, c in enumerate(cats)}
        m = folium.Map(location=center, zoom_start=8, tiles=None, control_scale=True)
        _add_free_basemaps(m)
        tip_f = [c for c in ["SU_UID", "SU", col, "Area_H"] if c in grid.columns]

        def _style(feature, _cmap=cmap, _col=col):
            val = feature["properties"].get(_col)
            return {
                "fillColor": _cmap.get(str(val), "#d4d4d4"),
                "color": "#ffffff",
                "weight": 0.5,
                "fillOpacity": 0.72,
            }

        folium.GeoJson(
            grid.__geo_interface__,
            name=title,
            style_function=_style,
            tooltip=GeoJsonTooltip(fields=tip_f, aliases=tip_f),
        ).add_to(m)
        # legend
        legend_items = "".join(
            f'<div style="margin:2px 0"><span style="display:inline-block;width:12px;height:12px;'
            f'background:{cmap[c]};margin-right:6px;border:1px solid #333"></span>{c}</div>'
            for c in cats[:14]
        )
        m.get_root().html.add_child(folium.Element(
            f'<div style="position:fixed;top:10px;left:50px;z-index:9999;background:rgba(255,253,248,0.94);'
            f'padding:8px 12px;border:1px solid #1b2838;border-radius:4px;max-width:320px;'
            f'font-family:Segoe UI,sans-serif;font-size:12px">'
            f"<b>{title}</b><br><span style='opacity:.85'>{blurb}</span>"
            f'<div style="margin-top:6px;max-height:180px;overflow:auto">{legend_items}</div></div>'
        ))
        folium.LayerControl(collapsed=False).add_to(m)
        pout = out_dir / f"interactive_{key}.html"
        m.save(str(pout))
        paths[key] = str(pout)

    return paths


def map_asir_grid_regions(asir_grid, asir_su, su_tree=None, out_dir: Path | None = None) -> dict:
    """Static cartographic figures for reports (PNG) with Esri imagery basemaps."""
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir) if out_dir else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    grid = asir_grid.to_crs(4326)
    su = asir_su.to_crs(4326)

    # Working free tile endpoints (no OSM / Carto - those block bulk notebook use)
    ESRI_IMAGERY = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}"
    )
    ESRI_TOPO = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
    )
    GOOGLE_SAT = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"

    def _basemap_sources(kind: str) -> list:
        """Ordered fallbacks that are known to load without OSM 403 blocks."""
        if kind in {"topo", "light", "streets"}:
            # Prefer Esri topo for “light map” look; never OSM/Carto
            return [ESRI_TOPO, ESRI_IMAGERY, GOOGLE_SAT]
        # default / imagery
        return [ESRI_IMAGERY, GOOGLE_SAT, ESRI_TOPO]

    def _plot_with_basemap(draw_fn, title: str, out_name: str, basemap: str = "imagery"):
        """
        Draw overlays in EPSG:3857 and add Esri (or Google) imagery tiles.
        OSM and Carto are intentionally excluded (tile-policy / API blocks).
        Falls back to plain axes if all tile sources fail.
        """
        fig, ax = plt.subplots(figsize=(10.5, 9.2))
        used_basemap = False
        basemap_name = ""
        try:
            import contextily as ctx

            grid_web = grid.to_crs(3857)
            su_web = su.to_crs(3857)
            st_web = su_tree.to_crs(3857) if su_tree is not None else None
            draw_fn(ax, grid_web, su_web, st_web, web=True)

            last_err = None
            for source in _basemap_sources(basemap):
                try:
                    ctx.add_basemap(
                        ax,
                        source=source,
                        attribution="Esri / Google tiles",
                        attribution_size=6,
                        zoom="auto",
                    )
                    used_basemap = True
                    basemap_name = (
                        "Esri World Imagery" if "World_Imagery" in source
                        else "Esri World Topo" if "World_Topo" in source
                        else "Google Satellite"
                    )
                    break
                except Exception as e:
                    last_err = e
                    continue
            if not used_basemap and last_err is not None:
                raise last_err
            ax.set_axis_off()
        except Exception as exc:
            # Geographic axes fallback - never leave blocked OSM error tiles on the figure
            ax.clear()
            draw_fn(ax, grid, su, su_tree, web=False)
            ax.set_xlabel("Longitude")
            ax.set_ylabel("Latitude")
            ax.text(
                0.01, 0.01, f"Basemap unavailable ({type(exc).__name__})",
                transform=ax.transAxes, fontsize=7, color="0.4",
            )
        suffix = f" | {basemap_name}" if used_basemap else " | no basemap"
        ax.set_title(title + suffix)
        fig.tight_layout()
        out_path = out_dir / out_name
        fig.savefig(out_path, dpi=170, bbox_inches="tight")
        plt.close(fig)
        return str(out_path), used_basemap

    def _draw_grid_su(ax, g, s, st, web=False):
        g.boundary.plot(ax=ax, linewidth=0.45, color="#38bdf8", alpha=0.9)
        s.plot(ax=ax, markersize=10, color="#b91c1c", alpha=0.85)

    def _draw_region(ax, g, s, st, web=False):
        g.plot(
            column="reg_e", ax=ax, legend=True, cmap="tab10",
            edgecolor="white", linewidth=0.25, alpha=0.72,
            legend_kwds={"loc": "lower left", "fontsize": 8},
        )

    def _draw_gov(ax, g, s, st, web=False):
        g.plot(
            column="gover_e", ax=ax, legend=False, cmap="gist_ncar",
            edgecolor="white", linewidth=0.2, alpha=0.72,
        )

    def _draw_area(ax, g, s, st, web=False):
        g.plot(
            column="Area_H", ax=ax, legend=True, cmap="YlGnBu",
            edgecolor="white", linewidth=0.2, alpha=0.78,
            legend_kwds={"label": "Area_H (ha)"},
        )

    def _draw_gate1(ax, g, s, st, web=False):
        g.boundary.plot(ax=ax, linewidth=0.35, color="#94a3b8", alpha=0.7)
        if st is None:
            return
        st.loc[st["has_tree_record"]].plot(ax=ax, markersize=16, color="#9f1239", label="Has tree records")
        st.loc[~st["has_tree_record"]].plot(
            ax=ax, markersize=16, color="#ea580c", label="No tree records (Gate 1)"
        )
        ax.legend(loc="lower left")

    p1, bm1 = _plot_with_basemap(
        _draw_grid_su,
        "Asir analytical grid with sampling-unit locations (n=430)",
        "map_asir_grid_su.png",
        basemap="imagery",
    )
    paths["grid_su"] = p1

    p2, bm2 = _plot_with_basemap(
        _draw_region,
        "Asir grid cells by administrative region (reg_e)",
        "map_asir_grid_by_region.png",
        basemap="topo",
    )
    paths["by_region"] = p2

    p3, bm3 = _plot_with_basemap(
        _draw_gov,
        "Asir grid cells by governorate (gover_e)",
        "map_asir_grid_by_governorate.png",
        basemap="imagery",
    )
    paths["by_governorate"] = p3

    if "Area_H" in grid.columns:
        p4, bm4 = _plot_with_basemap(
            _draw_area,
            "Inventory cell Area_H (attribute join by SU key)",
            "map_asir_grid_area_h.png",
            basemap="topo",
        )
        paths["area_h"] = p4

    if su_tree is not None:
        p5, bm5 = _plot_with_basemap(
            _draw_gate1,
            "Gate 1 review: tree-record presence (anti-clip SU universe)",
            "map_gate1_su_status.png",
            basemap="imagery",
        )
        paths["gate1"] = p5

    paths["_basemap_note"] = (
        "Static PNGs use Esri World Imagery / Esri World Topo (Google Satellite fallback). "
        "OSM and Carto tiles are not used (blocked / API-key issues). "
        "Interactive HTML maps: Esri World Imagery, Google Satellite, Google Hybrid only."
    )
    print("Static maps with basemaps written under", out_dir)
    print(paths["_basemap_note"])
    return paths
