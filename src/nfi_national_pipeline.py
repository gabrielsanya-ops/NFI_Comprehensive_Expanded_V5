# -*- coding: utf-8 -*-
"""National-first NFI geopipeline helpers (entire KSA tabular universe).

LEFT master is the national SU table (not an Asir clip). GIS Area_H is attached
only where regional shapefiles exist (Asir, Makkah). Design-based expansion by
Area_H stays blocked for SUs without a verified area attribute.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from nfi_audit import (
    StageStore,
    attach_keys,
    ensure_output_dirs,
    expected_plot_universe,
    make_su_uid,
    plot_coordinate_qa,
    read_first_sheet,
)
from nfi_calc_biomass import (
    CONVERSION_FACTOR_HA,
    SHRUB_EXCLUDE,
    TREE_EXCLUDE,
    apply_shrub_metrics,
    apply_tree_metrics,
    exclude_by_substrings,
    land_use_proportion_by_su,
)
from nfi_datascience import (
    apply_plot_style,
    bivariate_numeric,
    missingness_report,
    plot_corr_pair,
    plot_univariate_grid,
    univariate_numeric,
)


def load_national_tables(cfg: dict) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for name, path in cfg["tables"].items():
        df = read_first_sheet(path)
        if name == "su":
            tables[name] = attach_keys(df, cfg, kind="su")
        elif name == "plot":
            tables[name] = attach_keys(df, cfg, kind="plot")
        elif name == "fauna":
            tables[name] = attach_keys(df, cfg, kind="fauna")
        elif name == "teams":
            t = df.copy()
            t["SU_UID"] = make_su_uid(t[cfg["columns"]["su_id_in_child_tables"]])
            tables[name] = t
        else:
            tables[name] = attach_keys(df, cfg, kind="child")
    return tables


def national_universe_summary(su: pd.DataFrame, plot: pd.DataFrame, cfg: dict) -> dict[str, Any]:
    region_col = cfg["columns"]["region_en"]
    plots_per = plot.groupby("SU_UID").size()
    by_region = (
        su.groupby(region_col, dropna=False)
        .size()
        .rename("n_su")
        .reset_index()
        .rename(columns={region_col: "region"})
        .sort_values("n_su", ascending=False)
    )
    return {
        "n_su": int(len(su)),
        "n_su_unique": int(su["SU_UID"].nunique()),
        "n_plot_rows": int(len(plot)),
        "n_plot_uid": int(plot["PLOT_UID"].nunique()),
        "plots_per_su_min": int(plots_per.min()) if len(plots_per) else None,
        "plots_per_su_max": int(plots_per.max()) if len(plots_per) else None,
        "plots_per_su_all_equal_5": bool(len(plots_per) and (plots_per == 5).all()),
        "n_regions": int(by_region["region"].nunique()),
        "by_region": by_region,
    }


def build_national_plot_lattice(
    su: pd.DataFrame,
    trees: pd.DataFrame,
    cfg: dict,
) -> pd.DataFrame:
    """Anti-clip SU x plot lattice for the full national SU master."""
    plots_per_su = int(cfg["project"]["plots_per_su_design"])
    sep = cfg["project"]["plot_uid_separator"]
    universe = set(su["SU_UID"].astype(str))
    base = expected_plot_universe(universe, plots_per_su, sep)
    region_col = cfg["columns"]["region_en"]
    gov_col = cfg["columns"]["governorate_en"]
    if region_col in su.columns:
        base["region"] = base["SU_UID"].map(dict(zip(su["SU_UID"].astype(str), su[region_col])))
    if gov_col in su.columns:
        base["governorate"] = base["SU_UID"].map(dict(zip(su["SU_UID"].astype(str), su[gov_col])))
    tc = trees.groupby("PLOT_UID", dropna=False).size().rename("n_tree_records").reset_index()
    tc["PLOT_UID"] = tc["PLOT_UID"].astype(str)
    out = base.merge(tc, on="PLOT_UID", how="left")
    out["n_tree_records"] = out["n_tree_records"].fillna(0).astype(int)
    out["has_tree_record"] = out["n_tree_records"] > 0
    return out


def national_gate_tree_presence(su: pd.DataFrame, trees: pd.DataFrame) -> dict[str, Any]:
    universe = set(su["SU_UID"].astype(str))
    with_trees = set(trees.loc[trees["SU_UID"].astype(str).isin(universe), "SU_UID"].astype(str))
    zero = sorted(universe - with_trees)
    return {
        "total_sus": len(universe),
        "sus_with_trees": len(with_trees),
        "sus_no_trees": len(zero),
        "zero_tree_su_uids": zero,
    }


def attach_regional_gis_area(su: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Left-join Area_H from available regional grids; never drop non-GIS SUs."""
    out = su.copy()
    out["SU_UID"] = out["SU_UID"].astype(str)
    frames = []
    for label, grid_key, id_key in [
        ("Asir", "asir_grid", "asir_grid_key"),
        ("Makkah", "makkah_grid", "asir_grid_key"),
    ]:
        path = cfg["gis"].get(grid_key)
        if not path or not Path(path).exists():
            continue
        g = gpd.read_file(path)
        key = cfg["gis"].get(id_key, "SU")
        if key not in g.columns and "SU" in g.columns:
            key = "SU"
        g = g.copy()
        g["SU_UID"] = make_su_uid(g[key])
        if "Area_H" not in g.columns:
            continue
        piece = g[["SU_UID", "Area_H"]].drop_duplicates("SU_UID")
        piece["gis_region_source"] = label
        frames.append(piece)
    if not frames:
        out["Area_H_attr"] = np.nan
        out["gis_region_source"] = pd.NA
        out["area_status"] = "NO_REGIONAL_GRID"
        return out
    area = pd.concat(frames, ignore_index=True).drop_duplicates("SU_UID", keep="first")
    out = out.merge(area, on="SU_UID", how="left")
    out = out.rename(columns={"Area_H": "Area_H_attr"})
    out["area_status"] = np.where(out["Area_H_attr"].notna(), "GIS_AREA_ATTACHED", "AREA_BLOCKED_NO_GRID")
    return out


def national_tree_biomass(trees: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    sp = "tree_species_scientific_name"
    dbh_col = cfg["columns"]["dbh"]
    ht_col = cfg["columns"]["height"]
    t = trees.copy()
    keep = exclude_by_substrings(t[sp], TREE_EXCLUDE) if sp in t.columns else pd.Series(True, index=t.index)
    keep &= t[dbh_col].notna() & t[ht_col].notna()
    out = apply_tree_metrics(t.loc[keep].copy(), dbh_col, ht_col)
    out["biomass_scope"] = "national_tree_provisional"
    out["design_based"] = False
    return out


def national_shrub_biomass(shrubs: pd.DataFrame) -> pd.DataFrame:
    sp = "tree_species_scientific_name"
    s = shrubs.copy()
    keep = exclude_by_substrings(s[sp], SHRUB_EXCLUDE) if sp in s.columns else pd.Series(True, index=s.index)
    out = apply_shrub_metrics(s.loc[keep].copy())
    out["biomass_scope"] = "national_shrub_provisional"
    out["design_based"] = False
    out["shrub_log_base_assumption"] = "natural_log"
    out["shrub_height_unit_assumption"] = "meters_converted_to_cm"
    return out


def aggregate_plot_su_metrics(
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    lattice: pd.DataFrame,
    conversion_factor: float = CONVERSION_FACTOR_HA,
) -> dict[str, pd.DataFrame]:
    """Sample (not design-based) plot and SU roll-ups using CF=10 for density-like totals."""
    plot = lattice[["SU_UID", "PLOT_UID", "region", "governorate"]].copy() if "region" in lattice.columns else lattice[["SU_UID", "PLOT_UID"]].copy()

    def _sum_to_plot(df: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
        if df is None or len(df) == 0:
            return pd.DataFrame({"PLOT_UID": pd.Series(dtype=str)})
        use = [c for c in cols if c in df.columns]
        g = df.groupby("PLOT_UID", dropna=False)[use].sum(min_count=1).reset_index()
        rename = {c: f"{prefix}_{c}" for c in use}
        return g.rename(columns=rename)

    tree_cols = ["agb_mg", "bgb_mg", "total_biomass_mg", "carbon_mg_provisional", "co2eq_mg_provisional"]
    shrub_cols = ["agb_mg", "bgb_mg", "total_biomass_mg", "carbon_mg_provisional"]
    tp = _sum_to_plot(tree_m, tree_cols, "tree")
    sp = _sum_to_plot(shrub_m, shrub_cols, "shrub")
    plot = plot.merge(tp, on="PLOT_UID", how="left").merge(sp, on="PLOT_UID", how="left")
    metric_cols = [c for c in plot.columns if c.startswith("tree_") or c.startswith("shrub_")]
    for c in metric_cols:
        plot[c] = plot[c].fillna(0.0)
        # Document CF multiplies count-like per-plot totals toward per-ha (provisional sample metric).
        plot[c + "_per_ha_sample"] = plot[c] * float(conversion_factor)

    su = (
        plot.groupby("SU_UID", dropna=False)[metric_cols]
        .mean()
        .reset_index()
        .rename(columns={c: c + "_mean_of_5_plots" for c in metric_cols})
    )
    if "region" in plot.columns:
        reg = plot.groupby("SU_UID", dropna=False)["region"].agg(lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA)
        su["region"] = su["SU_UID"].map(reg)
    return {"plot_metrics": plot, "su_metrics": su}


def write_national_eda_figures(
    trees: pd.DataFrame,
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    out_dir: Path,
    cfg: dict,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    apply_plot_style()
    paths: dict[str, Path] = {}
    dbh = cfg["columns"]["dbh"]
    ht = cfg["columns"]["height"]
    raw_cols = [c for c in [dbh, ht] if c in trees.columns]
    if raw_cols:
        paths["univariate_trees_national"] = plot_univariate_grid(
            trees, raw_cols, out_dir / "univariate_trees_national.png", "National trees: univariate (raw field)"
        )
    eng_cols = [c for c in ["basal_area_m2", "volume_m3", "agb_mg", "carbon_mg_provisional"] if c in tree_m.columns]
    if eng_cols:
        paths["univariate_trees_fv_national"] = plot_univariate_grid(
            tree_m, eng_cols, out_dir / "univariate_trees_fv_national.png", "National trees: provisional FV metrics"
        )
        if len(eng_cols) >= 2:
            paths["bivariate_corr_trees_national"] = plot_corr_pair(
                tree_m,
                eng_cols,
                out_dir / "bivariate_corr_pair_trees_national.png",
                title="National trees: Spearman vs Pearson (provisional FV)",
            )
            bivariate_numeric(tree_m, eng_cols, method="spearman").to_csv(
                out_dir / "bivariate_spearman_trees_national.csv"
            )
            bivariate_numeric(tree_m, eng_cols, method="pearson").to_csv(
                out_dir / "bivariate_pearson_trees_national.csv"
            )
    shrub_cols = [c for c in ["mean_CD_m", "height_cm", "agb_mg", "carbon_mg_provisional"] if c in shrub_m.columns]
    if shrub_cols:
        paths["univariate_shrubs_national"] = plot_univariate_grid(
            shrub_m, shrub_cols, out_dir / "univariate_shrubs_national.png", "National shrubs: provisional metrics"
        )
    return paths


def write_national_maps(plot: pd.DataFrame, cfg: dict, out_dir: Path, su_metrics: pd.DataFrame | None = None) -> dict[str, Path]:
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    qa = plot_coordinate_qa(plot, cfg)
    fig, ax = plt.subplots(figsize=(9, 8), dpi=130)
    m = qa["lon_validated"].notna() & qa["lat_validated"].notna()
    ax.scatter(qa.loc[m, "lon_validated"], qa.loc[m, "lat_validated"], s=3, alpha=0.35, c="#0072B2")
    ax.set_title(f"National NFI plots with validated coordinates (n={int(m.sum()):,})")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    p1 = out_dir / "map_national_plots.png"
    fig.savefig(p1, dpi=200)
    plt.close(fig)
    paths["map_national_plots"] = p1

    if su_metrics is not None and "tree_carbon_mg_provisional_mean_of_5_plots" in su_metrics.columns:
        pts = qa.merge(su_metrics, on="SU_UID", how="left")
        fig, ax = plt.subplots(figsize=(9, 8), dpi=130)
        mm = pts["lon_validated"].notna() & pts["tree_carbon_mg_provisional_mean_of_5_plots"].notna()
        sc = ax.scatter(
            pts.loc[mm, "lon_validated"],
            pts.loc[mm, "lat_validated"],
            c=pts.loc[mm, "tree_carbon_mg_provisional_mean_of_5_plots"],
            s=6,
            cmap="YlGn",
            alpha=0.5,
        )
        plt.colorbar(sc, ax=ax, label="SU mean tree carbon (Mg, provisional sample)")
        ax.set_title("National SU mean provisional tree carbon (sample; not design-based)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        p2 = out_dir / "map_national_su_mean_tree_carbon.png"
        fig.savefig(p2, dpi=200)
        plt.close(fig)
        paths["map_national_su_mean_tree_carbon"] = p2
    return paths


def national_ancillary_inventory(tables: dict[str, pd.DataFrame], out_dir: Path) -> pd.DataFrame:
    """Counts for pools without Word-doc biomass formulas (deadwood, litter, regen, veg, LUCS).

    Biomass/carbon for these pools stay blocked: the calculation DOCX only
    specifies tree and shrub chains (see data/docs/_calc_doc_extract.md).
    """
    rows = []
    specs = [
        ("deadwood", "deadwood"),
        ("litter", "litter"),
        ("regeneration", "regeneration"),
        ("vegetation_cover", "vegetation_cover"),
        ("lucs", "lucs"),
        ("fire", "fire"),
        ("environmental_problems", "environmental_problems"),
        ("fauna", "fauna"),
    ]
    for label, key in specs:
        if key not in tables:
            rows.append({"pool": label, "status": "TABLE_MISSING", "n_rows": 0, "n_su": 0, "n_plot_uid": 0})
            continue
        df = tables[key]
        n_su = int(df["SU_UID"].nunique()) if "SU_UID" in df.columns else 0
        n_plot = int(df["PLOT_UID"].nunique()) if "PLOT_UID" in df.columns else 0
        rows.append({
            "pool": label,
            "status": "INVENTORIED_NO_BIOMASS_FORMULA",
            "n_rows": int(len(df)),
            "n_su": n_su,
            "n_plot_uid": n_plot,
            "biomass_status": "BLOCKED_NO_CALC_DOC_EQUATION",
        })
    inv = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    inv.to_csv(out_dir / "national_ancillary_pools.csv", index=False)
    return inv


def national_land_use_proportions(lucs: pd.DataFrame, cfg: dict, out_dir: Path) -> pd.DataFrame:
    """Plot-level LU proportion by SU using calc-doc CF design (5 plots per SU)."""
    class_col = None
    for cand in ("nat_lucs_label", "int_lucs_label", "nat_lucs", "int_lucs"):
        if cand in lucs.columns:
            class_col = cand
            break
    if class_col is None:
        return pd.DataFrame()
    props = land_use_proportion_by_su(
        lucs, "SU_UID", class_col, plots_per_su=int(cfg["project"]["plots_per_su_design"])
    )
    props.to_csv(out_dir / "national_land_use_proportions.csv", index=False)
    return props


def national_shrub_gate(su: pd.DataFrame, shrubs: pd.DataFrame) -> dict[str, Any]:
    universe = set(su["SU_UID"].astype(str))
    with_sh = set(shrubs.loc[shrubs["SU_UID"].astype(str).isin(universe), "SU_UID"].astype(str))
    zero = sorted(universe - with_sh)
    return {
        "total_sus": len(universe),
        "sus_with_shrubs": len(with_sh),
        "sus_no_shrubs": len(zero),
        "zero_shrub_su_uids": zero,
    }


def run_national_pipeline(cfg: dict, out_root: Path | None = None) -> dict[str, Any]:
    """Execute national ingest through biomass, EDA figures, and maps."""
    if out_root is None:
        parent = Path(cfg["paths"]["output_root"])
        out_root = parent.parent / "outputs_national_v5" if parent.name == "outputs" else parent / "outputs_national_v5"
    out_cfg = {**cfg, "paths": {**cfg["paths"], "output_root": str(out_root)}}
    OUT = ensure_output_dirs(out_cfg)
    stages = StageStore(OUT)

    tables = load_national_tables(cfg)
    su, plot, trees, shrubs = tables["su"], tables["plot"], tables["trees"], tables["shrubs"]
    summary = national_universe_summary(su, plot, cfg)
    summary["by_region"].to_csv(OUT / "audit" / "national_su_by_region.csv", index=False)

    lattice = build_national_plot_lattice(su, trees, cfg)
    expected_n = summary["n_su"] * int(cfg["project"]["plots_per_su_design"])
    if len(lattice) != expected_n:
        raise AssertionError(f"National lattice rows {len(lattice)} != expected {expected_n}")
    lattice.to_csv(OUT / "validated" / "national_plot_lattice.csv", index=False)

    gate = national_gate_tree_presence(su, trees)
    gate_sh = national_shrub_gate(su, shrubs)
    pd.DataFrame([{k: gate[k] for k in ("total_sus", "sus_with_trees", "sus_no_trees")}]).to_csv(
        OUT / "gates" / "national_gate_tree_presence.csv", index=False
    )
    pd.DataFrame([{k: gate_sh[k] for k in ("total_sus", "sus_with_shrubs", "sus_no_shrubs")}]).to_csv(
        OUT / "gates" / "national_gate_shrub_presence.csv", index=False
    )
    pd.DataFrame({"SU_UID": gate["zero_tree_su_uids"]}).to_csv(
        OUT / "gates" / "national_zero_tree_su_uids.csv", index=False
    )
    pd.DataFrame({"SU_UID": gate_sh["zero_shrub_su_uids"]}).to_csv(
        OUT / "gates" / "national_zero_shrub_su_uids.csv", index=False
    )

    su_area = attach_regional_gis_area(su, cfg)
    su_area.to_csv(OUT / "validated" / "national_su_with_optional_area.csv", index=False)
    area_cov = su_area["area_status"].value_counts(dropna=False).rename("n").reset_index()
    area_cov.columns = ["area_status", "n"]
    area_cov.to_csv(OUT / "audit" / "national_area_coverage.csv", index=False)

    tree_m = national_tree_biomass(trees, cfg)
    shrub_m = national_shrub_biomass(shrubs)
    tree_m.to_csv(OUT / "validated" / "national_trees_biomass_provisional.csv", index=False)
    shrub_m.to_csv(OUT / "validated" / "national_shrubs_biomass_provisional.csv", index=False)

    rolled = aggregate_plot_su_metrics(tree_m, shrub_m, lattice)
    rolled["plot_metrics"].to_csv(OUT / "validated" / "national_plot_biomass_sample.csv", index=False)
    rolled["su_metrics"].to_csv(OUT / "validated" / "national_su_biomass_sample.csv", index=False)

    ancillary = national_ancillary_inventory(tables, OUT / "audit")
    lu_props = pd.DataFrame()
    if "lucs" in tables:
        lu_props = national_land_use_proportions(tables["lucs"], cfg, OUT / "validated")

    miss_t = missingness_report(trees, "national_trees")
    miss_s = missingness_report(shrubs, "national_shrubs")
    miss_t.to_csv(OUT / "audit" / "missingness_national_trees.csv", index=False)
    miss_s.to_csv(OUT / "audit" / "missingness_national_shrubs.csv", index=False)
    uni_t = univariate_numeric(tree_m, [c for c in ["agb_mg", "carbon_mg_provisional", "volume_m3"] if c in tree_m.columns])
    uni_t.to_csv(OUT / "audit" / "univariate_national_trees_fv.csv", index=False)
    uni_s = univariate_numeric(
        shrub_m, [c for c in ["mean_CD_m", "height_cm", "agb_mg", "carbon_mg_provisional"] if c in shrub_m.columns]
    )
    uni_s.to_csv(OUT / "audit" / "univariate_national_shrubs_fv.csv", index=False)

    fig_paths = write_national_eda_figures(trees, tree_m, shrub_m, OUT / "figures" / "national_eda", cfg)
    map_paths = write_national_maps(plot, cfg, OUT / "maps" / "national", rolled["su_metrics"])

    stages.save("N01_universe", "by_region", summary["by_region"], note="National SU counts by region")
    stages.save("N02_lattice", "lattice_head", lattice.head(5000), note="National anti-clip lattice sample")
    stages.save("N03_biomass", "tree_head", tree_m.head(5000), note="National tree biomass provisional")
    stages.save("N03_biomass", "shrub_head", shrub_m.head(5000), note="National shrub biomass provisional")
    stages.save("N04_ancillary", "pools", ancillary, note="Ancillary pools inventoried; biomass blocked")

    run_summary = {
        "scope": "national_tabular_universe",
        "n_su": summary["n_su"],
        "n_plot_rows": summary["n_plot_rows"],
        "n_plot_uid": summary["n_plot_uid"],
        "n_regions": summary["n_regions"],
        "expected_lattice_rows": expected_n,
        "lattice_rows": int(len(lattice)),
        "gate_tree_presence": {k: gate[k] for k in ("total_sus", "sus_with_trees", "sus_no_trees")},
        "gate_shrub_presence": {k: gate_sh[k] for k in ("total_sus", "sus_with_shrubs", "sus_no_shrubs")},
        "n_tree_biomass_rows": int(len(tree_m)),
        "n_shrub_biomass_rows": int(len(shrub_m)),
        "n_lu_proportion_rows": int(len(lu_props)),
        "gis_area_attached_sus": int((su_area["area_status"] == "GIS_AREA_ATTACHED").sum()),
        "gis_area_blocked_sus": int((su_area["area_status"] == "AREA_BLOCKED_NO_GRID").sum()),
        "design_based_estimates": False,
        "carbon_label": "provisional",
        "figures": {k: str(v) for k, v in fig_paths.items()},
        "maps": {k: str(v) for k, v in map_paths.items()},
        "output_root": str(OUT),
        "assumptions": [
            "Shrub log treated as natural log (calc extract open question).",
            "Shrub sh_height treated as metres then converted to cm for the allometric formula when unit is missing or m.",
            "National Area_H expansion blocked except where Asir/Makkah grids attach.",
            "Biomass and carbon are provisional sample metrics, not design-based inventory totals.",
            "Deadwood, litter, regeneration, vegetation cover inventoried as counts only; no calc-doc biomass equations.",
            "Shrub CO2eq left blank: not stated in calculation DOCX shrub section.",
        ],
    }

    from nfi_national_html import produce_national_html_products

    html_products = produce_national_html_products(
        plot=plot,
        cfg=cfg,
        lattice=lattice,
        su_metrics=rolled["su_metrics"],
        run_summary=run_summary,
        by_region=summary["by_region"],
        ancillary=ancillary,
        area_cov=area_cov,
        gate=gate,
        gate_shrub=gate_sh,
        fig_paths=fig_paths,
        map_paths=map_paths,
        out_root=OUT,
    )
    run_summary["html_report"] = html_products.get("html_report")
    run_summary["html_atlas_index"] = html_products.get("atlas_index")
    run_summary["interactive_maps"] = html_products.get("interactive_maps")

    (OUT / "logs" / "national_run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return {
        "tables": tables,
        "summary": summary,
        "lattice": lattice,
        "gate": gate,
        "gate_shrub": gate_sh,
        "su_area": su_area,
        "tree_m": tree_m,
        "shrub_m": shrub_m,
        "rolled": rolled,
        "ancillary": ancillary,
        "lu_props": lu_props,
        "fig_paths": fig_paths,
        "map_paths": map_paths,
        "html_products": html_products,
        "run_summary": run_summary,
        "OUT": OUT,
    }
