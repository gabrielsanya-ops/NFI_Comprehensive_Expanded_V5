# -*- coding: utf-8 -*-
"""Fix NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb for full-Kingdom Colab runs."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NB = ROOT / "NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb"


def as_src(text: str) -> list[str]:
    lines = text.strip("\n").split("\n")
    return [ln + "\n" for ln in lines]


def main() -> None:
    nb = json.loads(NB.read_text(encoding="utf-8"))
    cells = nb["cells"]

    # --- 0. Intro: clarify Colab path for entire Kingdom ---
    cells[0]["source"] = as_src(
        """# KSA NFI GeoAI Comprehensive Expanded Pipeline V6 (Improved)

## Critical note on scope

This notebook **preserves the full analytical depth** of `NFI_GeoAI_Data_Preparation_V4_Refined.ipynb` (Part A below). It does **not** replace that workflow with a smaller demo.

| Part | Scope | Primary outputs |
| --- | --- | --- |
| **A** (preserved) | Asir GIS universe, anti-clip lattice, Gate 1/2, cleaning, EDA, cartography, GEDI, GeoAI protocol | `outputs/` |
| **B** (expansion) | National LULC Validation, calc-doc tree/shrub biomass, missingness, ESDA, ML | `outputs/` expansion folders |
| **C** (national) | **Entire Kingdom** tabular universe (all regions in the SU master) | `outputs_national_v5/` |

### Google Colab: run order for the entire Kingdom

1. **Runtime → Connect** (or Copy to Drive first if the notebook is open read-only from GitHub).
2. Run the **Colab / portable bootstrap** cell (installs packages + clones/finds the package with `data/`).
3. Either:
   - **Full notebook:** Run All (Part A Asir case study → Part B → Part C national), or
   - **National only:** jump to **PART C** (N0 to N5) after the bootstrap cell.
4. Open `outputs_national_v5/maps/html_atlas/index.html` and the HTML report from N4.

**National user guide (step-by-step):** `NFI_National_GeoPipeline_Guide_V5.ipynb`

**Shareable national HTML products** (after Part C):
- Report: `outputs_national_v5/documents/NFI_national_geopipeline_report.html`
- Atlas: `outputs_national_v5/maps/html_atlas/index.html`

Primary foundation path:
`F:\\1.KSA\\29.NFI\\KSA_NFI_GeoAI_Data_Preparation_Cursor\\nfi_geoai_data_preparation\\NFI_GeoAI_Data_Preparation_V4_Refined.ipynb`

HTML complement:
`F:\\1.KSA\\1.Forest\\10.NFI\\10.LULC_Validation\\LULC_VALIDATION_REPORT.html`
"""
    )

    # --- 2. Bootstrap: install requirements on Colab ---
    cells[2]["source"] = as_src(
        r"""from pathlib import Path
import os, sys, subprocess, shutil, warnings
warnings.filterwarnings('ignore')

IN_COLAB = False
try:
    from google.colab import drive
    try:
        drive.mount('/content/drive', force_remount=False)
    except Exception as e:
        print('Drive mount skipped/failed:', e)
    IN_COLAB = True
except Exception:
    IN_COLAB = Path('/content').exists() and not Path(r'F:/1.KSA').exists()

REPO_URL = 'https://github.com/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5.git'
CLONE_DIR = Path('/content/NFI_Comprehensive_Expanded_V5')
ALIASES = [
    'NFI_Comprehensive_Expanded_V5',
    '12.NFI_Comprehensive_Expanded_V5',
]

def looks_like_root(p: Path) -> bool:
    return (p / 'config.yaml').exists() and (p / 'src').exists() and (p / 'data' / 'cleansed').exists()

CANDIDATES = []
for name in ALIASES:
    CANDIDATES += [
        Path('/content/drive/MyDrive') / name,
        Path('/content/drive/MyDrive/33.Projects') / name,
        Path('/content') / name,
        Path(r'F:/1.KSA/29.NFI') / name,
        Path(r'F:/1.KSA/29.NFI/12.NFI_Comprehensive_Expanded_V5'),
    ]
CANDIDATES += [Path.cwd(), CLONE_DIR]

ROOT = next((c.resolve() for c in CANDIDATES if c.exists() and looks_like_root(c)), None)
if ROOT is None and IN_COLAB:
    print('Package not on Drive: cloning from GitHub...')
    if CLONE_DIR.exists():
        shutil.rmtree(CLONE_DIR, ignore_errors=True)
    subprocess.check_call(['git', 'clone', '--depth', '1', REPO_URL, str(CLONE_DIR)])
    ROOT = CLONE_DIR.resolve()

if ROOT is None or not looks_like_root(ROOT):
    raise FileNotFoundError(
        'Could not locate NFI_Comprehensive_Expanded_V5. '
        'Sync the folder to Drive MyDrive or ensure the GitHub repo is public, then re-run.'
    )

os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'src'))

# Install runtime deps on Colab (idempotent)
if IN_COLAB:
    req = ROOT / 'requirements.txt'
    print('Installing requirements for Colab (this can take a few minutes)...')
    cmd = [sys.executable, '-m', 'pip', 'install', '-q']
    if req.exists():
        cmd += ['-r', str(req)]
    else:
        cmd += [
            'pandas', 'numpy', 'openpyxl', 'pyarrow', 'geopandas', 'shapely', 'pyogrio',
            'pyproj', 'matplotlib', 'scipy', 'scikit-learn', 'statsmodels', 'pyyaml',
            'seaborn', 'missingno',
        ]
    subprocess.check_call(cmd)

print('IN_COLAB', IN_COLAB)
print('ROOT', ROOT)
print('notebook V6_Improved', (ROOT / 'NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb').exists())
print('cleansed', sorted(p.name for p in (ROOT / 'data' / 'cleansed').glob('*.xlsx'))[:8], '...')
print('asir_shp', (ROOT / 'data' / 'shapefile' / 'Asir_NFI_Shapefiles' / 'Asir_SU_Final.shp').exists())
"""
    )

    # --- Find Part C and replace N0/N1 code cells ---
    part_c = None
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if src.lstrip().startswith("# PART C"):
            part_c = i
            break
    if part_c is None:
        raise SystemExit("PART C not found")

    # Expect: part_c md, N0 md, N0 code, N1 md, N1 code, ...
    n0_code_i = part_c + 2
    n1_code_i = part_c + 4
    assert cells[n0_code_i]["cell_type"] == "code", cells[n0_code_i]["cell_type"]
    assert cells[n1_code_i]["cell_type"] == "code"

    cells[part_c]["source"] = as_src(
        """# PART C · National-first geopipeline (entire Kingdom)

This block runs the **national tabular universe** (all regions in the cleansed SU master), not an Asir-only clip.

| Item | Detail |
| --- | --- |
| LEFT master | `nfi_of_ksa_program_su.xlsx` (all SUs) x 5-plot lattice |
| Biomass | Word calc DOCX trees **and** shrubs |
| GIS `Area_H` | Asir and Makkah grids only; others `AREA_BLOCKED_NO_GRID` |
| Outputs | `outputs_national_v5/` (does not overwrite Part A `outputs/` or raw data) |
| Atlas cartography | Fixed class colours (land-cover style), points / Voronoi, satellite basemap |
| CLI twin | `python run_national_pipeline.py` |
| Dedicated guide | `NFI_National_GeoPipeline_Guide_V5.ipynb` |

**Colab:** after the bootstrap cell, run N0 to N5 here for the **entire Kingdom**. On Colab, N1 defaults to a full recompute (`SKIP_IF_PRODUCTS_EXIST = False`).

**Sections:** N0 environment · N1 pipeline · N2 gates and figures · N3 thematic atlas refresh · N4 open HTML deliverables · N5 scope reminder
"""
    )

    cells[n0_code_i]["source"] = as_src(
        r"""from pathlib import Path
import os, sys, json, warnings
warnings.filterwarnings('ignore')

from IPython.display import display, HTML, Markdown, Image, IFrame

def _find_national_root():
    candidates = []
    for name in ('ROOT', 'EXP_ROOT', 'NAT_ROOT'):
        if name in globals():
            try:
                candidates.append(Path(globals()[name]))
            except Exception:
                pass
    candidates += [
        Path.cwd(),
        Path('/content/NFI_Comprehensive_Expanded_V5'),
        Path('/content/drive/MyDrive/NFI_Comprehensive_Expanded_V5'),
        Path('/content/drive/MyDrive/33.Projects/NFI_Comprehensive_Expanded_V5'),
        Path(r'F:/1.KSA/29.NFI/12.NFI_Comprehensive_Expanded_V5'),
    ]
    for p in candidates:
        if p and p.exists() and (p / 'config.yaml').exists() and (p / 'src').exists():
            return p.resolve()
    raise FileNotFoundError(
        'config.yaml and src/ were not found. Run the Colab bootstrap cell first, '
        'or change into the package folder.'
    )

NAT_ROOT = _find_national_root()
os.chdir(NAT_ROOT)
sys.path.insert(0, str(NAT_ROOT / 'src'))

from nfi_audit import load_config, resolve_portable_paths
from nfi_national_pipeline import run_national_pipeline

CFG = resolve_portable_paths(load_config(NAT_ROOT / 'config.yaml'), NAT_ROOT)
NAT_CFG = CFG  # alias used by some cells
NAT_OUT = Path(CFG['paths'].get('output_national_root', NAT_ROOT / 'outputs_national_v5'))
if not NAT_OUT.is_absolute():
    NAT_OUT = NAT_ROOT / NAT_OUT
NAT_OUT.mkdir(parents=True, exist_ok=True)

SUMMARY_JSON = NAT_OUT / 'logs' / 'national_run_summary.json'
ATLAS_INDEX = NAT_OUT / 'maps' / 'html_atlas' / 'index.html'
REPORT_PATH = NAT_OUT / 'documents' / 'NFI_national_geopipeline_report.html'

IN_COLAB = bool(globals().get('IN_COLAB')) or (
    Path('/content').exists() and not Path(r'F:/1.KSA').exists()
)

print('IN_COLAB', IN_COLAB)
print('NAT_ROOT', NAT_ROOT)
print('NAT_OUT', NAT_OUT)
print('prior run summary exists:', SUMMARY_JSON.exists())
print('atlas exists:', ATLAS_INDEX.exists())
print('report exists:', REPORT_PATH.exists())
print('cleansed SU master:', (NAT_ROOT / 'data' / 'cleansed' / 'nfi_of_ksa_program_su.xlsx').exists())
"""
    )

    cells[n1_code_i]["source"] = as_src(
        r"""# On Colab always recompute so the entire Kingdom is processed with the package on this runtime.
# Locally you may set SKIP_IF_PRODUCTS_EXIST = True to reuse outputs_national_v5/.
IN_COLAB = bool(globals().get('IN_COLAB')) or (
    Path('/content').exists() and not Path(r'F:/1.KSA').exists()
)
SKIP_IF_PRODUCTS_EXIST = False if IN_COLAB else True

have_core = SUMMARY_JSON.exists() and ATLAS_INDEX.exists() and REPORT_PATH.exists()
if SKIP_IF_PRODUCTS_EXIST and have_core:
    RS = json.loads(SUMMARY_JSON.read_text(encoding='utf-8'))
    NAT = {'run_summary': RS, 'skipped_rerun': True}
    print('Skipped full pipeline: core national products already present.')
    print('Set SKIP_IF_PRODUCTS_EXIST = False to recompute.')
else:
    print('Running national pipeline for the entire Kingdom (all regions in SU master)...')
    NAT = run_national_pipeline(CFG, out_root=NAT_OUT)
    RS = NAT['run_summary']

keys = [k for k in RS if k not in ('figures', 'maps', 'assumptions', 'interactive_maps')]
display(Markdown('### Run summary (computed keys only)'))
display({k: RS[k] for k in keys})
print('assumptions:')
for a in RS.get('assumptions', []):
    print(' -', a)

by_region_csv = NAT_OUT / 'audit' / 'national_su_by_region.csv'
anc_csv = NAT_OUT / 'audit' / 'national_ancillary_pools.csv'
if by_region_csv.exists():
    import pandas as pd
    display(Markdown('### SU universe by region (entire Kingdom)'))
    display(pd.read_csv(by_region_csv))
if anc_csv.exists():
    import pandas as pd
    display(Markdown('### Ancillary pools (inventory only)'))
    display(pd.read_csv(anc_csv))
"""
    )

    # --- Harden V6 audit cell (last code cell before release notes) ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "code" and "AUDIT_DIR = EXP_OUT / 'audit_v6'" in src:
            cells[i]["source"] = as_src(
                r"""from pathlib import Path
import hashlib, json, platform, importlib.metadata as md
import pandas as pd
from datetime import datetime, timezone

# Resolve expansion / package roots if Part B was skipped
if 'EXP_OUT' not in globals() or 'CFG' not in globals():
    _root = Path(globals().get('NAT_ROOT') or globals().get('ROOT') or Path.cwd())
    if 'CFG' not in globals():
        from nfi_audit import load_config, resolve_portable_paths
        CFG = resolve_portable_paths(load_config(_root / 'config.yaml'), _root)
    EXP_OUT = Path(globals().get('EXP_OUT') or (_root / 'outputs' / 'expansion'))
EXP_OUT = Path(EXP_OUT)
EXP_OUT.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = EXP_OUT / 'audit_v6'
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

def sha256_file(path, chunk_size=1024*1024):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b''):
            h.update(chunk)
    return h.hexdigest()

from nfi_audit import read_first_sheet

def _table(name):
    if name in globals() and globals()[name] is not None:
        return globals()[name]
    path = Path(CFG['tables'][name])
    return read_first_sheet(path)

su = _table('su')
plot = _table('plot')
trees = _table('trees')
shrubs = _table('shrubs')
try:
    lulc = globals().get('lulc')
    if lulc is None:
        from nfi_lulc_html import load_lulc_validated
        lulc_path = Path(CFG.get('paths', {}).get('lulc_validated_csv', 'data/lulc/lucs_office_validated_esa_esri_ndvi.csv'))
        if not lulc_path.is_absolute():
            lulc_path = Path(globals().get('NAT_ROOT') or globals().get('ROOT') or Path.cwd()) / lulc_path
        lulc = load_lulc_validated(lulc_path) if lulc_path.exists() else pd.DataFrame()
except Exception as e:
    print('LULC dictionary skipped:', e)
    lulc = pd.DataFrame()

source_rows = []
for name in ('trees', 'plot', 'su', 'shrubs'):
    location = Path(CFG['tables'][name])
    source_rows.append({
        'source_id': name, 'path': str(location),
        'exists': location.is_file(),
        'sha256': sha256_file(location) if location.is_file() else None,
        'bytes': location.stat().st_size if location.is_file() else None,
        'captured_utc': datetime.now(timezone.utc).isoformat(),
        'license': 'REVIEW REQUIRED', 'data_class': 'REVIEW REQUIRED'
    })
ledger = pd.DataFrame(source_rows)
ledger.to_csv(AUDIT_DIR / 'source_ledger.csv', index=False)

dictionary = []
for name, df in [('trees', trees), ('plot', plot), ('su', su), ('shrubs', shrubs), ('lulc', lulc)]:
    if df is None or len(getattr(df, 'columns', [])) == 0:
        continue
    for col in df.columns:
        dictionary.append({
            'table': name, 'variable': col,
            'dtype': str(df[col].dtype), 'n_rows': len(df),
            'n_missing': int(df[col].isna().sum()),
            'definition': 'REVIEW REQUIRED', 'units': 'REVIEW REQUIRED',
            'personal_data_flag': 'REVIEW REQUIRED'
        })
pd.DataFrame(dictionary).to_csv(AUDIT_DIR / 'data_dictionary_draft.csv', index=False)

su_key = CFG['columns']['su_id_in_su_master']
if su_key not in su.columns:
    raise KeyError(f'Master sampling-unit key missing: {su_key}')
if su[su_key].isna().any():
    raise ValueError('Null sampling-unit keys in master table')
if su[su_key].astype(str).str.strip().duplicated().any():
    raise ValueError('Duplicate sampling-unit keys in master table')

manifest = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'python': platform.python_version(),
    'packages': {},
    'n_su_master': int(len(su)),
    'n_regions': int(su[CFG['columns']['region_en']].nunique()) if CFG['columns']['region_en'] in su.columns else None,
}
for pkg in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'geopandas', 'pyyaml', 'matplotlib']:
    try:
        manifest['packages'][pkg] = md.version(pkg)
    except md.PackageNotFoundError:
        manifest['packages'][pkg] = 'NOT INSTALLED'
(AUDIT_DIR / 'environment_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Audit artifacts:', AUDIT_DIR)
print('SU master rows (entire Kingdom table):', len(su))
display(ledger[['source_id', 'exists', 'bytes']])
"""
            )
            break

    NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Updated", NB.name, "cells", len(cells), "Part C at", part_c)


if __name__ == "__main__":
    main()
