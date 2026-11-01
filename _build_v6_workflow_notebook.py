# -*- coding: utf-8 -*-
"""Rebuild NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb around the
latest 17-step national End-to-End methodological workflow (entire Kingdom).
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_NB = ROOT / "NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb"
ARCHIVE = ROOT / "archive"


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

    c.append(md("""# KSA National Forest Inventory (NFI)
# Comprehensive Expanded Pipeline V6 · **Entire Kingdom**

Implements the latest workable scientific methodological workflow
(`docs/10_latest_methodological_workflow.md`):

| Phase | Steps | Focus |
| --- | --- | --- |
| **1 Data engineering** | 0 to 7 | Ingest, Area_H, anti-clip lattice, gates, coord QA |
| **2 Science / EDA / maps** | 8 to 14 | Population QA, EDA, integrity scorecard, atlas, spatial QA |
| **3 Evidence / AI / export** | 15 to 17 | National Meta CHMv2 + SRTM elevation, GeoAI protocol, GPKG |

**Scope:** full national SU master (all regions). **Not in scope:** Asir-only 430-SU Gate case study.

| Item | Value |
| --- | --- |
| Frame | National SU master × 5-plot anti-clip lattice |
| Typical scale | ~3,671 SUs · 13 regions · ~18,355 plot slots |
| Remote height | Meta CHMv2 + SRTM elevation (Kingdom-wide; GEDI optional) |
| Biomass | Calc DOCX trees and shrubs (**provisional** sample metrics) |
| Outputs | `outputs_national_v5/` |
| Workflow plate | `outputs_national_v5/documents/NFI_National_Methodological_Workflow_Latest.jpg` |
| CLI twins | `run_national_pipeline.py` · `run_workflow_e2e.py` · `run_national_remote_height.py` |

### Hard rules
1. Anti-clip: never inner-join the SU universe to trees only.
2. Imputation OFF for remote → field overwrite.
3. Carbon / biomass remain provisional until design weights exist.
4. `asir_only = false` for remote height evidence.

### Run order
1. Bootstrap → **W0** environment
2. Either step **W1 to W17**, or run **One-shot** then refresh atlas / HTML
3. Finish with deliverables checklist
"""))

    # Bootstrap
    c.append(md("""## Colab / portable bootstrap

Run once. Prefers a dedicated work disk (`D:/NFI_DISK.json`) so outputs can use the full free volume. On Colab: mounts Drive or clones GitHub.
"""))
    c.append(code(r"""from pathlib import Path
import os, sys, subprocess, shutil, warnings
warnings.filterwarnings("ignore")

IN_COLAB = Path("/content").exists() and not Path(r"F:/1.KSA").exists()
REPO_URL = "https://github.com/gabrielsanya-ops/NFI_Comprehensive_Expanded_V5.git"
CLONE_DIR = Path("/content/NFI_Comprehensive_Expanded_V5")
ALIASES = [
    "NFI_Comprehensive_Expanded_V5",
    "12.NFI_Comprehensive_Expanded_V5",
]

def looks_like_root(p: Path) -> bool:
    return (p / "config.yaml").exists() and (p / "src").exists() and (p / "data" / "cleansed").exists()

def resolve_work_disk():
    env = os.environ.get("NFI_WORK_DISK", "").strip()
    if env:
        d = Path(env)
        return d if d.exists() else None
    for letter in ("D", "E"):
        root = Path(f"{letter}:/")
        if root.exists() and (root / "NFI_DISK.json").exists():
            return root
    return None

WORK_DISK = resolve_work_disk()

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
if WORK_DISK is not None:
    candidates += [
        WORK_DISK / "NFI_Comprehensive_Expanded_V5",
        WORK_DISK / "12.NFI_Comprehensive_Expanded_V5",
    ]
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

if WORK_DISK is not None:
    os.environ["NFI_OUTPUT_NATIONAL_ROOT"] = str((WORK_DISK / "outputs_national_v5").resolve())

if IN_COLAB:
    req = ROOT / "requirements.txt"
    print("Installing requirements (Colab)...")
    cmd = [sys.executable, "-m", "pip", "install", "-q"]
    cmd += ["-r", str(req)] if req.exists() else [
        "pandas", "numpy", "openpyxl", "pyarrow", "geopandas", "shapely", "pyogrio",
        "matplotlib", "scipy", "scikit-learn", "statsmodels", "pyyaml", "seaborn", "missingno",
        "rasterio", "requests",
    ]
    subprocess.check_call(cmd)

print("IN_COLAB", IN_COLAB)
print("WORK_DISK", WORK_DISK)
print("ROOT", ROOT)
print("NFI_OUTPUT_NATIONAL_ROOT", os.environ.get("NFI_OUTPUT_NATIONAL_ROOT"))
print("national SU workbook", (ROOT / "data" / "cleansed" / "nfi_of_ksa_program_su.xlsx").exists())
print("cleansed files", len(list((ROOT / "data" / "cleansed").glob("*.xlsx"))))
"""))

    # W0
    c.append(md("""---
# PHASE 1 · Data engineering
<a id="w0"></a>
## W0 · Environment, StageStore, workflow catalog
"""))
    c.append(code(r"""from pathlib import Path
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
        Path(r"D:/NFI_Comprehensive_Expanded_V5"),
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

from nfi_audit import load_config, resolve_portable_paths, ensure_output_dirs, StageStore, plot_coordinate_qa
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
from nfi_datascience import univariate_numeric, bivariate_numeric, missingness_report
from nfi_workflow_e2e import (
    workflow_catalog, run_workflow_enhancements, national_integrity_scorecard,
    row_conservation_ledger, spatial_qa_national, lidar_evidence_gate,
    geoai_protocol_bundle, export_vector_package,
)
from nfi_national_remote_height import run_national_remote_height_evidence

CFG = resolve_portable_paths(load_config(ROOT / "config.yaml"), ROOT)
_env_out = os.environ.get("NFI_OUTPUT_NATIONAL_ROOT", "").strip()
if _env_out:
    OUT = Path(_env_out)
elif Path(r"D:/NFI_DISK.json").exists():
    OUT = Path(r"D:/outputs_national_v5")
else:
    OUT = Path(CFG["paths"].get("output_national_root", ROOT / "outputs_national_v5"))
    if not OUT.is_absolute():
        OUT = ROOT / OUT
OUT = Path(ensure_output_dirs({**CFG, "paths": {**CFG["paths"], "output_root": str(OUT)}}))
STAGES = StageStore(OUT)
HTML_PRODUCTS = {}
WF = {}
RS_SEED = int(CFG["project"].get("random_seed", 42))

CAT = workflow_catalog()
CAT.to_csv(OUT / "audit" / "workflow_e2e_catalog.csv", index=False)
display(Markdown("### 17-step workflow catalog (nationalized)"))
display(CAT)
plate = OUT / "documents" / "NFI_National_Methodological_Workflow_Latest.jpg"
if plate.exists():
    display(Markdown("### Methodological plate"))
    display(Image(filename=str(plate)))
print("ROOT", ROOT)
print("OUT ", OUT)
print("random_seed", RS_SEED)
"""))

    # W1 constants + ingest
    c.append(md("""<a id="w1"></a>
## W1 · Official constants + national ingest (all regions)

Calc DOCX tree chain: BA → Volume (FF=0.65) → AGB → BGB → C → CO2eq. CF=10. Shrub CO2eq blank if not stated.
"""))
    c.append(code(r"""constants = {
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

TABLES = load_national_tables(CFG)
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
SUMMARY["by_region"].to_csv(OUT / "audit" / "national_su_by_region.csv", index=False)
STAGES.save("W01_ingest", "by_region", SUMMARY["by_region"], note="National SU counts by region")
"""))

    # W2 area
    c.append(md("""<a id="w2"></a>
## W2 · Area appropriation (grids where available)

`Area_H` attaches only for Asir/Makkah grids. Other SUs remain `AREA_BLOCKED_NO_GRID`. Presence and biomass do not depend on Area_H.
"""))
    c.append(code(r"""SU_AREA = attach_regional_gis_area(su, CFG)
SU_AREA.to_csv(OUT / "validated" / "national_su_with_optional_area.csv", index=False)
AREA_COV = SU_AREA["area_status"].value_counts(dropna=False).rename("n").reset_index()
AREA_COV.columns = ["area_status", "n"]
AREA_COV.to_csv(OUT / "audit" / "national_area_coverage.csv", index=False)
display(AREA_COV)
"""))

    # W3 lattice
    c.append(md("""<a id="w3"></a>
## W3 · Anti-clip national plot lattice (SU × 5)

LEFT master keeps every national SU. Zero-tree slots stay visible.
"""))
    c.append(code(r"""LATTICE = build_national_plot_lattice(su, trees, CFG)
expected = SUMMARY["n_su"] * int(CFG["project"]["plots_per_su_design"])
assert len(LATTICE) == expected, f"lattice {len(LATTICE)} != expected {expected}"
LATTICE.to_csv(OUT / "validated" / "national_plot_lattice.csv", index=False)
print("lattice_rows", len(LATTICE), "zero_tree_slots", int((~LATTICE["has_tree_record"]).sum()))
display(LATTICE.head(12))
STAGES.save("W03_lattice", "lattice_head", LATTICE.head(5000), note="Anti-clip lattice sample")
"""))

    # W4-5 gates
    c.append(md("""<a id="w4"></a>
## W4 to W5 · Presence gates + region roll-ups

Country-wide tree/shrub presence. Not the Asir 240/190 baked Gate package.
"""))
    c.append(code(r"""GATE_T = national_gate_tree_presence(su, trees)
GATE_S = national_shrub_gate(su, shrubs)
pd.DataFrame([{k: GATE_T[k] for k in ("total_sus", "sus_with_trees", "sus_no_trees")}]).to_csv(
    OUT / "gates" / "national_gate_tree_presence.csv", index=False
)
pd.DataFrame([{k: GATE_S[k] for k in ("total_sus", "sus_with_shrubs", "sus_no_shrubs")}]).to_csv(
    OUT / "gates" / "national_gate_shrub_presence.csv", index=False
)
pd.DataFrame({"SU_UID": GATE_T["zero_tree_su_uids"]}).to_csv(OUT / "gates" / "national_zero_tree_su_uids.csv", index=False)
pd.DataFrame({"SU_UID": GATE_S["zero_shrub_su_uids"]}).to_csv(OUT / "gates" / "national_zero_shrub_su_uids.csv", index=False)
display(Markdown("### Tree gate"))
display({k: GATE_T[k] for k in ("total_sus", "sus_with_trees", "sus_no_trees")})
display(Markdown("### Shrub gate"))
display({k: GATE_S[k] for k in ("total_sus", "sus_with_shrubs", "sus_no_shrubs")})

import matplotlib.pyplot as plt
fig_dir = OUT / "figures" / "national_regions"
fig_dir.mkdir(parents=True, exist_ok=True)
by_reg = SUMMARY["by_region"].copy()
reg_col = next((c for c in by_reg.columns if "region" in c.lower()), by_reg.columns[0])
n_col = next((c for c in ("n_su", "n", "count") if c in by_reg.columns), by_reg.select_dtypes("number").columns[0])
plot_df = by_reg.sort_values(n_col, ascending=True)
fig, ax = plt.subplots(figsize=(9, 6), dpi=130)
ax.barh(plot_df[reg_col].astype(str), plot_df[n_col], color="#1b5e20")
ax.set_xlabel("Sampling units (SU)")
ax.set_title("National NFI: SU count by region (entire Kingdom)")
fig.tight_layout()
fig_path = fig_dir / "national_su_by_region.png"
fig.savefig(fig_path, dpi=160)
plt.show(); plt.close(fig)
print("wrote", fig_path)
"""))

    # W6-7 clean + coord QA + biomass
    c.append(md("""<a id="w6"></a>
## W6 to W7 · Biomass (calc DOCX) + field/office coordinate QA

Tree and shrub provisional sample metrics. Coordinate QA flags displacement; does not delete rows.
"""))
    c.append(code(r"""TREE_M = national_tree_biomass(trees, CFG)
SHRUB_M = national_shrub_biomass(shrubs)
TREE_M.to_csv(OUT / "validated" / "national_trees_biomass_provisional.csv", index=False)
SHRUB_M.to_csv(OUT / "validated" / "national_shrubs_biomass_provisional.csv", index=False)
print("tree biomass rows", len(TREE_M), "shrub biomass rows", len(SHRUB_M))
cols_t = [c for c in ["basal_area_m2", "volume_m3", "agb_mg", "bgb_mg", "carbon_mg_provisional", "co2eq_mg"] if c in TREE_M.columns]
display(TREE_M[cols_t].describe().T if cols_t else TREE_M.head())

COORD_QA = plot_coordinate_qa(plot, CFG)
COORD_QA.to_csv(OUT / "audit" / "national_plot_coordinate_qa.csv", index=False)
display(Markdown("### Coordinate QA summary"))
num = COORD_QA.select_dtypes("number")
display(num.describe().T.head(20) if len(num.columns) else COORD_QA.head())

ANCILLARY = national_ancillary_inventory(TABLES, OUT / "audit")
display(ANCILLARY)
LU = national_land_use_proportions(TABLES.get("lucs"), CFG, OUT / "validated") if "lucs" in TABLES else pd.DataFrame()
if len(LU):
    display(Markdown("### Land-use proportions (head)"))
    display(LU.head(10))
"""))

    # Phase 2
    c.append(md("""---
# PHASE 2 · Science, EDA and maps
<a id="w8"></a>
## W8 to W10 · Population QA, missingness, exhaustive EDA
"""))
    c.append(code(r"""ROLLED = aggregate_plot_su_metrics(TREE_M, SHRUB_M, LATTICE)
ROLLED["plot_metrics"].to_csv(OUT / "validated" / "national_plot_biomass_sample.csv", index=False)
ROLLED["su_metrics"].to_csv(OUT / "validated" / "national_su_biomass_sample.csv", index=False)

LEDGER = row_conservation_ledger(TABLES, LATTICE, TREE_M, SHRUB_M, GATE_T, GATE_S)
LEDGER.to_csv(OUT / "audit" / "row_conservation_ledger.csv", index=False)
display(Markdown("### Row-conservation ledger"))
display(LEDGER)

miss_t = missingness_report(trees, "national_trees")
miss_s = missingness_report(shrubs, "national_shrubs")
miss_t.to_csv(OUT / "audit" / "missingness_national_trees.csv", index=False)
miss_s.to_csv(OUT / "audit" / "missingness_national_shrubs.csv", index=False)
display(Markdown("### Missingness (trees head)"))
display(miss_t.head(12))

FIG_PATHS = write_national_eda_figures(trees, TREE_M, SHRUB_M, OUT / "figures" / "national_eda", CFG)
MAP_PATHS = write_national_maps(plot, CFG, OUT / "maps" / "national", ROLLED["su_metrics"])
display(Markdown("### Sample EDA / map products"))
for name, path in list(FIG_PATHS.items())[:4] + list(MAP_PATHS.items())[:2]:
    print(name, "->", path)
    if path and Path(path).exists():
        display(Image(filename=str(path)))
"""))

    c.append(md("""<a id="w11"></a>
## W11 · Integrity scorecard (clip/pivot vs anti-clip)
"""))
    c.append(code(r"""COMPARISON, SCORE = national_integrity_scorecard(
    su, trees, LATTICE, GATE_T, int(CFG["project"]["plots_per_su_design"])
)
COMPARISON.to_csv(OUT / "audit" / "integrity_clip_vs_anticlip.csv", index=False)
SCORE.to_csv(OUT / "audit" / "integrity_scorecard.csv", index=False)
display(Markdown("### Integrity comparison"))
display(COMPARISON)
display(Markdown("### Scorecard"))
display(SCORE)
STAGES.save("W11_integrity", "scorecard", SCORE, note="National clip vs anti-clip")
"""))

    c.append(md("""<a id="w12"></a>
## W12 to W13 · National thematic atlas (land-cover style)
"""))
    c.append(code(r"""THEMATIC = produce_national_thematic_maps(
    tables=TABLES, tree_m=TREE_M, shrub_m=SHRUB_M, lattice=LATTICE, plot=plot, cfg=CFG, out_root=OUT,
)
ATLAS_INDEX = write_national_dashboard_atlas(
    THEMATIC["su_thematic"], OUT / "maps" / "html_atlas", catalog=THEMATIC["catalog"]
)
HTML_PRODUCTS["atlas_index"] = str(ATLAS_INDEX)
HTML_PRODUCTS["interactive_maps"] = THEMATIC.get("interactive") or {}
HTML_PRODUCTS["static_thematic_maps"] = THEMATIC.get("static") or {}
display(THEMATIC["catalog"].head(20))
print("Atlas:", ATLAS_INDEX)
shown = 0
for theme, path in (THEMATIC.get("static") or {}).items():
    if shown >= 4:
        break
    p = Path(path)
    if p.exists():
        display(Markdown(f"**{theme}**"))
        display(Image(filename=str(p)))
        shown += 1
try:
    display(IFrame(src=Path(ATLAS_INDEX).resolve().as_uri(), width="100%", height=520))
except Exception as e:
    print("IFrame skipped:", e)
"""))

    c.append(md("""<a id="w14"></a>
## W14 · Spatial QA (lattice / coordinates)
"""))
    c.append(code(r"""SPATIAL = spatial_qa_national(plot, CFG, LATTICE)
(OUT / "audit" / "spatial_qa_national.json").write_text(json.dumps(SPATIAL, indent=2), encoding="utf-8")
display(SPATIAL)
"""))

    # Phase 3
    c.append(md("""---
# PHASE 3 · Evidence, AI and export
<a id="w15"></a>
## W15 · National remote height evidence (Meta CHMv2 + SRTM)

Kingdom-wide wall-to-wall alternatives to sparse GEDI. Reuses cached products when present.
Set `FORCE_REMOTE_HEIGHT_REFRESH = True` to resample COGs / elevation (slow).
"""))
    c.append(code(r"""FORCE_REMOTE_HEIGHT_REFRESH = False  # True = full Kingdom re-sample (network-bound)

chm_csv = OUT / "validated" / "national_su_meta_chm_v2.csv"
elev_csv = OUT / "validated" / "national_su_elevation_open_meteo.csv"
if FORCE_REMOTE_HEIGHT_REFRESH or not (chm_csv.exists() and elev_csv.exists()):
    REMOTE = run_national_remote_height_evidence(OUT)
else:
    print("Reusing cached national remote height products")
    REMOTE = json.loads((OUT / "logs" / "national_remote_height_evidence.json").read_text(encoding="utf-8")) if (OUT / "logs" / "national_remote_height_evidence.json").exists() else {}
    # refresh gate from files
    LIDAR_GATE = lidar_evidence_gate(CFG, OUT)
    REMOTE["evidence_adequate"] = LIDAR_GATE.get("evidence_adequate")
    REMOTE["n_chm_ok"] = LIDAR_GATE.get("n_chm_ok")
    REMOTE["n_elev_ok"] = LIDAR_GATE.get("n_elev_ok")

LIDAR_GATE = lidar_evidence_gate(CFG, OUT)
display(Markdown("### LiDAR / remote-height evidence gate"))
display(LIDAR_GATE)
disp_path = OUT / "audit" / "national_chm_field_disparity_by_region.csv"
if disp_path.exists():
    display(Markdown("### Field vs CHM disparity by region"))
    display(pd.read_csv(disp_path))
print("evidence_adequate", LIDAR_GATE.get("evidence_adequate"), "asir_only", LIDAR_GATE.get("asir_only", False))
"""))

    c.append(md("""<a id="w16"></a>
## W16 · GeoAI modelling protocol (SU-blocked prototypes, no field overwrite)
"""))
    c.append(code(r"""GEOAI = geoai_protocol_bundle(OUT, TREE_M)
display(Markdown("### Protocol"))
display(pd.read_csv(OUT / "audit" / "geoai_modelling_protocol.csv"))
display(Markdown("### Prototype status"))
display({k: GEOAI[k] for k in GEOAI if k != "metrics"})
if GEOAI.get("metrics"):
    display(GEOAI["metrics"])
proto = OUT / "audit" / "geoai_height_prototype_su_blocked_cv.json"
if proto.exists():
    display(json.loads(proto.read_text(encoding="utf-8")))
"""))

    c.append(md("""<a id="w17"></a>
## W17 · StageStore ledger + export package (GPKG)
"""))
    c.append(code(r"""WF = run_workflow_enhancements(
    CFG, OUT,
    tables=TABLES, lattice=LATTICE, gate=GATE_T, gate_sh=GATE_S,
    tree_m=TREE_M, shrub_m=SHRUB_M, su_metrics=ROLLED["su_metrics"], stages=STAGES,
)
EXPORTS = WF.get("exports") or {}
display(Markdown("### Workflow enhancement summary"))
display({k: WF[k] for k in ("integrity_score_new_pct", "lidar_evidence_adequate", "geoai_prototype_run", "spatial_qa") if k in WF})
display(Markdown("### Export manifest"))
display(EXPORTS)
gpkg = OUT / "exports" / "nfi_national_export_package.gpkg"
print("GPKG exists:", gpkg.exists(), gpkg)
"""))

    # One-shot
    c.append(md("""---
<a id="oneshot"></a>
## One-shot · Full national pipeline + workflow (optional)

Equivalent to `python run_national_pipeline.py` (now includes workflow enhancements).
Use when you want a fresh end-to-end rebuild; otherwise the stepped cells above are enough.
"""))
    c.append(code(r"""NAT = run_national_pipeline(CFG, out_root=OUT)
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
WF = NAT.get("workflow_summary") or RS.get("workflow_e2e") or {}
display(Markdown("### Run summary (computed)"))
display({k: RS[k] for k in RS if k not in ("figures", "maps", "assumptions", "interactive_maps")})
print("assumptions:")
for a in RS.get("assumptions", []):
    print(" -", a)
"""))

    # Report + checklist
    c.append(md("""<a id="deliverables"></a>
## Deliverables · HTML report + open links + checklist
"""))
    c.append(code(r"""guide_summary = {
    "scope": "national_tabular_universe_entire_kingdom",
    "workflow": "17_step_e2e_nationalized",
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
    "assumptions": (RS.get("assumptions") if "RS" in globals() and isinstance(RS, dict) else None) or [
        "National frame = entire cleansed SU master (all regions).",
        "Biomass/carbon are provisional sample metrics.",
        "Area_H expansion blocked except Asir/Makkah grids.",
        "Remote height uses Meta CHMv2 + SRTM; GEDI optional; no field overwrite.",
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
    fig_paths=FIG_PATHS if "FIG_PATHS" in globals() else {},
    map_paths=MAP_PATHS if "MAP_PATHS" in globals() else {},
    interactive_paths=HTML_PRODUCTS.get("interactive_maps") or {},
    atlas_index=HTML_PRODUCTS.get("atlas_index"),
)
HTML_PRODUCTS["html_report"] = str(REPORT_PATH)
(OUT / "documents" / "national_html_manifest.json").write_text(json.dumps(HTML_PRODUCTS, indent=2), encoding="utf-8")

ATLAS_INDEX = Path(HTML_PRODUCTS.get("atlas_index") or OUT / "maps" / "html_atlas" / "index.html")
links = [
    ("Methodology + results HTML report", Path(REPORT_PATH)),
    ("Interactive map atlas (entire Kingdom)", ATLAS_INDEX),
    ("Methodological workflow plate", OUT / "documents" / "NFI_National_Methodological_Workflow_Latest.jpg"),
]
bits = ['<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif;line-height:1.5">']
bits.append('<h3 style="color:#1b5e20;margin:0 0 8px">Open national HTML deliverables</h3>')
rows = []
for label, path in links:
    ok = path.exists()
    rows.append({"deliverable": label, "exists": ok, "bytes": path.stat().st_size if ok else 0, "path": str(path)})
    if ok and path.suffix.lower() in {".html", ".htm"}:
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
    OUT / "logs" / "workflow_e2e_summary.json",
    OUT / "logs" / "national_remote_height_evidence.json",
    OUT / "validated" / "national_plot_lattice.csv",
    OUT / "validated" / "national_trees_biomass_provisional.csv",
    OUT / "validated" / "national_shrubs_biomass_provisional.csv",
    OUT / "validated" / "national_su_meta_chm_v2.csv",
    OUT / "validated" / "national_su_elevation_open_meteo.csv",
    OUT / "audit" / "integrity_scorecard.csv",
    OUT / "audit" / "row_conservation_ledger.csv",
    OUT / "audit" / "spatial_qa_national.json",
    OUT / "exports" / "nfi_national_export_package.gpkg",
    OUT / "documents" / "NFI_national_geopipeline_report.html",
    OUT / "maps" / "html_atlas" / "index.html",
]
check = pd.DataFrame([
    {"path": str(p.relative_to(OUT)) if str(p).startswith(str(OUT)) else str(p),
     "exists": p.exists(),
     "bytes": p.stat().st_size if p.exists() else 0}
    for p in expected
])
display(Markdown("### Output checklist (workflow-complete national)"))
display(check)
print("All required present:", bool(check["exists"].all()))
"""))

    c.append(md("""<a id="assumptions"></a>
## Assumptions and open questions

1. Frame = entire national cleansed SU master (all regions). Asir 430-SU Gate analysis is out of scope.
2. Shrub allometric `log` treated as natural log (base not stated in calc DOCX).
3. Design-based national totals remain blocked until weights and approved variance estimators exist.
4. `Area_H` attaches only where Asir/Makkah grids are present.
5. Deadwood / litter / regeneration / vegetation cover: counts only until official equations are supplied.
6. Remote height: Meta CHMv2 + SRTM are wall-to-wall national alternatives; GEDI is optional/sparse; disparities only (no field overwrite).
7. Biomass and carbon remain **provisional** sample metrics.
8. Atlas categorical percents are SU class frequencies, not land-area shares.

See `docs/08_workflow_alignment_e2e.md`, `docs/09_national_remote_height_alternatives.md`, `docs/10_latest_methodological_workflow.md`.
"""))
    return c


def main() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    if OUT_NB.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = ARCHIVE / f"NFI_GeoAI_Comprehensive_Expanded_V6_Improved_pre_workflow_{stamp}.ipynb"
        shutil.copy2(OUT_NB, dest)
        print("Archived previous notebook ->", dest)

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
