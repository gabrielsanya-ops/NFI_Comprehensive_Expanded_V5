# 12.NFI_Comprehensive_Expanded_V5

Comprehensive expansion of the original GeoAI notebook. **Not a replacement with a smaller demo.**

## Where are the notebooks?

**Start here (national user guide):**  
`NFI_National_GeoPipeline_Guide_V5.ipynb`  
Clear section structure, user notes before each step, entire-country frame.

**Archive / deep-dive (Part A Asir + Part B LULC + Part C):**  
`NFI_GeoAI_Comprehensive_Expanded_V5.ipynb`  
Preserves the full V4_Refined analytical depth.

Rebuild the guide anytime: `python _build_national_guide_notebook.py`

Foundation preserved from:  
`F:\1.KSA\29.NFI\KSA_NFI_GeoAI_Data_Preparation_Cursor\nfi_geoai_data_preparation\NFI_GeoAI_Data_Preparation_V4_Refined.ipynb`

## How to run (national-first)

Entire-country tabular universe (all regions in the SU master):

```bash
pip install -r requirements.txt
python run_national_pipeline.py
# outputs -> outputs_national_v5/
python -m pytest tests -q
```

Or open `NFI_National_GeoPipeline_Guide_V5.ipynb` and run Sections 0 to 17 (or Section 16 one-shot).

HTML products after a run:
- Report: `outputs_national_v5/documents/NFI_national_geopipeline_report.html`
- Interactive atlas: `outputs_national_v5/maps/html_atlas/index.html`
- Leaflet maps: `outputs_national_v5/maps/html_interactive/`

## Docs

- `../docs/04_national_pipeline.md` (national phase)
- `docs/COMPARISON_MATRIX.md`
- `docs/GAP_ANALYSIS.md`
- `docs/METHODOLOGY_INVENTORY.md`
- `docs/CHANGELOG_V5.md`
- `docs/ASSUMPTIONS_AND_OPEN_QUESTIONS.md`
- `docs/00_ORIGINAL_NOTEBOOK_INVENTORY.md`
- `docs/LULC_REPORT_GAP_REVIEW.md`

## Supersedes

The thin notebook under `11.NFI_LULC_Biomass_Improved\` was an incorrect reduction of scope. Use this V5 package instead.
