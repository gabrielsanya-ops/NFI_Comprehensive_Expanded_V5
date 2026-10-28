from __future__ import annotations
import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

TABULAR = {".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".parquet"}
VECTOR = {".shp", ".gpkg", ".geojson", ".json", ".kml", ".gdb"}
RASTER = {".tif", ".tiff", ".img", ".vrt"}
DOCS = {".docx", ".pdf", ".png", ".jpg", ".jpeg", ".md"}

CANDIDATES = {
    "sampling_unit_id": [
        "sampling_unit_id", "sampling unit", "samplingunit", "su_id", "suid", "su",
        "su_no", "nfi_of_ksa_program_su_su_no", "cluster_id", "cluster",
    ],
    "sample_plot_id": [
        "sample_plot_id", "sample plot", "sampleplot", "plot_id", "plotid", "plot",
        "plot_id1", "plot_plot_id1", "sp_id",
    ],
    "source_record_id": [
        "source_record_id", "record_id", "recordid", "form_id", "formid",
        "uuid", "globalid", "objectid", "tree_id", "tree_no",
    ],
    "latitude": ["latitude", "lat", "y_coord", "ycoord", "gps_lat", "plot_info1_plot_coor1_y", "plot_info1_coor_db_y"],
    "longitude": ["longitude", "lon", "long", "lng", "x_coord", "xcoord", "gps_lon", "plot_info1_plot_coor1_x", "plot_info1_coor_db_x"],
    "region": ["region", "province", "su_group_region_e", "reg_e", "gover_e", "su_group_gover_e"],
}


def load_config(path: str | Path = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_portable_paths(cfg: dict, root: str | Path | None = None) -> dict:
    """Resolve relative file paths in config against project root.

    Skips non-path GIS keys such as asir_su_key / asir_grid_key (column names).
    """
    root = Path(root) if root is not None else Path.cwd()
    skip_keys = {"asir_su_key", "asir_grid_key"}
    path_exts = (
        ".xlsx", ".xls", ".csv", ".shp", ".gpkg", ".docx", ".pdf",
        ".md", ".yaml", ".yml", ".js", ".json",
    )
    for section in ("paths", "tables", "gis", "documents_reference_only"):
        if section not in cfg:
            continue
        for k, v in list(cfg[section].items()):
            if k in skip_keys or not isinstance(v, str) or not v:
                continue
            if Path(v).is_absolute():
                continue
            looks_path = (
                "/" in v
                or "\\" in v
                or v.startswith("data")
                or v.startswith("outputs")
                or v.lower().endswith(path_exts)
            )
            if looks_path:
                cfg[section][k] = str((root / v).resolve())
    return cfg


def ensure_output_dirs(cfg: dict) -> Path:
    out = Path(cfg["paths"]["output_root"])
    for sub in [
        "audit", "validated", "figures", "logs", "gates", "documents",
        "stages", "maps",
    ]:
        (out / sub).mkdir(parents=True, exist_ok=True)
    return out


class StageStore:
    """
    Snapshot tables/layers after each pipeline stage for interactive review.
    Prefer long-form key joins over Excel-style pivots that drop zero cells.
    """

    def __init__(self, root: Path):
        self.root = Path(root) / "stages"
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest: list[dict] = []

    def save(self, stage: str, name: str, obj, *, note: str = "") -> Path:
        import geopandas as gpd

        if not isinstance(stage, str) or not isinstance(name, str):
            raise TypeError(
                "StageStore.save(stage, name, obj, note=...) requires string stage and name; "
                f"got stage={type(stage).__name__}, name={type(name).__name__}"
            )
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{stage}__{name}")
        if isinstance(obj, gpd.GeoDataFrame):
            path = self.root / f"{safe}.gpkg"
            try:
                obj.to_file(path, layer=name[:40] or "layer", driver="GPKG")
            except Exception:
                path = self.root / f"{safe}.csv"
                obj.drop(columns="geometry", errors="ignore").to_csv(path, index=False)
        elif isinstance(obj, pd.DataFrame):
            path = self.root / f"{safe}.csv"
            obj.drop(columns="geometry", errors="ignore").to_csv(path, index=False)
        elif isinstance(obj, (dict, list)):
            path = self.root / f"{safe}.csv"
            pd.DataFrame(obj).to_csv(path, index=False)
        else:
            raise TypeError(
                f"StageStore.save cannot serialize type {type(obj).__name__}; "
                "pass a DataFrame, GeoDataFrame, dict, or list"
            )
        meta = {
            "stage": stage, "name": name, "path": str(path),
            "rows": int(len(obj)), "note": note,
            "columns": list(getattr(obj, "columns", [])),
        }
        self.manifest.append(meta)
        pd.DataFrame(self.manifest).to_csv(self.root / "stage_manifest.csv", index=False)
        return path

    def list_stages(self) -> pd.DataFrame:
        p = self.root / "stage_manifest.csv"
        if p.exists():
            return pd.read_csv(p)
        return pd.DataFrame(self.manifest)

    def load(self, stage: str, name: str):
        import geopandas as gpd

        hits = [m for m in self.manifest if m["stage"] == stage and m["name"] == name]
        if not hits:
            man = self.list_stages()
            if len(man):
                hits = man.loc[(man.stage == stage) & (man.name == name)].to_dict("records")
        if not hits:
            raise KeyError(f"No snapshot {stage}/{name}")
        path = Path(hits[-1]["path"])
        if path.suffix.lower() == ".gpkg":
            return gpd.read_file(path)
        return pd.read_csv(path)


def norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())


def file_hash(path: str | Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def scan_files(paths: dict) -> pd.DataFrame:
    rows = []
    for label, p in paths.items():
        path = Path(p)
        if not path.exists():
            rows.append({
                "root": label, "path": str(path), "exists": False,
                "type": "missing", "extension": None, "size_bytes": None,
            })
            continue
        iterator = path.rglob("*") if path.is_dir() else [path]
        for f in iterator:
            if not f.is_file():
                continue
            if f.name.endswith(".lock") or f.suffix.lower() in {".sbn", ".sbx", ".cpg", ".prj", ".shx", ".xml"}:
                # keep sidecar awareness light; shp itself is enough for registry
                if f.suffix.lower() != ".shp" and f.suffix.lower() in {".sbn", ".sbx", ".cpg", ".prj", ".shx"}:
                    continue
            ext = f.suffix.lower()
            typ = (
                "tabular" if ext in TABULAR else
                "vector" if ext in VECTOR else
                "raster" if ext in RASTER else
                "document" if ext in DOCS else
                "other"
            )
            try:
                size = f.stat().st_size
            except OSError:
                size = None
            rows.append({
                "root": label, "path": str(f), "exists": True,
                "type": typ, "extension": ext, "size_bytes": size,
            })
    return pd.DataFrame(rows)


def detect_columns(columns) -> dict:
    lookup = {norm(c): c for c in columns}
    out = {}
    for role, names in CANDIDATES.items():
        hits = []
        for n in names:
            nn = norm(n)
            if nn in lookup:
                hits.append(lookup[nn])
        out[role] = hits
    return out


def profile_df(df: pd.DataFrame, source: str, sheet: str | None = None):
    detected = detect_columns(df.columns)
    rows = []
    for c in df.columns:
        s = df[c]
        rows.append({
            "source": source, "sheet": sheet, "column": str(c), "dtype": str(s.dtype),
            "n": len(s), "non_null": int(s.notna().sum()), "null_n": int(s.isna().sum()),
            "null_pct": float(s.isna().mean() * 100) if len(s) else 0.0,
            "unique_n": int(s.nunique(dropna=True)),
            "duplicate_nonnull_n": int(s.notna().sum() - s.nunique(dropna=True)),
            "sample_values": " | ".join(map(str, s.dropna().astype(str).head(5).tolist())),
        })
    return pd.DataFrame(rows), detected


def read_tabular(path: str | Path) -> dict[str, pd.DataFrame]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in {".xlsx", ".xlsm", ".xls"}:
        x = pd.ExcelFile(p)
        return {s: pd.read_excel(p, sheet_name=s) for s in x.sheet_names}
    if ext == ".csv":
        return {"__csv__": pd.read_csv(p, low_memory=False)}
    if ext == ".parquet":
        return {"__parquet__": pd.read_parquet(p)}
    if ext == ".txt":
        for sep in [",", "\t", ";", "|"]:
            try:
                d = pd.read_csv(p, sep=sep, low_memory=False)
                if d.shape[1] > 1:
                    return {"__txt__": d}
            except Exception:
                pass
    return {}


def read_first_sheet(path: str | Path) -> pd.DataFrame:
    tabs = read_tabular(path)
    if not tabs:
        raise FileNotFoundError(f"No readable tabular content: {path}")
    return next(iter(tabs.values()))


def docx_paragraphs(path: str | Path) -> list[str]:
    """Extract plain paragraphs from a .docx without python-docx."""
    z = zipfile.ZipFile(path)
    root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p_el in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        texts = [
            t.text or ""
            for t in p_el.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        ]
        line = "".join(texts).strip()
        if line:
            paras.append(line)
    return paras


def document_registry(cfg: dict) -> pd.DataFrame:
    rows = []
    for label, path in (cfg.get("documents") or {}).items():
        p = Path(path)
        row = {
            "doc_id": label,
            "path": str(p),
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else None,
            "n_paragraphs": None,
            "preview": None,
        }
        if p.exists() and p.suffix.lower() == ".docx":
            paras = docx_paragraphs(p)
            row["n_paragraphs"] = len(paras)
            row["preview"] = " | ".join(paras[:8])
        rows.append(row)
    return pd.DataFrame(rows)


def canonical_key(series: pd.Series) -> pd.Series:
    return (
        series.astype("string").str.strip().str.upper()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
    )


def make_su_uid(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)


def make_plot_uid(su: pd.Series, plot: pd.Series, sep: str = "-") -> pd.Series:
    return make_su_uid(su) + sep + make_su_uid(plot)


def attach_keys(df: pd.DataFrame, cfg: dict, *, kind: str) -> pd.DataFrame:
    """kind in {'su','plot','child','trees','fauna'}."""
    out = df.copy()
    cols = cfg["columns"]
    sep = cfg["project"].get("plot_uid_separator", "-")
    if kind == "su":
        out["SU_UID"] = make_su_uid(out[cols["su_id_in_su_master"]])
    elif kind == "plot":
        out["SU_UID"] = make_su_uid(out[cols["su_id_in_child_tables"]])
        out["PLOT_ID"] = make_su_uid(out[cols["plot_id_in_plot"]])
        out["PLOT_UID"] = make_plot_uid(out["SU_UID"], out["PLOT_ID"], sep)
    elif kind in {"child", "trees"}:
        out["SU_UID"] = make_su_uid(out[cols["su_id_in_child_tables"]])
        pid = cols["plot_id_in_child_tables"]
        out["PLOT_ID"] = make_su_uid(out[pid])
        out["PLOT_UID"] = make_plot_uid(out["SU_UID"], out["PLOT_ID"], sep)
    elif kind == "fauna":
        out["SU_UID"] = make_su_uid(out[cols["su_id_in_child_tables"]])
    else:
        raise ValueError(kind)
    return out


def validate_key(df: pd.DataFrame, col: str, source: str) -> pd.DataFrame:
    k = canonical_key(df[col])
    return pd.DataFrame([{
        "source": source, "column": col, "rows": len(df),
        "missing_keys": int(k.isna().sum()),
        "unique_keys": int(k.nunique(dropna=True)),
        "duplicate_rows": int(k.notna().sum() - k.nunique(dropna=True)),
    }])


def coordinate_checks(df: pd.DataFrame, lat: str, lon: str, source: str,
                      lon_range=(34.0, 56.0), lat_range=(16.0, 33.0)) -> pd.DataFrame:
    la = pd.to_numeric(df[lat], errors="coerce")
    lo = pd.to_numeric(df[lon], errors="coerce")
    issue = pd.Series("PASS", index=df.index, dtype="string")
    issue[(la.isna()) | (lo.isna())] = "MISSING_OR_NONNUMERIC"
    issue[(la < -90) | (la > 90) | (lo < -180) | (lo > 180)] = "OUTSIDE_GLOBAL_RANGE"
    issue[(la == 0) & (lo == 0)] = "ZERO_ZERO"
    in_sa = (lo >= lon_range[0]) & (lo <= lon_range[1]) & (la >= lat_range[0]) & (la <= lat_range[1])
    issue[(issue == "PASS") & ~in_sa] = "OUTSIDE_SAUDI_ENVELOPE"
    return pd.DataFrame({
        "source": source, "row_index": df.index,
        "latitude": la, "longitude": lo, "coordinate_status": issue,
    })


def plot_coordinate_qa(plot: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cols = cfg["columns"]
    # Defaults match coordinate_checks() and V4_Refined config settings block.
    settings = cfg.get("settings") or {}
    out = plot.copy()
    out["lon_field_orig"] = pd.to_numeric(out[cols["lon_field"]], errors="coerce")
    out["lat_field_orig"] = pd.to_numeric(out[cols["lat_field"]], errors="coerce")
    out["lon_db_orig"] = pd.to_numeric(out[cols["lon_db"]], errors="coerce")
    out["lat_db_orig"] = pd.to_numeric(out[cols["lat_db"]], errors="coerce")
    lon_lo, lon_hi = settings.get("saudi_lon_range", [34.0, 56.0])
    lat_lo, lat_hi = settings.get("saudi_lat_range", [16.0, 33.0])

    def _ok(lon, lat):
        return (lon >= lon_lo) & (lon <= lon_hi) & (lat >= lat_lo) & (lat <= lat_hi)

    field_ok = _ok(out["lon_field_orig"], out["lat_field_orig"])
    db_ok = _ok(out["lon_db_orig"], out["lat_db_orig"])
    out["lon_validated"] = np.where(db_ok, out["lon_db_orig"], np.where(field_ok, out["lon_field_orig"], np.nan))
    out["lat_validated"] = np.where(db_ok, out["lat_db_orig"], np.where(field_ok, out["lat_field_orig"], np.nan))
    out["coord_source"] = np.where(db_ok, "db", np.where(field_ok, "field", "missing"))
    out["coord_confidence"] = np.where(
        db_ok & field_ok, "high",
        np.where(db_ok | field_ok, "medium", "low"),
    )
    both = field_ok & db_ok
    out["coord_displacement_m"] = np.nan
    if both.any():
        dlon = (out.loc[both, "lon_field_orig"] - out.loc[both, "lon_db_orig"]) * 111000 * np.cos(
            np.radians(out.loc[both, "lat_db_orig"].fillna(23))
        )
        dlat = (out.loc[both, "lat_field_orig"] - out.loc[both, "lat_db_orig"]) * 111000
        out.loc[both, "coord_displacement_m"] = np.sqrt(dlon**2 + dlat**2)
    return out


def reconcile(left, right, left_key, right_key, left_name="tabular", right_name="gis") -> pd.DataFrame:
    a = left.copy()
    b = right.copy()
    a["_join_key"] = canonical_key(a[left_key])
    b["_join_key"] = canonical_key(b[right_key])
    ac = a["_join_key"].value_counts(dropna=False)
    bc = b["_join_key"].value_counts(dropna=False)
    keys = pd.Index(a["_join_key"].dropna().unique()).union(pd.Index(b["_join_key"].dropna().unique()))
    r = pd.DataFrame({"join_key": keys})
    r["left_n"] = r.join_key.map(ac).fillna(0).astype(int)
    r["right_n"] = r.join_key.map(bc).fillna(0).astype(int)
    cond = [
        (r.left_n == 1) & (r.right_n == 1),
        (r.left_n > 0) & (r.right_n == 0),
        (r.left_n == 0) & (r.right_n > 0),
        (r.left_n > 1) & (r.right_n > 0),
        (r.left_n > 0) & (r.right_n > 1),
    ]
    choices = [
        "MATCH_1_TO_1",
        f"{left_name.upper()}_ONLY",
        f"{right_name.upper()}_ONLY",
        "LEFT_DUPLICATE",
        "RIGHT_DUPLICATE",
    ]
    r["status"] = np.select(cond, choices, default="AMBIGUOUS")
    return r


def row_conservation(stage, before_n, after_n, expected_change=0) -> dict:
    delta = after_n - before_n
    return {
        "stage": stage, "before_n": before_n, "after_n": after_n, "delta": delta,
        "expected_change": expected_change, "pass": delta == expected_change,
    }


def load_asir_su_universe(cfg: dict):
    import geopandas as gpd
    path = cfg["gis"]["asir_su"]
    g = gpd.read_file(path)
    key = cfg["gis"]["asir_su_key"]
    g["SU_UID"] = make_su_uid(g[key])
    return g


def expected_plot_universe(su_uids, plots_per_su: int = 5, sep: str = "-") -> pd.DataFrame:
    rows = []
    for su in sorted(su_uids, key=lambda x: int(str(x)) if str(x).isdigit() else str(x)):
        for p in range(1, plots_per_su + 1):
            rows.append({
                "SU_UID": str(su),
                "PLOT_ID": str(p),
                "PLOT_UID": f"{su}{sep}{p}",
            })
    return pd.DataFrame(rows)


def aseer_gate1_zero_tree_sus(asir_su: pd.DataFrame, trees: pd.DataFrame) -> dict:
    """Validation Point 1  -  SUs with no matching Trees records."""
    universe = set(asir_su["SU_UID"].astype(str))
    with_trees = set(trees.loc[trees["SU_UID"].astype(str).isin(universe), "SU_UID"].astype(str))
    zero = sorted(universe - with_trees, key=lambda x: int(x) if x.isdigit() else x)
    gov_col = "gover_e" if "gover_e" in asir_su.columns else None
    annex = asir_su.loc[asir_su["SU_UID"].astype(str).isin(zero)].copy()
    if gov_col:
        annex = annex.sort_values([gov_col, "SU_UID"])
    summary = pd.DataFrame([{
        "total_sus": len(universe),
        "sus_with_trees": len(with_trees),
        "sus_no_trees": len(zero),
    }])
    by_gov = None
    if gov_col:
        by_gov = (
            annex.groupby(gov_col, dropna=False)["SU_UID"]
            .agg(n_sus="count", su_numbers=lambda s: ", ".join(map(str, sorted(s, key=lambda x: int(x) if str(x).isdigit() else str(x)))))
            .reset_index()
            .rename(columns={gov_col: "governorate"})
        )
    return {
        "summary": summary,
        "zero_su_ids": zero,
        "annex": annex,
        "by_governorate": by_gov,
    }


def aseer_gate2_plot_completeness(
    asir_su: pd.DataFrame,
    trees: pd.DataFrame,
    plots_per_su: int = 5,
    sep: str = "-",
    gate1_zero_su_ids: list | None = None,
) -> dict:
    """Validation Point 2  -  expected plots with no Trees records (excl. Gate-1 SUs)."""
    universe_su = set(asir_su["SU_UID"].astype(str))
    expected = expected_plot_universe(universe_su, plots_per_su, sep)
    tree_plots = set(
        trees.loc[trees["SU_UID"].astype(str).isin(universe_su), "PLOT_UID"].astype(str)
    )
    expected["has_tree_record"] = expected["PLOT_UID"].isin(tree_plots)
    if gate1_zero_su_ids is None:
        gate1_zero_su_ids = sorted(
            universe_su - set(trees.loc[trees["SU_UID"].astype(str).isin(universe_su), "SU_UID"].astype(str))
        )
    zero_set = set(map(str, gate1_zero_su_ids))
    expected["in_gate1_zero_su"] = expected["SU_UID"].isin(zero_set)
    gate2 = expected.loc[~expected["has_tree_record"] & ~expected["in_gate1_zero_su"]].copy()

    gov_map = {}
    if "gover_e" in asir_su.columns:
        gov_map = dict(zip(asir_su["SU_UID"].astype(str), asir_su["gover_e"]))
    gate2["governorate"] = gate2["SU_UID"].map(gov_map)

    def _agg(g):
        plots = sorted(g["PLOT_ID"].astype(int))
        uids = [f"{g.name}-{p}" for p in plots]
        return pd.Series({
            "missing_plots": ", ".join(map(str, plots)),
            "plot_uids": ", ".join(uids),
            "n_missing": len(plots),
            "governorate": g["governorate"].iloc[0] if "governorate" in g else None,
        })

    annex = (
        gate2.groupby("SU_UID", sort=False)
        .apply(_agg, include_groups=False)
        .reset_index()
        .sort_values(["governorate", "SU_UID"], key=lambda s: s.astype(str))
    )

    summary = pd.DataFrame([{
        "total_sus": len(universe_su),
        "expected_plots": len(expected),
        "plots_in_gate1_zero_sus": int(expected["in_gate1_zero_su"].sum()),
        "plots_with_trees": int(expected["has_tree_record"].sum()),
        "gate2_plots": len(gate2),
        "gate2_sus_affected": gate2["SU_UID"].nunique(),
    }])
    return {
        "summary": summary,
        "expected": expected,
        "gate2_plots": gate2,
        "annex": annex,
    }


def compare_to_doc_targets(observed: dict, expected_cfg: dict) -> pd.DataFrame:
    rows = []
    mapping = [
        ("total_sus", "total_sus"),
        ("sus_with_trees", "sus_with_trees"),
        ("sus_no_trees", "sus_no_trees"),
        ("expected_plots", "expected_plots"),
        ("plots_in_gate1_zero_sus", "plots_in_zero_tree_sus"),
        ("plots_with_trees", "plots_with_trees"),
        ("gate2_plots", "gate2_plots"),
        ("gate2_sus_affected", "gate2_sus_affected"),
    ]
    for obs_key, exp_key in mapping:
        if obs_key not in observed or exp_key not in expected_cfg:
            continue
        o = int(observed[obs_key])
        e = int(expected_cfg[exp_key])
        rows.append({
            "metric": obs_key,
            "observed": o,
            "document_target": e,
            "match": o == e,
        })
    return pd.DataFrame(rows)


def biological_tree_flags(trees: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cols = cfg["columns"]
    # Defaults match V4_Refined config.yaml settings block.
    settings = cfg.get("settings") or {}
    dbh_max = float(settings.get("dbh_unusual_max_cm", 300))
    ht_max = float(settings.get("height_unusual_max_m", 80))
    out = trees.copy()
    out["_dbh"] = pd.to_numeric(out[cols["dbh"]], errors="coerce")
    out["_ht"] = pd.to_numeric(out[cols["height"]], errors="coerce")
    flags = []
    for idx, r in out.iterrows():
        reasons = []
        if pd.notna(r["_dbh"]) and (r["_dbh"] <= 0 or r["_dbh"] > dbh_max):
            reasons.append("unusual_dbh")
        if pd.notna(r["_ht"]) and (r["_ht"] <= 0 or r["_ht"] > ht_max):
            reasons.append("unusual_height")
        if reasons:
            flags.append({
                "PLOT_UID": r.get("PLOT_UID"),
                "SU_UID": r.get("SU_UID"),
                "tree_id": r.get("tree_id"),
                "tree_no": r.get("tree_no"),
                "dbh": r["_dbh"],
                "height": r["_ht"],
                "flags": "|".join(reasons),
                "disposition": "FLAGGED_NOT_DELETED",
            })
    return pd.DataFrame(flags)


def table_presence_matrix(tables: dict[str, pd.DataFrame], universe_su: set[str]) -> pd.DataFrame:
    rows = []
    for name, df in tables.items():
        if "SU_UID" not in df.columns:
            continue
        present = set(df["SU_UID"].astype(str)) & universe_su
        rows.append({
            "table": name,
            "rows_total": len(df),
            "sus_in_aseer": len(present),
            "sus_missing_in_aseer": len(universe_su - present),
            "coverage_pct": round(100 * len(present) / len(universe_su), 2) if universe_su else None,
        })
    return pd.DataFrame(rows).sort_values("table")


def tree_counts_by_su(trees: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tree presence to SU  -  used for left-join onto the SU universe."""
    g = trees.groupby("SU_UID", dropna=False)
    return g.agg(
        n_tree_records=("SU_UID", "size"),
        n_plots_with_trees=("PLOT_UID", "nunique") if "PLOT_UID" in trees.columns else ("SU_UID", "size"),
    ).reset_index()


def anti_clip_su_tree_frame(asir_su, trees: pd.DataFrame):
    """
    Circumnavigate the 'clip loses missing-SU' failure mode.

    Wrong pattern (causes the Word-doc issue):
      - clip / inner-join trees → GIS, then treat remaining SUs as the universe
      - SUs with no tree rows vanish and are silently treated as absent

    Right pattern (GeoPandas / pandas):
      - keep Asir_SU_Final (or grid) as LEFT master
      - LEFT JOIN tree aggregates
      - classify: HAS_TREES vs NO_TREE_RECORD_REQUIRES_GATE1
      - never overwrite the source shapefile / Excel
    """
    import geopandas as gpd

    master = asir_su.copy()
    if not isinstance(master, gpd.GeoDataFrame):
        raise TypeError("asir_su must be a GeoDataFrame")
    master["SU_UID"] = make_su_uid(master["SU_UID"])
    counts = tree_counts_by_su(trees)
    counts["SU_UID"] = make_su_uid(counts["SU_UID"])
    out = master.merge(counts, on="SU_UID", how="left")
    out["n_tree_records"] = out["n_tree_records"].fillna(0).astype(int)
    if "n_plots_with_trees" in out.columns:
        out["n_plots_with_trees"] = out["n_plots_with_trees"].fillna(0).astype(int)
    out["has_tree_record"] = out["n_tree_records"] > 0
    out["gate1_class"] = np.where(
        out["has_tree_record"],
        "HAS_TREE_RECORDS",
        "NO_TREE_RECORD_REQUIRES_FIELD_CLASSIFICATION",
    )
    # Explicit: absence of rows is NOT proof of zero trees
    out["zero_trees_confirmed"] = False
    out["survey_status"] = "UNRESOLVED"
    return out


def demonstrate_clip_loss(asir_su, trees: pd.DataFrame) -> pd.DataFrame:
    """
    Quantify damage of the wrong workflow vs anti-clip left join.
    """
    universe_n = len(asir_su)
    tree_su = set(make_su_uid(trees["SU_UID"]))
    master_su = set(make_su_uid(asir_su["SU_UID"]))
    # Wrong: inner join / clip to SUs that appear in trees
    clipped_n = len(master_su & tree_su)
    lost_n = len(master_su - tree_su)
    preserved = anti_clip_su_tree_frame(asir_su, trees)
    return pd.DataFrame([
        {
            "method": "WRONG_inner_join_or_clip_to_trees",
            "su_retained": clipped_n,
            "su_lost_silently": lost_n,
            "universe_complete": False,
            "note": "Matches the Word-doc failure: 190 SUs disappear and cannot be validated",
        },
        {
            "method": "RIGHT_geopandas_left_join_on_Asir_SU_Final",
            "su_retained": len(preserved),
            "su_lost_silently": universe_n - len(preserved),
            "universe_complete": len(preserved) == universe_n,
            "note": "All 430 SUs kept; no-tree SUs flagged for Gate 1 classification",
        },
    ])


def spatial_filter_preserve_universe(universe_gdf, aoi_gdf, predicate: str = "intersects"):
    """
    Spatially subset WITHOUT destroying the master: return
    (subset_gdf, excluded_gdf, reconciliation_df).

    Use this instead of gpd.clip() when the clip result would become
    the authoritative NFI record list.
    """
    import geopandas as gpd

    u = universe_gdf.copy()
    aoi = aoi_gdf.copy()
    if u.crs != aoi.crs:
        aoi = aoi.to_crs(u.crs)
    # dissolve AOI to one geometry for membership test
    aoi_geom = aoi.unary_union
    mask = u.intersects(aoi_geom) if predicate == "intersects" else u.within(aoi_geom)
    subset = u.loc[mask].copy()
    excluded = u.loc[~mask].copy()
    recon = pd.DataFrame([
        {"group": "in_aoi", "n": len(subset)},
        {"group": "outside_aoi_preserved_in_master", "n": len(excluded)},
        {"group": "universe_total", "n": len(u)},
    ])
    subset["spatial_membership"] = "IN_AOI"
    excluded["spatial_membership"] = "OUTSIDE_AOI"
    return subset, excluded, recon


def plots_to_geodataframe(plot_qa: pd.DataFrame, lon="lon_validated", lat="lat_validated", crs="EPSG:4326"):
    """Build plot points for spatial left-joins; rows with bad coords kept in tabular side."""
    import geopandas as gpd
    from shapely.geometry import Point

    df = plot_qa.copy()
    ok = df[lon].notna() & df[lat].notna()
    geom = [
        Point(xy) if valid else None
        for valid, xy in zip(ok, zip(df[lon], df[lat]))
    ]
    gdf = gpd.GeoDataFrame(df, geometry=geom, crs=crs)
    return gdf


def left_sjoin_plots_to_su_grid(plot_gdf, su_grid_gdf, su_key="SU_UID"):
    """
    Assign plots to grid cells with how='left' so plots are never dropped.
    Compare assigned grid SU vs attribute SU_UID for mismatch QA.
    """
    import geopandas as gpd

    plots = plot_gdf.copy()
    grid = su_grid_gdf[[su_key, "geometry"]].rename(columns={su_key: "grid_SU_UID"}).copy()
    if plots.crs != grid.crs:
        plots = plots.to_crs(grid.crs)
    has_geom = plots.geometry.notna()

    matched = gpd.sjoin(plots.loc[has_geom], grid, how="left", predicate="within")
    matched["grid_SU_UID"] = make_su_uid(matched["grid_SU_UID"])
    matched["attr_SU_UID"] = make_su_uid(matched[su_key]) if su_key in matched.columns else pd.NA
    matched["su_grid_mismatch"] = (
        matched["grid_SU_UID"].notna() & matched["attr_SU_UID"].notna()
        & (matched["grid_SU_UID"] != matched["attr_SU_UID"])
    )
    matched["spatial_join_status"] = np.where(
        matched["grid_SU_UID"].notna(), "WITHIN_GRID", "COORD_OUTSIDE_GRID"
    )
    if "index_right" in matched.columns:
        matched = matched.drop(columns=["index_right"])

    no_geom = plots.loc[~has_geom].copy()
    no_geom["grid_SU_UID"] = pd.NA
    no_geom["attr_SU_UID"] = make_su_uid(no_geom[su_key]) if su_key in no_geom.columns else pd.NA
    no_geom["su_grid_mismatch"] = False
    no_geom["spatial_join_status"] = "NO_VALID_COORDINATE"

    return gpd.GeoDataFrame(pd.concat([matched, no_geom], ignore_index=True), crs=grid.crs)


# ---------------------------------------------------------------------------
# Lexical / spelling QA (observed values only; never overwrite sources)
# ---------------------------------------------------------------------------

# Canonical English forms for reporting. Keys are values observed in NFI tables/GIS.
PLACE_NAME_CORRECTIONS = {
    "Aseer": {
        "proposed": "Asir",
        "issue": "transliteration_variant",
        "rationale": (
            "Source tables and Asir GIS use Aseer; common English / many official maps use Asir. "
            "Pick one canonical reporting form and keep Aseer as a source alias."
        ),
        "action": "ADD_ALIAS_MAP_DO_NOT_OVERWRITE_SOURCE",
    },
    "Ar Riyad": {
        "proposed": "Ar Riyadh",
        "issue": "transliteration_incomplete",
        "rationale": "Observed spelling drops the final h used in standard English Ar Riyadh.",
        "action": "STANDARDISE_IN_REPORTING_LAYER",
    },
    "Al Qaseem": {
        "proposed": "Al Qassim",
        "issue": "transliteration_variant",
        "rationale": "Al Qaseem appears in source; Al Qassim is the more common English form.",
        "action": "STANDARDISE_IN_REPORTING_LAYER",
    },
    "Rijal Al Ma": {
        "proposed": "Rijal Alma",
        "issue": "possible_truncated_transliteration",
        "rationale": (
            "Governorate label ends abruptly at Ma; Rijal Alma is the usual English form. "
            "Confirm with authority list before bulk replace."
        ),
        "action": "CONFIRM_WITH_AUTHORITY_LIST",
    },
}

# Exact label misspellings / orthography observed in cleansed tables
LABEL_CORRECTIONS = {
    "Innaccessible - other reason": {
        "proposed": "Inaccessible - other reason",
        "issue": "english_spelling",
        "rationale": "Double-n typo: Innaccessible -> Inaccessible.",
        "action": "CORRECT_IN_DERIVED_LABEL",
    },
    "Innaccessible - slope": {
        "proposed": "Inaccessible - slope",
        "issue": "english_spelling",
        "rationale": "Double-n typo: Innaccessible -> Inaccessible.",
        "action": "CORRECT_IN_DERIVED_LABEL",
    },
    "Innaccessible - owner refusal": {
        "proposed": "Inaccessible - owner refusal",
        "issue": "english_spelling",
        "rationale": "Double-n typo: Innaccessible -> Inaccessible.",
        "action": "CORRECT_IN_DERIVED_LABEL",
    },
    "Innaccessible - restricted area": {
        "proposed": "Inaccessible - restricted area",
        "issue": "english_spelling",
        "rationale": "Double-n typo: Innaccessible -> Inaccessible.",
        "action": "CORRECT_IN_DERIVED_LABEL",
    },
    "Innaccessible - water body": {
        "proposed": "Inaccessible - water body",
        "issue": "english_spelling",
        "rationale": "Double-n typo: Innaccessible -> Inaccessible.",
        "action": "CORRECT_IN_DERIVED_LABEL",
    },
    "from office Study": {
        "proposed": "from office study",
        "issue": "inconsistent_capitalisation",
        "rationale": "Desk-study note capitalisation is inconsistent across rows.",
        "action": "NORMALISE_CASE_IN_DERIVED_LAYER",
    },
    "from desk office": {
        "proposed": "from desk study",
        "issue": "near_duplicate_phrase",
        "rationale": "Likely same meaning as from office study; standardise phrasing in derived notes.",
        "action": "CONFIRM_THEN_ALIAS",
    },
}

LANGUAGE_CODE_ALLOWED = {"lat", "ara", "en", "eng", "ar", "latin"}

# Columns expected numeric in tree/plot derived cleaning
EXPECTED_NUMERIC_HINTS = {
    "trees": ["tree_dbh", "tree_height", "crown_diameterl1", "crown_diameterl2"],
    "plot": [
        "plot_info1_plot_coor1_x", "plot_info1_plot_coor1_y",
        "plot_info1_coor_db_x", "plot_info1_coor_db_y",
    ],
}


def lexical_quality_audit(
    tables: dict[str, pd.DataFrame],
    path_hints: dict | None = None,
) -> dict:
    """
    Detect spelling / field-contamination / path typos from observed values.
    Returns findings + proposed correction measures. Does not mutate sources.
    """
    findings = []

    if path_hints:
        for key, p in path_hints.items():
            s = str(p)
            if "Clensed" in s:
                findings.append({
                    "table": "_paths",
                    "column": key,
                    "observed": "Clensed",
                    "proposed": "Cleansed",
                    "n_rows": 1,
                    "issue": "folder_name_spelling",
                    "severity": "medium",
                    "correction_measure": (
                        "Rename folder when safe, or keep path as-is and document "
                        "Clensed as a historical misspelling of Cleansed."
                    ),
                    "action": "DOCUMENT_OR_RENAME_FOLDER",
                })

    for tname, df in tables.items():
        if df is None or len(df) == 0:
            continue
        for col in df.columns:
            if df[col].dtype != object and str(df[col].dtype) != "string":
                continue
            s = df[col].dropna().astype(str).str.strip()
            s = s.loc[~s.isin(["", "nan", "None", "NaN", "<NA>"])]
            if s.empty:
                continue

            for observed, meta in {**PLACE_NAME_CORRECTIONS, **LABEL_CORRECTIONS}.items():
                n = int((s == observed).sum())
                if n:
                    findings.append({
                        "table": tname,
                        "column": col,
                        "observed": observed,
                        "proposed": meta["proposed"],
                        "n_rows": n,
                        "issue": meta["issue"],
                        "severity": "high" if meta["issue"] == "english_spelling" else "medium",
                        "correction_measure": meta["rationale"],
                        "action": meta["action"],
                    })

            # Control / non-printable characters
            ctrl_n = int(s.map(lambda x: bool(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", str(x)))).sum())
            if ctrl_n:
                findings.append({
                    "table": tname,
                    "column": col,
                    "observed": "control_characters",
                    "proposed": "strip_control_chars",
                    "n_rows": ctrl_n,
                    "issue": "illegal_characters",
                    "severity": "high",
                    "correction_measure": "Remove ASCII control characters in the derived layer before joins and maps.",
                    "action": "STRIP_CONTROL_CHARS_IN_DERIVED_LAYER",
                })

            raw = df[col].dropna().astype(str)
            ws = raw.loc[raw.str.strip() != raw]
            if len(ws):
                findings.append({
                    "table": tname,
                    "column": col,
                    "observed": "leading_or_trailing_whitespace",
                    "proposed": "strip()",
                    "n_rows": int(len(ws)),
                    "issue": "whitespace",
                    "severity": "low",
                    "correction_measure": "Trim on ingest into reporting keys; keep raw source unchanged.",
                    "action": "STRIP_IN_DERIVED_LAYER",
                })
            dbl = s.loc[s.str.contains(r"  +", regex=True, na=False)]
            if len(dbl):
                findings.append({
                    "table": tname,
                    "column": col,
                    "observed": "repeated_internal_spaces",
                    "proposed": "collapse_spaces",
                    "n_rows": int(len(dbl)),
                    "issue": "whitespace",
                    "severity": "low",
                    "correction_measure": "Collapse repeated spaces in derived text fields.",
                    "action": "NORMALIZE_WHITESPACE_IN_DERIVED_LAYER",
                })

            if col.lower() in {
                "tree_species_language_code", "species_language_code", "language_code"
            }:
                bad = s.loc[~s.str.lower().isin(LANGUAGE_CODE_ALLOWED)]
                if len(bad):
                    for val, cnt in bad.value_counts().head(20).items():
                        findings.append({
                            "table": tname,
                            "column": col,
                            "observed": val,
                            "proposed": "null_or_ara_if_vernacular",
                            "n_rows": int(cnt),
                            "issue": "field_contamination",
                            "severity": "high",
                            "correction_measure": (
                                "Value is a vernacular name, not a language code. "
                                "Move text into tree_species_vernacular_name if empty; "
                                "set language_code to missing or ara after expert review."
                            ),
                            "action": "REMAP_CONTAMINATED_CELLS_IN_DERIVED_LAYER",
                        })

    findings_df = pd.DataFrame(findings)
    if len(findings_df) == 0:
        findings_df = pd.DataFrame(columns=[
            "table", "column", "observed", "proposed", "n_rows",
            "issue", "severity", "correction_measure", "action",
        ])

    measures = pd.DataFrame([
        {
            "priority": 1,
            "measure": "Build a reporting alias table (source_value -> canonical_en) for region/governorate.",
            "applies_to": "su_group_region_e, su_group_gover_e, reg_e, gover_e",
        },
        {
            "priority": 2,
            "measure": "Correct Innaccessible -> Inaccessible on plot access labels in the derived layer.",
            "applies_to": "plot_info1_plot_access1_label",
        },
        {
            "priority": 3,
            "measure": "Remap contaminated tree_species_language_code cells; never auto-delete tree rows.",
            "applies_to": "trees.tree_species_language_code",
        },
        {
            "priority": 4,
            "measure": "Coerce measurement columns to numeric; keep original text in a _raw companion if needed.",
            "applies_to": "tree_dbh, tree_height, coordinates",
        },
        {
            "priority": 5,
            "measure": "Strip/collapse whitespace and control characters only in derived keys used for joins and maps.",
            "applies_to": "all text join keys and labels",
        },
        {
            "priority": 6,
            "measure": "Document Clensed Data folder spelling; rename only with IT/backup approval.",
            "applies_to": "paths.clean_data",
        },
        {
            "priority": 7,
            "measure": "Do not overwrite cleansed Excel or shapefiles; publish corrections in validated/ only.",
            "applies_to": "all sources",
        },
    ])

    summary = (
        findings_df.groupby(["issue", "severity"], dropna=False)
        .agg(n_findings=("observed", "count"), n_rows_affected=("n_rows", "sum"))
        .reset_index()
        if len(findings_df) else pd.DataFrame()
    )
    return {"findings": findings_df, "correction_measures": measures, "summary": summary}


def field_type_audit(tables: dict[str, pd.DataFrame], cfg: dict | None = None) -> pd.DataFrame:
    """
    Detect columns that look numeric but remain object, or codes stored as floats.
    """
    rows = []
    hints = EXPECTED_NUMERIC_HINTS
    cols_map = (cfg or {}).get("columns", {})
    extra = [cols_map.get("dbh"), cols_map.get("height"), cols_map.get("lat_field"), cols_map.get("lon_field")]
    for tname, df in tables.items():
        if df is None or len(df) == 0:
            continue
        want = set(hints.get(tname, [])) | {c for c in extra if c}
        for col in df.columns:
            s = df[col]
            # float codes that should often be ints / labels
            if col.endswith("_label") is False and s.dtype == float:
                if s.dropna().apply(lambda x: float(x).is_integer()).all() and s.nunique(dropna=True) <= 20:
                    rows.append({
                        "table": tname, "column": col, "observed_dtype": str(s.dtype),
                        "issue": "float_coded_category",
                        "proposed": "keep code; prefer companion _label for graphs",
                        "n_non_null": int(s.notna().sum()),
                        "correction_measure": "Plot with the _label column; treat numeric codes as categories, not continuous.",
                    })
            if col in want or col in hints.get(tname, []):
                if s.dtype == object or str(s.dtype) == "string":
                    coerced = pd.to_numeric(s, errors="coerce")
                    bad = int(s.notna().sum() - coerced.notna().sum())
                    rows.append({
                        "table": tname, "column": col, "observed_dtype": str(s.dtype),
                        "issue": "numeric_stored_as_text" if bad == 0 else "numeric_with_non_numeric_tokens",
                        "proposed": "to_numeric(errors='coerce') in derived layer",
                        "n_non_null": int(s.notna().sum()),
                        "n_non_numeric_tokens": bad,
                        "correction_measure": "Coerce to float in derived frames; quarantine non-numeric tokens for review.",
                    })
            # object columns that are mostly numeric
            if s.dtype == object:
                sample = s.dropna().astype(str).head(500)
                if len(sample) >= 20:
                    frac_num = sample.str.match(r"^-?\d+(\.\d+)?$").mean()
                    if frac_num >= 0.9:
                        rows.append({
                            "table": tname, "column": col, "observed_dtype": "object",
                            "issue": "mostly_numeric_object",
                            "proposed": "to_numeric in derived layer",
                            "n_non_null": int(s.notna().sum()),
                            "pct_numeric_tokens": round(100 * frac_num, 1),
                            "correction_measure": "Likely a measurement/code stored as text; coerce for analysis.",
                        })
    return pd.DataFrame(rows)


def cleaning_guide_notes() -> pd.DataFrame:
    """Operator-facing guide for the cleaning stage (display in notebook)."""
    return pd.DataFrame([
        {
            "step": "1. Inventory findings first",
            "theme": "process",
            "guidance": "Read spelling, illegal characters, field contamination, and type mismatches before changing anything.",
            "example": "Innaccessible on access labels; vernacular names inside language_code",
            "why_it_matters": "Skipping inventory hides how widespread a typo is and what graphs will distort.",
            "graph_hint": "Start EDA only after reviewing findings severity and n_rows.",
        },
        {
            "step": "2. Sources stay immutable",
            "theme": "governance",
            "guidance": "Never overwrite cleansed Excel or shapefiles. Corrections live only in derived / validated layers and StageStore.",
            "example": "validated/aseer_plots_derived_clean.csv",
            "why_it_matters": "Audit trail for NFI reporting and reversible re-runs.",
            "graph_hint": "Tag figure captions as derived-clean when labels were corrected.",
        },
        {
            "step": "3. Prefer labels over numeric codes",
            "theme": "graphing",
            "guidance": "Plot *_label fields (access, owner, LUCC, condition, agents). Codes are categories, never continuous axes.",
            "example": "plot_info1_owner1_label instead of plot_info1_owner1",
            "why_it_matters": "Float-coded categories create false numeric scales on axes.",
            "graph_hint": "Frequency bars, stacked bars, and boxplots-by-category all need labels.",
        },
        {
            "step": "4. Fix spelling in derived labels",
            "theme": "lexical",
            "guidance": "Apply known typo maps on derived copies only (access labels, place-name reporting aliases).",
            "example": "Innaccessible -> Inaccessible; Aseer -> Asir (reporting)",
            "why_it_matters": "Split categories inflate accessibility counts and break legends.",
            "graph_hint": "Compare access-label value counts before vs after in the cleaning cell.",
        },
        {
            "step": "5. Strip illegal characters and whitespace",
            "theme": "characters",
            "guidance": "Remove control characters, trim edges, collapse repeated spaces in text columns.",
            "example": "embedded tabs/newlines in notes2 or vernacular names",
            "why_it_matters": "Invisible characters break joins, filters, and Folium/tooltips.",
            "graph_hint": "Clean text before species or notes presence charts.",
        },
        {
            "step": "6. Coerce wrong field types explicitly",
            "theme": "types",
            "guidance": "DBH, height, crown diameters, and coordinates: pd.to_numeric(..., errors='coerce'). Count failed tokens.",
            "example": "tree_dbh stored as object with stray letters",
            "why_it_matters": "Object dtypes silently drop from histograms, KDE, and FV formulas.",
            "graph_hint": "Rebuild FV distribution suites only after numeric coercion.",
        },
        {
            "step": "7. Quarantine field contamination",
            "theme": "contamination",
            "guidance": "Vernacular text inside language_code is remapped to missing; do not delete the tree row.",
            "example": "Arabic species name sitting in tree_species_language_code",
            "why_it_matters": "Contaminated codes corrupt language pie charts and species language filters.",
            "graph_hint": "Use tree_species_vernacular_name for vernacular frequency; language_code for ISO-like codes only.",
        },
        {
            "step": "8. Qualifiers and free-text notes",
            "theme": "descriptive",
            "guidance": "Keep Arabic/English qualifiers and notes2 as free text; graph presence flags or top tokens, not raw dumps.",
            "example": "plot_info1_plot_access1_qualifier, plot_info1_owner1_qualifier, notes2",
            "why_it_matters": "High-cardinality free text overwhelms legends; presence still informs accessibility QC.",
            "graph_hint": "has_access_qualifier / has_owner_qualifier / has_field_notes dashboards.",
        },
        {
            "step": "9. Coordinate and survey descriptors",
            "theme": "spatial",
            "guidance": "Use coord_source and coord_confidence from plot QA for spatial trust graphs; coerce lat/lon numerics.",
            "example": "field GPS vs database coordinates",
            "why_it_matters": "Maps and displacement metrics need trusted numeric coordinates.",
            "graph_hint": "Bars for coord_source; boxplot of coord_displacement_m by access label.",
        },
        {
            "step": "10. Document residual risk",
            "theme": "methods",
            "guidance": "Arabic qualifier variants and unlisted spellings stay as-is until an authority synonym list is approved.",
            "example": "multiple Arabic phrasings for the same access barrier",
            "why_it_matters": "Honest methods notes for inventory reports and model cards.",
            "graph_hint": "Footnote residual label risk on accessibility and ownership figures.",
        },
    ])


def apply_derived_cleaning(df: pd.DataFrame, *, kind: str = "generic") -> pd.DataFrame:
    """
    Build a derived cleaned frame: spelling fixes, whitespace, control chars,
    numeric coercion for known measurement columns. Sources untouched.
    """
    out = df.copy()
    label_map = {k: v["proposed"] for k, v in LABEL_CORRECTIONS.items()}
    place_map = {k: v["proposed"] for k, v in PLACE_NAME_CORRECTIONS.items()}
    text_map = {**label_map, **place_map}

    for col in out.columns:
        if out[col].dtype == object or str(out[col].dtype) == "string":
            s = out[col].astype(str)
            # preserve true nulls
            mask_null = out[col].isna()
            s = s.str.replace(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", regex=True)
            s = s.str.strip().str.replace(r"  +", " ", regex=True)
            s = s.replace(text_map)
            # language-code contamination: vernacular -> NA
            if col.lower() in {"tree_species_language_code", "species_language_code", "language_code"}:
                bad = ~s.str.lower().isin(LANGUAGE_CODE_ALLOWED | {"nan", "none", "<na>"})
                s = s.mask(bad, other=pd.NA)
            out[col] = s
            out.loc[mask_null, col] = pd.NA

    # numeric coercion for measurement-like columns present in frame
    for col in [
        "tree_dbh", "tree_height", "crown_diameterl1", "crown_diameterl2",
        "tree_bole_height", "years_since_cut",
        "plot_info1_plot_coor1_x", "plot_info1_plot_coor1_y",
        "plot_info1_coor_db_x", "plot_info1_coor_db_y",
        "dbh_cm", "height_m", "coord_displacement_m", "time_record1_days_no",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out["_cleaning_layer"] = f"derived_{kind}"
    return out


def apply_reporting_text_aliases(series: pd.Series) -> pd.Series:
    """Derived-layer helper: map known place-name and label variants to proposed forms."""
    mapping = {k: v["proposed"] for k, v in {**PLACE_NAME_CORRECTIONS, **LABEL_CORRECTIONS}.items()}
    out = series.astype(str)
    return out.replace(mapping)


def build_cleaning_corrections_report(
    raw_tables: dict[str, pd.DataFrame],
    clean_tables: dict[str, pd.DataFrame],
    *,
    max_examples: int = 8,
) -> pd.DataFrame:
    """
    After derived cleaning: list every observed correction class with counts.
    Covers spelling/label maps, whitespace/control-char cleanup, language-code
    quarantine, and numeric coercion of mixed text/number cells.
    """
    rows: list[dict] = []
    label_map = {k: v["proposed"] for k, v in LABEL_CORRECTIONS.items()}
    place_map = {k: v["proposed"] for k, v in PLACE_NAME_CORRECTIONS.items()}
    text_map = {**label_map, **place_map}
    issue_meta = {**LABEL_CORRECTIONS, **PLACE_NAME_CORRECTIONS}

    for tname, raw in raw_tables.items():
        clean = clean_tables.get(tname)
        if raw is None or clean is None or len(raw) == 0:
            continue
        # Align on index position (same row order from apply_derived_cleaning copy)
        n = min(len(raw), len(clean))
        raw_i = raw.iloc[:n]
        clean_i = clean.iloc[:n]

        for col in raw_i.columns:
            if col not in clean_i.columns:
                continue
            s0 = raw_i[col]
            s1 = clean_i[col]

            # Spelling / place / label replacements
            if s0.dtype == object or str(s0.dtype) == "string":
                as0 = s0.astype(str)
                for observed, proposed in text_map.items():
                    n_hit = int((as0 == observed).sum())
                    if n_hit:
                        meta = issue_meta.get(observed, {})
                        rows.append({
                            "table": tname,
                            "column": col,
                            "correction_class": meta.get("issue", "label_or_place_map"),
                            "observed": observed,
                            "corrected_to": proposed,
                            "n_cells": n_hit,
                            "examples": observed,
                            "action": meta.get("action", "CORRECT_IN_DERIVED_LABEL"),
                            "rationale": meta.get("rationale", ""),
                        })

                # Control characters / trailing whitespace cleaned
                mask_nonnull = s0.notna()
                raw_txt = as0.where(mask_nonnull, other="")
                stripped = (
                    raw_txt.str.replace(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", regex=True)
                    .str.strip()
                    .str.replace(r"  +", " ", regex=True)
                )
                char_changed = mask_nonnull & (raw_txt != stripped)
                # exclude pure spelling map hits already counted
                mapped = as0.isin(text_map.keys())
                char_only = char_changed & ~mapped
                n_char = int(char_only.sum())
                if n_char:
                    ex = raw_txt.loc[char_only].head(max_examples).tolist()
                    rows.append({
                        "table": tname,
                        "column": col,
                        "correction_class": "whitespace_or_control_characters",
                        "observed": "leading/trailing spaces, repeated spaces, or control chars",
                        "corrected_to": "trimmed / control chars removed",
                        "n_cells": n_char,
                        "examples": " | ".join(repr(x)[:40] for x in ex),
                        "action": "STRIP_IN_DERIVED_LAYER",
                        "rationale": "Invisible characters and messy whitespace break joins and legends.",
                    })

                # Language-code contamination
                if col.lower() in {"tree_species_language_code", "species_language_code", "language_code"}:
                    bad = mask_nonnull & ~as0.str.lower().isin(LANGUAGE_CODE_ALLOWED | {"nan", "none", "<na>"})
                    n_bad = int(bad.sum())
                    if n_bad:
                        ex_vals = as0.loc[bad].value_counts().head(max_examples)
                        rows.append({
                            "table": tname,
                            "column": col,
                            "correction_class": "characters_or_text_mixed_in_code_field",
                            "observed": "; ".join(f"{k} (n={v})" for k, v in ex_vals.items()),
                            "corrected_to": "<NA> (quarantine; vernacular belongs in vernacular_name)",
                            "n_cells": n_bad,
                            "examples": "; ".join(ex_vals.index.astype(str)[:max_examples]),
                            "action": "QUARANTINE_DO_NOT_DELETE_ROW",
                            "rationale": "Vernacular / free text sitting inside a language-code column.",
                        })

            # Numeric coercion: mixed text with measurements
            if col in {
                "tree_dbh", "tree_height", "crown_diameterl1", "crown_diameterl2",
                "tree_bole_height", "years_since_cut",
                "plot_info1_plot_coor1_x", "plot_info1_plot_coor1_y",
                "plot_info1_coor_db_x", "plot_info1_coor_db_y",
                "dbh_cm", "height_m", "coord_displacement_m", "time_record1_days_no",
            } or (s0.dtype == object and pd.to_numeric(s0, errors="coerce").notna().mean() > 0.5):
                coerced = pd.to_numeric(s0, errors="coerce")
                # values that were non-null text but became NaN, or object -> numeric success
                was_object = s0.dtype == object or str(s0.dtype) == "string"
                if was_object:
                    failed = s0.notna() & coerced.isna()
                    succeeded = s0.notna() & coerced.notna()
                    # only report if dtype actually changed or failures exist
                    if int(failed.sum()) or (succeeded.any() and str(s1.dtype) != str(s0.dtype)):
                        ex_fail = s0.loc[failed].astype(str).head(max_examples).tolist()
                        rows.append({
                            "table": tname,
                            "column": col,
                            "correction_class": "wrong_field_type_or_mixed_text_numeric",
                            "observed": f"dtype={s0.dtype}; non-numeric tokens={int(failed.sum())}",
                            "corrected_to": f"dtype={s1.dtype}; coerced with errors='coerce'",
                            "n_cells": int(succeeded.sum()) + int(failed.sum()),
                            "examples": " | ".join(ex_fail) if ex_fail else "numeric tokens coerced",
                            "action": "TO_NUMERIC_IN_DERIVED_LAYER",
                            "rationale": "Measurement/coordinate fields must be numeric for graphs and FV formulas.",
                        })

    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["correction_class", "n_cells"], ascending=[True, False]).reset_index(drop=True)
    return out


def build_ready_clean_deliverable(
    trees_clean: pd.DataFrame,
    plot_clean: pd.DataFrame,
    asir_su,
    *,
    trees_fv: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Build ready-to-use cleaned tables for maps and presentation graphs.
    Applies reporting aliases on region labels (Aseer->Asir, Ar Riyad->Ar Riyadh).
    """
    su = asir_su.drop(columns="geometry", errors="ignore").copy()
    if "SU_UID" not in su.columns and "SU" in su.columns:
        su["SU_UID"] = make_su_uid(su["SU"])
    su["SU_UID"] = make_su_uid(su["SU_UID"])
    if "reg_e" in su.columns:
        su["region_source"] = su["reg_e"]
        su["region"] = apply_reporting_text_aliases(su["reg_e"])
    if "gover_e" in su.columns:
        su["governorate_source"] = su["gover_e"]
        su["governorate"] = apply_reporting_text_aliases(su["gover_e"])

    plots = plot_clean.copy()
    plots["SU_UID"] = make_su_uid(plots["SU_UID"]) if "SU_UID" in plots.columns else plots.get("SU_UID")
    su_cols = [c for c in ["SU_UID", "region", "region_source", "governorate", "governorate_source", "Area_H", "Area_H_attr"] if c in su.columns]
    if "Area_H" not in su.columns and "Area_H_attr" in su.columns:
        pass
    plots_ready = plots.merge(su[su_cols].drop_duplicates("SU_UID"), on="SU_UID", how="left")
    plots_ready["_ready_for_maps"] = True
    plots_ready["_ready_for_graphs"] = True

    trees = (trees_fv if trees_fv is not None else trees_clean).copy()
    trees["SU_UID"] = make_su_uid(trees["SU_UID"]) if "SU_UID" in trees.columns else trees.get("SU_UID")
    plot_keep = [c for c in [
        "PLOT_UID", "plot_info1_plot_access1_label", "plot_info1_owner1_label",
        "coord_source", "coord_confidence", "coord_displacement_m",
        "lat_validated", "lon_validated", "notes2",
        "region", "region_source", "governorate", "governorate_source",
    ] if c in plots_ready.columns]
    if "PLOT_UID" in trees.columns and plot_keep:
        trees_ready = trees.merge(
            plots_ready[plot_keep].drop_duplicates("PLOT_UID"),
            on="PLOT_UID", how="left", suffixes=("", "_plot"),
        )
    else:
        trees_ready = trees.merge(su[su_cols].drop_duplicates("SU_UID"), on="SU_UID", how="left")
    trees_ready["_ready_for_maps"] = True
    trees_ready["_ready_for_graphs"] = True

    # SU roll-up ready table (one row per SU) for choropleths / SU-number graphics
    su_ready = su.copy()
    if "region" not in su_ready.columns and "reg_e" in su_ready.columns:
        su_ready["region"] = apply_reporting_text_aliases(su_ready["reg_e"])
    tree_counts = (
        trees_ready.groupby("SU_UID", dropna=False).size().rename("n_tree_records").reset_index()
        if "SU_UID" in trees_ready.columns else pd.DataFrame(columns=["SU_UID", "n_tree_records"])
    )
    plot_counts = (
        plots_ready.groupby("SU_UID", dropna=False).size().rename("n_plots").reset_index()
        if "SU_UID" in plots_ready.columns else pd.DataFrame(columns=["SU_UID", "n_plots"])
    )
    su_ready = su_ready.merge(tree_counts, on="SU_UID", how="left").merge(plot_counts, on="SU_UID", how="left")
    su_ready["n_tree_records"] = su_ready["n_tree_records"].fillna(0).astype(int)
    su_ready["n_plots"] = su_ready["n_plots"].fillna(0).astype(int)
    su_ready["has_tree_record"] = su_ready["n_tree_records"] > 0
    su_ready["_ready_for_maps"] = True
    su_ready["_ready_for_graphs"] = True

    by_region = (
        su_ready.groupby("region", dropna=False)
        .agg(
            n_su=("SU_UID", "nunique"),
            n_with_trees=("has_tree_record", "sum"),
            n_tree_records=("n_tree_records", "sum"),
            n_plots=("n_plots", "sum"),
        )
        .reset_index()
        .sort_values("n_su", ascending=False)
    )
    by_region["n_gate1_zero_tree_su"] = by_region["n_su"] - by_region["n_with_trees"]
    by_region["_ready_for_graphs"] = True

    return {
        "su_ready": su_ready,
        "plots_ready": plots_ready,
        "trees_ready": trees_ready,
        "by_region": by_region,
    }


def _story_print(title: str, paragraphs: list[str]) -> None:
    """Readable console story blocks for notebook operators."""
    bar = "=" * 72
    print(bar)
    print(title)
    print(bar)
    for p in paragraphs:
        print(p)
        print()


def _format_correction_examples(sub: pd.DataFrame, *, max_examples: int = 4) -> list[str]:
    """Build 'observed → corrected' example lines from a corrections slice."""
    if sub is None or len(sub) == 0:
        return []
    lines: list[str] = []
    ordered = sub.sort_values("n_cells", ascending=False)
    for _, r in ordered.head(max_examples).iterrows():
        obs = str(r.get("observed", "")).strip()
        to = str(r.get("corrected_to", "")).strip()
        # Prefer concrete sample tokens when the observed field is a class description
        ex = str(r.get("examples", "") or "").strip()
        if ex and (
            obs.lower().startswith("leading/")
            or obs.lower().startswith("dtype=")
            or "control char" in obs.lower()
        ):
            # examples may be pipe- or semicolon-separated snippets
            first = ex.split("|")[0].split(";")[0].strip()
            if first:
                obs = first
        n = int(r.get("n_cells", 0) or 0)
        tbl = str(r.get("table", ""))
        col = str(r.get("column", ""))
        if len(obs) > 72:
            obs = obs[:69] + "…"
        if len(to) > 72:
            to = to[:69] + "…"
        lines.append(f"    · {tbl}.{col}: “{obs}” → “{to}”  (n={n:,})")
    return lines


def narrate_cleaning_story(
    corrections: pd.DataFrame,
    lex_findings: pd.DataFrame | None = None,
    type_findings: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Professional data-quality memorandum for the notebook: issues found,
    derived-layer corrections with concrete before→after examples, and the
    full corrections log (source Excel / shapefiles remain unchanged).
    """
    try:
        from IPython.display import display
    except ImportError:
        display = print  # type: ignore

    n_rules = int(len(corrections)) if corrections is not None else 0
    n_cells = int(corrections["n_cells"].sum()) if n_rules and "n_cells" in corrections.columns else 0
    n_lex = int(len(lex_findings)) if lex_findings is not None else 0
    n_types = int(len(type_findings)) if type_findings is not None else 0
    n_classes = (
        int(corrections["correction_class"].nunique())
        if n_rules and "correction_class" in corrections.columns
        else 0
    )

    paragraphs = [
        "Purpose. Document lexical, character, and field-type defects in the Asir "
        "analytical extract, and record every derived-layer correction applied before "
        "maps, legends, or statistical figures are trusted. Source workbooks and "
        "shapefiles are never overwritten; cleaned frames carry `_cleaning_layer`.",
        "Issues identified. Field crews and desk entry produced free-text labels with "
        "English spelling errors, inconsistent capitalisation, near-duplicate access "
        "notes, intermittent control characters / irregular whitespace, and - in other "
        "slices - mixed alphanumeric tokens in measurement columns. An inventory scan "
        f"recorded {n_lex} lexical/character finding(s) and {n_types} field-type finding(s).",
        f"Action taken. Derived cleaning applied {n_rules} rule(s) across {n_classes} "
        f"correction class(es), touching approximately {n_cells:,} cell(s). The sections "
        "below state the analytic risk for each class, give concrete before→after "
        "examples from this run, then display the full corrections log and class roll-up "
        "for methods notes.",
    ]
    _story_print(
        "DERIVED-LAYER DATA QUALITY MEMORANDUM - Asir analytical tables",
        paragraphs,
    )

    if n_rules == 0:
        print(
            "No cell-level corrections were required in this slice. "
            "Review the lexical and field-type inventories before publishing legends."
        )
        display(corrections)
        return corrections

    class_briefs = {
        "english_spelling": (
            "English spelling defects in categorical labels. Untreated typos fragment "
            "categories (e.g. accessibility) and inflate bar counts / choropleth classes."
        ),
        "transliteration_variant": (
            "Place-name transliteration variants. Reporting aliases align legends while "
            "`region_source` retains the GIS spelling."
        ),
        "transliteration_incomplete": (
            "Incomplete Latin place spellings standardised for reporting consistency."
        ),
        "whitespace_or_control_characters": (
            "Leading/trailing spaces, repeated spaces, or non-printable control characters. "
            "These break exact-match filters, joins, and map tooltip text."
        ),
        "characters_or_text_mixed_in_code_field": (
            "Free text (often vernacular names) stored inside a language-code column. "
            "Values were quarantined to missing; rows were retained."
        ),
        "wrong_field_type_or_mixed_text_numeric": (
            "Measurement or coordinate fields containing non-numeric tokens. Values were "
            "coerced to numeric in the derived layer so distributions and FV formulas can run."
        ),
        "inconsistent_capitalisation": (
            "Inconsistent title/sentence case in desk-study and access notes. Normalised "
            "so categorical summaries do not split on case alone."
        ),
        "near_duplicate_phrase": (
            "Near-duplicate free-text phrases with the same operational meaning. Aliased "
            "in the derived notes after pattern confirmation."
        ),
        "label_or_place_map": (
            "Authority label / place map applied in the derived layer."
        ),
        "possible_truncated_transliteration": (
            "Possible truncated transliteration - confirm against the authority list "
            "before further aliasing."
        ),
    }

    summary = (
        corrections.groupby("correction_class", dropna=False)
        .agg(n_rules=("column", "count"), n_cells=("n_cells", "sum"))
        .reset_index()
        .sort_values("n_cells", ascending=False)
    )

    print("-" * 72)
    print("CORRECTION CLASSES - analytic risk and worked examples")
    print("-" * 72)
    for _, r in summary.iterrows():
        cls = str(r["correction_class"])
        brief = class_briefs.get(
            cls,
            "Correction applied in the derived layer; see the log for observed values.",
        )
        print(
            f"\n[{cls}]  {int(r['n_rules'])} rule(s) · {int(r['n_cells']):,} cell(s)"
        )
        print(f"  Issue. {brief}")
        print("  Examples from this run:")
        ex_lines = _format_correction_examples(
            corrections.loc[corrections["correction_class"] == cls]
        )
        if ex_lines:
            print("\n".join(ex_lines))
        else:
            print("    · (no row-level examples available)")
    print()

    print("-" * 72)
    print("FULL CORRECTIONS LOG")
    print("-" * 72)
    display(corrections)
    print()
    print("ROLL-UP BY CORRECTION CLASS")
    display(summary)

    print()
    print("-" * 72)
    print("HIGHEST-VOLUME LINE ITEMS (by cells affected)")
    print("-" * 72)
    top = corrections.sort_values("n_cells", ascending=False).head(10)
    for i, (_, r) in enumerate(top.iterrows(), start=1):
        print(
            f"  {i:>2}. [{r.get('table')}.{r.get('column')}]  "
            f"“{r.get('observed')}”  →  “{r.get('corrected_to')}”  "
            f"(n={int(r.get('n_cells', 0)):,}; class={r.get('correction_class')})"
        )
    print()
    print(
        "Memorandum complete. Source files unchanged; consume derived frames marked "
        "`_cleaning_layer` for maps and graphs."
    )
    print("=" * 72)
    return corrections


def narrate_ready_deliverable_story(ready: dict[str, pd.DataFrame]) -> None:
    """Narrate the ready-clean tables for maps and graphs."""
    try:
        from IPython.display import display
    except ImportError:
        display = print  # type: ignore

    by_region = ready.get("by_region", pd.DataFrame())
    su_ready = ready.get("su_ready", pd.DataFrame())
    plots_ready = ready.get("plots_ready", pd.DataFrame())
    trees_ready = ready.get("trees_ready", pd.DataFrame())

    n_su = len(su_ready)
    n_plots = len(plots_ready)
    n_trees = len(trees_ready)
    n_reg = len(by_region)
    top_reg = ""
    if len(by_region) and "region" in by_region.columns and "n_su" in by_region.columns:
        r0 = by_region.sort_values("n_su", ascending=False).iloc[0]
        top_reg = f" The largest share of SUs sits in {r0['region']} ({int(r0['n_su'])} units)."

    paragraphs = [
        "Story so far: spelling, character, and type issues are corrected in derived layers. "
        "We now join cleaned plots and trees to the Asir SU master and publish ready tables "
        "that maps and graphs should consume.",
        f"Ready deliverable holds {n_su:,} SUs, {n_plots:,} plots, and {n_trees:,} tree rows "
        f"across {n_reg} reporting regions.{top_reg}",
        "Region names on these tables use reporting aliases (Asir, Ar Riyadh) while region_source "
        "keeps the GIS/source spelling. Flags _ready_for_maps and _ready_for_graphs mark rows safe "
        "for cartography and the statistical figure pack.",
        "Read the complete clean region table first, then skim SU / plot / tree heads. "
        "SU-number graphics that follow use the same colours as the map legend.",
    ]
    _story_print("READY CLEAN STORY - tables for maps and graphs", paragraphs)

    print("COMPLETE CLEAN TABLE: SU counts by reporting region")
    display(by_region)
    print("SU-ready head (complete columns available in validated CSV)")
    display(su_ready.head(20))
    print("Plots-ready head")
    display(plots_ready.head(12))
    show = [c for c in [
        "SU_UID", "PLOT_UID", "region", "governorate",
        "tree_or_stump_label", "tree_species_scientific_name",
        "plot_info1_plot_access1_label", "plot_info1_owner1_label",
        "tree_dbh", "tree_height", "_cleaning_layer", "_ready_for_graphs",
    ] if c in trees_ready.columns]
    print("Trees-ready head (key columns)")
    display(trees_ready[show].head(12) if show else trees_ready.head(12))
    print("=" * 72)


def narrate_region_su_story(by_region: pd.DataFrame, *, region_col: str = "region", su_col: str = "n_su") -> None:
    """Short story for the SU-number graphics section."""
    try:
        from IPython.display import display
    except ImportError:
        display = print  # type: ignore

    df = by_region.copy()
    if region_col not in df.columns and "reg_e" in df.columns:
        region_col = "reg_e"
    total = int(pd.to_numeric(df[su_col], errors="coerce").fillna(0).sum()) if su_col in df.columns else 0
    paragraphs = [
        "Beyond the map legend, analysts need a compact numeric view of how many "
        "sampling units sit in each administrative region on the Asir grid.",
        f"Across the displayed regions we count {total:,} sampling units. "
        "The single-row board shows counts, regional share, and (where available) "
        "tree-present versus Gate 1 zero-tree composition, using the same colour "
        "language as the cartography legend "
        "(Al Bahah, Ar Riyad/Ar Riyadh, Aseer/Asir, Jazan, Makkah Al Mukarramah, Najran).",
        "Use this board in slides when a full map is too heavy; keep the map for spatial context.",
    ]
    _story_print("REGION SU BOARD: numbers beside the map", paragraphs)
    display(df)
