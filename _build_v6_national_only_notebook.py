# -*- coding: utf-8 -*-
"""Build NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb as NATIONAL-ONLY (entire KSA).

No Asir 430-SU Gate case study. Archive hybrid copy lives under archive/.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_NB = ROOT / "NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb"


def md(text: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [ln + "\n" for ln in text.strip("\n").split("\n")],
    }


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [ln + "\n" for ln in text.strip("\n").split("\n")],
    }


def cells() -> list:
    c: list = []

    c.append(
        md(
            """# KSA National Forest Inventory (NFI)
# Comprehensive Expanded Pipeline V6 · **Entire Kingdom**

**Scope:** the full national tabular universe (all regions in the cleansed SU master).  
**Not in scope:** Asir-only 430-SU GIS Gate case study (archived separately).

| Item | Value |
| --- | --- |
| Frame | National SU master × 5-plot design lattice |
| Typical scale | ~3,671 sampling units · 13 regions · ~18,355 plot slots |
| Biomass | Calc DOCX trees **and** shrubs (provisional sample metrics) |
| Outputs | `outputs_national_v5/` |
| Interactive atlas | `outputs_national_v5/maps/html_atlas/index.html` |
| HTML report | `outputs_national_v5/documents/NFI_national_geopipeline_report.html` |
| Colab | [Open this notebook](https://colab.research.google.com/github/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5/blob/master/NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb) |
| CLI twin | `python run_national_pipeline.py` |

### Run order (Colab)
1. Connect runtime → run **bootstrap**
2. Run **Section 0** (imports)
3. Either step through Sections 1 to 12, or jump to **Section 10 (one-shot)**
4. Finish with **Section 11** checklist and **Section 12** open links
"""
        )
    )

    c.append(
        md(
            """## Colab / portable bootstrap

Run once. Mounts Drive if available, otherwise clones the public GitHub package (includes `data/`), installs requirements, and sets the working directory.
"""
        )
    )
    c.append(
        code(
            r"""from pathlib import Path
import os, sys, subprocess, shutil, warnings
warnings.filterwarnings("ignore")

IN_COLAB = Path("/content").exists() and not Path(r"F:/1.KSA").exists()
REPO_URL = "https://github.com/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5.git"
CLONE_DIR = Path("/content/NFI_Comprehensive_Expanded_V5")
ALIASES = ["NFI_Comprehensive_Expanded_V5", "12.NFI_Comprehensive_Expanded_V5"]

def looks_like_root(p: Path) -> bool:
    return (p / "config.yaml").exists() and (p / "src").exists() and (p / "data" / "cleansed").exists()

if IN_COLAB:
    try:
        from google.colab import drive
        try:
            drive.mount("/content/drive", force_remount=False)
        except Exception as e:
            print("Drive mount skipped/failed:", e)
    except Exception:
        pass

candidates = []
for name in ALIASES:
    candidates += [
        Path("/content/drive/MyDrive") / name,
        Path("/content/drive/MyDrive/33.Projects") / name,
        Path("/content") / name,
        Path(r"F:/1.KSA/29.NFI") / name,
        Path(r"F:/1.KSA/29.NFI/12.NFI_Comprehensive_Expanded_V5"),
    ]
candidates += [Path.cwd(), CLONE_DIR]

ROOT = next((p.resolve() for p in candidates if p.exists() and looks_like_root(p)), None)
if ROOT is None and IN_COLAB:
    print("Cloning package from GitHub...")
    if CLONE_DIR.exists():
        shutil.rmtree(CLONE_DIR, ignore_errors=True)
    subprocess.check_call(["git", "clone", "--depth", "1", REPO_URL, str(CLONE_DIR)])
    ROOT = CLONE_DIR.resolve()

if ROOT is None or not looks_like_root(ROOT):
    raise FileNotFoundError("Could not locate NFI_Comprehensive_Expanded_V5 with data/cleansed.")

os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

if IN_COLAB:
    req = ROOT / "requirements.txt"
    print("Installing requirements (Colab)...")
    cmd = [sys.executable, "-m", "pip", "install", "-q"]
    cmd += ["-r", str(req)] if req.exists() else [
        "pandas", "numpy", "openpyxl", "pyarrow", "geopandas", "shapely", "pyogrio",
        "matplotlib", "scipy", "scikit-learn", "statsmodels", "pyyaml", "seaborn", "missingno",
    ]
    subprocess.check_call(cmd)

print("IN_COLAB", IN_COLAB)
print("ROOT", ROOT)
print("national SU workbook", (ROOT / "data" / "cleansed" / "nfi_of_ksa_program_su.xlsx").exists())
print("cleansed files", len(list((ROOT / "data" / "cleansed").glob("*.xlsx"))))
"""
        )
    )

    c.append(
        md(
            """<a id="s0"></a>
## 0 · National environment

Loads config, creates `outputs_national_v5/`, imports national modules. Entire-country constants only.
"""
        )
    )
    c.append(
        code(
            r"""from pathlib import Path
import os, sys, json, warnings
warnings.filterwarnings("ignore")

from IPython.display import display, Markdown, Image, HTML, IFrame
import pandas as pd
import numpy as np

def _find_root() -> Path:
    for name in ("ROOT",):
        if name in globals() and Path(globals()[name]).exists():
            p = Path(globals()[name])
            if (p / "config.yaml").exists():
                return p.resolve()
    for p in [
        Path.cwd(),
        Path("/content/NFI_Comprehensive_Expanded_V5"),
        Path(r"F:/1.KSA/29.NFI/12.NFI_Comprehensive_Expanded_V5"),
    ]:
        if (p / "config.yaml").exists() and (p / "src").exists():
            return p.resolve()
    raise FileNotFoundError("Run the bootstrap cell first.")

ROOT = _find_root()
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

from nfi_audit import load_config, resolve_portable_paths, ensure_output_dirs
from nfi_calc_biomass import (
    FORM_FACTOR, WOOD_DENSITY, BEF, ROOT_SHOOT, CARBON_FRACTION, CO2EQ_FACTOR,
    CONVERSION_FACTOR_HA, TREE_EXCLUDE, SHRUB_EXCLUDE,
)
from nfi_national_pipeline import (
    load_national_tables, national_universe_summary, build_national_plot_lattice,
    national_gate_tree_presence, national_shrub_gate, attach_regional_gis_area,
    national_tree_biomass, national_shrub_biomass, aggregate_plot_su_metrics,
    national_ancillary_inventory, national_land_use_proportions,
    write_national_eda_figures, write_national_maps, run_national_pipeline,
)
from nfi_national_thematic_maps import produce_national_thematic_maps
from nfi_national_atlas_dashboard import write_national_dashboard_atlas
from nfi_national_html import write_national_html_report
from nfi_datascience import univariate_numeric, bivariate_numeric

CFG = resolve_portable_paths(load_config(ROOT / "config.yaml"), ROOT)
OUT = Path(CFG["paths"].get("output_national_root", ROOT / "outputs_national_v5"))
if not OUT.is_absolute():
    OUT = ROOT / OUT
OUT = Path(ensure_output_dirs({**CFG, "paths": {**CFG["paths"], "output_root": str(OUT)}}))
HTML_PRODUCTS = {}
RS = int(CFG["project"].get("random_seed", 42))

print("ROOT", ROOT)
print("OUT ", OUT)
print("plots_per_su_design", CFG["project"]["plots_per_su_design"])
print("random_seed", RS)
"""
        )
    )

    c.append(
        md(
            """<a id="s1"></a>
## 1 · Official constants (calc DOCX)

Tree chain: BA → Volume (FF=0.65) → AGB (WD×BEF) → BGB (×0.28) → Carbon (×0.47) → CO2eq (×3.67).  
Per-ha sample factor CF=10. Shrub CO2eq left blank (not stated in shrub section).
"""
        )
    )
    c.append(
        code(
            r"""constants = {
    "form_factor": FORM_FACTOR,
    "wood_density": WOOD_DENSITY,
    "bef": BEF,
    "root_shoot": ROOT_SHOOT,
    "carbon_fraction": CARBON_FRACTION,
    "co2eq_factor": CO2EQ_FACTOR,
    "conversion_factor_ha": CONVERSION_FACTOR_HA,
    "tree_exclude": list(TREE_EXCLUDE),
    "shrub_exclude": list(SHRUB_EXCLUDE),
}
display(Markdown("### Active national constants"))
display(constants)
"""
        )
    )

    c.append(
        md(
            """<a id="s2"></a>
## 2 · National ingest (all regions)

Reads every cleansed national table. LEFT master = full SU workbook for the Kingdom.
"""
        )
    )
    c.append(
        code(
            r"""TABLES = load_national_tables(CFG)
su, plot = TABLES["su"], TABLES["plot"]
trees, shrubs = TABLES["trees"], TABLES["shrubs"]
SUMMARY = national_universe_summary(su, plot, CFG)

display(Markdown("### National universe"))
display({
    "n_su": SUMMARY["n_su"],
    "n_regions": SUMMARY["n_regions"],
    "n_plot_rows": SUMMARY["n_plot_rows"],
    "n_plot_uid": SUMMARY["n_plot_uid"],
    "expected_lattice": SUMMARY["n_su"] * int(CFG["project"]["plots_per_su_design"]),
})
display(Markdown("### SU count by region (entire Kingdom)"))
display(SUMMARY["by_region"])
(SUMMARY["by_region"]).to_csv(OUT / "audit" / "national_su_by_region.csv", index=False)
"""
        )
    )

    c.append(
        md(
            """<a id="s3"></a>
## 3 · Anti-clip national plot lattice (SU × 5)

Keeps every national SU in the LEFT frame (zero-tree SUs retained).
"""
        )
    )
    c.append(
        code(
            r"""LATTICE = build_national_plot_lattice(su, trees, CFG)
expected = SUMMARY["n_su"] * int(CFG["project"]["plots_per_su_design"])
print("lattice_rows", len(LATTICE), "expected", expected, "match", len(LATTICE) == expected)
LATTICE.to_csv(OUT / "validated" / "national_plot_lattice.csv", index=False)
display(LATTICE.head(12))
"""
        )
    )

    c.append(
        md(
            """<a id="s4"></a>
## 4 · National presence gates (trees and shrubs)

Country-wide presence / absence counts. Not the Asir 240/190 baked Gate package.
"""
        )
    )
    c.append(
        code(
            r"""GATE_T = national_gate_tree_presence(su, trees)
GATE_S = national_shrub_gate(su, shrubs)
display(Markdown("### Tree presence gate (national)"))
display({k: GATE_T[k] for k in ("total_sus", "sus_with_trees", "sus_no_trees") if k in GATE_T})
display(Markdown("### Shrub presence gate (national)"))
display({k: GATE_S[k] for k in ("total_sus", "sus_with_shrubs", "sus_no_shrubs") if k in GATE_S})

# Region composition for the whole country
by_reg = SUMMARY["by_region"].copy()
display(Markdown("### Regions in the national master"))
display(by_reg)

# Simple national SU board (all regions)
import matplotlib.pyplot as plt
fig_dir = OUT / "figures" / "national_regions"
fig_dir.mkdir(parents=True, exist_ok=True)
reg_col = next((c for c in by_reg.columns if "region" in c.lower() or c.lower() in ("reg_e", "region_en")), by_reg.columns[0])
n_col = next((c for c in ("n_su", "n", "count") if c in by_reg.columns), None)
if n_col is None:
    n_col = by_reg.select_dtypes("number").columns[0]
plot_df = by_reg.sort_values(n_col, ascending=True)
fig, ax = plt.subplots(figsize=(9, 6), dpi=130)
ax.barh(plot_df[reg_col].astype(str), plot_df[n_col], color="#1b5e20")
ax.set_xlabel("Sampling units (SU)")
ax.set_title("National NFI: SU count by region (entire Kingdom)")
for y, v in enumerate(plot_df[n_col].tolist()):
    ax.text(v + max(plot_df[n_col]) * 0.01, y, f"{int(v)}", va="center", fontsize=9)
fig.tight_layout()
fig_path = fig_dir / "national_su_by_region.png"
fig.savefig(fig_path, dpi=160)
plt.show()
plt.close(fig)
print("wrote", fig_path)
"""
        )
    )

    c.append(
        md(
            """<a id="s5"></a>
## 5 · Optional GIS Area_H (Asir + Makkah grids only)

Area expansion stays blocked elsewhere (`AREA_BLOCKED_NO_GRID`). National presence and biomass below do **not** depend on Area_H.
"""
        )
    )
    c.append(
        code(
            r"""SU_AREA = attach_regional_gis_area(su, CFG)
SU_AREA.to_csv(OUT / "validated" / "national_su_with_optional_area.csv", index=False)
AREA_COV = SU_AREA["area_status"].value_counts(dropna=False).rename("n").reset_index()
AREA_COV.columns = ["area_status", "n"]
display(AREA_COV)
"""
        )
    )

    c.append(
        md(
            """<a id="s6"></a>
## 6 · Tree biomass (national, calc DOCX)

Provisional sample metrics for every eligible tree record in the national cleansed table.
"""
        )
    )
    c.append(
        code(
            r"""TREE_M = national_tree_biomass(trees, CFG)
TREE_M.to_csv(OUT / "validated" / "national_trees_biomass_provisional.csv", index=False)
print("tree biomass rows", len(TREE_M))
cols = [c for c in ["basal_area_m2", "volume_m3", "agb_mg", "bgb_mg", "carbon_mg_provisional", "co2eq_mg"] if c in TREE_M.columns]
display(TREE_M[cols].describe().T if cols else TREE_M.head())
"""
        )
    )

    c.append(
        md(
            """<a id="s7"></a>
## 7 · Shrub biomass (national, calc DOCX)
"""
        )
    )
    c.append(
        code(
            r"""SHRUB_M = national_shrub_biomass(shrubs)
SHRUB_M.to_csv(OUT / "validated" / "national_shrubs_biomass_provisional.csv", index=False)
print("shrub biomass rows", len(SHRUB_M))
cols = [c for c in ["agb_mg", "bgb_mg", "total_biomass_mg", "carbon_mg_provisional"] if c in SHRUB_M.columns]
display(SHRUB_M[cols].describe().T if cols else SHRUB_M.head())
"""
        )
    )

    c.append(
        md(
            """<a id="s8"></a>
## 8 · Ancillary pools + land-use proportions (national)

Deadwood / litter / regen / vegetation: inventory counts only (no invented biomass). LULC proportions use calc-doc style plot shares where the LULC product exists.
"""
        )
    )
    c.append(
        code(
            r"""ANCILLARY = national_ancillary_inventory(TABLES, OUT / "audit")
display(ANCILLARY)

LU = national_land_use_proportions(TABLES.get("lucs"), CFG, OUT / "validated") if "lucs" in TABLES else pd.DataFrame()
if len(LU):
    display(Markdown("### Land-use proportions by SU (head)"))
    display(LU.head(12))
else:
    print("No lucs table in national load; LULC proportions skipped.")
"""
        )
    )

    c.append(
        md(
            """<a id="s9"></a>
## 9 · National univariate / bivariate EDA + static maps

All figures are national (not Asir-clipped).
"""
        )
    )
    c.append(
        code(
            r"""ROLLED = aggregate_plot_su_metrics(TREE_M, SHRUB_M, LATTICE)
ROLLED["plot_metrics"].to_csv(OUT / "validated" / "national_plot_biomass_sample.csv", index=False)
ROLLED["su_metrics"].to_csv(OUT / "validated" / "national_su_biomass_sample.csv", index=False)
display(Markdown("### SU biomass sample (national head)"))
display(ROLLED["su_metrics"].head(12))

FIG_PATHS = write_national_eda_figures(trees, TREE_M, SHRUB_M, OUT / "figures" / "national_eda", CFG)
display(Markdown("### EDA figures"))
for name, path in list(FIG_PATHS.items())[:8]:
    print(name, "->", path)
    if path and Path(path).exists():
        display(Image(filename=str(path)))

MAP_PATHS = write_national_maps(plot, CFG, OUT / "maps" / "national", ROLLED["su_metrics"])
display(Markdown("### Static national maps"))
for name, path in MAP_PATHS.items():
    print(name, "->", path)
    if path and Path(path).exists():
        display(Image(filename=str(path)))
"""
        )
    )

    c.append(
        md(
            """<a id="s10"></a>
## 10 · One-shot national pipeline (optional shortcut)

Equivalent to `python run_national_pipeline.py`. Rebuilds validated tables, EDA, maps, interactive HTML, atlas, and report for the **entire Kingdom**.
"""
        )
    )
    c.append(
        code(
            r"""NAT = run_national_pipeline(CFG, out_root=OUT)
RS = NAT["run_summary"]
TABLES = NAT["tables"]
su, plot, trees, shrubs = TABLES["su"], TABLES["plot"], TABLES["trees"], TABLES["shrubs"]
SUMMARY, LATTICE = NAT["summary"], NAT["lattice"]
GATE_T, GATE_S = NAT["gate"], NAT["gate_shrub"]
SU_AREA = NAT["su_area"]
TREE_M, SHRUB_M = NAT["tree_m"], NAT["shrub_m"]
ROLLED, ANCILLARY = NAT["rolled"], NAT["ancillary"]
FIG_PATHS, MAP_PATHS = NAT["fig_paths"], NAT["map_paths"]
HTML_PRODUCTS = NAT.get("html_products") or {}

display(Markdown("### Run summary (computed keys)"))
display({k: RS[k] for k in RS if k not in ("figures", "maps", "assumptions", "interactive_maps")})
print("assumptions:")
for a in RS.get("assumptions", []):
    print(" -", a)
"""
        )
    )

    c.append(
        md(
            """<a id="s11"></a>
## 11 · Thematic atlas (land-cover style) · entire Kingdom

Fixed class colours for categorical themes; points / Voronoi; satellite basemap; all national SUs.
"""
        )
    )
    c.append(
        code(
            r"""THEMATIC = produce_national_thematic_maps(
    tables=TABLES,
    tree_m=TREE_M,
    shrub_m=SHRUB_M,
    lattice=LATTICE,
    plot=plot,
    cfg=CFG,
    out_root=OUT,
)
ATLAS_INDEX = write_national_dashboard_atlas(
    THEMATIC["su_thematic"], OUT / "maps" / "html_atlas", catalog=THEMATIC["catalog"]
)
HTML_PRODUCTS["atlas_index"] = str(ATLAS_INDEX)
HTML_PRODUCTS["interactive_maps"] = THEMATIC.get("interactive") or {}
HTML_PRODUCTS["static_thematic_maps"] = THEMATIC.get("static") or {}

display(Markdown("### Thematic catalog (head)"))
display(THEMATIC["catalog"].head(20))
print("Atlas:", ATLAS_INDEX)
print("Interactive themes:", len(HTML_PRODUCTS["interactive_maps"]))

# Show a few national thematic PNGs
shown = 0
for theme, path in (THEMATIC.get("static") or {}).items():
    if shown >= 6:
        break
    p = Path(path)
    if p.exists():
        display(Markdown(f"**{theme}**"))
        display(Image(filename=str(p)))
        shown += 1

try:
    display(IFrame(src=Path(ATLAS_INDEX).resolve().as_uri(), width="100%", height=560))
except Exception as e:
    print("IFrame skipped:", e)
"""
        )
    )

    c.append(
        md(
            """<a id="s12"></a>
## 12 · HTML methodology report + open deliverables
"""
        )
    )
    c.append(
        code(
            r"""guide_summary = {
    "scope": "national_tabular_universe_entire_kingdom",
    "n_su": SUMMARY["n_su"],
    "n_regions": SUMMARY["n_regions"],
    "n_plot_rows": SUMMARY["n_plot_rows"],
    "n_plot_uid": SUMMARY["n_plot_uid"],
    "lattice_rows": int(len(LATTICE)),
    "n_tree_biomass_rows": int(len(TREE_M)),
    "n_shrub_biomass_rows": int(len(SHRUB_M)),
    "gis_area_attached_sus": int((SU_AREA["area_status"] == "GIS_AREA_ATTACHED").sum()) if "area_status" in SU_AREA.columns else None,
    "gis_area_blocked_sus": int((SU_AREA["area_status"] == "AREA_BLOCKED_NO_GRID").sum()) if "area_status" in SU_AREA.columns else None,
    "design_based_estimates": False,
    "carbon_label": "provisional",
    "output_root": str(OUT),
    "gate_tree_presence": {k: GATE_T[k] for k in ("total_sus", "sus_with_trees", "sus_no_trees") if k in GATE_T},
    "gate_shrub_presence": {k: GATE_S[k] for k in ("total_sus", "sus_with_shrubs", "sus_no_shrubs") if k in GATE_S},
    "assumptions": RS.get("assumptions") if "RS" in globals() else [
        "National frame = entire cleansed SU master (all regions).",
        "Asir 430-SU Gate package is out of scope in this V6 Improved notebook.",
        "Biomass/carbon are provisional sample metrics, not design-based inventory totals.",
        "Area_H expansion blocked except Asir/Makkah grids.",
    ],
}
AREA_COV = SU_AREA["area_status"].value_counts(dropna=False).rename("n").reset_index()
AREA_COV.columns = ["area_status", "n"]
REPORT_PATH = write_national_html_report(
    out_path=OUT / "documents" / "NFI_national_geopipeline_report.html",
    run_summary=guide_summary,
    by_region=SUMMARY["by_region"],
    ancillary=ANCILLARY,
    area_cov=AREA_COV,
    gate=GATE_T,
    gate_shrub=GATE_S,
    fig_paths=FIG_PATHS,
    map_paths=MAP_PATHS,
    interactive_paths=HTML_PRODUCTS.get("interactive_maps") or {},
    atlas_index=HTML_PRODUCTS.get("atlas_index"),
)
HTML_PRODUCTS["html_report"] = str(REPORT_PATH)
(OUT / "documents" / "national_html_manifest.json").write_text(
    json.dumps(HTML_PRODUCTS, indent=2), encoding="utf-8"
)

ATLAS_INDEX = Path(HTML_PRODUCTS.get("atlas_index") or OUT / "maps" / "html_atlas" / "index.html")
links = [
    ("Methodology + results HTML report", Path(REPORT_PATH)),
    ("Interactive map atlas (entire Kingdom)", ATLAS_INDEX),
]
imap = OUT / "maps" / "html_interactive"
if imap.exists():
    for p in sorted(imap.glob("interactive_national_*.html"))[:8]:
        links.append((f"Interactive · {p.stem.replace('interactive_national_', '')}", p))

bits = ['<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif;line-height:1.5">']
bits.append('<h3 style="color:#1b5e20;margin:0 0 8px">Open national HTML deliverables</h3>')
rows = []
for label, path in links:
    ok = path.exists()
    rows.append({"deliverable": label, "exists": ok, "bytes": path.stat().st_size if ok else 0, "path": str(path)})
    if ok:
        bits.append(
            f'<p style="margin:8px 0"><a style="display:inline-block;padding:10px 14px;background:#14351c;color:#fff;'
            f'text-decoration:none;border-radius:8px;font-weight:600" href="{path.resolve().as_uri()}" target="_blank">{label}</a>'
            f'<br/><code style="font-size:12px">{path}</code></p>'
        )
bits.append("</div>")
display(HTML("".join(bits)))
display(pd.DataFrame(rows))

expected = [
    OUT / "logs" / "national_run_summary.json",
    OUT / "validated" / "national_plot_lattice.csv",
    OUT / "validated" / "national_trees_biomass_provisional.csv",
    OUT / "validated" / "national_shrubs_biomass_provisional.csv",
    OUT / "audit" / "national_su_by_region.csv",
    OUT / "documents" / "NFI_national_geopipeline_report.html",
    OUT / "maps" / "html_atlas" / "index.html",
]
check = pd.DataFrame([
    {"path": str(p.relative_to(OUT)), "exists": p.exists(), "bytes": p.stat().st_size if p.exists() else 0}
    for p in expected
])
display(Markdown("### Output checklist (national)"))
display(check)
print("All required present:", bool(check["exists"].all()))
"""
        )
    )

    c.append(
        md(
            """<a id="s13"></a>
## 13 · Assumptions and open questions

1. Frame = entire national cleansed SU master (all regions). Asir 430-SU Gate analysis is **out of scope** here.
2. Shrub allometric `log` treated as natural log (base not stated in calc DOCX).
3. Design-based national totals remain blocked until weights and approved variance estimators exist.
4. `Area_H` attaches only where Asir/Makkah grids are present; other SUs stay `AREA_BLOCKED_NO_GRID`.
5. Deadwood / litter / regeneration / vegetation cover: counts only until official equations are supplied.
6. Atlas categorical percents are SU class frequencies, not land-area shares.
7. Biomass and carbon remain **provisional** sample metrics.

See `docs/04_national_pipeline.md` and `docs/07_landcover_style_cartography.md`.
"""
        )
    )

    return c


def main() -> None:
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": cells(),
    }
    OUT_NB.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Wrote", OUT_NB)
    print("cells", len(nb["cells"]))


if __name__ == "__main__":
    main()
