# outputs_national_v5

National-first KSA NFI geopipeline outputs (entire country tabular universe).

## Reproduce

```text
python run_national_pipeline.py
```

## Layout

| Folder | Contents |
| --- | --- |
| `audit/` | Region counts, missingness, area coverage, ancillary pool inventory, univariate tables |
| `validated/` | Anti-clip lattice, tree/shrub biomass, plot/SU sample roll-ups, LU proportions, optional Area_H |
| `gates/` | National zero-tree and zero-shrub SU lists and summary gates |
| `figures/national_eda/` | Univariate and bivariate charts (trees and shrubs) |
| `figures/national_ds/` | DS report pack: flowchart, missingness, KDE suites, thematic bars (fire, agents, env) |
| `maps/national/` | Static PNG maps |
| `maps/html_interactive/` | Interactive Leaflet thematic HTML maps (32 themes incl. causative agent / fire / env) |
| `maps/national/thematic/` | Static PNG companions for thematic maps |
| `maps/cartography/` | Voronoi GeoJSON + Voronoi choropleth PNGs + hexbin surfaces |
| `maps/national_thematic_catalog.csv` | Theme catalog (id, category, written flags) |
| `maps/html_atlas/index.html` | Dashboard atlas: theme KPIs, admin filters, points / Voronoi / overlay modes |
| `validated/national_su_thematic_attributes.csv` | SU-level attributes feeding the thematic maps |
| `documents/NFI_national_geopipeline_report.html` | Professional data-science HTML report |
| `logs/national_run_summary.json` | Exact computed counts and assumptions for this run |
| `stages/` | StageStore snapshots |

## Labels

All biomass and carbon products are **provisional sample metrics**. Design-based national totals remain blocked where `Area_H` is missing and where design weights are unavailable.
