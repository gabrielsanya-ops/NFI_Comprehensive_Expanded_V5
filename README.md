# 12.NFI_Comprehensive_Expanded_V5

Comprehensive expansion of the original GeoAI notebook. **Not a replacement with a smaller demo.**

## Where is the revised notebook?

`F:\1.KSA\29.NFI\12.NFI_Comprehensive_Expanded_V5\NFI_GeoAI_Comprehensive_Expanded_V5.ipynb`

Foundation preserved from:

`F:\1.KSA\29.NFI\KSA_NFI_GeoAI_Data_Preparation_Cursor\nfi_geoai_data_preparation\NFI_GeoAI_Data_Preparation_V4_Refined.ipynb`

## How to run

1. Open the V5 notebook in Jupyter / VS Code / Colab (upload package or clone).
2. Run **Part A** cells (preserved V4 workflow). Requires Asir shapefiles + cleansed Excel under paths in `config.yaml`.
3. Run **Part B** expansion cells (LULC HTML + Word calc + ESDA/ML extras).

```bash
pip install -r requirements.txt
# optional for Moran/Gi*:
pip install libpysal esda
python -m pytest tests -q
```

## Docs

- `docs/COMPARISON_MATRIX.md`
- `docs/GAP_ANALYSIS.md`
- `docs/METHODOLOGY_INVENTORY.md`
- `docs/CHANGELOG_V5.md`
- `docs/ASSUMPTIONS_AND_OPEN_QUESTIONS.md`
- `docs/00_ORIGINAL_NOTEBOOK_INVENTORY.md`
- `docs/LULC_REPORT_GAP_REVIEW.md`

## Supersedes

The thin notebook under `11.NFI_LULC_Biomass_Improved\` was an incorrect reduction of scope. Use this V5 package instead.
