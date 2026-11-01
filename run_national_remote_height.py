# -*- coding: utf-8 -*-
"""CLI: Kingdom-wide remote height evidence (Meta CHMv2 + Open-Meteo elevation).

Not Asir-bounded. Samples the national SU master across all regions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from nfi_audit import load_config, resolve_portable_paths
from nfi_national_remote_height import run_national_remote_height_evidence


def _resolve_out() -> Path:
    env = os.environ.get("NFI_OUTPUT_NATIONAL_ROOT", "").strip()
    if env:
        return Path(env)
    for letter in ("D", "E"):
        if Path(f"{letter}:/NFI_DISK.json").exists():
            return Path(f"{letter}:/outputs_national_v5")
    return ROOT / "outputs_national_v5"


def main() -> int:
    ap = argparse.ArgumentParser(description="National remote height evidence (entire KSA)")
    ap.add_argument("--skip-chm", action="store_true", help="Skip Meta CHM sampling")
    ap.add_argument("--skip-elevation", action="store_true", help="Skip Open-Meteo elevation")
    ap.add_argument(
        "--max-chm-points",
        type=int,
        default=None,
        help="Optional cap (stratified by region). Default: all national SUs with coords.",
    )
    args = ap.parse_args()

    cfg = resolve_portable_paths(load_config(ROOT / "config.yaml"), ROOT)
    out = _resolve_out()
    report = run_national_remote_height_evidence(
        out,
        sample_chm=not args.skip_chm,
        sample_elevation=not args.skip_elevation,
        max_chm_points=args.max_chm_points,
    )
    print(json.dumps({
        "scope": report.get("scope"),
        "asir_only": report.get("asir_only"),
        "n_su_with_coords": report.get("n_su_with_coords"),
        "n_regions": report.get("n_regions"),
        "evidence_adequate": report.get("evidence_adequate"),
        "products": [
            {"name": p["name"], "n_sample_ok": p["n_sample_ok"], "path": p["path"]}
            for p in report.get("products", [])
        ],
        "disparity": {k: v for k, v in (report.get("disparity") or {}).items() if k != "by_region"},
        "log": str(out / "logs" / "national_remote_height_evidence.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
