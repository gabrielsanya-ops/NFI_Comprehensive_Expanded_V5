# Methodology inventory

## Preserved from V4_Refined (Part A)

1. Environment, configuration, StageStore
2. Tabular ingest and Asir SU GIS universe (430)
3. Area appropriation / policy checks
4. Anti-clip SU x plot lattice
5. Gate 1 and Gate 2 vs baked targets
6. Regional / governorate roll-ups
7. Data cleaning and value QC
8. Ready clean deliverables
9. Field vs office coordinate cross-check
10. Analytical-population gate
11. Statistical validation gate
12. EDA statistical figure pack (`nfi_datascience`)
13. Integrity scorecard (clip/pivot vs anti-clip)
14. Cartography / interactive maps
15. Beautiful HTML atlas
16. Spatial left-join QA
17. GEDI L2A LiDAR validation (+ optional download)
18. GeoAI modelling protocol (frozen before modelling)
19. StageStore inventory
20. Row-conservation ledger / exports
21. Executive summary / scientific safeguard

Supporting modules preserved: `nfi_audit`, `nfi_datascience`, `nfi_area_maps`, `nfi_beautiful_maps`, `nfi_gedi_l2a`, `nfi_imputation_candidates`, `nfi_lidar_global`.

## Added in V5 expansion (Part B)

1. National LULC Validation ingest and key numbers (`nfi_lulc_html`)
2. Validation rule counts and Final LULC distributions
3. Confusion / accuracy CSV reintegration + OA computation
4. Restored error-matrix PNG display
5. Accepted vs updated and national point maps
6. Variable-type classification and missingness tables
7. Median-imputation sensitivity benchmarks; optional MICE
8. Calculation-document tree biomass/carbon chain (`nfi_calc_biomass`)
9. National anti-clip SU tree density
10. Land-use proportions by SU from Final LULC
11. Shrub provisional allometry
12. Pearson/Spearman + PCA on derived metrics
13. Conditional Moran / Gi* ESDA (`nfi_esda_expanded`)
14. Random vs SU-blocked CV optimism gap
15. Additional national thematic maps
16. Expansion run summary with explicit limitations

## Conditionally skipped (documented, not forced)

- Spatial lag/error regression, spatial panels, Bayesian hierarchical models, survival analysis: require stronger design/assumptions than currently available.
- Design-based national totals: blocked without weights/SU area.
- Official use of imputed heights for carbon: blocked by policy.
