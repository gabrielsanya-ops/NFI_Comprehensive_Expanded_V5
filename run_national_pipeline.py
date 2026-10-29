# -*- coding: utf-8 -*-
"""CLI entry: national-first KSA NFI geopipeline (entire country tabular universe)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from nfi_audit import load_config, resolve_portable_paths
from nfi_national_pipeline import run_national_pipeline


def main() -> int:
    cfg = load_config(ROOT / "config.yaml")
    cfg = resolve_portable_paths(cfg, ROOT)
    out = Path(cfg["paths"].get("output_national_root", ROOT / "outputs_national_v5"))
    if not out.is_absolute():
        out = ROOT / out
    result = run_national_pipeline(cfg, out_root=out)
    summary = result["run_summary"]
    print(json.dumps({k: summary[k] for k in summary if k not in ("figures", "maps", "assumptions")}, indent=2))
    print("figures:", list(summary.get("figures", {}).keys()))
    print("maps:", list(summary.get("maps", {}).keys()))
    print("output_root:", summary["output_root"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
