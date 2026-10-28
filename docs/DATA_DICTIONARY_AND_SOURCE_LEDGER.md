# Data dictionary and source ledger (key fields)

## Sources

| Source | Path | Role |
|---|---|---|
| Cleansed NFI Excel | `F:\1.KSA\29.NFI\Clensed Data\*.xlsx` | SU, plot, trees, shrubs, LUCS, etc. |
| Asir GIS | `F:\1.KSA\29.NFI\Shapefile\Asir NFI Shapefiles\` | Gate frame 430 SU / grid |
| LULC validated | `data/lulc/lucs_office_validated_esa_esri_ndvi.csv` | Final LULC / rules / office coords |
| Calc document | `data/docs/NFI_ KSA Calculation_Trees&shrubs.docx` | Biomass/carbon formulas |
| HTML report | `...\10.LULC_Validation\LULC_VALIDATION_REPORT.html` | Complementary methods/outputs |
| Original notebook | `...\NFI_GeoAI_Data_Preparation_V4_Refined.ipynb` | Analytical foundation |

## Key fields (selected)

| Field | Table | Meaning |
|---|---|---|
| su_no | su / lulc | Sampling unit id |
| plot_id1 / plot_no | plot / lulc | Plot id within SU |
| tree_dbh | trees | DBH (cm implied by BA divisor 40000) |
| tree_height | trees | Height (m) |
| final_lulc | lulc | Validated Final LULC / New LCU |
| validation_true | lulc | Accepted field label vs updated |
| validation_rule | lulc | Decision rule id |
| inside_forest_reserved | lulc | Priority-1 Forest flag |
| lon, lat | lulc | Office coordinates EPSG:4326 |

Full column profiling is produced at runtime into `outputs/expansion/tables/types_*.csv` and `missingness_*.csv`.
