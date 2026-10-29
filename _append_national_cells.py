# -*- coding: utf-8 -*-
"""Append Part C national-first cells to the existing V5 notebook (never overwrite Part A/B)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NB = ROOT / "NFI_GeoAI_Comprehensive_Expanded_V5.ipynb"
MARKER = "PART C · National-first geopipeline"


def md(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [ln + "\n" for ln in text.strip("\n").split("\n")],
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [ln + "\n" for ln in text.strip("\n").split("\n")],
    }


def national_cells() -> list:
    cells = []
    cells.append(
        md(
            f"""# {MARKER} (entire country)

This block runs the **national tabular universe** (all regions in the cleansed SU master), not an Asir-only clip.

- LEFT master: `nfi_of_ksa_program_su.xlsx` (all SUs) × 5-plot lattice
- Biomass: Word calc DOCX trees **and** shrubs (`apply_tree_metrics` / `apply_shrub_metrics`)
- GIS `Area_H`: attached only for Asir and Makkah grids; other SUs stay `AREA_BLOCKED_NO_GRID`
- Outputs: `outputs_national_v5/` (does not overwrite Part A `outputs/` or original notebooks)

CLI equivalent: `python run_national_pipeline.py`
"""
        )
    )
    cells.append(md("## N0 · National environment"))
    cells.append(
        code(
            r"""from pathlib import Path
import os, sys, json, warnings
warnings.filterwarnings('ignore')

CANDIDATES = [
    Path(r'F:/1.KSA/29.NFI/12.NFI_Comprehensive_Expanded_V5'),
    Path.cwd(),
]
NAT_ROOT = next((p for p in CANDIDATES if (p/'config.yaml').exists() and (p/'src').exists()), Path.cwd())
os.chdir(NAT_ROOT)
sys.path.insert(0, str(NAT_ROOT / 'src'))

from nfi_audit import load_config, resolve_portable_paths
from nfi_national_pipeline import run_national_pipeline

CFG = resolve_portable_paths(load_config(NAT_ROOT / 'config.yaml'), NAT_ROOT)
NAT_OUT = Path(CFG['paths'].get('output_national_root', NAT_ROOT / 'outputs_national_v5'))
if not NAT_OUT.is_absolute():
    NAT_OUT = NAT_ROOT / NAT_OUT
print('NAT_ROOT', NAT_ROOT)
print('NAT_OUT', NAT_OUT)
"""
        )
    )
    cells.append(md("## N1 · Run national pipeline (ingest, lattice, trees, shrubs, EDA, maps)"))
    cells.append(
        code(
            r"""NAT = run_national_pipeline(CFG, out_root=NAT_OUT)
RS = NAT['run_summary']
print(json.dumps({k: RS[k] for k in RS if k not in ('figures','maps','assumptions')}, indent=2))
print('assumptions:')
for a in RS.get('assumptions', []):
    print(' -', a)
display(NAT['summary']['by_region'].head(20))
display(NAT['ancillary'])
"""
        )
    )
    cells.append(md("## N2 · Inspect national gates and sample biomass roll-ups"))
    cells.append(
        code(
            r"""print('Tree gate', NAT['gate']['total_sus'], 'with_trees', NAT['gate']['sus_with_trees'], 'zero', NAT['gate']['sus_no_trees'])
print('Shrub gate', NAT['gate_shrub']['total_sus'], 'with_shrubs', NAT['gate_shrub']['sus_with_shrubs'], 'zero', NAT['gate_shrub']['sus_no_shrubs'])
print('Lattice rows', len(NAT['lattice']), 'tree biomass rows', len(NAT['tree_m']), 'shrub biomass rows', len(NAT['shrub_m']))
display(NAT['rolled']['su_metrics'].head(10))
from IPython.display import Image, display as idisplay
for label, p in {**NAT['fig_paths'], **NAT['map_paths']}.items():
    print(label, p)
    if Path(p).exists():
        idisplay(Image(filename=str(p)))
"""
        )
    )
    cells.append(
        md(
            """## N3 · Scope reminder

| Layer | Coverage in this run |
| --- | --- |
| SU / plot tabular | Entire national cleansed master |
| Tree biomass (calc DOCX) | All SUs with eligible tree records |
| Shrub biomass (calc DOCX) | All SUs with eligible shrub records |
| Deadwood / litter / regen / veg | Count inventory only (no calc-doc equations) |
| Design-based Area_H totals | Only SUs with Asir or Makkah grid Area_H; others blocked |

See `outputs_national_v5/logs/national_run_summary.json` and `docs/04_national_pipeline.md`.
"""
        )
    )
    return cells


def main() -> None:
    nb = json.loads(NB.read_text(encoding="utf-8"))
    sources = "".join("".join(c.get("source", [])) for c in nb.get("cells", []))
    if MARKER in sources:
        print("Part C already present; skipping append.")
        return
    nb["cells"] = nb.get("cells", []) + national_cells()
    NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Appended Part C to", NB, "cells", len(nb["cells"]))


if __name__ == "__main__":
    main()
