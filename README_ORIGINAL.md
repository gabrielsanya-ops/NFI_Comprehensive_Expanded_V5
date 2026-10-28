# KSA NFI GeoAI - Data Preparation & Linkage Recovery

## Purpose
Audit and reconstruct the National Forest Inventory data foundation before any forest estimates,
remote-sensing extraction, GeoAI training, or biomass/carbon calculations.

The workflow is deliberately **audit-first** and implements the Aseer **Validation Gate 1**
(zero-tree Sampling Units) and **Validation Gate 2** (plot completeness) packages.

## Wired local paths
| Role | Path |
|------|------|
| Cleansed Excel tables | `F:\1.KSA\32.NFI\Clensed Data` |
| Asir shapefiles | `F:\1.KSA\32.NFI\Shapefile\Asir NFI Shapefiles` |
| Makkah shapefiles | `F:\1.KSA\32.NFI\Shapefile\Makkah NFI Shapefiles` |
| Validation Word docs | `F:\1.KSA\32.NFI\documents` |
| PhD reference | `C:\Users\Admin\Phd` |
| Audit outputs | `C:\Users\Admin\NFI_GeoAI_Data_Preparation_Outputs` |

Edit `config.yaml` if drive letters change.

## Validation rules (baked into the notebook - no `.docx` reload at runtime)
Gate 1 / Gate 2 targets and field-classification requirements from the Word packages are
encoded in the notebook markdown + `config.yaml` → `aseer_gate_expected`.

- Gate 1: 430 / 240 / 190 SU survey-status classification
- Gate 2: 2150 / 656 / 544 plot completeness classification

### Anti-clip (GeoPandas)
Do **not** clip/inner-join Trees → GIS (drops the 190 no-tree SUs).  
Use `anti_clip_su_tree_frame()`: LEFT join tree counts onto `Asir_SU_Final` and flag Gate-1 SUs.

## Run
```powershell
cd <project-folder>
C:\Python313\python.exe -m notebook NFI_GeoAI_Data_Preparation.ipynb
```

**Run All** - Excel + shapefiles only; Word files are not opened.

## Critical rule
Do **not** manually clip an Excel table and then use the clipped table as the authoritative source.
Spatial subsets are derived products. The master record universe is preserved and every subset is
linked back through stable identifiers (`SU_UID`, `PLOT_UID`) and reconciliation tables.

## Main outputs
Under `C:\Users\Admin\NFI_GeoAI_Data_Preparation_Outputs`:
- `audit/file_registry.csv`, `table_load_log.csv`, `linkage_*.csv`, `row_conservation.csv`
- `gates/gate1_*.csv`, `gates/gate2_*.csv`, `gates/document_target_reconciliation.csv`
- `documents/*.txt` extracts of the Word validation packages
- `validated/aseer_*` analytical stubs with gate-status columns (records labelled, not dropped)

No source file is overwritten.
