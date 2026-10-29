# -*- coding: utf-8 -*-
"""Improve Part C (+ intro) of NFI_GeoAI_Comprehensive_Expanded_V5.ipynb. Part A/B left intact."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NB = ROOT / "NFI_GeoAI_Comprehensive_Expanded_V5.ipynb"


def md(text: str) -> dict:
    lines = text.strip("\n").split("\n")
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [ln + "\n" for ln in lines],
    }


def code(text: str) -> dict:
    lines = text.strip("\n").split("\n")
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [ln + "\n" for ln in lines],
    }


INTRO = """# KSA NFI GeoAI Comprehensive Expanded Pipeline V5

## Critical note on scope

This notebook **preserves the full analytical depth** of `NFI_GeoAI_Data_Preparation_V4_Refined.ipynb` (Part A below). It does **not** replace that workflow with a smaller demo.

| Part | Scope | Primary outputs |
| --- | --- | --- |
| **A** (preserved) | Asir GIS universe, anti-clip lattice, Gate 1/2, cleaning, EDA, cartography, GEDI, GeoAI protocol | `outputs/` |
| **B** (expansion) | National LULC Validation, calc-doc tree/shrub biomass, missingness, ESDA, ML | `outputs/` expansion folders |
| **C** (national) | Entire Kingdom tabular universe (all regions in SU master) | `outputs_national_v5/` |

**National user guide (recommended for country-wide runs):** `NFI_National_GeoPipeline_Guide_V5.ipynb`

**Shareable national HTML products** (after Part C or the guide notebook):
- Report: `outputs_national_v5/documents/NFI_national_geopipeline_report.html`
- Atlas: `outputs_national_v5/maps/html_atlas/index.html` (land-cover style fixed class colours, Voronoi/points, admin filters)

Primary foundation path:
`F:\\1.KSA\\29.NFI\\KSA_NFI_GeoAI_Data_Preparation_Cursor\\nfi_geoai_data_preparation\\NFI_GeoAI_Data_Preparation_V4_Refined.ipynb`

HTML complement:
`F:\\1.KSA\\1.Forest\\10.NFI\\10.LULC_Validation\\LULC_VALIDATION_REPORT.html`
"""

PART_C_MD0 = """# PART C · National-first geopipeline (entire country)

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

**Sections:** N0 environment · N1 pipeline · N2 gates and figures · N3 thematic atlas refresh · N4 open HTML deliverables · N5 scope reminder
"""

N0_MD = """## N0 · National environment

**User note:** Sets `NAT_ROOT` / `NAT_OUT` and imports. Safe to re-run. Prefer the National Guide notebook if you want step-by-step national sections with inline EDA tables.
"""

N0_CODE = r"""from pathlib import Path
import os, sys, json, warnings
warnings.filterwarnings('ignore')

from IPython.display import display, HTML, Markdown, Image, IFrame

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
NAT_OUT.mkdir(parents=True, exist_ok=True)

SUMMARY_JSON = NAT_OUT / 'logs' / 'national_run_summary.json'
ATLAS_INDEX = NAT_OUT / 'maps' / 'html_atlas' / 'index.html'
REPORT_PATH = NAT_OUT / 'documents' / 'NFI_national_geopipeline_report.html'

print('NAT_ROOT', NAT_ROOT)
print('NAT_OUT', NAT_OUT)
print('prior run summary exists:', SUMMARY_JSON.exists())
print('atlas exists:', ATLAS_INDEX.exists())
print('report exists:', REPORT_PATH.exists())
"""

N1_MD = """## N1 · Run national pipeline (ingest, lattice, trees, shrubs, EDA, maps, HTML)

**User note:** Full country run. Set `SKIP_IF_PRODUCTS_EXIST = True` to reuse an existing `outputs_national_v5/` when you only want to refresh atlas HTML later (N3).
"""

N1_CODE = r"""SKIP_IF_PRODUCTS_EXIST = True  # set False to force a full recompute

have_core = SUMMARY_JSON.exists() and ATLAS_INDEX.exists() and REPORT_PATH.exists()
if SKIP_IF_PRODUCTS_EXIST and have_core:
    RS = json.loads(SUMMARY_JSON.read_text(encoding='utf-8'))
    NAT = {'run_summary': RS, 'skipped_rerun': True}
    print('Skipped full pipeline: core national products already present.')
    print('Set SKIP_IF_PRODUCTS_EXIST = False to recompute.')
else:
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
    display(Markdown('### SU universe by region'))
    display(pd.read_csv(by_region_csv).head(20))
if anc_csv.exists():
    import pandas as pd
    display(Markdown('### Ancillary pools (inventory only)'))
    display(pd.read_csv(anc_csv))
"""

N2_MD = """## N2 · Inspect national gates and sample figures

**User note:** Gate counts and a short figure gallery from `outputs_national_v5/`. Numbers come from the run summary / CSVs; nothing is invented here.
"""

N2_CODE = r"""import pandas as pd
from pathlib import Path

RS = NAT.get('run_summary') or json.loads(SUMMARY_JSON.read_text(encoding='utf-8'))
gate = RS.get('gate_tree_presence') or {}
gate_s = RS.get('gate_shrub_presence') or {}
print('Tree gate total_sus', gate.get('total_sus'), 'with_trees', gate.get('sus_with_trees'), 'zero', gate.get('sus_no_trees'))
print('Shrub gate total_sus', gate_s.get('total_sus'), 'with_shrubs', gate_s.get('sus_with_shrubs'), 'zero', gate_s.get('sus_no_shrubs'))
print('Lattice rows', RS.get('lattice_rows'), 'tree biomass rows', RS.get('n_tree_biomass_rows'), 'shrub biomass rows', RS.get('n_shrub_biomass_rows'))

su_metrics = NAT_OUT / 'validated' / 'national_su_biomass_sample.csv'
if su_metrics.exists():
    display(Markdown('### SU biomass sample (head)'))
    display(pd.read_csv(su_metrics).head(10))

fig_dir = NAT_OUT / 'figures' / 'national_eda'
map_dir = NAT_OUT / 'maps' / 'national'
them_dir = map_dir / 'thematic'
show = [
    fig_dir / 'univariate_trees_fv_national.png',
    fig_dir / 'bivariate_corr_pair_trees_national.png',
    fig_dir / 'univariate_shrubs_national.png',
    map_dir / 'map_national_plots.png',
    them_dir / 'thematic_land_use.png',
]
display(Markdown('### Selected national figures'))
for p in show:
    if p.exists():
        display(Markdown(f'**{p.name}**'))
        display(Image(filename=str(p)))
    else:
        print('missing', p)
"""

N3_MD = """## N3 · Thematic atlas with land-cover style cartography

**User note:** Rebuilds the dashboard atlas from existing thematic tables when available. Categorical themes use **fixed class colours** (same idea as land-cover legends): map points, legend swatches, and the donut/percent panel share one colour per class. Geometry modes: points, Voronoi, or overlay. Basemap: Esri / Google satellite.
"""

N3_CODE = r"""from nfi_national_atlas_dashboard import write_national_dashboard_atlas
from nfi_national_thematic_maps import produce_national_thematic_maps
from nfi_national_boundary import load_country, country_geojson
import pandas as pd

su_them = NAT_OUT / 'validated' / 'national_su_thematic_attributes.csv'
cat_path = NAT_OUT / 'maps' / 'national_thematic_catalog.csv'
vor_path = NAT_OUT / 'maps' / 'cartography' / 'su_voronoi_thiessen.geojson'

HTML_PRODUCTS = {}
if su_them.exists() and cat_path.exists():
    themes_df = pd.read_csv(su_them)
    catalog = pd.read_csv(cat_path)
    voronoi_fc = None
    if vor_path.exists():
        voronoi_fc = json.loads(vor_path.read_text(encoding='utf-8'))
    try:
        country_fc = country_geojson(load_country())
    except Exception as e:
        print('Country boundary skipped:', e)
        country_fc = None
    ATLAS_INDEX = write_national_dashboard_atlas(
        themes_df,
        NAT_OUT / 'maps' / 'html_atlas',
        catalog=catalog,
        voronoi_fc=voronoi_fc,
        country_fc=country_fc,
    )
    print('Atlas refreshed from existing thematic tables.')
else:
    print('Thematic tables missing: running produce_national_thematic_maps (heavier).')
    if NAT.get('tables') is None:
        NAT = run_national_pipeline(CFG, out_root=NAT_OUT)
    THEMATIC = produce_national_thematic_maps(
        tables=NAT['tables'],
        tree_m=NAT['tree_m'],
        shrub_m=NAT['shrub_m'],
        lattice=NAT['lattice'],
        plot=NAT['tables']['plot'],
        cfg=CFG,
        out_root=NAT_OUT,
    )
    ATLAS_INDEX = write_national_dashboard_atlas(
        THEMATIC['su_thematic'], NAT_OUT / 'maps' / 'html_atlas', catalog=THEMATIC['catalog']
    )
    HTML_PRODUCTS['interactive_maps'] = THEMATIC.get('interactive') or {}

REPORT_PATH = NAT_OUT / 'documents' / 'NFI_national_geopipeline_report.html'
HTML_PRODUCTS['atlas_index'] = str(ATLAS_INDEX)
HTML_PRODUCTS['html_report'] = str(REPORT_PATH)

display(Markdown('### Atlas portal'))
print(ATLAS_INDEX)
if cat_path.exists():
    display(Markdown('### Thematic catalog (head)'))
    display(pd.read_csv(cat_path).head(20))
uri = ATLAS_INDEX.resolve().as_uri()
display(HTML(
    '<div style="padding:12px;border:1px solid #d5ddd7;border-radius:10px;background:#e8f0e9;">'
    '<b>Land-cover style atlas</b><br/>'
    'Fixed class colours for land use, canopy, herbaceous, fire, env. problems, causative agents, tree/crown condition, region.<br/>'
    f'<a href="{uri}" target="_blank">Open interactive atlas</a></div>'
))
try:
    display(IFrame(src=uri, width='100%', height=560))
except Exception as e:
    print('IFrame embed skipped:', e)
"""

N4_MD = """## N4 · Open HTML deliverables

**User note:** Shareable products for the national process (methodology report + interactive atlas). Opens in the browser when running locally.
"""

N4_CODE = r"""import pandas as pd
import webbrowser

REPORT_PATH = Path(HTML_PRODUCTS.get('html_report') or NAT_OUT / 'documents' / 'NFI_national_geopipeline_report.html')
ATLAS_INDEX = Path(HTML_PRODUCTS.get('atlas_index') or NAT_OUT / 'maps' / 'html_atlas' / 'index.html')
imap = NAT_OUT / 'maps' / 'html_interactive'
INTERACTIVE = HTML_PRODUCTS.get('interactive_maps') or {}
if not INTERACTIVE and imap.exists():
    INTERACTIVE = {p.stem.replace('interactive_national_', ''): str(p) for p in imap.glob('interactive_national_*.html')}

links = [
    ('Methodology + results HTML report', REPORT_PATH),
    ('Interactive map atlas (Leaflet portal)', ATLAS_INDEX),
]
for name, path in list(INTERACTIVE.items())[:6]:
    links.append((f'Interactive map · {name}', Path(path)))

rows = []
html_bits = ['<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif;line-height:1.5">']
html_bits.append('<h3 style="color:#1b5e20;margin:0 0 8px">Open these HTML deliverables</h3>')
for label, path in links:
    path = Path(path)
    ok = path.exists()
    rows.append({'deliverable': label, 'exists': ok, 'bytes': path.stat().st_size if ok else 0, 'path': str(path)})
    if ok:
        uri = path.resolve().as_uri()
        html_bits.append(
            f'<p style="margin:8px 0"><a style="display:inline-block;padding:10px 14px;background:#14351c;color:#fff;'
            f'text-decoration:none;border-radius:8px;font-weight:600" href="{uri}" target="_blank">{label}</a>'
            f'<br/><code style="font-size:12px">{path}</code></p>'
        )
    else:
        html_bits.append(f'<p style="color:#a33">Missing: {label} ({path})</p>')
html_bits.append('</div>')
display(HTML(''.join(html_bits)))
display(pd.DataFrame(rows))

for path in (REPORT_PATH, ATLAS_INDEX):
    if path.exists():
        try:
            webbrowser.open(path.resolve().as_uri())
        except Exception as e:
            print('browser open skipped:', path, e)
"""

N5_MD = """## N5 · Scope reminder

| Layer | Coverage in this run |
| --- | --- |
| SU / plot tabular | Entire national cleansed master |
| Tree biomass (calc DOCX) | All SUs with eligible tree records |
| Shrub biomass (calc DOCX) | All SUs with eligible shrub records |
| Deadwood / litter / regen / veg | Count inventory only (no calc-doc equations) |
| Design-based Area_H totals | Only SUs with Asir or Makkah grid Area_H; others blocked |
| Atlas categorical colours | Fixed land-cover style palettes (not design-based area shares) |

See `outputs_national_v5/logs/national_run_summary.json`, `docs/04_national_pipeline.md`, and `docs/07_landcover_style_cartography.md`.

For the step-by-step national tutorial with inline uni/biv tables, use **`NFI_National_GeoPipeline_Guide_V5.ipynb`**.
"""


def main() -> None:
    nb = json.loads(NB.read_text(encoding="utf-8"))
    nb["cells"][0] = md(INTRO)

    part_c = [
        md(PART_C_MD0),
        md(N0_MD),
        code(N0_CODE),
        md(N1_MD),
        code(N1_CODE),
        md(N2_MD),
        code(N2_CODE),
        md(N3_MD),
        code(N3_CODE),
        md(N4_MD),
        code(N4_CODE),
        md(N5_MD),
    ]

    idx = None
    for i, c in enumerate(nb["cells"]):
        src = "".join(c.get("source") or [])
        if src.lstrip().startswith("# PART C"):
            idx = i
            break
    if idx is None:
        raise SystemExit("PART C marker not found")

    nb["cells"] = nb["cells"][:idx] + part_c
    NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Updated {NB.name}: {len(nb['cells'])} cells; Part C at {idx} ({len(part_c)} cells)")


if __name__ == "__main__":
    main()
