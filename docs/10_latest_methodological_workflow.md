# Latest workable scientific methodological workflow (national)

Companion to the plate:
`outputs_national_v5/documents/NFI_National_Methodological_Workflow_Latest.jpg`

Scope: **entire Kingdom** (`asir_only: false`). Frame: 3671 SUs, 18355 anti-clip plot slots, 13 regions.

```mermaid
flowchart TB
  subgraph P1["Phase 1 · Data engineering"]
    S0["0 Environment + StageStore"]
    S1["1 National ingest<br/>SU · plot · trees · shrubs · ancillary"]
    S2["2 Area_H attach<br/>Asir/Makkah grids only · else blocked"]
    S3["3 Anti-clip lattice<br/>SU × 5 LEFT master"]
    S4["4-5 Gates + region roll-ups<br/>trees · shrubs"]
    S6["6-7 Clean ledger + coord QA<br/>field vs office"]
    S0 --> S1 --> S2 --> S3 --> S4 --> S6
  end

  subgraph P2["Phase 2 · Science, EDA, maps"]
    S8["8-9 Population + stat QA<br/>flag outliers · do not delete"]
    S10["10 Exhaustive EDA"]
    S11["11 Integrity scorecard<br/>clip/pivot vs anti-clip"]
    S12["12-13 National atlas + themes"]
    S14["14 Spatial QA<br/>lattice / coordinate coverage"]
    S8 --> S10 --> S11 --> S12 --> S14
  end

  subgraph P3["Phase 3 · Evidence, AI, export"]
    S15["15 National remote height<br/>Meta CHMv2 + SRTM elevation<br/>GEDI optional / sparse"]
    DEC{"Evidence adequate?"}
    S16["16 GeoAI protocol<br/>SU-blocked CV prototypes<br/>no field overwrite"]
    S17["17 StageStore + ledger<br/>GPKG export package"]
    S15 --> DEC
    DEC -->|yes| S16 --> S17
    DEC -->|no · augment| S8
  end

  S6 --> S8
  S14 --> S15

  subgraph OUT["Deliverables"]
    D1["HTML atlas + report"]
    D2["Analytics tables / figures"]
    D3["Remote height disparities"]
    D4["Model prototypes + uncertainty"]
    D5["Export GPKG / CSV"]
  end
  S17 --> D1
  S17 --> D2
  S17 --> D3
  S17 --> D4
  S17 --> D5
```

## Hard rules (current implementation)

1. Anti-clip: never inner-join the SU universe to trees only.
2. Imputation OFF for remote products overwriting field measurements.
3. Biomass / carbon remain **provisional sample metrics**.
4. National remote height evidence uses wall-to-wall Meta CHMv2 + SRTM elevation (3,671 SUs); GEDI is not required for adequacy.
5. Design-based national totals stay blocked until weights and full Area_H exist.

## Entry points

- Full national run: `python run_national_pipeline.py`
- Workflow refresh: `python run_workflow_e2e.py`
- Remote height: `python run_national_remote_height.py`
