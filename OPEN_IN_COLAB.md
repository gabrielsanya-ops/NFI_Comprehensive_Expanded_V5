# Open in Colab

## National user-guide notebook (preferred)

https://colab.research.google.com/github/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5/blob/master/NFI_National_GeoPipeline_Guide_V5.ipynb

Repo (auto-cloned by the Colab bootstrap cell if Drive is empty; includes `data/`):
https://github.com/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5

Folder layout after bootstrap: see `docs/COLAB_DATA_LAYOUT.md`.

Archive deep-dive gist (Part A/B):
https://colab.research.google.com/gist/gabrielsanya-ops/c98d2445f50b3781b7ab3e17007df532

Local notebooks:
- **User guide (start here):** `NFI_National_GeoPipeline_Guide_V5.ipynb`
- Archive deep-dive: `NFI_GeoAI_Comprehensive_Expanded_V5.ipynb`

## Run order on Colab (national guide)
1. Open the Colab link above → Runtime → Connect
2. Run **Colab bootstrap** (clones package + prints `data/` tree)
3. Run **Section 0** imports
4. Either run **Sections 2 to 15** step-by-step, or jump to **Section 16** one-shot
5. Finish with **Section 17** output checklist
6. Download / open `outputs_national_v5/documents/NFI_national_geopipeline_report.html` and `maps/html_atlas/index.html`

National CLI (local or after clone):
`python run_national_pipeline.py`
