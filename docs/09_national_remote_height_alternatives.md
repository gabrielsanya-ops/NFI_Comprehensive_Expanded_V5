# National remote height evidence (entire Kingdom)

## Decision

For **country-wide** NFI work, footprint GEDI is **not** the primary layer.
GEDI is sparse and historically Asir-oriented in this workspace. National evidence
uses wall-to-wall alternatives that cover all regions in the SU master.

## Products used

| Product | Coverage | Role |
| --- | --- | --- |
| Meta / WRI CHMv2 (Source Cooperative COGs) | Global / Kingdom | Canopy height at every national SU centroid |
| OpenTopoData SRTM30m (fallback: Open-Meteo) | Global / Kingdom | Terrain covariate at every national SU centroid |
| GEDI L2A footprints | Sparse tracks | Optional supplement only (not required for adequacy) |

Citations are written into `logs/national_remote_height_evidence.json`.

## Policy

- Scope: **national_entire_kingdom** (`asir_only: false`)
- Field `tree_height` / SU `mean_height_m` are never overwritten
- Imputation OFF for remote → field
- Disparities are reported nationally and by region when both field and CHM exist

## How to run

```text
python run_national_remote_height.py
```

Optional stratified cap (still all regions):

```text
python run_national_remote_height.py --max-chm-points 1500
```

## Outputs

- `validated/national_su_meta_chm_v2.csv`
- `validated/national_su_elevation_open_meteo.csv`
- `audit/national_chm_field_disparity_by_region.csv`
- `audit/lidar_evidence_gate.json` (national adequacy)
- `logs/national_remote_height_evidence.json`
