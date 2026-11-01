# -*- coding: utf-8 -*-
"""Run (or refresh) the national End-to-End workflow enhancements.

Uses existing national outputs when present; otherwise runs the full national pipeline.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from nfi_audit import StageStore, load_config, resolve_portable_paths
from nfi_national_pipeline import (
    aggregate_plot_su_metrics,
    attach_regional_gis_area,
    build_national_plot_lattice,
    load_national_tables,
    national_gate_tree_presence,
    national_shrub_biomass,
    national_shrub_gate,
    national_tree_biomass,
    run_national_pipeline,
)
from nfi_workflow_e2e import run_workflow_enhancements


def _resolve_out(cfg: dict) -> Path:
    env = os.environ.get("NFI_OUTPUT_NATIONAL_ROOT", "").strip()
    if env:
        return Path(env)
    for letter in ("D", "E"):
        if Path(f"{letter}:/NFI_DISK.json").exists():
            return Path(f"{letter}:/outputs_national_v5")
    out = Path(cfg["paths"].get("output_national_root", ROOT / "outputs_national_v5"))
    if not out.is_absolute():
        out = ROOT / out
    return out


def main() -> int:
    cfg = resolve_portable_paths(load_config(ROOT / "config.yaml"), ROOT)
    out = _resolve_out(cfg)
    out.mkdir(parents=True, exist_ok=True)

    lattice_csv = out / "validated" / "national_plot_lattice.csv"
    tree_csv = out / "validated" / "national_trees_biomass_provisional.csv"
    shrub_csv = out / "validated" / "national_shrubs_biomass_provisional.csv"
    su_csv = out / "validated" / "national_su_biomass_sample.csv"

    if not (lattice_csv.exists() and tree_csv.exists() and shrub_csv.exists()):
        print("Core national products missing; running full national pipeline first...")
        result = run_national_pipeline(cfg, out_root=out)
        print(json.dumps({k: result["run_summary"].get(k) for k in (
            "n_su", "lattice_rows", "workflow_e2e"
        )}, indent=2))
        return 0

    import pandas as pd

    print("Refreshing workflow enhancements on existing national products...")
    tables = load_national_tables(cfg)
    su, trees, shrubs = tables["su"], tables["trees"], tables["shrubs"]
    lattice = pd.read_csv(lattice_csv)
    tree_m = pd.read_csv(tree_csv)
    shrub_m = pd.read_csv(shrub_csv)
    if su_csv.exists():
        su_metrics = pd.read_csv(su_csv)
    else:
        su_metrics = aggregate_plot_su_metrics(tree_m, shrub_m, lattice)["su_metrics"]
    gate = national_gate_tree_presence(su, trees)
    gate_sh = national_shrub_gate(su, shrubs)
    stages = StageStore(out)
    summary = run_workflow_enhancements(
        cfg,
        out,
        tables=tables,
        lattice=lattice,
        gate=gate,
        gate_sh=gate_sh,
        tree_m=tree_m,
        shrub_m=shrub_m,
        su_metrics=su_metrics,
        stages=stages,
    )
    # also refresh area coverage audit if missing
    if not (out / "validated" / "national_su_with_optional_area.csv").exists():
        attach_regional_gis_area(su, cfg).to_csv(
            out / "validated" / "national_su_with_optional_area.csv", index=False
        )
    print(json.dumps({
        "integrity_score_new_pct": summary.get("integrity_score_new_pct"),
        "lidar_evidence_adequate": summary.get("lidar_evidence_adequate"),
        "geoai_prototype_run": summary.get("geoai_prototype_run"),
        "exports": summary.get("exports"),
        "spatial_qa_pct_coords": (summary.get("spatial_qa") or {}).get("pct_any_coords_valid"),
        "log": str(out / "logs" / "workflow_e2e_summary.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
