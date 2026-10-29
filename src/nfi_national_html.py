# -*- coding: utf-8 -*-
"""National HTML report and interactive Leaflet map production.

Writes under outputs_national_v5/documents/ and maps/html_interactive/.
Uses only computed values passed in by the caller (no invented KPIs).
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nfi_audit import plot_coordinate_qa
from nfi_area_maps import _add_free_basemaps


def _esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def _center_from_xy(lon: pd.Series, lat: pd.Series) -> list[float]:
    lo = pd.to_numeric(lon, errors="coerce")
    la = pd.to_numeric(lat, errors="coerce")
    m = lo.notna() & la.notna()
    if not m.any():
        return [23.5, 45.0]
    return [float(la[m].median()), float(lo[m].median())]


def _banner(m, title: str, subtitle: str) -> None:
    import folium

    m.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;top:10px;left:50px;z-index:9999;'
            "background:rgba(255,253,248,0.94);padding:8px 12px;border:1px solid #1b2838;"
            'border-radius:4px;font-family:Segoe UI,sans-serif;max-width:420px;">'
            f"<b>{_esc(title)}</b><br>"
            f"<span style='font-size:12px'>{_esc(subtitle)}</span></div>"
        )
    )


def _su_presence_points(lattice: pd.DataFrame, plot_qa: pd.DataFrame) -> pd.DataFrame:
    """One representative validated coordinate per SU with tree-presence flag."""
    coords = (
        plot_qa.loc[plot_qa["lon_validated"].notna() & plot_qa["lat_validated"].notna(),
                    ["SU_UID", "lon_validated", "lat_validated"]]
        .groupby("SU_UID", as_index=False)
        .first()
    )
    tree_flag = (
        lattice.groupby("SU_UID", as_index=False)["has_tree_record"]
        .any()
        .rename(columns={"has_tree_record": "has_tree_record"})
    )
    out = coords.merge(tree_flag, on="SU_UID", how="left")
    if "region" in lattice.columns:
        reg = lattice.groupby("SU_UID", dropna=False)["region"].agg(
            lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA
        )
        out["region"] = out["SU_UID"].map(reg)
    return out


def write_national_interactive_maps(
    plot: pd.DataFrame,
    cfg: dict,
    lattice: pd.DataFrame,
    su_metrics: pd.DataFrame | None,
    out_dir: Path,
    *,
    max_plot_markers: int = 8000,
) -> dict[str, str]:
    """Build interactive Leaflet HTML maps for the national plot universe."""
    import folium
    from folium.plugins import Fullscreen, MarkerCluster, MousePosition

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    qa = plot_coordinate_qa(plot, cfg)
    center = _center_from_xy(qa["lon_validated"], qa["lat_validated"])

    # --- Map 1: national plots ---
    m1 = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
    _add_free_basemaps(m1)
    Fullscreen().add_to(m1)
    MousePosition().add_to(m1)
    cluster = MarkerCluster(name="NFI plots (clustered)", show=True)
    pts = qa.loc[qa["lon_validated"].notna() & qa["lat_validated"].notna()].copy()
    if len(pts) > max_plot_markers:
        pts = pts.sample(n=max_plot_markers, random_state=int(cfg.get("project", {}).get("random_seed", 42)))
        subtitle = f"Validated plot coordinates (sampled {len(pts):,} of available for browser performance)"
    else:
        subtitle = f"Validated plot coordinates (n={len(pts):,})"
    for _, row in pts.iterrows():
        folium.CircleMarker(
            location=[float(row["lat_validated"]), float(row["lon_validated"])],
            radius=3,
            color="#0072B2",
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>PLOT_UID:</b> {_esc(row.get('PLOT_UID'))}<br>"
                f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                f"<b>coord_source:</b> {_esc(row.get('coord_source'))}",
                max_width=280,
            ),
            tooltip=str(row.get("PLOT_UID", "")),
        ).add_to(cluster)
    cluster.add_to(m1)
    folium.LayerControl(collapsed=False).add_to(m1)
    _banner(m1, "National NFI plots", subtitle + " | Esri / Google basemaps")
    p1 = out_dir / "interactive_national_plots.html"
    m1.save(str(p1))
    paths["plots"] = str(p1)

    # --- Map 2: SU tree presence ---
    su_pts = _su_presence_points(lattice, qa)
    m2 = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
    _add_free_basemaps(m2)
    Fullscreen().add_to(m2)
    g_yes = folium.FeatureGroup(name="SU with tree records", show=True)
    g_no = folium.FeatureGroup(name="SU with zero trees (Gate)", show=True)
    for _, row in su_pts.iterrows():
        has_t = bool(row.get("has_tree_record")) if pd.notna(row.get("has_tree_record")) else False
        color = "#009E73" if has_t else "#D55E00"
        target = g_yes if has_t else g_no
        folium.CircleMarker(
            location=[float(row["lat_validated"]), float(row["lon_validated"])],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.8,
            popup=folium.Popup(
                f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                f"<b>region:</b> {_esc(row.get('region'))}<br>"
                f"<b>has_tree_record:</b> {has_t}",
                max_width=280,
            ),
            tooltip=f"SU {row.get('SU_UID')}",
        ).add_to(target)
    g_yes.add_to(m2)
    g_no.add_to(m2)
    folium.LayerControl(collapsed=False).add_to(m2)
    _banner(
        m2,
        "National tree-presence gate (SU points)",
        f"SUs with coords: {len(su_pts):,} | green=has trees, orange=zero trees",
    )
    p2 = out_dir / "interactive_national_tree_presence.html"
    m2.save(str(p2))
    paths["tree_presence"] = str(p2)

    # --- Map 3: provisional tree carbon ---
    carbon_col = "tree_carbon_mg_provisional_mean_of_5_plots"
    if su_metrics is not None and carbon_col in su_metrics.columns:
        m3 = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
        _add_free_basemaps(m3)
        Fullscreen().add_to(m3)
        joined = su_pts.merge(su_metrics[["SU_UID", carbon_col]], on="SU_UID", how="left")
        vals = pd.to_numeric(joined[carbon_col], errors="coerce")
        vmax = float(vals.quantile(0.95)) if vals.notna().any() else 1.0
        vmax = vmax if vmax > 0 else 1.0
        fg = folium.FeatureGroup(name="SU mean provisional tree carbon", show=True)
        for _, row in joined.iterrows():
            v = row.get(carbon_col)
            if pd.isna(v):
                continue
            t = min(float(v) / vmax, 1.0)
            # YlGn-like: pale -> dark green
            color = "#006d2c" if t > 0.66 else ("#31a354" if t > 0.33 else "#a1d99b")
            folium.CircleMarker(
                location=[float(row["lat_validated"]), float(row["lon_validated"])],
                radius=4 + 6 * t,
                color=color,
                fill=True,
                fill_opacity=0.75,
                popup=folium.Popup(
                    f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                    f"<b>mean tree carbon (Mg, provisional sample):</b> {float(v):.4g}",
                    max_width=300,
                ),
            ).add_to(fg)
        fg.add_to(m3)
        folium.LayerControl(collapsed=False).add_to(m3)
        _banner(
            m3,
            "National SU mean provisional tree carbon",
            "Sample metric (not design-based). Marker size and colour scale with value.",
        )
        p3 = out_dir / "interactive_national_tree_carbon.html"
        m3.save(str(p3))
        paths["tree_carbon"] = str(p3)

    # --- Map 4: shrub carbon if present ---
    shrub_col = "shrub_carbon_mg_provisional_mean_of_5_plots"
    if su_metrics is not None and shrub_col in su_metrics.columns:
        m4 = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
        _add_free_basemaps(m4)
        Fullscreen().add_to(m4)
        joined = su_pts.merge(su_metrics[["SU_UID", shrub_col]], on="SU_UID", how="left")
        vals = pd.to_numeric(joined[shrub_col], errors="coerce")
        vmax = float(vals.quantile(0.95)) if vals.notna().any() else 1.0
        vmax = vmax if vmax > 0 else 1.0
        fg = folium.FeatureGroup(name="SU mean provisional shrub carbon", show=True)
        for _, row in joined.iterrows():
            v = row.get(shrub_col)
            if pd.isna(v) or float(v) <= 0:
                continue
            t = min(float(v) / vmax, 1.0)
            color = "#8c2d04" if t > 0.66 else ("#d94801" if t > 0.33 else "#fdbe85")
            folium.CircleMarker(
                location=[float(row["lat_validated"]), float(row["lon_validated"])],
                radius=4 + 6 * t,
                color=color,
                fill=True,
                fill_opacity=0.75,
                popup=folium.Popup(
                    f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                    f"<b>mean shrub carbon (Mg, provisional sample):</b> {float(v):.4g}",
                    max_width=300,
                ),
            ).add_to(fg)
        fg.add_to(m4)
        folium.LayerControl(collapsed=False).add_to(m4)
        _banner(
            m4,
            "National SU mean provisional shrub carbon",
            "Sample metric from calc-doc shrub chain. CO2eq not stated for shrubs in DOCX.",
        )
        p4 = out_dir / "interactive_national_shrub_carbon.html"
        m4.save(str(p4))
        paths["shrub_carbon"] = str(p4)

    return paths


def write_national_html_atlas(
    map_paths: dict[str, str],
    out_dir: Path,
    catalog: pd.DataFrame | None = None,
) -> Path:
    """Portal index that embeds interactive national Leaflet maps in an iframe."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Prefer catalog order when provided; else fall back to map_paths keys
    themes: list[tuple[str, str, str, str]] = []
    if catalog is not None and len(catalog):
        for _, r in catalog.iterrows():
            key = str(r["theme_id"])
            if key not in map_paths:
                continue
            themes.append((
                key,
                str(r.get("title") or key),
                str(r.get("blurb") or ""),
                str(r.get("category") or "Themes"),
            ))
    else:
        for key in map_paths:
            themes.append((key, key.replace("_", " ").title(), "", "Themes"))

    cards = []
    first_src = None
    last_cat = None
    for key, title, blurb, category in themes:
        src = Path(map_paths[key])
        try:
            rel = str(src.resolve().relative_to(out_dir.resolve()))
        except ValueError:
            rel = str(Path("..") / "html_interactive" / src.name)
        if first_src is None:
            first_src = rel
        if category != last_cat:
            cards.append(f'<div class="cat">{_esc(category)}</div>')
            last_cat = category
        cards.append(
            f'<button class="theme" data-src="{_esc(rel)}" type="button">'
            f"<strong>{_esc(title)}</strong><span>{_esc(blurb)}</span></button>"
        )
    index = out_dir / "index.html"
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>KSA NFI National Interactive Atlas</title>
<style>
body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#171717;display:flex;height:100vh}}
aside{{width:320px;min-width:280px;border-right:1px solid #d4d4d4;padding:16px;overflow:auto;background:#fafafa}}
main{{flex:1;display:flex;flex-direction:column}}
h1{{font-size:18px;margin:0 0 6px}}
.sub{{font-size:12px;color:#525252;margin-bottom:14px}}
.theme{{display:block;width:100%;text-align:left;margin:0 0 8px;padding:10px 12px;border:1px solid #d4d4d4;
border-left:4px solid #404040;border-radius:8px;background:#fff;cursor:pointer}}
.theme strong{{display:block;font-size:13px}}
.theme span{{display:block;font-size:11px;color:#525252;margin-top:4px}}
.theme.active{{border-left-color:#0072B2;background:#f0f7fb}}
.cat{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#525252;margin:14px 0 6px;font-weight:700}}
iframe{{border:0;flex:1;width:100%}}
.bar{{padding:8px 12px;border-bottom:1px solid #d4d4d4;font-size:12px;background:#fff}}
</style>
</head>
<body>
<aside>
  <h1>KSA NFI National Atlas</h1>
  <div class="sub">Thematic interactive Leaflet maps for the entire-country tabular frame. Biomass and carbon themes are provisional sample metrics.</div>
  {''.join(cards)}
</aside>
<main>
  <div class="bar" id="caption">Select a theme</div>
  <iframe id="frame" src="{_esc(first_src or '')}" title="National interactive map"></iframe>
</main>
<script>
const buttons=[...document.querySelectorAll('.theme')];
const frame=document.getElementById('frame');
const caption=document.getElementById('caption');
function activate(btn){{
  buttons.forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  frame.src=btn.dataset.src;
  caption.textContent=btn.querySelector('strong').textContent;
}}
buttons.forEach(btn=>btn.addEventListener('click',()=>activate(btn)));
if(buttons[0]) activate(buttons[0]);
</script>
</body>
</html>
"""
    index.write_text(doc, encoding="utf-8")
    return index


def _df_html_table(df: pd.DataFrame, max_rows: int = 25) -> str:
    if df is None or len(df) == 0:
        return "<p><em>No rows.</em></p>"
    view = df.head(max_rows).copy()
    for c in view.select_dtypes(include=[np.number]).columns:
        view[c] = view[c].map(lambda x: f"{x:.4g}" if pd.notna(x) else "-")
    return view.to_html(index=False, border=0, classes="tbl", na_rep="-", escape=True)


def _img_tag(path: Path | str | None, alt: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return f"<p class='note'>Missing figure: {_esc(alt)}</p>"
    import base64

    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return (
        f'<figure class="fig"><img alt="{_esc(alt)}" src="data:{mime};base64,{b64}"/>'
        f"<figcaption>{_esc(alt)}</figcaption></figure>"
    )


def _ds_img_block(ds_pack: dict | None, key: str, alt: str) -> str:
    if not ds_pack:
        return ""
    path = ds_pack.get(key)
    return _img_tag(path, alt) if path else ""


def _ds_path_dict_block(path_dict: dict | None, title_prefix: str, limit: int = 12) -> str:
    if not path_dict:
        return ""
    parts = []
    for i, (name, path) in enumerate(path_dict.items()):
        if i >= limit:
            break
        parts.append(_img_tag(path, f"{title_prefix}: {name}"))
    return "".join(parts)


def write_national_html_report(
    *,
    out_path: Path,
    run_summary: dict,
    by_region: pd.DataFrame,
    ancillary: pd.DataFrame,
    area_cov: pd.DataFrame | None = None,
    gate: dict | None = None,
    gate_shrub: dict | None = None,
    fig_paths: dict | None = None,
    map_paths: dict | None = None,
    interactive_paths: dict | None = None,
    atlas_index: Path | str | None = None,
    assumptions: list[str] | None = None,
    uni_trees: pd.DataFrame | None = None,
    uni_shrubs: pd.DataFrame | None = None,
    biv_spearman: pd.DataFrame | None = None,
    biv_pearson: pd.DataFrame | None = None,
    ds_pack: dict | None = None,
) -> Path:
    """Professional data-science national report: process, missingness, KDE, themes, maps."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig_paths = fig_paths or {}
    map_paths = map_paths or {}
    interactive_paths = interactive_paths or {}
    ds_pack = ds_pack or {}

    gate = gate or run_summary.get("gate_tree_presence") or {}
    gate_shrub = gate_shrub or run_summary.get("gate_shrub_presence") or {}
    assumptions = assumptions or run_summary.get("assumptions") or []

    kpis = [
        ("SUs (national)", run_summary.get("n_su")),
        ("Regions", run_summary.get("n_regions")),
        ("Plot lattice", run_summary.get("lattice_rows")),
        ("Tree biomass rows", run_summary.get("n_tree_biomass_rows")),
        ("Shrub biomass rows", run_summary.get("n_shrub_biomass_rows")),
        ("SUs with trees", gate.get("sus_with_trees")),
        ("SUs with shrubs", gate_shrub.get("sus_with_shrubs")),
        ("GIS Area_H attached", run_summary.get("gis_area_attached_sus")),
        ("Area blocked", run_summary.get("gis_area_blocked_sus")),
        ("Design-based", "No" if not run_summary.get("design_based_estimates") else "Yes"),
        ("Interactive themes", run_summary.get("n_interactive_themes")),
        ("Voronoi cells", run_summary.get("n_voronoi_cells")),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div></div>'
        for k, v in kpis
    )

    imap_btns = "".join(
        f'<a class="btn soft" href="../maps/html_interactive/{_esc(Path(p).name)}" target="_blank">{_esc(name)}</a>'
        for name, p in list(interactive_paths.items())[:24]
    )
    atlas_btn = (
        '<a class="btn" href="../maps/html_atlas/index.html" target="_blank">Open interactive map atlas</a>'
        if atlas_index else ""
    )

    fig_block = ""
    for key, title in [
        ("univariate_trees_national", "Fancy univariate: trees raw field (hist+KDE, box, violin, strip)"),
        ("univariate_trees_fv_national", "Fancy univariate: tree provisional FV (hist+KDE, box, violin, strip)"),
        ("univariate_shrubs_national", "Fancy univariate: shrub provisional metrics"),
        ("bivariate_scatter_trees_national", "Fancy bivariate: tree scatter / density matrix"),
        ("bivariate_scatter_shrubs_national", "Fancy bivariate: shrub scatter / density matrix"),
        ("bivariate_corr_trees_national", "Bivariate: tree Spearman vs Pearson heatmaps"),
    ]:
        if key in fig_paths:
            fig_block += _img_tag(fig_paths[key], title)
    # Per-metric distribution suites (box / violin / KDE)
    suite_keys = sorted(k for k in fig_paths if str(k).startswith("suite_"))
    for key in suite_keys[:16]:
        fig_block += _img_tag(fig_paths[key], f"Distribution suite: {key.replace('suite_', '').replace('_', ' ')}")

    flow_fig = _ds_img_block(ds_pack, "flowchart", "Data processing and feature-engineering flowchart")
    miss_figs = (
        _ds_img_block(ds_pack, "missingness_trees", "Missingness profile: national trees")
        + _ds_img_block(ds_pack, "missingness_shrubs", "Missingness profile: national shrubs")
    )
    kde_block = (
        _ds_path_dict_block(ds_pack.get("kde_raw"), "KDE suite (raw field)", 6)
        + _ds_path_dict_block(ds_pack.get("kde_trees_fv"), "KDE suite (tree FV)", 8)
        + _ds_path_dict_block(ds_pack.get("kde_shrubs"), "KDE suite (shrubs)", 6)
    )
    theme_bars = _ds_path_dict_block(ds_pack.get("theme_bars"), "Thematic frequency", 12)
    agent_tbl = ds_pack.get("agent_tbl")
    fire_tbl = ds_pack.get("fire_tbl")
    env_tbl = ds_pack.get("env_tbl")
    miss_top = ds_pack.get("miss_trees")
    if isinstance(miss_top, pd.DataFrame) and len(miss_top):
        miss_top = miss_top.head(15)
    else:
        miss_top = pd.DataFrame()

    map_block = ""
    preferred_map_keys = [
        ("map_national_plots", "National plots (static)"),
        ("map_national_su_mean_tree_carbon", "SU mean provisional tree carbon (static)"),
        ("thematic_tree_count", "Thematic (points): tree count"),
        ("thematic_species_richness", "Thematic (points): species richness"),
        ("thematic_mean_dbh", "Thematic (points): mean DBH"),
        ("thematic_sum_agb", "Thematic (points): tree AGB"),
        ("thematic_sum_carbon", "Thematic (points): tree carbon"),
        ("thematic_land_use", "Thematic (points): modal land use"),
        ("thematic_tree_canopy", "Thematic (points): tree canopy"),
        ("thematic_fire_presence", "Thematic (points): fire evidence"),
        ("thematic_fire_type", "Thematic (points): fire type"),
        ("thematic_env_problem", "Thematic (points): env. problem present"),
        ("thematic_env_category", "Thematic (points): env. category"),
        ("thematic_causative_agent", "Thematic (points): modal causative agent"),
        ("thematic_has_causative_agent", "Thematic (points): causative agent recorded"),
        ("thematic_deadwood_presence", "Thematic (points): deadwood"),
        ("thematic_regen_count", "Thematic (points): regeneration"),
        ("thematic_tree_condition", "Thematic (points): tree condition"),
        ("thematic_crown_condition", "Thematic (points): crown condition"),
        ("thematic_region", "Thematic (points): region"),
        ("thematic_voronoi_sum_carbon", "Voronoi choropleth: tree carbon"),
        ("thematic_voronoi_mean_dbh", "Voronoi choropleth: mean DBH"),
        ("thematic_voronoi_fire_presence", "Voronoi choropleth: fire evidence"),
        ("thematic_voronoi_causative_agent", "Voronoi choropleth: causative agent"),
        ("thematic_hexbin_sum_carbon", "Hexbin surface: tree carbon"),
        ("thematic_hexbin_mean_dbh", "Hexbin surface: mean DBH"),
        ("thematic_hexbin_fire_presence", "Hexbin surface: fire presence"),
    ]
    for key, title in preferred_map_keys:
        if key in map_paths:
            map_block += _img_tag(map_paths[key], title)
    shown = {k for k, _ in preferred_map_keys}
    extra = 0
    for key, path in map_paths.items():
        if key in shown or not str(key).startswith("thematic_"):
            continue
        if extra >= 10:
            break
        map_block += _img_tag(path, key.replace("thematic_", "Thematic: ").replace("_", " "))
        extra += 1

    open_items = [
        ("National Area_H", "Only Asir and Makkah grids attach Area_H in this workspace."),
        ("Design weights", "Design-based national totals remain blocked."),
        ("Shrub log base", "Natural log assumed (not stated in calc DOCX)."),
        ("Ancillary biomass", "Deadwood/litter/regen/veg have no calc-doc biomass equations."),
        ("Voronoi / hex", "Influence polygons and hex aggregates are cartographic representations; points are the sample frame."),
    ]
    oi = "".join(f"<li><b>{_esc(a)}</b>: {_esc(b)}</li>" for a, b in open_items)
    assump = "".join(f"<li>{_esc(a)}</li>" for a in assumptions)

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>KSA NFI National Data Science Report</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Literata:opsz,wght@7..72,500;7..72,700&display=swap');
:root {{
  --ink:#1a2420; --muted:#4a5a52; --line:#d5ddd7; --paper:#f7f9f6; --card:#fff;
  --forest:#1b5e20; --soft:#e8f0e9; --shadow:0 8px 28px rgba(26,36,32,.07);
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0; color:var(--ink); font-family:"IBM Plex Sans","Segoe UI",sans-serif; line-height:1.55;
  background: radial-gradient(1200px 500px at 10% -10%, #e6efe7 0%, transparent 55%),
              radial-gradient(900px 420px at 100% 0%, #f3ebe3 0%, transparent 45%), var(--paper);
}}
header {{
  background: linear-gradient(135deg, #14351c 0%, #1b5e20 48%, #245c38 100%);
  color:#f4faf5; padding:34px clamp(16px,4vw,40px) 28px; box-shadow:var(--shadow);
}}
header h1 {{ font-family:Literata,Georgia,serif; margin:0; font-size:clamp(1.4rem,2.2vw,2rem); color:#fff; }}
header p {{ margin:12px 0 0; color:rgba(255,255,255,.92); max-width:72rem; }}
.kicker {{ font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:#b7d4bc; font-weight:600; margin:0 0 10px; }}
.toc {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
.toc a {{ color:#14351c; background:rgba(255,255,255,.92); text-decoration:none; font-size:.78rem; font-weight:600; padding:6px 10px; border-radius:999px; }}
main {{ padding:28px clamp(16px,4vw,40px) 64px; max-width:1100px; margin:0 auto; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin:0 0 22px; box-shadow:var(--shadow); }}
h2 {{ font-family:Literata,Georgia,serif; color:var(--forest); margin:0 0 8px; font-size:1.25rem; }}
h3 {{ color:#245c38; margin:16px 0 8px; font-size:1.05rem; }}
.lead {{ color:var(--muted); margin:0 0 12px; font-size:.95rem; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:10px; }}
.kpi {{ border:1px solid var(--line); border-top:4px solid var(--forest); border-radius:10px; padding:10px 12px; background:#fff; }}
.kpi .k {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.kpi .v {{ font-size:1.35rem; font-weight:800; margin-top:4px; }}
.tbl {{ border-collapse:collapse; width:100%; font-size:13px; }}
.tbl th,.tbl td {{ border:1px solid #e5e5e5; padding:6px 8px; text-align:left; }}
.tbl th {{ background:var(--soft); }}
.fig {{ margin:14px 0; }}
.fig img {{ width:100%; height:auto; border:1px solid var(--line); border-radius:10px; display:block; }}
.figcaption {{ font-size:12px; color:var(--muted); margin-top:6px; }}
.btn {{ display:inline-block; margin:4px 6px 4px 0; padding:10px 14px; background:#14351c; color:#fff; text-decoration:none; border-radius:8px; font-weight:600; font-size:.9rem; }}
.btn.soft {{ background:#fff; color:#14351c; border:1px solid var(--line); }}
.note {{ background:var(--soft); border:1px solid var(--line); border-radius:8px; padding:10px 12px; font-size:13px; }}
.flow {{ display:grid; gap:8px; }}
.flow div {{ background:#fff; border-left:4px solid var(--forest); border:1px solid var(--line); border-left-width:4px; border-radius:8px; padding:8px 12px; font-size:.92rem; }}
footer {{ color:var(--muted); font-size:12px; padding:0 0 40px; text-align:center; }}
</style>
</head>
<body>
<header>
  <p class="kicker">Kingdom of Saudi Arabia · National Forest Inventory · Data science report</p>
  <h1>National geopipeline: data processing, EDA and thematic results</h1>
  <p>Entire-country tabular universe. Structure follows a professional data-science reporting arc: ingest and engineering, missing-data handling, distributional EDA (KDE suites), thematic disturbance and health results (fire, causative agents, environmental problems), then cartographic products (points, Voronoi / Thiessen, hexbin).</p>
  <nav class="toc" aria-label="Jump to section">
    <a href="#executive">Executive</a>
    <a href="#workflow">Process</a>
    <a href="#missingness">Missing data</a>
    <a href="#methodology">Methodology</a>
    <a href="#kde">KDE / distributions</a>
    <a href="#thematic-results">Fire · disease · env</a>
    <a href="#univariate">Univariate</a>
    <a href="#bivariate">Bivariate</a>
    <a href="#maps">Cartography</a>
    <a href="#interactive">Interactive</a>
    <a href="#assumptions">Assumptions</a>
    <a href="#outputs">Outputs</a>
  </nav>
</header>
<main>

<section id="executive">
  <h2>1. Executive summary (computed KPIs)</h2>
  <p class="lead">Values below are taken from the computed run summary for this package run. No invented figures.</p>
  <div class="kpis">{kpi_html}</div>
</section>

<section id="workflow">
  <h2>2. Data processing and feature engineering</h2>
  <p class="lead">Anti-clip national frame: every SU keeps five plot slots even when trees or shrubs are absent. Feature engineering follows the official Trees and Shrubs calculation document only.</p>
  {flow_fig}
  <div class="flow">
    <div>1. Ingest national cleansed tables and attach SU_UID / PLOT_UID keys</div>
    <div>2. Coordinate QA (field vs database) and validated lon/lat</div>
    <div>3. Build SU × 5 anti-clip plot lattice for the full SU master</div>
    <div>4. Presence gates (trees and shrubs) without deleting zero cells</div>
    <div>5. Optional Area_H join from Asir and Makkah grids only</div>
    <div>6. Exclude grass / Calotropis / palm (trees) and grass (shrubs)</div>
    <div>7. Engineer BA, volume, AGB, BGB, carbon, CO2eq (trees) and shrub allometrics</div>
    <div>8. Missingness audit + KDE / distribution suites</div>
    <div>9. Thematic SU attributes: fire, env problems, causative agents, condition</div>
    <div>10. Point maps + Voronoi / Thiessen + hexbin cartography + HTML atlas</div>
  </div>
</section>

<section id="missingness">
  <h2>3. Missing-data handling</h2>
  <p class="lead">Missingness is profiled before modelling. Zero-tree and zero-shrub SUs are retained (anti-clip). Biomass metrics are computed only where required inputs are present; design-based expansion remains blocked without Area_H and weights.</p>
  <h3>Top incomplete columns (national trees)</h3>
  {_df_html_table(miss_top, max_rows=15)}
  {miss_figs or '<p class="note">Missingness figures not produced in this run.</p>'}
</section>

<section id="methodology">
  <h2>4. Methodology (official formulas)</h2>
  <p class="lead">Source: <code>data/docs/NFI_ KSA Calculation_Trees&amp;shrubs.docx</code> and extract <code>data/docs/_calc_doc_extract.md</code>.</p>
  <h3>Trees</h3>
  <ul>
    <li>Basal area (m²) = π × DBH² / 40000</li>
    <li>Volume (m³) = BA × height (m) × form factor 0.65</li>
    <li>AGB (Mg) = volume × wood density 0.6 × BEF 2</li>
    <li>BGB (Mg) = AGB × 0.28</li>
    <li>Carbon (Mg) = (AGB + BGB) × 0.47</li>
    <li>CO₂eq (Mg) = Carbon × 3.67</li>
    <li>Per-ha sample scaling uses conversion factor 10 (plot 1000 m²)</li>
  </ul>
  <h3>Shrubs</h3>
  <ul>
    <li>mean_CD_m = mean of crown diameters; height converted to cm</li>
    <li>AGB = (exp(-0.37 + 1.903 log(CD) + 0.652 log(H)) + 1.403) / 1000</li>
    <li>BGB = AGB × 0.28; carbon = (AGB + BGB) × 0.47</li>
    <li>Shrub CO₂eq not stated in the DOCX shrub section (left blank)</li>
  </ul>
  <div class="note">Exclusions: trees exclude grass / Calotropis / palm substrings; shrubs exclude grass.</div>
</section>

<section id="regions">
  <h2>5. Sampling frame by region</h2>
  {_df_html_table(by_region, max_rows=20)}
  <h3>GIS Area_H coverage</h3>
  {_df_html_table(area_cov if area_cov is not None else pd.DataFrame(), max_rows=10)}
  <h3>Ancillary pools (inventory only)</h3>
  {_df_html_table(ancillary, max_rows=20)}
</section>

<section id="kde">
  <h2>6. Distributional EDA (histogram + KDE, box, violin, strip)</h2>
  <p class="lead">Fancy coloured distribution suites for raw field metrics and engineered provisional FV metrics. Each panel embeds histogram with kernel density estimate, boxplot, violin, and strip/bubble scatter.</p>
  {fig_block}
  {kde_block or '<p class="note">Additional per-metric KDE suites live under figures/national_ds/.</p>'}
</section>

<section id="thematic-results">
  <h2>7. Thematic results: fire, causative agents, environmental problems</h2>
  <p class="lead">Frequencies computed from national cleansed tables. Causative agents are disease / damage agents recorded on trees (<code>causative_agent_label[1]</code>). Fire comes from <code>fire_evidence</code>. Environmental problem categories include pest and disease where coded in <code>categories_label</code>.</p>
  <h3>Causative agent frequency (trees)</h3>
  {_df_html_table(agent_tbl if isinstance(agent_tbl, pd.DataFrame) else pd.DataFrame(), max_rows=20)}
  <h3>Fire evidence frequency</h3>
  {_df_html_table(fire_tbl if isinstance(fire_tbl, pd.DataFrame) else pd.DataFrame(), max_rows=20)}
  <h3>Environmental problem categories</h3>
  {_df_html_table(env_tbl if isinstance(env_tbl, pd.DataFrame) else pd.DataFrame(), max_rows=20)}
  {theme_bars or '<p class="note">Thematic bar charts not produced in this run.</p>'}
</section>

<section id="univariate">
  <h2>8. Univariate summary tables</h2>
  <p class="lead">National provisional tree and shrub metrics (computed). Fancy coloured plots appear in Section 6.</p>
  <h3>Tree provisional metrics</h3>
  {_df_html_table(uni_trees if uni_trees is not None else pd.DataFrame(), max_rows=20)}
  <h3>Shrub provisional metrics</h3>
  {_df_html_table(uni_shrubs if uni_shrubs is not None else pd.DataFrame(), max_rows=20)}
</section>

<section id="bivariate">
  <h2>9. Bivariate analysis</h2>
  <p class="lead">Scatter / density matrices and pairwise correlations on provisional FV metrics (Spearman and Pearson). Fancy coloured plots are embedded in Section 6.</p>
  <h3>Spearman</h3>
  {_df_html_table(biv_spearman if biv_spearman is not None else pd.DataFrame(), max_rows=30)}
  <h3>Pearson</h3>
  {_df_html_table(biv_pearson if biv_pearson is not None else pd.DataFrame(), max_rows=30)}
</section>

<section id="maps">
  <h2>10. Cartography: points, Voronoi / Thiessen, hexbin</h2>
  <p class="lead">Point symbols show sample locations. Voronoi (Thiessen) polygons are nearest-neighbour influence zones used when an SU area frame is absent (Okabe et al., 2000). Hexbin mosaics summarise local means (Carr et al., 1992). Interactive atlas supports toggling points / polygons / overlay.</p>
  {map_block or '<p class="note">No static maps in this run.</p>'}
</section>

<section id="interactive">
  <h2>11. Interactive map HTML and atlas</h2>
  <p class="lead">Open the atlas for Leaflet pan/zoom with dynamic KPIs, region/governorate filters, and cartographic representation modes (points, Voronoi, polygons + points).</p>
  <p>{atlas_btn}</p>
  <p>{imap_btns}</p>
</section>

<section id="assumptions">
  <h2>12. Open items and assumptions</h2>
  <h3>Open items</h3>
  <ul>{oi}</ul>
  <h3>Assumptions logged with this run</h3>
  <ul>{assump}</ul>
</section>

<section id="outputs">
  <h2>13. Outputs to share</h2>
  <ul>
    <li>This report: <code>documents/NFI_national_geopipeline_report.html</code></li>
    <li>Interactive atlas: <code>maps/html_atlas/index.html</code></li>
    <li>DS figures: <code>figures/national_ds/</code></li>
    <li>Cartography: <code>maps/cartography/</code> (Voronoi GeoJSON, hexbin PNGs)</li>
    <li>Interactive maps: <code>maps/html_interactive/</code></li>
    <li>Run receipt: <code>logs/national_run_summary.json</code></li>
    <li>CLI twin: <code>python run_national_pipeline.py</code></li>
    <li>Output root: <code>{_esc(run_summary.get('output_root'))}</code></li>
  </ul>
  <p>{atlas_btn}
  <a class="btn soft" href="./NFI_national_geopipeline_report.html">This report</a></p>
</section>

</main>
<footer>KSA NFI national data-science report · provisional sample metrics · generated from computed run objects only</footer>
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def produce_national_html_products(
    *,
    plot: pd.DataFrame,
    cfg: dict,
    lattice: pd.DataFrame,
    su_metrics: pd.DataFrame,
    run_summary: dict,
    by_region: pd.DataFrame,
    ancillary: pd.DataFrame,
    area_cov: pd.DataFrame,
    gate: dict,
    gate_shrub: dict,
    fig_paths: dict,
    map_paths: dict,
    out_root: Path,
    tables: dict | None = None,
    tree_m: pd.DataFrame | None = None,
    shrub_m: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Write thematic interactive maps, atlas portal, and HTML report. Returns path dict."""
    out_root = Path(out_root)
    atlas_dir = out_root / "maps" / "html_atlas"
    docs_dir = out_root / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    from nfi_national_thematic_maps import produce_national_thematic_maps
    from nfi_national_atlas_dashboard import write_national_dashboard_atlas
    from nfi_national_ds_report import produce_national_ds_figures

    thematic = {
        "interactive": {}, "static": {}, "catalog": pd.DataFrame(),
        "su_thematic": pd.DataFrame(), "cartography": {},
    }
    ds_pack: dict = {}
    if tables is not None and tree_m is not None and shrub_m is not None:
        ds_pack = produce_national_ds_figures(
            tables=tables,
            tree_m=tree_m,
            shrub_m=shrub_m,
            out_root=out_root,
            cfg=cfg,
        )
        thematic = produce_national_thematic_maps(
            tables=tables,
            tree_m=tree_m,
            shrub_m=shrub_m,
            lattice=lattice,
            plot=plot,
            cfg=cfg,
            out_root=out_root,
        )
        interactive = thematic["interactive"]
        catalog = thematic["catalog"]
        vor_fc = (thematic.get("cartography") or {}).get("voronoi_fc")
        atlas_index = write_national_dashboard_atlas(
            thematic["su_thematic"], atlas_dir, catalog=catalog, voronoi_fc=vor_fc,
        )
        n_vor = len((vor_fc or {}).get("features") or [])
        run_summary["n_voronoi_cells"] = n_vor
    else:
        # Fallback: legacy four-map set + simple portal
        interactive = write_national_interactive_maps(
            plot, cfg, lattice, su_metrics, out_root / "maps" / "html_interactive"
        )
        catalog = None
        atlas_index = write_national_html_atlas(interactive, atlas_dir, catalog=catalog)

    def _read_csv(path: Path) -> pd.DataFrame | None:
        return pd.read_csv(path) if path.exists() else None

    audit = out_root / "audit"
    eda = out_root / "figures" / "national_eda"
    uni_trees = ds_pack.get("uni_trees") if ds_pack.get("uni_trees") is not None else _read_csv(audit / "univariate_national_trees_fv.csv")
    uni_shrubs = ds_pack.get("uni_shrubs") if ds_pack.get("uni_shrubs") is not None else _read_csv(audit / "univariate_national_shrubs_fv.csv")
    biv_s = _read_csv(eda / "bivariate_spearman_trees_national.csv")
    biv_p = _read_csv(eda / "bivariate_pearson_trees_national.csv")

    # Merge static thematic PNGs into map_paths for the report gallery
    map_paths = dict(map_paths or {})
    for k, v in (thematic.get("static") or {}).items():
        map_paths[f"thematic_{k}"] = v

    report = write_national_html_report(
        out_path=docs_dir / "NFI_national_geopipeline_report.html",
        run_summary=run_summary,
        by_region=by_region,
        ancillary=ancillary,
        area_cov=area_cov,
        gate=gate,
        gate_shrub=gate_shrub,
        fig_paths=fig_paths,
        map_paths=map_paths,
        interactive_paths=interactive,
        atlas_index=atlas_index,
        assumptions=run_summary.get("assumptions"),
        uni_trees=uni_trees,
        uni_shrubs=uni_shrubs,
        biv_spearman=biv_s,
        biv_pearson=biv_p,
        ds_pack=ds_pack,
    )
    manifest = {
        "interactive_maps": interactive,
        "static_thematic_maps": thematic.get("static") or {},
        "n_interactive_themes": len(interactive),
        "n_static_themes": len(thematic.get("static") or {}),
        "n_voronoi_cells": run_summary.get("n_voronoi_cells"),
        "ds_figures": str(out_root / "figures" / "national_ds"),
        "atlas_index": str(atlas_index),
        "html_report": str(report),
        "thematic_catalog": str(out_root / "maps" / "national_thematic_catalog.csv"),
    }
    (docs_dir / "national_html_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest
