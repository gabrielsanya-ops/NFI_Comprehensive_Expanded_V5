# Workflow alignment: attached End-to-End Process Flow → national geopipeline

Source diagram: `KSA_NFI_GeoAI_Data_Preparation_Cursor/nfi_geoai_data_preparation/workflow.png`
(title: **KSA NFI GeoAI - End-to-End Process Flow**).

This note maps the attached 17-step Asir-oriented flow onto the **national** package
`12.NFI_Comprehensive_Expanded_V5`, using only computed facts from cleansed data and
`outputs_national_v5/logs/national_run_summary.json`.

## Data relook (cleansed tables)

| Table | Rows | Role |
| --- | ---: | --- |
| `nfi_of_ksa_program_su.xlsx` | 3671 | National SU LEFT master |
| `plot.xlsx` | 18355 | Plot rows (18354 distinct PLOT_UID) |
| `trees.xlsx` | 12732 | Tree stems |
| `shrubs_bushes.xlsx` | 4823 | Shrubs |
| `lucs1.xlsx` | 18360 | Land use / cover sample |
| `vegetation_cover.xlsx` | 18326 | Cover |
| `fire_evidence1.xlsx` | 4148 | Fire |
| `environmental_problems.xlsx` | 7977 | Env problems |
| `litter1.xlsx` | 5689 | Litter counts |
| `deadwood1.xlsx` | 244 | Deadwood counts |
| `regeneration1.xlsx` | 527 | Regen counts |
| `fauna.xlsx` | 664 | Fauna |
| `teams_members.xlsx` | 4061 | Teams |
| `reference_tbl.xlsx` | 148 | Reference |

Anti-clip rule (attached diagram, nationalized): never inner-join the SU universe to
trees only. LEFT master keeps all **3671** SUs and **18355** design plot slots.

## Gap map (before → after this phase)

| Step | Attached workflow | Prior national status | Enhancement |
| ---: | --- | --- | --- |
| 0 | Environment / StageStore | Present | Kept; StageStore snapshots extended |
| 1 | Ingest NFI + GIS | Present (national tables) | Kept |
| 2 | Area appropriation | Asir/Makkah Area_H only | Kept; blocked SUs logged |
| 3 | Anti-clip lattice | Present | Kept; asserted 18355 rows |
| 4-5 | Gates and regions | Present | Kept |
| 6-7 | Clean / coord QA | Partial | **Added** national plot coordinate QA CSV |
| 8-9 | Population / stat QA | Missingness + uni tables | **Added** row-conservation ledger |
| 10 | Exhaustive EDA | Present | Kept |
| 11 | Integrity scorecard | Asir-only helper existed | **Added** national clip vs anti-clip scorecard |
| 12-13 | Maps / atlas | Present (32 interactive themes) | Kept |
| 14 | Spatial QA | Thin | **Added** spatial_qa_national.json |
| 15 | LiDAR evidence gate | Module existed; not gated in runner | **Added** evidence adequacy JSON (no field overwrite) |
| 16 | GeoAI protocol | Protocol table only in Part A | **Added** protocol CSV + optional SU-blocked height prototype |
| 17 | Export package | HTML/CSV heavy | **Added** GeoPackage plots + export manifest |

## Implementation entry points

- Module: `src/nfi_workflow_e2e.py`
- CLI refresh: `python run_workflow_e2e.py`
- Wired into: `run_national_pipeline()` after biomass/EDA tables, before HTML products

## Policies retained from the diagram

1. Solid flow is the main path; red dashed loop = augment features when LiDAR evidence is not adequate.
2. Imputation OFF for remote products overwriting field measurements.
3. Model outputs are prototypes with uncertainty proxies, not observations.
4. Biomass/carbon remain **provisional sample metrics** until design weights and full Area_H exist.

## Open questions (unchanged)

See `docs/ASSUMPTIONS_AND_OPEN_QUESTIONS.md` and the run summary `assumptions` list.
