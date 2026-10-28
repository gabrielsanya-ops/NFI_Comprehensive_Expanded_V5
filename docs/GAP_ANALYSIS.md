# Gap analysis

## A. Gaps in the original V4 notebook (relative to HTML LULC report)

1. No ingest of `lucs_office_validated_esa_esri_ndvi.csv` national Final LULC product.
2. No reproduction of LULC validation rule counts / Final LULC distributions from the report.
3. No multi-class confusion matrices / OA for field vs ESA / ESRI / Final LULC.
4. No national office-point LULC acceptance map (report Leaflet map content).
5. Forest-reserve priority narrative exists in HTML more completely than in V4 (V4 is Asir GeoAI / GEDI focused).

## B. Gaps in the HTML report (relative to notebook + PROCESS)

1. Multi-class charts and omission/commission panels removed from HTML body (Appendix / Section 8 statements).
2. PROCESS-listed figures 01-16 and error-matrix figures 17-18 not linked in HTML (assets remain on disk).
3. No tree/shrub biomass or calculation-document formulas.
4. No limitations / assumptions / references sections.
5. No SU-blocked predictive modelling or GEDI height validation (those live in the notebook).

## C. Gaps in both (methodological)

1. Design-based estimators (weights / inclusion probabilities / SU area) unavailable → national stock totals blocked.
2. Full ESDA stack (LISA maps, spatial regression) only partially present; needs packages + justified use.
3. Causal identification not supported by current design documentation.
4. Shrub allometric log base unspecified in Word document.

## D. How V5 closes gaps

| Gap | V5 response |
|---|---|
| HTML accuracy removed from body | E3 reloads confusion/accuracy CSVs + PNGs |
| National LULC absent from notebook | E2-E4 ingest + figures + maps |
| Word calc biomass absent | E6-E8 |
| Missingness depth | E5 |
| ESDA depth | E10 conditional Moran/Gi* |
| ML optimism gap explicit | E11 |
| Docs / audit | COMPARISON_MATRIX, this file, METHODOLOGY_INVENTORY, CHANGELOG |
