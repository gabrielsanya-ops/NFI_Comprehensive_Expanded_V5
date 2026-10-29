# Colab package and data layout

After Section 0 bootstrap (or `git clone`), the working directory is:

```text
NFI_Comprehensive_Expanded_V5/
├── NFI_National_GeoPipeline_Guide_V5.ipynb   <- start here (national user guide)
├── NFI_GeoAI_Comprehensive_Expanded_V5.ipynb <- archive Part A/B deep-dive
├── config.yaml
├── requirements.txt
├── run_national_pipeline.py
├── OPEN_IN_COLAB.md
├── README.md
├── src/                          # Python modules
│   ├── nfi_national_pipeline.py
│   ├── nfi_national_html.py
│   ├── nfi_calc_biomass.py
│   ├── nfi_audit.py
│   └── ...
├── data/                         # associated inputs (do not edit in place)
│   ├── cleansed/                 # national Excel tables (SU, plot, trees, shrubs, ...)
│   ├── shapefile/
│   │   ├── Asir_NFI_Shapefiles/
│   │   └── Makkah_NFI_Shapefiles/
│   ├── lulc/                     # validated LULC CSV + confusion matrices
│   └── docs/                     # calc DOCX + validation Word docs + extract
├── docs/                         # methodology notes
├── tests/
├── outputs/                      # Part A/B outputs (created on run)
└── outputs_national_v5/          # national pipeline outputs (created on run)
    ├── audit/
    ├── validated/
    ├── gates/
    ├── figures/national_eda/
    ├── maps/
    │   ├── national/             # PNG
    │   ├── html_interactive/     # Leaflet HTML
    │   └── html_atlas/           # atlas portal index.html
    ├── documents/                # HTML report
    └── logs/
```

## Open in Colab

https://colab.research.google.com/github/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5/blob/master/NFI_National_GeoPipeline_Guide_V5.ipynb

Repo: https://github.com/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5
