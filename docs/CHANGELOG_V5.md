# CHANGELOG V5 - Comprehensive Expanded Pipeline

## Preserved

- Full source of `NFI_GeoAI_Data_Preparation_V4_Refined.ipynb` (all markdown/code cells).
- Entire `src/` analytical library from the GeoAI Data Preparation project.
- Asir Gate 1/2 logic, anti-clip philosophy, GEDI protocol, no remote height overwrite.

## Modified

- `config.yaml` retargeted from missing `F:\1.KSA\32.NFI` paths to `F:\1.KSA\29.NFI`.
- `output_root` set under this package (`...\12.NFI_Comprehensive_Expanded_V5\outputs`).
- Notebook outputs stripped on copy to keep the expanded file maintainable; analytical source retained.

## Added

- Expansion Part B cells (LULC HTML analyses, Word calc biomass, missingness, ESDA, maps, ML gap).
- Modules: `nfi_lulc_html.py`, `nfi_calc_biomass.py`, `nfi_missingness_expanded.py`, `nfi_esda_expanded.py`.
- Docs: comparison matrix, gap analysis, methodology inventory, assumptions, this changelog.
- LULC validated CSV + confusion/accuracy assets + calc document.
- **Part C national-first geopipeline** (`src/nfi_national_pipeline.py`, `run_national_pipeline.py`, `apply_shrub_metrics`, `outputs_national_v5/`, notebook N0-N3). Frame = entire national SU master (3671 SUs / 18355 lattice plots / 13 regions). Tree + shrub calc-doc biomass; ancillary pools inventoried without invented equations; Area_H only where Asir/Makkah grids exist.
- **User-guide notebook** `NFI_National_GeoPipeline_Guide_V5.ipynb` (sections 0-18 + appendices, user notes and TOC). Builder `_build_national_guide_notebook.py`. Archive `NFI_GeoAI_Comprehensive_Expanded_V5.ipynb` kept intact.
- **National HTML products** via `src/nfi_national_html.py`: interactive Leaflet maps (`maps/html_interactive/`), atlas portal (`maps/html_atlas/index.html`), shareable report (`documents/NFI_national_geopipeline_report.html`). Wired into `run_national_pipeline` and guide Sections 14-15.

## Conditionally excluded / not silently dropped

- Methods that need unsupported packages or design weights are coded to **skip with reason**, not deleted from the analytical plan.
- The thin `11.NFI_LULC_Biomass_Improved` Colab notebook is **superseded** (was an incorrect reduction).

## Not done in this revision (open)

- Re-embedding every PROCESS figure 01-16 into HTML report itself (notebook restores key accuracy products).
- Full interactive Leaflet national atlas parity with the HTML report map (static national maps added; HTML atlas remains Asir-focused from V4).
- Design-based estimators (await weights/SU area).
