# -*- coding: utf-8 -*-
"""National adaptation of the attached KSA NFI GeoAI End-to-End Process Flow.

Phases (attached workflow.png, nationalized):
  Phase 1 Data engineering (steps 0 to 7)
  Phase 2 Science, EDA and maps (steps 8 to 14)
  Phase 3 Evidence, AI and export (steps 15 to 17)

Rules carried forward:
  - Anti-clip: never inner-join/clip the SU universe to trees only (LEFT master).
  - Imputation OFF for remote overwriting field measurements.
  - LiDAR / models produce disparities and prototypes only (no field overwrite).
  - All biomass/carbon remain provisional sample metrics unless design weights exist.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nfi_audit import StageStore, plot_coordinate_qa
from nfi_datascience import (
    accuracy_scorecard,
    compare_old_vs_new_method,
    modelling_protocol_table,
)


WORKFLOW_STEPS = [
    {"id": 0, "phase": 1, "name": "Environment and StageStore"},
    {"id": 1, "phase": 1, "name": "Ingest NFI + GIS"},
    {"id": 2, "phase": 1, "name": "Area appropriation"},
    {"id": 3, "phase": 1, "name": "Anti-clip lattice"},
    {"id": 4, "phase": 1, "name": "Gates and regions"},
    {"id": 5, "phase": 1, "name": "Region / governorate roll-ups"},
    {"id": 6, "phase": 1, "name": "Clean and ready"},
    {"id": 7, "phase": 1, "name": "Field vs office coordinate QA"},
    {"id": 8, "phase": 2, "name": "Analytical population gate"},
    {"id": 9, "phase": 2, "name": "Statistical QA (flag, do not delete)"},
    {"id": 10, "phase": 2, "name": "Exhaustive EDA"},
    {"id": 11, "phase": 2, "name": "Integrity scorecard (clip vs anti-clip)"},
    {"id": 12, "phase": 2, "name": "Maps and HTML atlas"},
    {"id": 13, "phase": 2, "name": "Thematic layers and filters"},
    {"id": 14, "phase": 2, "name": "Spatial QA"},
    {"id": 15, "phase": 3, "name": "LiDAR cross-check (GEDI L2A + optional CHM)"},
    {"id": 16, "phase": 3, "name": "GeoAI model protocol"},
    {"id": 17, "phase": 3, "name": "StageStore ledger and export package"},
]


def workflow_catalog() -> pd.DataFrame:
    return pd.DataFrame(WORKFLOW_STEPS)


def national_integrity_scorecard(
    su: pd.DataFrame,
    trees: pd.DataFrame,
    lattice: pd.DataFrame,
    gate: dict[str, Any],
    plots_per_su: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clip/pivot vs anti-clip integrity using national computed gate counts."""
    plots_with_trees = int(lattice["has_tree_record"].sum()) if "has_tree_record" in lattice.columns else 0
    targets = {
        "total_sus": int(gate["total_sus"]),
        "sus_with_trees": int(gate["sus_with_trees"]),
        "sus_no_trees": int(gate["sus_no_trees"]),
        "expected_plots": int(gate["total_sus"]) * int(plots_per_su),
        "plots_with_trees": plots_with_trees,
    }
    comparison = compare_old_vs_new_method(su, trees, lattice, targets)
    score = accuracy_scorecard(comparison)
    return comparison, score


def row_conservation_ledger(
    tables: dict[str, pd.DataFrame],
    lattice: pd.DataFrame,
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    gate: dict[str, Any],
    gate_sh: dict[str, Any],
) -> pd.DataFrame:
    """Explicit row counts: source → lattice → biomass (no silent drops)."""
    su = tables["su"]
    plot = tables["plot"]
    trees = tables["trees"]
    shrubs = tables["shrubs"]
    rows = [
        {"stage": "source_su", "n_rows": int(len(su)), "n_keys": int(su["SU_UID"].nunique()), "note": "LEFT master"},
        {"stage": "source_plot", "n_rows": int(len(plot)), "n_keys": int(plot["PLOT_UID"].nunique()), "note": "plot table"},
        {"stage": "source_trees", "n_rows": int(len(trees)), "n_keys": int(trees["PLOT_UID"].nunique()) if "PLOT_UID" in trees.columns else None, "note": "tree records"},
        {"stage": "source_shrubs", "n_rows": int(len(shrubs)), "n_keys": int(shrubs["PLOT_UID"].nunique()) if "PLOT_UID" in shrubs.columns else None, "note": "shrub records"},
        {"stage": "anticlip_lattice", "n_rows": int(len(lattice)), "n_keys": int(lattice["PLOT_UID"].nunique()), "note": "SU x 5 design slots"},
        {"stage": "lattice_zero_tree_slots", "n_rows": int((~lattice["has_tree_record"]).sum()) if "has_tree_record" in lattice.columns else None, "n_keys": None, "note": "kept visible"},
        {"stage": "gate_zero_tree_su", "n_rows": int(gate["sus_no_trees"]), "n_keys": int(gate["sus_no_trees"]), "note": "classified absence"},
        {"stage": "gate_zero_shrub_su", "n_rows": int(gate_sh["sus_no_shrubs"]), "n_keys": int(gate_sh["sus_no_shrubs"]), "note": "classified absence"},
        {"stage": "tree_biomass_provisional", "n_rows": int(len(tree_m)), "n_keys": int(tree_m["PLOT_UID"].nunique()) if "PLOT_UID" in tree_m.columns else None, "note": "calc DOCX"},
        {"stage": "shrub_biomass_provisional", "n_rows": int(len(shrub_m)), "n_keys": int(shrub_m["PLOT_UID"].nunique()) if "PLOT_UID" in shrub_m.columns else None, "note": "calc DOCX"},
    ]
    return pd.DataFrame(rows)


def spatial_qa_national(plot: pd.DataFrame, cfg: dict, lattice: pd.DataFrame) -> dict[str, Any]:
    """Coordinate coverage and lattice join QA (numeric only; no invented geometry)."""
    lat_c = cfg["columns"]["lat_field"]
    lon_c = cfg["columns"]["lon_field"]
    lat_db = cfg["columns"].get("lat_db")
    lon_db = cfg["columns"].get("lon_db")

    def _valid(series_lat, series_lon):
        ok = series_lat.notna() & series_lon.notna()
        if ok.any():
            ok &= series_lat.between(-90, 90) & series_lon.between(-180, 180)
        return ok

    field_ok = _valid(plot[lat_c], plot[lon_c]) if lat_c in plot.columns and lon_c in plot.columns else pd.Series(False, index=plot.index)
    office_ok = (
        _valid(plot[lat_db], plot[lon_db])
        if lat_db and lon_db and lat_db in plot.columns and lon_db in plot.columns
        else pd.Series(False, index=plot.index)
    )
    any_ok = field_ok | office_ok
    lattice_plots = set(lattice["PLOT_UID"].astype(str))
    plot_uids = set(plot["PLOT_UID"].astype(str)) if "PLOT_UID" in plot.columns else set()
    in_lattice = plot_uids & lattice_plots
    outside_lattice = plot_uids - lattice_plots
    return {
        "n_plot_rows": int(len(plot)),
        "n_field_coords_valid": int(field_ok.sum()),
        "n_office_coords_valid": int(office_ok.sum()),
        "n_any_coords_valid": int(any_ok.sum()),
        "pct_any_coords_valid": round(100 * float(any_ok.mean()), 2) if len(plot) else None,
        "n_plot_uid_in_lattice": int(len(in_lattice)),
        "n_plot_uid_outside_lattice": int(len(outside_lattice)),
        "n_lattice_slots": int(len(lattice)),
        "note": "Spatial QA is coverage/topology against the analytical lattice; not a design-based area frame.",
    }


def lidar_evidence_gate(cfg: dict, out_root: Path) -> dict[str, Any]:
    """Step 15: national wall-to-wall remote height evidence (entire Kingdom).

    Prefer Meta CHMv2 + Open-Meteo elevation (country-wide). Optional GEDI
    footprints are supplementary only; Asir-bounded GEDI is not required.
    Never overwrite field heights.
    """
    out_root = Path(out_root)
    national_candidates = [
        out_root / "validated" / "national_su_meta_chm_v2.csv",
        out_root / "validated" / "national_su_elevation_open_meteo.csv",
        out_root / "logs" / "national_remote_height_evidence.json",
    ]
    # Optional sparse footprints (not required for national adequacy)
    from nfi_gedi_l2a import GEDI_DEFAULT_TABLE, GEDI_STORAGE_ROOT

    optional_gedi = [
        Path(GEDI_DEFAULT_TABLE),
        GEDI_STORAGE_ROOT / "gedi_l2a_footprints.csv",
        GEDI_STORAGE_ROOT / "gedi_l2a_footprints.gpkg",
        Path(cfg.get("paths", {}).get("gedi_l2a_table", "")) if cfg.get("paths", {}).get("gedi_l2a_table") else None,
        out_root / "validated" / "gedi_l2a_plot_join.csv",
    ]
    found_national = [str(p) for p in national_candidates if p and Path(p).exists()]
    found_gedi = [str(p) for p in optional_gedi if p and Path(p).exists()]

    adequate = False
    n_chm_ok = 0
    n_elev_ok = 0
    n_regions = None
    chm_csv = out_root / "validated" / "national_su_meta_chm_v2.csv"
    elev_csv = out_root / "validated" / "national_su_elevation_open_meteo.csv"
    if chm_csv.exists():
        try:
            chm = pd.read_csv(chm_csv, usecols=lambda c: c in {"sample_ok", "region", "SU_UID"})
            if "sample_ok" in chm.columns:
                n_chm_ok = int(chm["sample_ok"].fillna(False).astype(bool).sum())
            else:
                n_chm_ok = int(len(chm))
            if "region" in chm.columns:
                n_regions = int(chm["region"].nunique())
        except Exception:
            n_chm_ok = 0
    if elev_csv.exists():
        try:
            elev = pd.read_csv(elev_csv, usecols=lambda c: c in {"elevation_m_open_meteo", "SU_UID"})
            if "elevation_m_open_meteo" in elev.columns:
                n_elev_ok = int(elev["elevation_m_open_meteo"].notna().sum())
            else:
                n_elev_ok = int(len(elev))
        except Exception:
            n_elev_ok = 0

    # National adequacy: wall-to-wall products covering the Kingdom
    adequate = (n_chm_ok >= 100) or (n_elev_ok >= 500) or bool(found_national and (n_chm_ok or n_elev_ok))

    report = {
        "step": 15,
        "scope": "national_entire_kingdom",
        "asir_only": False,
        "product": "Meta_CHMv2 + Open-Meteo elevation (national alternatives); GEDI optional/sparse",
        "evidence_adequate": adequate,
        "found_paths": found_national + found_gedi,
        "n_chm_ok": n_chm_ok,
        "n_elev_ok": n_elev_ok,
        "n_regions": n_regions,
        "imputation": "OFF",
        "field_overwrite": False,
        "action_if_not_adequate": "Run python run_national_remote_height.py for Kingdom-wide CHM+elevation.",
        "action_if_adequate": "Compare disparities only; do not overwrite field tree_height.",
    }
    (out_root / "audit" / "lidar_evidence_gate.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def geoai_protocol_bundle(out_root: Path, tree_m: pd.DataFrame | None = None) -> dict[str, Any]:
    """Step 16: freeze protocol table; optional SU-blocked height prototype when data allow."""
    protocol = modelling_protocol_table()
    protocol.to_csv(out_root / "audit" / "geoai_modelling_protocol.csv", index=False)

    result: dict[str, Any] = {
        "protocol_csv": str(out_root / "audit" / "geoai_modelling_protocol.csv"),
        "prototype_run": False,
        "field_overwrite": False,
        "note": "Null / RF / boosting / ensemble + AoA listed as protocol; prototypes are not observations.",
    }

    if tree_m is None or len(tree_m) < 200:
        result["skip_reason"] = "Insufficient tree_m rows for prototype."
        return result

    dbh_col = next((c for c in ("tree_dbh", "dbh_cm", "dbh") if c in tree_m.columns), None)
    ht_col = next((c for c in ("tree_height", "height_m", "height") if c in tree_m.columns), None)
    su_col = "SU_UID" if "SU_UID" in tree_m.columns else None
    if not (dbh_col and ht_col and su_col):
        result["skip_reason"] = "Need DBH, height, and SU_UID columns."
        return result

    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
        from sklearn.model_selection import GroupKFold
    except Exception as e:
        result["skip_reason"] = f"sklearn unavailable: {e}"
        return result

    work = tree_m[[su_col, dbh_col, ht_col]].dropna().copy()
    work = work[(work[dbh_col] > 0) & (work[ht_col] > 0)]
    if len(work) < 200 or work[su_col].nunique() < 10:
        result["skip_reason"] = "Too few complete rows/SUs after filters."
        return result

    X = work[[dbh_col]].to_numpy()
    y = work[ht_col].to_numpy()
    groups = work[su_col].astype(str).to_numpy()
    gkf = GroupKFold(n_splits=min(5, work[su_col].nunique()))
    maes, r2s = [], []
    rng = np.random.RandomState(42)
    for tr, te in gkf.split(X, y, groups):
        model = RandomForestRegressor(
            n_estimators=200, random_state=42, n_jobs=-1, min_samples_leaf=5
        )
        model.fit(X[tr], y[tr])
        pred = model.predict(X[te])
        maes.append(float(mean_absolute_error(y[te], pred)))
        r2s.append(float(r2_score(y[te], pred)))
    # unused rng kept for reproducibility hook
    _ = rng.randint(0, 1)

    metrics = {
        "target": ht_col,
        "features": [dbh_col],
        "cv": "GroupKFold by SU_UID",
        "n_rows": int(len(work)),
        "n_su": int(work[su_col].nunique()),
        "mae_mean": round(float(np.mean(maes)), 4),
        "r2_mean": round(float(np.mean(r2s)), 4),
        "label": "prototype_only_not_observation",
        "field_overwrite": False,
    }
    (out_root / "audit" / "geoai_height_prototype_su_blocked_cv.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    result["prototype_run"] = True
    result["metrics"] = metrics
    return result


def export_vector_package(
    plot: pd.DataFrame,
    cfg: dict,
    su_metrics: pd.DataFrame,
    lattice: pd.DataFrame,
    out_root: Path,
) -> dict[str, str]:
    """Step 17 export slice: GeoPackage vectors (plots with coords + SU metrics table)."""
    import geopandas as gpd
    from shapely.geometry import Point

    export_dir = out_root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    gpkg = export_dir / "nfi_national_export_package.gpkg"
    if gpkg.exists():
        gpkg.unlink()

    lat_c = cfg["columns"]["lat_field"]
    lon_c = cfg["columns"]["lon_field"]
    written: dict[str, str] = {}

    if lat_c in plot.columns and lon_c in plot.columns:
        pp = plot.dropna(subset=[lat_c, lon_c]).copy()
        pp = pp[pp[lat_c].between(-90, 90) & pp[lon_c].between(-180, 180)]
        geom = [Point(xy) for xy in zip(pp[lon_c].astype(float), pp[lat_c].astype(float))]
        gdf = gpd.GeoDataFrame(pp, geometry=geom, crs="EPSG:4326")
        # keep a lean attribute set
        keep = [c for c in ["SU_UID", "PLOT_UID", lat_c, lon_c] if c in gdf.columns]
        gdf[keep + ["geometry"]].to_file(gpkg, layer="plots_field_xy", driver="GPKG")
        written["plots_field_xy"] = str(gpkg)

    # non-geometry tables as GPKG attribute layers via geopandas (empty geom)
    for name, df in (("su_metrics", su_metrics), ("lattice_sample", lattice.head(5000))):
        if df is None or len(df) == 0:
            continue
        # write CSV twin always
        csv_path = export_dir / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        written[f"{name}_csv"] = str(csv_path)

    written["gpkg"] = str(gpkg) if gpkg.exists() else ""
    written["note"] = "GeoTIFF national surfaces deferred until a continuous raster frame is approved."
    (export_dir / "export_manifest.json").write_text(json.dumps(written, indent=2), encoding="utf-8")
    return written


def run_workflow_enhancements(
    cfg: dict,
    out_root: Path,
    *,
    tables: dict[str, pd.DataFrame],
    lattice: pd.DataFrame,
    gate: dict[str, Any],
    gate_sh: dict[str, Any],
    tree_m: pd.DataFrame,
    shrub_m: pd.DataFrame,
    su_metrics: pd.DataFrame,
    stages: StageStore | None = None,
) -> dict[str, Any]:
    """Execute workflow steps that were thin or missing in the prior national runner."""
    out_root = Path(out_root)
    for sub in ("audit", "validated", "gates", "logs", "exports", "documents", "stages"):
        (out_root / sub).mkdir(parents=True, exist_ok=True)

    su, plot, trees = tables["su"], tables["plot"], tables["trees"]
    plots_per = int(cfg["project"]["plots_per_su_design"])

    catalog = workflow_catalog()
    catalog.to_csv(out_root / "audit" / "workflow_e2e_catalog.csv", index=False)

    # Step 7 coord QA
    coord_qa = plot_coordinate_qa(plot, cfg)
    coord_qa.to_csv(out_root / "audit" / "national_plot_coordinate_qa.csv", index=False)

    # Step 11 integrity
    comparison, score = national_integrity_scorecard(su, trees, lattice, gate, plots_per)
    comparison.to_csv(out_root / "audit" / "integrity_clip_vs_anticlip.csv", index=False)
    score.to_csv(out_root / "audit" / "integrity_scorecard.csv", index=False)

    # Row ledger (steps 6/17)
    ledger = row_conservation_ledger(tables, lattice, tree_m, shrub_m, gate, gate_sh)
    ledger.to_csv(out_root / "audit" / "row_conservation_ledger.csv", index=False)

    # Step 14 spatial QA
    spatial = spatial_qa_national(plot, cfg, lattice)
    (out_root / "audit" / "spatial_qa_national.json").write_text(
        json.dumps(spatial, indent=2), encoding="utf-8"
    )

    # Step 15 LiDAR gate
    lidar = lidar_evidence_gate(cfg, out_root)

    # Step 16 GeoAI protocol (+ optional prototype)
    geoai = geoai_protocol_bundle(out_root, tree_m)

    # Step 17 exports
    exports = export_vector_package(plot, cfg, su_metrics, lattice, out_root)

    if stages is not None:
        stages.save("W11_integrity", "scorecard", score, note="Clip vs anti-clip integrity")
        stages.save("W06_ledger", "row_conservation", ledger, note="Row conservation ledger")
        stages.save("W16_geoai", "protocol", protocol_head(geoai), note="GeoAI protocol snapshot")

    summary = {
        "workflow": "KSA_NFI_GeoAI_End_to_End_Process_Flow_nationalized",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "steps": WORKFLOW_STEPS,
        "integrity_score_new_pct": float(score.loc[score["method"].str.contains("NEW"), "integrity_score_pct"].iloc[0])
        if len(score) else None,
        "spatial_qa": spatial,
        "lidar_evidence_adequate": lidar.get("evidence_adequate"),
        "geoai_prototype_run": geoai.get("prototype_run"),
        "exports": exports,
        "anti_clip_rule": "Never inner-join/clip the SU universe to trees only; LEFT master keeps all SUs.",
        "imputation_policy": "OFF for remote→field overwrite",
    }
    (out_root / "logs" / "workflow_e2e_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def protocol_head(geoai: dict[str, Any]) -> pd.DataFrame:
    if geoai.get("metrics"):
        return pd.DataFrame([geoai["metrics"]])
    return pd.DataFrame([{"prototype_run": geoai.get("prototype_run"), "note": geoai.get("skip_reason") or geoai.get("note")}])
