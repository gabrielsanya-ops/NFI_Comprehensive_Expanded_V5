"""Tree/shrub formulas from NFI_ KSA Calculation_Trees&shrubs.docx (extract)."""

from __future__ import annotations

import numpy as np
import pandas as pd

FORM_FACTOR = 0.65
WOOD_DENSITY = 0.6
BEF = 2.0
ROOT_SHOOT = 0.28
CARBON_FRACTION = 0.47
CO2EQ_FACTOR = 3.67
CONVERSION_FACTOR_HA = 10

TREE_EXCLUDE = ("calotropis", "palm", "grass")
SHRUB_EXCLUDE = ("grass",)


def basal_area_m2(dbh_cm):
    dbh = np.asarray(dbh_cm, dtype=float)
    return (np.pi * dbh**2) / 40000.0


def tree_volume_m3(dbh_cm, height_m, form_factor=FORM_FACTOR):
    return basal_area_m2(dbh_cm) * np.asarray(height_m, dtype=float) * form_factor


def tree_agb_mg(dbh_cm, height_m, wood_density=WOOD_DENSITY, bef=BEF, form_factor=FORM_FACTOR):
    return tree_volume_m3(dbh_cm, height_m, form_factor) * wood_density * bef


def tree_bgb_mg(agb_mg, root_shoot=ROOT_SHOOT):
    return np.asarray(agb_mg, dtype=float) * root_shoot


def total_biomass_mg(agb_mg, bgb_mg):
    return np.asarray(agb_mg, dtype=float) + np.asarray(bgb_mg, dtype=float)


def carbon_mg(total_biomass, carbon_fraction=CARBON_FRACTION):
    return np.asarray(total_biomass, dtype=float) * carbon_fraction


def co2eq_mg(carbon, factor=CO2EQ_FACTOR):
    return np.asarray(carbon, dtype=float) * factor


def exclude_by_substrings(series: pd.Series, substrings) -> pd.Series:
    s = series.astype(str).str.lower()
    keep = pd.Series(True, index=series.index)
    for sub in substrings:
        keep &= ~s.str.contains(str(sub).lower(), na=False)
    return keep


def apply_tree_metrics(df: pd.DataFrame, dbh_col: str, height_col: str) -> pd.DataFrame:
    out = df.copy()
    dbh = pd.to_numeric(out[dbh_col], errors="coerce")
    ht = pd.to_numeric(out[height_col], errors="coerce")
    out["basal_area_m2"] = basal_area_m2(dbh)
    out["volume_m3"] = tree_volume_m3(dbh, ht)
    out["agb_mg"] = tree_agb_mg(dbh, ht)
    out["bgb_mg"] = tree_bgb_mg(out["agb_mg"])
    out["total_biomass_mg"] = total_biomass_mg(out["agb_mg"], out["bgb_mg"])
    out["carbon_mg_provisional"] = carbon_mg(out["total_biomass_mg"])
    out["co2eq_mg_provisional"] = co2eq_mg(out["carbon_mg_provisional"])
    return out


def shrub_agb_mg(mean_cd_m, height_cm):
    """Document equation; natural log assumed (open question in extract)."""
    cd = np.asarray(mean_cd_m, dtype=float)
    h = np.asarray(height_cm, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw = np.exp(-0.37 + 1.903 * np.log(cd) + 0.652 * np.log(h)) + 1.403
    return raw / 1000.0


def _pick_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    for c in df.columns:
        cl = c.lower()
        for cand in candidates:
            if cand.lower() in cl:
                return c
    return None


def shrub_height_to_cm(height: pd.Series, unit_name: pd.Series | None = None) -> pd.Series:
    """Convert shrub height to cm per calc extract (H = tree_height_cm from metres).

    When unit is missing, values with median < 20 are treated as metres (x100).
    """
    h = pd.to_numeric(height, errors="coerce")
    out = h.copy()
    if unit_name is not None:
        u = unit_name.astype(str).str.lower()
        is_m = u.str.contains("m", na=False) & ~u.str.contains("cm", na=False)
        is_cm = u.str.contains("cm", na=False)
        out = np.where(is_cm, h, np.where(is_m, h * 100.0, out))
        out = pd.Series(out, index=height.index, dtype=float)
        unknown = ~(is_m | is_cm)
        if unknown.any():
            med = h.loc[unknown].median(skipna=True)
            if pd.notna(med) and med < 20:
                out.loc[unknown] = h.loc[unknown] * 100.0
            else:
                out.loc[unknown] = h.loc[unknown]
        return out
    med = h.median(skipna=True)
    if pd.notna(med) and med < 20:
        return h * 100.0
    return h


def apply_shrub_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Word-doc shrub AGB/BGB/carbon chain (provisional per-individual).

    Field names in cleansed shrubs_bushes.xlsx: crown_diam1, crown_diam2, sh_height.
    Calc extract also names crown_diameterl1 / crown_diameterl2 / tree_height_cm.
    """
    out = df.copy()
    cd1 = _pick_col(out, ("crown_diam1", "crown_diameterl1", "crown_diameter1"))
    cd2 = _pick_col(out, ("crown_diam2", "crown_diameterl2", "crown_diameter2"))
    ht = _pick_col(out, ("sh_height", "tree_height_cm", "tree_height", "height"))
    unit = _pick_col(out, ("sh_height_unit_name", "height_unit", "sh_height_unit"))
    if cd1 is None or cd2 is None or ht is None:
        raise KeyError(
            "apply_shrub_metrics needs crown diameter pair and height columns; "
            f"found cd1={cd1}, cd2={cd2}, ht={ht}; columns={list(out.columns)}"
        )
    d1 = pd.to_numeric(out[cd1], errors="coerce")
    d2 = pd.to_numeric(out[cd2], errors="coerce")
    out["mean_CD_m"] = (d1 + d2) / 2.0
    unit_s = out[unit] if unit is not None else None
    out["height_cm"] = shrub_height_to_cm(out[ht], unit_s)
    ok = out["mean_CD_m"].gt(0) & out["height_cm"].gt(0)
    out["agb_mg"] = np.nan
    out.loc[ok, "agb_mg"] = shrub_agb_mg(out.loc[ok, "mean_CD_m"], out.loc[ok, "height_cm"])
    out["bgb_mg"] = tree_bgb_mg(out["agb_mg"])
    out["total_biomass_mg"] = total_biomass_mg(out["agb_mg"], out["bgb_mg"])
    out["carbon_mg_provisional"] = carbon_mg(out["total_biomass_mg"])
    # Shrub CO2eq not stated in calc doc; leave blank intentionally.
    out["co2eq_mg_provisional"] = np.nan
    out["shrub_metric_ok"] = ok
    return out.loc[ok].copy()


def land_use_proportion_by_su(plot_lulc: pd.DataFrame, su_col: str, class_col: str, plots_per_su: int = 5):
    d = plot_lulc[[su_col, class_col]].copy()
    d[su_col] = d[su_col].astype(str).str.strip()
    counts = d.groupby([su_col, class_col], dropna=False).size().rename("n_plots").reset_index()
    counts["land_use_proportion"] = counts["n_plots"] / float(plots_per_su)
    return counts
