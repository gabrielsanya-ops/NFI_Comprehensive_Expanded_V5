# -*- coding: utf-8 -*-
"""
Height / terrain discrepancy audits and *optional* imputation (default OFF).

Reports:
  - trees with missing / non-observed height
  - potential height errors (unusual values, bole > total, GEDI L2A discrepancy)
  - plots with missing terrain elevation and GEDI ground available
  - row counts that *would* be affected if imputation were executed

Imputation (when explicitly enabled) writes sibling columns only
(``*_imputed`` / ``*_imputation_source``) and never overwrites NFI source fields.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Default gates (overridable)
DEFAULT_HEIGHT_UNUSUAL_MAX_M = 80.0
DEFAULT_GEDI_HEIGHT_ABS_M = 5.0          # |GEDI RH - field P95| beyond this → potential error
DEFAULT_GEDI_HEIGHT_REL = 0.50           # or >50% relative difference
DEFAULT_GEDI_ELEV_ABS_M = 25.0           # terrain discrepancy gate
DEFAULT_GEDI_SUPPORT_M = 30.0


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _is_stump(df: pd.DataFrame) -> pd.Series:
    if "tree_or_stump_label" in df.columns:
        return df["tree_or_stump_label"].astype(str).str.lower().str.contains("stump", na=False)
    if "tree_or_stump" in df.columns:
        return df["tree_or_stump"].astype(str).str.lower().isin({"2", "stump", "s"})
    return pd.Series(False, index=df.index)


def audit_tree_height_discrepancies(
    trees: pd.DataFrame,
    *,
    height_col: str = "tree_height",
    bole_col: str = "tree_bole_height",
    gedi_compare: pd.DataFrame | None = None,
    gedi_rh_col: str = "rh98",
    gedi_support_m: float = DEFAULT_GEDI_SUPPORT_M,
    gedi_abs_m: float = DEFAULT_GEDI_HEIGHT_ABS_M,
    gedi_rel: float = DEFAULT_GEDI_HEIGHT_REL,
    height_unusual_max_m: float = DEFAULT_HEIGHT_UNUSUAL_MAX_M,
) -> dict:
    """
    Flag missing heights and potential errors; summarise imputation candidates.

    Does **not** impute.
    """
    t = trees.copy()
    if height_col not in t.columns:
        return {
            "status": "SKIPPED",
            "reason": f"missing column {height_col}",
            "summary": pd.DataFrame(),
            "candidates": pd.DataFrame(),
        }

    h = _num(t[height_col])
    stump = _is_stump(t)
    live = ~stump

    flags = pd.DataFrame(index=t.index)
    flags["missing_null"] = h.isna()
    # blank / non-numeric that became NaN already covered; also explicit empty strings
    if t[height_col].dtype == object:
        flags["missing_blank"] = t[height_col].astype(str).str.strip().isin({"", "nan", "None", "NA", "N/A", "-"})
    else:
        flags["missing_blank"] = False
    flags["non_positive_live_tree"] = live & h.notna() & (h <= 0)
    flags["unusual_high"] = h.notna() & (h > float(height_unusual_max_m))
    if "height_observed" in t.columns:
        flags["not_observed_flag"] = t["height_observed"].astype("boolean") == False  # noqa: E712
    else:
        flags["not_observed_flag"] = False
    if "eligible_height_analysis" in t.columns:
        flags["ineligible_height_analysis"] = t["eligible_height_analysis"].astype("boolean") == False  # noqa: E712
    else:
        flags["ineligible_height_analysis"] = False

    if bole_col in t.columns:
        bole = _num(t[bole_col])
        flags["bole_exceeds_total"] = h.notna() & bole.notna() & (bole > h + 0.05)
    else:
        flags["bole_exceeds_total"] = False

    # GEDI L2A discrepancy at plot support → mark trees on those plots
    flags["gedi_discrepancy_potential_error"] = False
    flags["gedi_support_available_missing_field"] = False
    gedi_plot_hits = pd.DataFrame()
    if gedi_compare is not None and len(gedi_compare) and "PLOT_UID" in t.columns:
        g = gedi_compare.copy()
        if "gedi_distance_m" in g.columns:
            g = g.loc[_num(g["gedi_distance_m"]) <= float(gedi_support_m)].copy()
        if gedi_rh_col in g.columns and "nfi_height_p95" in g.columns:
            rh = _num(g[gedi_rh_col])
            p95 = _num(g["nfi_height_p95"])
            abs_d = (rh - p95).abs()
            rel_d = abs_d / p95.replace(0, np.nan).abs()
            g["gedi_height_abs_diff_m"] = abs_d
            g["gedi_height_rel_diff"] = rel_d
            g["gedi_discrepancy"] = (
                p95.notna() & rh.notna()
                & ((abs_d >= float(gedi_abs_m)) | (rel_d >= float(gedi_rel)))
            )
            gedi_plot_hits = g.loc[g["gedi_discrepancy"], ["PLOT_UID"]].drop_duplicates()
            if len(gedi_plot_hits):
                bad_plots = set(gedi_plot_hits["PLOT_UID"].astype(str))
                flags["gedi_discrepancy_potential_error"] = t["PLOT_UID"].astype(str).isin(bad_plots)
            # field missing but GEDI RH present at plot
            miss_plots = g.loc[rh.notna() & p95.isna(), "PLOT_UID"].astype(str)
            if len(miss_plots):
                flags["gedi_support_available_missing_field"] = (
                    t["PLOT_UID"].astype(str).isin(set(miss_plots)) & flags["missing_null"]
                )

    # rows needing review / potential imputation of tree_height
    need_fill = (
        flags["missing_null"] | flags["missing_blank"] | flags["non_positive_live_tree"]
        | flags["not_observed_flag"] | flags["gedi_support_available_missing_field"]
    )
    potential_error = (
        flags["unusual_high"] | flags["bole_exceeds_total"]
        | flags["gedi_discrepancy_potential_error"] | flags["non_positive_live_tree"]
    )

    reason_cols = [c for c in flags.columns]
    # build candidate table
    cand = t.copy()
    cand["_tree_height_num"] = h
    for c in reason_cols:
        cand[c] = flags[c].values
    cand["imputation_candidate_tree_height"] = need_fill
    cand["potential_error_tree_height"] = potential_error
    cand["any_height_issue"] = need_fill | potential_error

    def _n(mask) -> int:
        return int(np.asarray(mask).sum())

    summary_rows = [
        {"issue": "missing_null_height", "kind": "gap", "field": height_col,
         "n_rows": _n(flags["missing_null"]),
         "would_impute_if_enabled": True,
         "note": "Null/NaN tree height"},
        {"issue": "missing_blank_height", "kind": "gap", "field": height_col,
         "n_rows": _n(flags["missing_blank"]),
         "would_impute_if_enabled": True,
         "note": "Blank/non-numeric height token"},
        {"issue": "non_positive_live_tree", "kind": "gap_or_error", "field": height_col,
         "n_rows": _n(flags["non_positive_live_tree"]),
         "would_impute_if_enabled": True,
         "note": "Live tree with height ≤ 0 (not stump)"},
        {"issue": "not_observed_flag", "kind": "gap", "field": height_col,
         "n_rows": _n(flags["not_observed_flag"]),
         "would_impute_if_enabled": True,
         "note": "height_observed == False when flag exists"},
        {"issue": "unusual_high_height", "kind": "potential_error", "field": height_col,
         "n_rows": _n(flags["unusual_high"]),
         "would_impute_if_enabled": False,
         "note": f"Height > {height_unusual_max_m} m (flag only; do not auto-replace)"},
        {"issue": "bole_exceeds_total", "kind": "potential_error", "field": bole_col,
         "n_rows": _n(flags["bole_exceeds_total"]),
         "would_impute_if_enabled": False,
         "note": "Bole height exceeds total tree height"},
        {"issue": "gedi_l2a_discrepancy", "kind": "potential_error", "field": height_col,
         "n_rows": _n(flags["gedi_discrepancy_potential_error"]),
         "would_impute_if_enabled": False,
         "note": f"Tree on plot with |GEDI {gedi_rh_col} - field P95| ≥ {gedi_abs_m} m or ≥ {100*gedi_rel:.0f}% (≤{gedi_support_m} m)"},
        {"issue": "gedi_available_field_missing", "kind": "gap", "field": height_col,
         "n_rows": _n(flags["gedi_support_available_missing_field"]),
         "would_impute_if_enabled": True,
         "note": "Field height missing but GEDI L2A RH available at plot support"},
        {"issue": "TOTAL_unique_imputation_candidates", "kind": "summary", "field": height_col,
         "n_rows": _n(need_fill),
         "would_impute_if_enabled": True,
         "note": "Unique tree rows that would receive tree_height_imputed if imputation enabled"},
        {"issue": "TOTAL_unique_potential_errors", "kind": "summary", "field": height_col,
         "n_rows": _n(potential_error),
         "would_impute_if_enabled": False,
         "note": "Unique tree rows flagged for review (not auto-imputed)"},
    ]
    summary = pd.DataFrame(summary_rows)

    return {
        "status": "OK",
        "summary": summary,
        "candidates": cand.loc[cand["any_height_issue"]].copy(),
        "n_trees": int(len(t)),
        "n_imputation_candidates": _n(need_fill),
        "n_potential_errors": _n(potential_error),
        "gedi_discrepant_plots": gedi_plot_hits,
        "imputation_enabled_default": False,
    }


def audit_terrain_height_discrepancies(
    plots: pd.DataFrame,
    *,
    elev_cols: list[str] | None = None,
    gedi_compare: pd.DataFrame | None = None,
    gedi_elev_col: str = "elev_ground",
    gedi_support_m: float = DEFAULT_GEDI_SUPPORT_M,
    gedi_elev_abs_m: float = DEFAULT_GEDI_ELEV_ABS_M,
) -> dict:
    """
    Flag missing plot/terrain elevation and GEDI L2A ground discrepancies.

    Does **not** impute.
    """
    p = plots.copy()
    elev_cols = elev_cols or [
        c for c in [
            "nfi_elevation_m", "elevation", "elev", "altitude", "plot_elevation",
            "dem_elevation_m", "terrain_height_m", "height_asl",
        ]
        if c in p.columns
    ]
    # synthesise working elevation
    elev = pd.Series(np.nan, index=p.index, dtype=float)
    used_col = None
    for c in elev_cols:
        v = _num(p[c])
        if v.notna().any():
            elev = elev.fillna(v)
            used_col = used_col or c
    p["_terrain_elev_m"] = elev
    p["_terrain_elev_source_col"] = used_col

    missing = elev.isna()
    flags = pd.DataFrame(index=p.index)
    flags["missing_field_elevation"] = missing
    flags["gedi_ground_available"] = False
    flags["gedi_terrain_discrepancy"] = False
    flags["imputation_candidate_terrain"] = False

    gedi_join = None
    if gedi_compare is not None and len(gedi_compare) and "PLOT_UID" in p.columns and "PLOT_UID" in gedi_compare.columns:
        g = gedi_compare.copy()
        if "gedi_distance_m" in g.columns:
            g = g.loc[_num(g["gedi_distance_m"]) <= float(gedi_support_m)].copy()
        if gedi_elev_col in g.columns:
            keep = ["PLOT_UID", gedi_elev_col] + (["gedi_distance_m"] if "gedi_distance_m" in g.columns else [])
            gedi_join = g[keep].drop_duplicates("PLOT_UID")
            gedi_join = gedi_join.rename(columns={gedi_elev_col: "_gedi_elev_ground_m"})
            p = p.merge(gedi_join, on="PLOT_UID", how="left")
            flags = flags.reindex(p.index)
            flags["gedi_ground_available"] = _num(p["_gedi_elev_ground_m"]).notna()
            both = _num(p["_terrain_elev_m"]).notna() & flags["gedi_ground_available"]
            diff = (_num(p["_gedi_elev_ground_m"]) - _num(p["_terrain_elev_m"])).abs()
            flags["gedi_terrain_discrepancy"] = both & (diff >= float(gedi_elev_abs_m))
            # impute candidate: missing field elev but GEDI ground present nearby
            flags["imputation_candidate_terrain"] = flags["missing_field_elevation"] & flags["gedi_ground_available"]
            p["gedi_terrain_abs_diff_m"] = diff

    for c in flags.columns:
        p[c] = flags[c].values

    def _n(mask) -> int:
        return int(np.asarray(mask).sum())

    target_field = used_col or "nfi_elevation_m (new)"
    summary = pd.DataFrame([
        {"issue": "missing_field_elevation", "kind": "gap", "field": target_field,
         "n_rows": _n(flags["missing_field_elevation"]),
         "would_impute_if_enabled": True,
         "note": "Plot/terrain elevation missing or not present in cleansed tables"},
        {"issue": "gedi_l2a_ground_available", "kind": "support", "field": "elev_ground",
         "n_rows": _n(flags["gedi_ground_available"]),
         "would_impute_if_enabled": False,
         "note": f"GEDI L2A elev_ground within {gedi_support_m} m of plot"},
        {"issue": "gedi_terrain_discrepancy", "kind": "potential_error", "field": target_field,
         "n_rows": _n(flags["gedi_terrain_discrepancy"]),
         "would_impute_if_enabled": False,
         "note": f"|GEDI ground - field elev| ≥ {gedi_elev_abs_m} m"},
        {"issue": "TOTAL_unique_terrain_imputation_candidates", "kind": "summary",
         "field": target_field,
         "n_rows": _n(flags["imputation_candidate_terrain"]),
         "would_impute_if_enabled": True,
         "note": "Plots that would receive elevation_imputed from GEDI L2A if imputation enabled"},
    ])

    issues = (
        flags["missing_field_elevation"] | flags["gedi_terrain_discrepancy"]
        | flags["imputation_candidate_terrain"]
    )
    return {
        "status": "OK",
        "summary": summary,
        "candidates": p.loc[issues].copy(),
        "n_plots": int(len(p)),
        "n_imputation_candidates": _n(flags["imputation_candidate_terrain"]),
        "n_potential_errors": _n(flags["gedi_terrain_discrepancy"]),
        "elevation_source_col": used_col,
        "imputation_enabled_default": False,
    }


def optional_impute_tree_height(
    trees: pd.DataFrame,
    *,
    enabled: bool = False,
    height_col: str = "tree_height",
    gedi_compare: pd.DataFrame | None = None,
    gedi_rh_col: str = "rh98",
    gedi_support_m: float = DEFAULT_GEDI_SUPPORT_M,
) -> dict:
    """
    Optional tree-height imputation (OFF by default).

    When enabled, fills only sibling columns:
      tree_height_imputed, tree_height_imputation_source
    Never overwrites ``height_col``.
    """
    out = trees.copy()
    out["tree_height_imputed"] = _num(out[height_col]) if height_col in out.columns else np.nan
    out["tree_height_imputation_source"] = pd.Series(pd.NA, index=out.index, dtype="string")

    if not enabled:
        return {
            "status": "DISABLED",
            "frame": out,
            "n_filled": 0,
            "message": "Tree-height imputation DISABLED (optional). No rows modified.",
        }

    # Only fill gaps: null / non-positive live trees
    stump = _is_stump(out)
    h = out["tree_height_imputed"]
    need = h.isna() | ((~stump) & (h <= 0))
    n_before = int(need.sum())
    if gedi_compare is not None and "PLOT_UID" in out.columns and gedi_rh_col in gedi_compare.columns:
        g = gedi_compare.copy()
        if "gedi_distance_m" in g.columns:
            g = g.loc[_num(g["gedi_distance_m"]) <= float(gedi_support_m)]
        gmap = (
            g.dropna(subset=[gedi_rh_col])
            .drop_duplicates("PLOT_UID")
            .set_index("PLOT_UID")[gedi_rh_col]
        )
        fill = out["PLOT_UID"].map(gmap)
        take = need & fill.notna()
        out.loc[take, "tree_height_imputed"] = _num(fill[take])
        out.loc[take, "tree_height_imputation_source"] = f"GEDI_L2A_{gedi_rh_col}"
        n_filled = int(take.sum())
    else:
        n_filled = 0

    return {
        "status": "APPLIED_SIBLING_ONLY",
        "frame": out,
        "n_candidates": n_before,
        "n_filled": n_filled,
        "message": (
            f"Optional imputation filled {n_filled} / {n_before} candidate rows into "
            "tree_height_imputed only (source column untouched)."
        ),
    }


def optional_impute_terrain_height(
    plots: pd.DataFrame,
    *,
    enabled: bool = False,
    gedi_compare: pd.DataFrame | None = None,
    gedi_elev_col: str = "elev_ground",
    gedi_support_m: float = DEFAULT_GEDI_SUPPORT_M,
) -> dict:
    """
    Optional terrain-elevation imputation (OFF by default).

    Writes sibling columns only: elevation_imputed, elevation_imputation_source.
    """
    out = plots.copy()
    # seed from any existing elev-like column
    elev = pd.Series(np.nan, index=out.index, dtype=float)
    for c in ["nfi_elevation_m", "elevation", "elev", "altitude", "plot_elevation"]:
        if c in out.columns:
            elev = elev.fillna(_num(out[c]))
    out["elevation_imputed"] = elev
    out["elevation_imputation_source"] = pd.Series(pd.NA, index=out.index, dtype="string")

    if not enabled:
        return {
            "status": "DISABLED",
            "frame": out,
            "n_filled": 0,
            "message": "Terrain-height imputation DISABLED (optional). No rows modified.",
        }

    need = out["elevation_imputed"].isna()
    n_before = int(need.sum())
    n_filled = 0
    if gedi_compare is not None and "PLOT_UID" in out.columns and gedi_elev_col in gedi_compare.columns:
        g = gedi_compare.copy()
        if "gedi_distance_m" in g.columns:
            g = g.loc[_num(g["gedi_distance_m"]) <= float(gedi_support_m)]
        gmap = (
            g.dropna(subset=[gedi_elev_col])
            .drop_duplicates("PLOT_UID")
            .set_index("PLOT_UID")[gedi_elev_col]
        )
        fill = out["PLOT_UID"].map(gmap)
        take = need & fill.notna()
        out.loc[take, "elevation_imputed"] = _num(fill[take])
        out.loc[take, "elevation_imputation_source"] = "GEDI_L2A_elev_ground"
        n_filled = int(take.sum())

    return {
        "status": "APPLIED_SIBLING_ONLY",
        "frame": out,
        "n_candidates": n_before,
        "n_filled": n_filled,
        "message": (
            f"Optional terrain imputation filled {n_filled} / {n_before} plots into "
            "elevation_imputed only (no source overwrite)."
        ),
    }


def write_imputation_audit(
    tree_audit: dict,
    terrain_audit: dict,
    out_dir: Path,
) -> dict:
    """Persist summary + candidate tables for review."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    if tree_audit.get("summary") is not None and len(tree_audit["summary"]):
        p = out_dir / "tree_height_imputation_candidates_summary.csv"
        tree_audit["summary"].to_csv(p, index=False)
        paths["tree_summary"] = str(p)
    if tree_audit.get("candidates") is not None and len(tree_audit["candidates"]):
        p = out_dir / "tree_height_imputation_candidates_rows.csv"
        # keep a lean export
        cols = [c for c in [
            "SU_UID", "PLOT_UID", "tree_id", "tree_no", "tree_or_stump_label",
            "tree_height", "_tree_height_num",
            "missing_null", "missing_blank", "non_positive_live_tree", "not_observed_flag",
            "unusual_high", "bole_exceeds_total", "gedi_discrepancy_potential_error",
            "gedi_support_available_missing_field",
            "imputation_candidate_tree_height", "potential_error_tree_height",
        ] if c in tree_audit["candidates"].columns]
        tree_audit["candidates"][cols].to_csv(p, index=False)
        paths["tree_rows"] = str(p)
    if terrain_audit.get("summary") is not None and len(terrain_audit["summary"]):
        p = out_dir / "terrain_height_imputation_candidates_summary.csv"
        terrain_audit["summary"].to_csv(p, index=False)
        paths["terrain_summary"] = str(p)
    if terrain_audit.get("candidates") is not None and len(terrain_audit["candidates"]):
        p = out_dir / "terrain_height_imputation_candidates_rows.csv"
        cols = [c for c in [
            "SU_UID", "PLOT_UID", "_terrain_elev_m", "_terrain_elev_source_col",
            "_gedi_elev_ground_m", "gedi_distance_m", "gedi_terrain_abs_diff_m",
            "missing_field_elevation", "gedi_ground_available", "gedi_terrain_discrepancy",
            "imputation_candidate_terrain",
        ] if c in terrain_audit["candidates"].columns]
        terrain_audit["candidates"][cols].to_csv(p, index=False)
        paths["terrain_rows"] = str(p)
    return paths
