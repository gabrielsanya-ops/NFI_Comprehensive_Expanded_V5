import math, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nfi_calc_biomass import (
    FORM_FACTOR, WOOD_DENSITY, BEF, ROOT_SHOOT, CARBON_FRACTION, CO2EQ_FACTOR,
    basal_area_m2, tree_volume_m3, tree_agb_mg, tree_bgb_mg, total_biomass_mg, carbon_mg, co2eq_mg, shrub_agb_mg,
)

def test_constants():
    assert FORM_FACTOR == 0.65 and WOOD_DENSITY == 0.6 and BEF == 2.0
    assert ROOT_SHOOT == 0.28 and CARBON_FRACTION == 0.47 and CO2EQ_FACTOR == 3.67

def test_chain():
    dbh, ht = 20.0, 10.0
    ba = basal_area_m2(dbh)
    vol = tree_volume_m3(dbh, ht)
    assert abs(vol - ba * ht * FORM_FACTOR) < 1e-12
    agb = tree_agb_mg(dbh, ht)
    bgb = tree_bgb_mg(agb)
    tot = total_biomass_mg(agb, bgb)
    c = carbon_mg(tot)
    assert abs(co2eq_mg(c) - c * CO2EQ_FACTOR) < 1e-12

def test_shrub():
    assert float(shrub_agb_mg(1.0, 100.0)) > 0


def test_apply_shrub_metrics():
    import pandas as pd
    from nfi_calc_biomass import apply_shrub_metrics
    df = pd.DataFrame({
        "crown_diam1": [1.0, 2.0],
        "crown_diam2": [1.0, 2.0],
        "sh_height": [1.5, 2.0],
        "sh_height_unit_name": [None, None],
        "tree_species_scientific_name": ["Acacia", "grass"],
    })
    out = apply_shrub_metrics(df)
    assert len(out) == 2
    assert "agb_mg" in out.columns
    assert out["height_cm"].iloc[0] == 150.0
    assert out["agb_mg"].notna().all()
