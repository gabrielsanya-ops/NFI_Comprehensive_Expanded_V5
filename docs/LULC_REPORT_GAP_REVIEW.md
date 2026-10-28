# Gap review: LULC_VALIDATION_REPORT.html

Source audited: `F:\1.KSA\1.Forest\10.NFI\10.LULC_Validation\LULC_VALIDATION_REPORT.html` (about 19 MB, dated 2026-10-11).

Compared against:
- Report content itself (including Appendix notes that content was removed)
- `PROCESS_AND_VALIDATION.md` (expected figures and accuracy tables)
- On-disk `figures/` and confusion/accuracy CSVs
- Calculation document scope (trees/shrubs) for V5 improvement needs

## What the report covers well

1. Objective and Final LULC decision rules (forest reserve priority, field Forest, inaccessible Level 2, ESA/ESRI match).
2. Office-point join method (SU/plot keys, EPSG:4326 office coords).
3. Interactive national validation map (Leaflet).
4. Forest reserved layers (FAO/NCVC, topology examples).
5. Earth Engine sampling method (ESA WorldCover + Aug 2024 dry NDVI).
6. Forest-focused headline counts (744 Final Forest, 163 inside reserve, etc.).
7. Share package list (CSV/XLSX/GPKG/reserves).
8. Level 2 catalog appendix.

## Explicit removals already stated in the HTML

These are not accidents. The report itself says they were cut:

| Location | Statement |
|---|---|
| Section 8 | "Omission/commission charts were removed." |
| Appendix | "Supporting multi-class charts were removed so the report stays focused on Forest accuracy." |
| Workflow blurb | "Accuracy checks focus on Forest only." |
| Section 7 title | "Results (Forest focus)" and "Multi-class LULC tallies are not the accuracy focus." |

## Missing from the report (but present on disk / in PROCESS)

These assets exist under `10.LULC_Validation` and are described in `PROCESS_AND_VALIDATION.md`, yet are **not** in the HTML:

### Accuracy / error matrices
- `figures/17_error_matrix_field_vs_final_lulc.png`
- `figures/18_error_matrices_compact.png`
- Compact OA / Cohen kappa tables (PROCESS: Field vs ESA 0.555/0.052; Field vs ESRI 0.381/0.085; Field vs Final LULC 0.662/0.505)
- Confusion CSVs (`confusion_field_vs_*.csv`, `error_matrices_compact/`)
- Producer/user accuracy, omission/commission tables (charts removed; numbers also absent from HTML body)

HTML keyword scan: **0** hits for `kappa`, `overall accuracy`, `error matrix`, `confusion matrix`.

### Core validation charts listed in PROCESS section 6
- Accepted vs imputed (`01_validation_true_false.png`)
- Validation rule distribution (`15_validation_rule.png`)
- Original field labels (`02_int_lucs_label_distribution.png`)
- New LCU / Final LULC distribution (`03_final_lulc_distribution.png`)
- ESA/ESRI correspondence (`06_rs_agreement_percent.png`)
- Dry NDVI by outcome (`05_ndvi_by_validation.png`)
- Level 2 replacements (`07_top_replacements.png`)
- Processing stack (`08_software_sources.png`)
- Simple workflow PNG (`16_workflow.png`) (a large workflow **slide** is embedded; the PROCESS PNG set is not)

### What IS embedded (9 images, all data-URIs)
1. Methodological workflow slide
2. National forest reserved by source
3-6. Topology correction examples (Al-Baha x2, Asir, Makkah)
7. Forest vs non-Forest by location/access
8-9. Forest accuracy donuts (inside reserve; outside vs global)

So the live report is **forest-topology + forest-accuracy heavy**, and **light on multi-class validation evidence**.

## Missing for a full NFI / calculation-document report

Not expected of the old LULC-only HTML, but missing if this report is the national NFI deliverable:

1. Tree biometric chain (BA, volume, AGB, BGB, carbon, CO2eq) from the Word calculation document.
2. Shrub allometry and shrub carbon.
3. Land-use proportion / area by SU (n plots / 5).
4. Joins of Trees / Shrubs / Regeneration / Dead wood / Litter / Vegetation cover to Final LULC.
5. Limitations, assumptions, and references sections.
6. Uncertainty language (sample vs design-based).
7. SEPAL mapping pathway (only a token mention; full path lives in `SEPAL_PIPELINE.md`).
8. Non-forest class results as first-class report content (currently sidelined).

## Bottom line

The HTML is a strong **Forest-priority LULC validation briefing**, not a complete multi-class accuracy report and not an inventory biomass report.

Largest report gaps to restore or add next:
1. Re-embed multi-class error matrices + OA/kappa (already computed on disk).
2. Re-embed PROCESS validation figures (accepted/imputed, rule mix, Final LULC distribution, NDVI, replacements).
3. Restore omission/commission (or equivalent producer/user accuracy) for Final LULC.
4. Add limitations / assumptions / references.
5. For V5 national NFI: add calculation-document tree/shrub sections linked to Final LULC.
