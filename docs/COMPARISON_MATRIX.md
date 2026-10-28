# Comparison matrix: original notebook vs HTML report vs expanded V5

Evidence sources:
- Original: `NFI_GeoAI_Data_Preparation_V4_Refined.ipynb` (48 cells; inventory in `00_ORIGINAL_NOTEBOOK_INVENTORY.md`)
- HTML: `LULC_VALIDATION_REPORT.html` + `PROCESS_AND_VALIDATION.md` + on-disk figures/CSVs
- Thin wrong revision (for contrast only): `11.NFI_LULC_Biomass_Improved/NFI_LULC_Biomass_Improved_Colab.ipynb` (~20 KB)

| Analytical component | Original V4 notebook | HTML report | Final expanded V5 | Action taken |
|---|---|---|---|---|
| Research design / gates | Strong (Gates 1/2, analytical population, modelling protocol) | Decision rules for Final LULC / Forest priority | Preserve V4 + add Phase A note linking LULC estimands | Preserve and expand |
| Data engineering / StageStore | Strong (ingest, keys, cleaning, ledger) | Join of lucs1+plot office coords | Preserve V4; retarget config to `29.NFI` | Preserve and expand |
| Missingness by data type | Present (statistical QA + imputation policy; no remote overwrite) | Limited | Add type classification, benchmarks, optional MICE | Expand comprehensively |
| Univariate analysis | Strong EDA figure pack | Key numbers; Forest focus | Preserve V4 + LULC distributions + tree metric describe | Preserve and enhance |
| Bivariate analysis | Correlation / EDA suite | ESA/ESRI correspondence (partially removed from HTML body) | Preserve V4 + Pearson/Spearman on calc metrics | Preserve and enhance |
| Multivariate analysis | Feature engineering + modelling protocol | Weak | Add PCA on tree metrics | Expand |
| Exploratory spatial analysis | Spatial join QA; limited Moran mentions | National Leaflet map; topology | Add Global Moran / Gi* (conditional) | Expand |
| Univariate maps | Leaflet atlas + static maps (Asir) | National validation map | Preserve atlas + national acceptance/carbon maps | Expand |
| Bivariate maps | Limited | Forest vs access visuals | Add acceptance choropleth-style point map | Add or enhance |
| Error matrices / OA / kappa | Not LULC multi-class focus | **Removed from HTML body** but CSVs/PNGs on disk | Re-integrate confusion CSVs + OA + PNGs | Restore from HTML assets |
| Statistical inference | QA + robust metrics; protocol | Rule counts | Preserve; document design-based BLOCKED | Expand as applicable |
| Advanced / ML modelling | SU-grouped protocol, no circular leakage emphasis in V4 | None | Add explicit random vs GroupKFold optimism gap | Integrate |
| LiDAR / GEDI | Strong (V3/V4) | None | Preserve all GEDI cells | Preserve |
| Tree/shrub biomass (Word calc) | Weak / provisional mentions | None | Full calc-doc chain + shrub equation | Newly introduced |
| Land-use proportions | Not calc-doc section 5 | Final LULC classes | Add n/5 proportions by SU | Newly introduced |
| Validation and sensitivity | Integrity scorecard; imputation audits | Forest accuracy donuts | Preserve + missingness sensitivity + CV gap | Strengthen |
| Reporting and reproducibility | Executive summary cell; StageStore | Share package section | Expansion summary JSON + docs package | Improve |

## Explicit non-shrinkage check

| Artifact | Approx size / cells | Role |
|---|---|---|
| V4_Refined original | ~20 MB / 48 cells | Foundation (copied, outputs stripped, sources retained) |
| Thin Colab V5 (superseded) | ~20 KB / 23 cells | Incorrect reduction; not the deliverable |
| Comprehensive Expanded V5 | V4 cells + expansion block | Required deliverable |
