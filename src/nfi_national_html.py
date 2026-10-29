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


def write_national_html_atlas(map_paths: dict[str, str], out_dir: Path) -> Path:
    """Portal index that embeds interactive national Leaflet maps in an iframe."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Copy or reference maps from interactive folder via relative links
    themes = [
        ("plots", "National plots", "Clustered validated plot coordinates on imagery basemaps."),
        ("tree_presence", "Tree presence gate", "SU points coloured by whether any tree records exist."),
        ("tree_carbon", "Provisional tree carbon", "SU mean sample tree carbon (not design-based)."),
        ("shrub_carbon", "Provisional shrub carbon", "SU mean sample shrub carbon (calc DOCX)."),
    ]
    cards = []
    first_src = None
    for key, title, blurb in themes:
        if key not in map_paths:
            continue
        src = Path(map_paths[key])
        # Prefer relative name if file was written into out_dir or sibling
        rel = src.name
        # If map lives in sibling folder, use relative path from atlas dir
        try:
            rel = str(src.resolve().relative_to(out_dir.resolve()))
        except ValueError:
            # maps/html_interactive vs maps/html_atlas
            try:
                rel = str(Path("..") / "html_interactive" / src.name)
            except Exception:
                rel = src.as_uri()
        if first_src is None:
            first_src = rel
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
iframe{{border:0;flex:1;width:100%}}
.bar{{padding:8px 12px;border-bottom:1px solid #d4d4d4;font-size:12px;background:#fff}}
</style>
</head>
<body>
<aside>
  <h1>KSA NFI National Atlas</h1>
  <div class="sub">Interactive Leaflet maps. Entire-country tabular frame. Carbon layers are provisional sample metrics.</div>
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
    return view.to_html(index=False, border=0, classes="tbl", na_rep="-")


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
) -> Path:
    """Self-contained national HTML report with KPI cards, tables, and map links."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    headline = [
        ("SUs (national)", run_summary.get("n_su")),
        ("Regions", run_summary.get("n_regions")),
        ("Plot lattice", run_summary.get("lattice_rows")),
        ("Tree biomass rows", run_summary.get("n_tree_biomass_rows")),
        ("Shrub biomass rows", run_summary.get("n_shrub_biomass_rows")),
        ("GIS Area_H attached", run_summary.get("gis_area_attached_sus")),
        ("Area blocked", run_summary.get("gis_area_blocked_sus")),
        ("Design-based", "No" if not run_summary.get("design_based_estimates") else "Yes"),
    ]
    cards = "".join(
        f'<div class="card"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div></div>'
        for k, v in headline
    )

    gate = gate or run_summary.get("gate_tree_presence") or {}
    gate_shrub = gate_shrub or run_summary.get("gate_shrub_presence") or {}
    assumptions = assumptions or run_summary.get("assumptions") or []

    fig_list = ""
    for name, p in (fig_paths or {}).items():
        pp = Path(p)
        fig_list += f"<li><b>{_esc(name)}</b>: {_esc(pp.name)}</li>"

    static_maps = ""
    for name, p in (map_paths or {}).items():
        static_maps += f"<li><b>{_esc(name)}</b>: {_esc(Path(p).name)}</li>"

    imap_links = ""
    for name, p in (interactive_paths or {}).items():
        rel = Path(p).name
        imap_links += f'<li><a href="../maps/html_interactive/{_esc(rel)}" target="_blank">{_esc(name)}</a></li>'

    atlas_link = ""
    if atlas_index:
        atlas_link = (
            f'<p><a class="btn" href="../maps/html_atlas/index.html" target="_blank">'
            f"Open interactive atlas portal</a></p>"
        )

    open_items = [
        ("National Area_H", "Only Asir and Makkah grids attach Area_H in this workspace."),
        ("Design weights", "Design-based national totals remain blocked."),
        ("Shrub log base", "Natural log assumed (not stated in calc DOCX)."),
        ("Ancillary biomass", "Deadwood/litter/regen/veg have no calc-doc biomass equations."),
    ]
    oi = "".join(f"<li><b>{_esc(a)}</b>: {_esc(b)}</li>" for a, b in open_items)
    assump = "".join(f"<li>{_esc(a)}</li>" for a in assumptions)

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>KSA NFI National Geopipeline Report</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#171717;
max-width:980px;margin:32px auto;padding:0 20px;line-height:1.55}}
h1{{font-size:26px;margin:0 0 4px}}
h2{{font-size:17px;border-bottom:2px solid #d4d4d4;padding-bottom:4px;margin-top:28px}}
.sub{{color:#525252;font-size:13px;margin-bottom:18px}}
.cards{{display:flex;flex-wrap:wrap;gap:10px}}
.card{{flex:1 1 140px;border:1px solid #d4d4d4;border-top:4px solid #404040;border-radius:8px;padding:10px 12px}}
.k{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#525252}}
.v{{font-size:22px;font-weight:800}}
.tbl{{border-collapse:collapse;width:100%;font-size:13px}}
.tbl th,.tbl td{{border:1px solid #e5e5e5;padding:6px 8px;text-align:left}}
.tbl th{{background:#f5f5f5}}
.btn{{display:inline-block;padding:10px 14px;background:#1b2838;color:#fff;text-decoration:none;border-radius:6px}}
.note{{background:#fafafa;border:1px solid #e5e5e5;border-radius:8px;padding:10px 12px;font-size:13px}}
</style>
</head>
<body>
<h1>KSA NFI National Geopipeline Report</h1>
<div class="sub">Entire-country tabular universe. Generated from computed run summary only.
Carbon and biomass figures are provisional sample metrics unless stated otherwise.</div>
<div class="cards">{cards}</div>

<h2>Presence gates</h2>
<ul>
<li>Trees: { _esc(gate.get('sus_with_trees')) } SUs with trees / { _esc(gate.get('sus_no_trees')) } zero-tree
  (of { _esc(gate.get('total_sus')) })</li>
<li>Shrubs: { _esc(gate_shrub.get('sus_with_shrubs')) } SUs with shrubs / { _esc(gate_shrub.get('sus_no_shrubs')) } zero-shrub
  (of { _esc(gate_shrub.get('total_sus')) })</li>
</ul>

<h2>Sampling units by region</h2>
{_df_html_table(by_region, max_rows=20)}

<h2>GIS Area_H coverage</h2>
{_df_html_table(area_cov if area_cov is not None else pd.DataFrame(), max_rows=10)}

<h2>Ancillary pools (inventory only)</h2>
<div class="note">Biomass blocked for these pools: no equations in the calculation DOCX.</div>
{_df_html_table(ancillary, max_rows=20)}

<h2>Interactive maps (HTML)</h2>
{atlas_link}
<ul>{imap_links or '<li>No interactive maps written in this run.</li>'}</ul>

<h2>Static maps and EDA figures</h2>
<ul>{static_maps}{fig_list}</ul>

<h2>Open items</h2>
<ul>{oi}</ul>

<h2>Assumptions logged with this run</h2>
<ul>{assump}</ul>

<h2>Reproducibility</h2>
<ul>
<li>Output root: <code>{_esc(run_summary.get('output_root'))}</code></li>
<li>Run summary JSON: <code>logs/national_run_summary.json</code></li>
<li>CLI twin: <code>python run_national_pipeline.py</code></li>
<li>Scope label: <code>{_esc(run_summary.get('scope'))}</code></li>
</ul>
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
) -> dict[str, Any]:
    """Write interactive maps, atlas portal, and HTML report. Returns path dict."""
    out_root = Path(out_root)
    imap_dir = out_root / "maps" / "html_interactive"
    atlas_dir = out_root / "maps" / "html_atlas"
    docs_dir = out_root / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    interactive = write_national_interactive_maps(
        plot, cfg, lattice, su_metrics, imap_dir
    )
    # Also place copies/links usable from atlas: write atlas index with relative refs
    atlas_index = write_national_html_atlas(interactive, atlas_dir)
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
    )
    manifest = {
        "interactive_maps": interactive,
        "atlas_index": str(atlas_index),
        "html_report": str(report),
    }
    (docs_dir / "national_html_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest
