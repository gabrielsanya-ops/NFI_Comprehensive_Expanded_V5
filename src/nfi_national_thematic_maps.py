# -*- coding: utf-8 -*-
"""National thematic map production (interactive Leaflet + static PNG).

Builds SU-level theme attributes from national cleansed tables and provisional
biomass products, then writes one HTML map per theme into
maps/html_interactive/ and matching PNGs into maps/national/thematic/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from nfi_area_maps import _add_free_basemaps
from nfi_audit import plot_coordinate_qa
from nfi_national_html import _banner, _center_from_xy, _esc


# theme_id, title, value_col, kind ('continuous'|'categorical'|'binary'), category, blurb, cmap/palette
NATIONAL_THEMES: list[tuple] = [
    ("plots", "National plots", None, "special_plots", "Frame", "Validated plot coordinates (clustered)."),
    ("tree_presence", "Tree presence (SU)", "has_tree_record", "binary", "Gates", "SU with any tree record vs zero-tree."),
    ("shrub_presence", "Shrub presence (SU)", "has_shrub_record", "binary", "Gates", "SU with any shrub record vs zero-shrub."),
    ("tree_count", "Tree count (SU)", "n_trees", "continuous", "Structure", "Number of tree records per SU."),
    ("species_richness", "Tree species richness (SU)", "n_tree_species", "continuous", "Biodiversity", "Unique scientific names per SU."),
    ("mean_dbh", "Mean DBH (cm)", "mean_dbh_cm", "continuous", "Structure", "Mean tree DBH (cm) per SU."),
    ("mean_height", "Mean tree height (m)", "mean_height_m", "continuous", "Structure", "Mean tree height (m) per SU."),
    ("sum_basal", "Basal area sum (m2)", "sum_basal_m2", "continuous", "Structure", "Summed basal area of eligible trees."),
    ("sum_volume", "Volume sum (m3, provisional)", "sum_volume_m3", "continuous", "Structure", "Provisional tree volume sum."),
    ("sum_agb", "Tree AGB sum (Mg, provisional)", "sum_tree_agb_mg", "continuous", "Biomass and carbon", "Provisional above-ground biomass."),
    ("sum_bgb", "Tree BGB sum (Mg, provisional)", "sum_tree_bgb_mg", "continuous", "Biomass and carbon", "Provisional below-ground biomass."),
    ("sum_carbon", "Tree carbon sum (Mg, provisional)", "sum_tree_carbon_mg", "continuous", "Biomass and carbon", "Provisional tree carbon."),
    ("sum_co2eq", "Tree CO2eq sum (Mg, provisional)", "sum_tree_co2eq_mg", "continuous", "Biomass and carbon", "Provisional tree CO2 equivalent."),
    ("shrub_count", "Shrub count (SU)", "n_shrubs", "continuous", "Shrubs", "Number of shrub records per SU."),
    ("sum_shrub_agb", "Shrub AGB sum (Mg, provisional)", "sum_shrub_agb_mg", "continuous", "Shrubs", "Provisional shrub AGB."),
    ("sum_shrub_carbon", "Shrub carbon sum (Mg, provisional)", "sum_shrub_carbon_mg", "continuous", "Shrubs", "Provisional shrub carbon."),
    ("land_use", "Modal natural land use (SU)", "nat_lucs_mode", "categorical", "Land use", "Most frequent nat_lucs_label among plots."),
    ("tree_canopy", "Modal tree canopy class (SU)", "tree_canopy_mode", "categorical", "Vegetation cover", "Modal tree_canopy_label."),
    ("herbaceous", "Modal herbaceous class (SU)", "herbaceous_mode", "categorical", "Vegetation cover", "Modal herbaceous_label."),
    ("fire_presence", "Fire evidence present (SU)", "has_fire", "binary", "Disturbance", "Any fire_evidence record on the SU."),
    ("fire_type", "Modal fire type (SU)", "fire_type_mode", "categorical", "Disturbance", "Modal fir_type_label where recorded."),
    ("env_problem", "Environmental problem present (SU)", "has_env_problem", "binary", "Disturbance", "Any environmental_problems record."),
    ("env_category", "Modal env. problem category (SU)", "env_category_mode", "categorical", "Disturbance", "Modal categories_label."),
    ("deadwood_presence", "Deadwood present (SU)", "has_deadwood", "binary", "Deadwood and regen", "Any deadwood record."),
    ("regen_count", "Regeneration count (SU)", "regen_count_sum", "continuous", "Deadwood and regen", "Sum of regeneration count field."),
    ("tree_condition", "Modal overall tree condition (SU)", "tree_condition_mode", "categorical", "Tree health", "Modal overall_tree_condition_label."),
    ("crown_condition", "Modal crown condition (SU)", "crown_condition_mode", "categorical", "Tree health", "Modal crown_condition_label."),
    ("stump_share", "Stump share of tree records", "stump_share", "continuous", "Structure", "Share of records labelled as stump (deforestation proxy)."),
    ("region", "Region (SU master)", "region", "categorical", "Frame", "Administrative region from SU master."),
    ("coord_confidence", "Modal plot coord confidence (SU)", "coord_confidence_mode", "categorical", "Coordinate QA", "Modal validated coordinate confidence."),
]


CAT_PALETTE = [
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9",
    "#F0E442", "#000000", "#999999", "#882255", "#44AA99", "#117733",
    "#332288", "#AA4499", "#DDCC77", "#88CCEE",
]


def _mode_or_na(s: pd.Series):
    s = s.dropna().astype(str)
    s = s[~s.str.lower().isin(["nan", "none", "<na>", ""])]
    if len(s) == 0:
        return pd.NA
    return s.value_counts().index[0]


def _su_xy(plot: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    qa = plot_coordinate_qa(plot, cfg)
    pts = qa.loc[qa["lon_validated"].notna() & qa["lat_validated"].notna()].copy()
    conf = (
        pts.groupby("SU_UID", dropna=False)["coord_confidence"]
        .agg(_mode_or_na)
        .rename("coord_confidence_mode")
        .reset_index()
    )
    xy = (
        pts.groupby("SU_UID", as_index=False)[["lon_validated", "lat_validated"]]
        .first()
    )
    return xy.merge(conf, on="SU_UID", how="left")


def build_national_su_thematic_table(
    tables: dict[str, pd.DataFrame],
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    lattice: pd.DataFrame,
    plot: pd.DataFrame,
    cfg: dict,
) -> pd.DataFrame:
    """One row per SU with coordinates and thematic attributes (computed only)."""
    su = tables["su"].copy()
    region_col = cfg["columns"]["region_en"]
    base = su[["SU_UID"]].drop_duplicates().copy()
    if region_col in su.columns:
        base["region"] = su.groupby("SU_UID")[region_col].agg(_mode_or_na).reindex(base["SU_UID"]).values

    xy = _su_xy(plot, cfg)
    out = base.merge(xy, on="SU_UID", how="left")

    # Tree / shrub presence from lattice + shrub table
    if "has_tree_record" in lattice.columns:
        out = out.merge(
            lattice.groupby("SU_UID", as_index=False)["has_tree_record"].any(),
            on="SU_UID",
            how="left",
        )
    shrubs = tables.get("shrubs")
    if shrubs is not None and len(shrubs):
        sh_flag = shrubs.groupby("SU_UID").size().gt(0).rename("has_shrub_record").reset_index()
        out = out.merge(sh_flag, on="SU_UID", how="left")
    out["has_shrub_record"] = out.get("has_shrub_record", False).fillna(False)
    out["has_tree_record"] = out.get("has_tree_record", False).fillna(False)

    trees = tables.get("trees")
    if trees is not None and len(trees):
        g = trees.groupby("SU_UID", dropna=False)
        out = out.merge(g.size().rename("n_trees").reset_index(), on="SU_UID", how="left")
        if "tree_species_scientific_name" in trees.columns:
            out = out.merge(
                g["tree_species_scientific_name"].nunique().rename("n_tree_species").reset_index(),
                on="SU_UID",
                how="left",
            )
        dbh = cfg["columns"]["dbh"]
        ht = cfg["columns"]["height"]
        if dbh in trees.columns:
            out = out.merge(g[dbh].mean().rename("mean_dbh_cm").reset_index(), on="SU_UID", how="left")
        if ht in trees.columns:
            out = out.merge(g[ht].mean().rename("mean_height_m").reset_index(), on="SU_UID", how="left")
        if "overall_tree_condition_label" in trees.columns:
            out = out.merge(
                g["overall_tree_condition_label"].agg(_mode_or_na).rename("tree_condition_mode").reset_index(),
                on="SU_UID",
                how="left",
            )
        if "crown_condition_label" in trees.columns:
            out = out.merge(
                g["crown_condition_label"].agg(_mode_or_na).rename("crown_condition_mode").reset_index(),
                on="SU_UID",
                how="left",
            )
        if "tree_or_stump_label" in trees.columns:
            stump = trees.assign(
                _stump=trees["tree_or_stump_label"].astype(str).str.lower().str.contains("stump", na=False)
            )
            share = stump.groupby("SU_UID")["_stump"].mean().rename("stump_share").reset_index()
            out = out.merge(share, on="SU_UID", how="left")

    if tree_m is not None and len(tree_m):
        tg = tree_m.groupby("SU_UID", dropna=False)
        for src, dst in [
            ("basal_area_m2", "sum_basal_m2"),
            ("volume_m3", "sum_volume_m3"),
            ("agb_mg", "sum_tree_agb_mg"),
            ("bgb_mg", "sum_tree_bgb_mg"),
            ("carbon_mg_provisional", "sum_tree_carbon_mg"),
            ("co2eq_mg_provisional", "sum_tree_co2eq_mg"),
        ]:
            if src in tree_m.columns:
                out = out.merge(tg[src].sum().rename(dst).reset_index(), on="SU_UID", how="left")

    if shrub_m is not None and len(shrub_m):
        sg = shrub_m.groupby("SU_UID", dropna=False)
        out = out.merge(sg.size().rename("n_shrubs").reset_index(), on="SU_UID", how="left")
        for src, dst in [
            ("agb_mg", "sum_shrub_agb_mg"),
            ("carbon_mg_provisional", "sum_shrub_carbon_mg"),
        ]:
            if src in shrub_m.columns:
                out = out.merge(sg[src].sum().rename(dst).reset_index(), on="SU_UID", how="left")

    # Land use
    lucs = tables.get("lucs")
    if lucs is not None and "nat_lucs_label" in lucs.columns:
        out = out.merge(
            lucs.groupby("SU_UID")["nat_lucs_label"].agg(_mode_or_na).rename("nat_lucs_mode").reset_index(),
            on="SU_UID",
            how="left",
        )

    veg = tables.get("vegetation_cover")
    if veg is not None:
        if "tree_canopy_label" in veg.columns:
            out = out.merge(
                veg.groupby("SU_UID")["tree_canopy_label"].agg(_mode_or_na).rename("tree_canopy_mode").reset_index(),
                on="SU_UID",
                how="left",
            )
        if "herbaceous_label" in veg.columns:
            out = out.merge(
                veg.groupby("SU_UID")["herbaceous_label"].agg(_mode_or_na).rename("herbaceous_mode").reset_index(),
                on="SU_UID",
                how="left",
            )

    fire = tables.get("fire")
    if fire is not None and len(fire):
        out = out.merge(fire.groupby("SU_UID").size().gt(0).rename("has_fire").reset_index(), on="SU_UID", how="left")
        if "fir_type_label" in fire.columns:
            out = out.merge(
                fire.groupby("SU_UID")["fir_type_label"].agg(_mode_or_na).rename("fire_type_mode").reset_index(),
                on="SU_UID",
                how="left",
            )
    out["has_fire"] = out.get("has_fire", False).fillna(False)

    env = tables.get("environmental_problems")
    if env is not None and len(env):
        out = out.merge(env.groupby("SU_UID").size().gt(0).rename("has_env_problem").reset_index(), on="SU_UID", how="left")
        if "categories_label" in env.columns:
            out = out.merge(
                env.groupby("SU_UID")["categories_label"].agg(_mode_or_na).rename("env_category_mode").reset_index(),
                on="SU_UID",
                how="left",
            )
    out["has_env_problem"] = out.get("has_env_problem", False).fillna(False)

    dead = tables.get("deadwood")
    if dead is not None and len(dead):
        out = out.merge(dead.groupby("SU_UID").size().gt(0).rename("has_deadwood").reset_index(), on="SU_UID", how="left")
    out["has_deadwood"] = out.get("has_deadwood", False).fillna(False)

    regen = tables.get("regeneration")
    if regen is not None and len(regen):
        if "count" in regen.columns:
            out = out.merge(
                pd.to_numeric(regen["count"], errors="coerce").groupby(regen["SU_UID"]).sum().rename("regen_count_sum").reset_index(),
                on="SU_UID",
                how="left",
            )
        else:
            out = out.merge(regen.groupby("SU_UID").size().rename("regen_count_sum").reset_index(), on="SU_UID", how="left")

    return out


def _continuous_color(t: float) -> str:
    # YlGnBu-like
    if t > 0.75:
        return "#081d58"
    if t > 0.5:
        return "#225ea8"
    if t > 0.25:
        return "#41b6c4"
    return "#c7e9b4"


def _write_su_theme_map(
    df: pd.DataFrame,
    *,
    theme_id: str,
    title: str,
    value_col: str | None,
    kind: str,
    blurb: str,
    out_html: Path,
    center: list[float],
) -> Path | None:
    import folium
    from folium.plugins import Fullscreen, MousePosition

    use = df.loc[df["lon_validated"].notna() & df["lat_validated"].notna()].copy()
    if value_col and value_col not in use.columns:
        return None
    if value_col and kind != "binary" and use[value_col].notna().sum() == 0:
        return None

    m = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
    _add_free_basemaps(m)
    Fullscreen().add_to(m)
    MousePosition().add_to(m)
    fg = folium.FeatureGroup(name=title, show=True)

    if kind == "binary":
        g_yes = folium.FeatureGroup(name="Yes / present", show=True)
        g_no = folium.FeatureGroup(name="No / absent", show=True)
        for _, row in use.iterrows():
            flag = bool(row.get(value_col)) if pd.notna(row.get(value_col)) else False
            color = "#009E73" if flag else "#D55E00"
            target = g_yes if flag else g_no
            folium.CircleMarker(
                [float(row["lat_validated"]), float(row["lon_validated"])],
                radius=4,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=folium.Popup(
                    f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                    f"<b>{_esc(value_col)}:</b> {flag}<br>"
                    f"<b>region:</b> {_esc(row.get('region'))}",
                    max_width=280,
                ),
            ).add_to(target)
        g_yes.add_to(m)
        g_no.add_to(m)
    elif kind == "continuous":
        vals = pd.to_numeric(use[value_col], errors="coerce")
        vmax = float(vals.quantile(0.95)) if vals.notna().any() else 1.0
        vmax = vmax if vmax > 0 else 1.0
        for _, row in use.iterrows():
            v = row.get(value_col)
            if pd.isna(v):
                continue
            t = min(float(v) / vmax, 1.0)
            folium.CircleMarker(
                [float(row["lat_validated"]), float(row["lon_validated"])],
                radius=3 + 7 * t,
                color=_continuous_color(t),
                fill=True,
                fill_opacity=0.75,
                popup=folium.Popup(
                    f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                    f"<b>{_esc(value_col)}:</b> {float(v):.4g}<br>"
                    f"<b>region:</b> {_esc(row.get('region'))}",
                    max_width=300,
                ),
            ).add_to(fg)
        fg.add_to(m)
    elif kind == "categorical":
        levels = [x for x in use[value_col].dropna().astype(str).value_counts().index.tolist()]
        cmap = {lev: CAT_PALETTE[i % len(CAT_PALETTE)] for i, lev in enumerate(levels[:24])}
        groups = {lev: folium.FeatureGroup(name=str(lev)[:40], show=True) for lev in levels[:24]}
        other = folium.FeatureGroup(name="Other / rare", show=False)
        for _, row in use.iterrows():
            lev = row.get(value_col)
            if pd.isna(lev):
                continue
            lev = str(lev)
            color = cmap.get(lev, "#999999")
            target = groups.get(lev, other)
            folium.CircleMarker(
                [float(row["lat_validated"]), float(row["lon_validated"])],
                radius=4,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=folium.Popup(
                    f"<b>SU_UID:</b> {_esc(row.get('SU_UID'))}<br>"
                    f"<b>{_esc(value_col)}:</b> {_esc(lev)}<br>"
                    f"<b>region:</b> {_esc(row.get('region'))}",
                    max_width=300,
                ),
            ).add_to(target)
        for g in groups.values():
            g.add_to(m)
        other.add_to(m)
    else:
        return None

    folium.LayerControl(collapsed=False).add_to(m)
    _banner(m, title, blurb + " | provisional sample metrics where biomass-related")
    out_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_html))
    return out_html


def _write_static_theme_png(
    df: pd.DataFrame,
    *,
    theme_id: str,
    title: str,
    value_col: str | None,
    kind: str,
    out_png: Path,
) -> Path | None:
    use = df.loc[df["lon_validated"].notna() & df["lat_validated"].notna()].copy()
    if value_col and value_col not in use.columns:
        return None
    fig, ax = plt.subplots(figsize=(9, 8), dpi=120)
    if kind == "binary":
        yes = use[value_col].fillna(False).astype(bool)
        ax.scatter(use.loc[~yes, "lon_validated"], use.loc[~yes, "lat_validated"], s=6, c="#D55E00", alpha=0.5, label="No")
        ax.scatter(use.loc[yes, "lon_validated"], use.loc[yes, "lat_validated"], s=6, c="#009E73", alpha=0.5, label="Yes")
        ax.legend(markerscale=2)
    elif kind == "continuous":
        vals = pd.to_numeric(use[value_col], errors="coerce")
        sc = ax.scatter(use["lon_validated"], use["lat_validated"], c=vals, s=8, cmap="YlGnBu", alpha=0.55)
        plt.colorbar(sc, ax=ax, label=value_col)
    elif kind == "categorical":
        cats = use[value_col].astype(str)
        codes, uniques = pd.factorize(cats)
        sc = ax.scatter(use["lon_validated"], use["lat_validated"], c=codes, s=8, cmap="tab20", alpha=0.55)
        # compact legend for top classes only
        top = cats.value_counts().head(8).index.tolist()
        handles = []
        for i, lab in enumerate(top):
            handles.append(plt.Line2D([0], [0], marker="o", color="w", label=lab[:28],
                                      markerfacecolor=plt.cm.tab20(i / max(len(top), 1)), markersize=6))
        if handles:
            ax.legend(handles=handles, fontsize=7, loc="best")
    else:
        plt.close(fig)
        return None
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160)
    plt.close(fig)
    return out_png


def write_national_plots_cluster_map(plot: pd.DataFrame, cfg: dict, out_html: Path, max_plot_markers: int = 8000) -> Path:
    import folium
    from folium.plugins import Fullscreen, MarkerCluster, MousePosition

    qa = plot_coordinate_qa(plot, cfg)
    center = _center_from_xy(qa["lon_validated"], qa["lat_validated"])
    m = folium.Map(location=center, zoom_start=6, tiles=None, control_scale=True)
    _add_free_basemaps(m)
    Fullscreen().add_to(m)
    MousePosition().add_to(m)
    cluster = MarkerCluster(name="NFI plots (clustered)", show=True)
    pts = qa.loc[qa["lon_validated"].notna() & qa["lat_validated"].notna()].copy()
    if len(pts) > max_plot_markers:
        pts = pts.sample(n=max_plot_markers, random_state=int(cfg.get("project", {}).get("random_seed", 42)))
    for _, row in pts.iterrows():
        folium.CircleMarker(
            [float(row["lat_validated"]), float(row["lon_validated"])],
            radius=3,
            color="#0072B2",
            fill=True,
            fill_opacity=0.7,
            popup=folium.Popup(
                f"<b>PLOT_UID:</b> {_esc(row.get('PLOT_UID'))}<br><b>SU_UID:</b> {_esc(row.get('SU_UID'))}",
                max_width=260,
            ),
        ).add_to(cluster)
    cluster.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    _banner(m, "National NFI plots", f"Validated coordinates n={len(pts):,}")
    out_html.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_html))
    return out_html


def produce_national_thematic_maps(
    *,
    tables: dict[str, pd.DataFrame],
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    lattice: pd.DataFrame,
    plot: pd.DataFrame,
    cfg: dict,
    out_root: Path,
) -> dict[str, Any]:
    """Write thematic interactive HTML maps, static PNGs, SU theme table, and theme catalog."""
    out_root = Path(out_root)
    html_dir = out_root / "maps" / "html_interactive"
    png_dir = out_root / "maps" / "national" / "thematic"
    html_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    themes_df = build_national_su_thematic_table(tables, tree_m, shrub_m, lattice, plot, cfg)
    themes_df.to_csv(out_root / "validated" / "national_su_thematic_attributes.csv", index=False)

    center = _center_from_xy(themes_df["lon_validated"], themes_df["lat_validated"])
    interactive: dict[str, str] = {}
    static: dict[str, str] = {}
    catalog_rows = []

    # Always: clustered plots
    p_plots = write_national_plots_cluster_map(plot, cfg, html_dir / "interactive_national_plots.html")
    interactive["plots"] = str(p_plots)

    for theme_id, title, value_col, kind, category, blurb in NATIONAL_THEMES:
        catalog_rows.append({
            "theme_id": theme_id,
            "title": title,
            "value_col": value_col,
            "kind": kind,
            "category": category,
            "blurb": blurb,
        })
        if kind == "special_plots":
            continue
        html_path = html_dir / f"interactive_national_{theme_id}.html"
        png_path = png_dir / f"thematic_{theme_id}.png"
        wrote = _write_su_theme_map(
            themes_df,
            theme_id=theme_id,
            title=title,
            value_col=value_col,
            kind=kind,
            blurb=blurb,
            out_html=html_path,
            center=center,
        )
        if wrote:
            interactive[theme_id] = str(wrote)
        wrote_png = _write_static_theme_png(
            themes_df,
            theme_id=theme_id,
            title=title,
            value_col=value_col,
            kind=kind,
            out_png=png_path,
        )
        if wrote_png:
            static[theme_id] = str(wrote_png)

    catalog = pd.DataFrame(catalog_rows)
    catalog["html_written"] = catalog["theme_id"].map(lambda t: t in interactive)
    catalog["png_written"] = catalog["theme_id"].map(lambda t: t in static)
    catalog.to_csv(out_root / "maps" / "national_thematic_catalog.csv", index=False)

    return {
        "su_thematic": themes_df,
        "interactive": interactive,
        "static": static,
        "catalog": catalog,
    }
