# -*- coding: utf-8 -*-
"""Fix V6_Improved: clarify Asir subset charts; unblock E7 LULC conflicts; harden E8-E13 + Part C."""

from __future__ import annotations

import json
from pathlib import Path

NB = Path(__file__).resolve().parent / "NFI_GeoAI_Comprehensive_Expanded_V6_Improved.ipynb"


def as_src(text: str) -> list[str]:
    return [ln + "\n" for ln in text.strip("\n").split("\n")]


def main() -> None:
    nb = json.loads(NB.read_text(encoding="utf-8"))
    cells = nb["cells"]

    # --- Intro: clarify Part A chart vs Kingdom ---
    cells[0]["source"] = as_src(
        """# KSA NFI GeoAI Comprehensive Expanded Pipeline V6 (Improved)

## Critical note on scope

This notebook **preserves the full analytical depth** of `NFI_GeoAI_Data_Preparation_V4_Refined.ipynb` (Part A below). It does **not** replace that workflow with a smaller demo.

| Part | Scope | Primary outputs |
| --- | --- | --- |
| **A** (preserved) | **Asir GIS 430-SU analytical frame** (Gate 1/2 case study). Charts such as "SU by region" show only regions that intersect this frame (often ~6 labels, Aseer-dominant). **Not** the full Kingdom. | `outputs/` |
| **B** (expansion) | National LULC Validation + calc-doc tree/shrub biomass on cleansed national tables | `outputs/expansion/` |
| **C** (national) | **Entire Kingdom** tabular universe (all regions in the SU master; ~3,671 SU) | `outputs_national_v5/` |

### Google Colab: run order for the entire Kingdom

1. Runtime → Connect (Copy to Drive if the GitHub open is read-only).
2. Run **Colab / portable bootstrap**.
3. For **all of KSA**, jump to **PART C** (N0 to N5) after bootstrap, or Run All (Part A stays Asir-only by design).
4. Open `outputs_national_v5/maps/html_atlas/index.html` from N4.

**National user guide:** `NFI_National_GeoPipeline_Guide_V5.ipynb`

**Shareable national HTML products** (after Part C):
- Report: `outputs_national_v5/documents/NFI_national_geopipeline_report.html`
- Atlas: `outputs_national_v5/maps/html_atlas/index.html`
"""
    )

    # --- Section 5 markdown: Asir subset note ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "markdown" and "## 5 · Regional roll-ups" in src:
            cells[i]["source"] = as_src(
                """<a id="s5"></a>

## 5 · Regional roll-ups and SU-number graphics

Builds region and governorate tables from the **Asir GIS anti-clip lattice (430 SU)**, then draws SU-count graphics.

**Important:** This is a **subset**, not all of KSA. Only administrative regions that intersect the Asir analytical grid appear (commonly Aseer plus neighbouring fringe SUs such as Makkah, Najran, Jazan, Al Bahah, Ar Riyad). For **all 13 regions / ~3,671 SU**, run **PART C** (national pipeline) or the National Guide notebook.
"""
            )
            break

    # --- Patch section 5 code with explicit callout ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if "SECTION 5 · REGIONAL ROLL-UPS" in src and "plot_region_su_dashboard" in src:
            if "Asir GIS 430-SU subset" not in src:
                cells[i]["source"] = as_src(
                    src.rstrip()
                    + """

callout("info", "Asir GIS 430-SU subset",
        "This board is <b>not</b> the national inventory. It summarises the Asir analytical frame (430 SU). "
        "Aseer dominates because the GIS master is Asir-centred. For every KSA region, continue to <b>PART C</b>.")
"""
                )
            break

    # --- E7: resolve conflicts instead of hard stop ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "code" and "lulc_conflicting_plot_keys" in src:
            cells[i]["source"] = as_src(
                r"""# E7 · Land-use proportions by SU (Final LULC)
# A few plot keys can carry conflicting final_lulc rows (field forest label vs ESA/ESRI).
# Do not halt the national expansion: log conflicts, then resolve with a documented rule.

_lulc_keys = ['su_no', 'plot_no']
_required = _lulc_keys + ['final_lulc', 'lon', 'lat', 'validation_true', 'inside_forest_reserved']
_missing = sorted(set(_required) - set(lulc.columns))
if _missing:
    raise KeyError(f'LULC source missing required fields: {_missing}')

_conflicts = (lulc.groupby(_lulc_keys, dropna=False)['final_lulc'].nunique(dropna=False))
_conflicts = _conflicts[_conflicts > 1]
(EXP_OUT / 'tables').mkdir(parents=True, exist_ok=True)
if len(_conflicts):
    _conflicts.rename('n_distinct_classes').to_csv(EXP_OUT / 'tables' / 'lulc_conflicting_plot_keys.csv')
    print(f'NOTE: {len(_conflicts)} plot keys have conflicting final_lulc labels.')
    print('Resolution rule: prefer validation_true==True, then field_forest_label source, else first row after stable sort.')
    print('Conflicts written to', EXP_OUT / 'tables' / 'lulc_conflicting_plot_keys.csv')

# Stable sort so drop_duplicates is reproducible after priority ranking
_work = lulc.copy()
_work['_prio'] = 0
if 'validation_true' in _work.columns:
    _work.loc[_work['validation_true'] == True, '_prio'] += 2
if 'final_lulc_source' in _work.columns:
    _work.loc[_work['final_lulc_source'].astype(str).str.contains('field_forest', case=False, na=False), '_prio'] += 1
_work = _work.sort_values(_lulc_keys + ['_prio'], ascending=[True, True, False])

_keep_cols = [c for c in ['su_no', 'plot_no', 'final_lulc', 'lon', 'lat', 'validation_true', 'inside_forest_reserved', 'final_lulc_source'] if c in _work.columns]
plot_lulc = _work.drop_duplicates(_lulc_keys, keep='first')[_keep_cols].copy()

lu = land_use_proportion_by_su(plot_lulc, 'su_no', 'final_lulc', CFG['project']['plots_per_su_design'])
display(lu.head(20))
lu.to_csv(EXP_OUT / 'tables' / 'national_land_use_proportion_by_su.csv', index=False)
share = plot_lulc['final_lulc'].value_counts(normalize=True).rename('plot_share').to_frame()
share['n_plots'] = plot_lulc['final_lulc'].value_counts()
display(share.head(15))
share.to_csv(EXP_OUT / 'tables' / 'national_final_lulc_plot_share.csv')
print('plot_lulc rows', len(plot_lulc), 'SU with proportions', lu['su_no'].nunique() if 'su_no' in lu.columns else len(lu))
print('SU area not stated in calc doc: SU totals requiring area remain BLOCKED.')
"""
            )
            break

    # --- E10: soft skip without esda / insufficient points ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "code" and "global_moran_i" in src and "ESDA points" in src:
            cells[i]["source"] = as_src(
                r"""# E10 · ESDA (optional). Skips cleanly when libpysal/esda are missing or support is thin.
mi = {'status': 'skipped', 'reason': 'not_run'}
gi = {'status': 'skipped', 'reason': 'not_run'}

plot_uid_col = None
if 'plot_plot_id1' in trees_m.columns:
    trees_m['plot_uid'] = trees_m['su_key'] + '-' + trees_m['plot_plot_id1'].astype(str).str.strip()
    plot_uid_col = 'plot_uid'

pts = plot_lulc.copy()
pts['su_key'] = pts['su_no'].astype(str).str.strip()
su_c = trees_m.groupby('su_key')['carbon_mg_provisional'].mean().rename('mean_c_su')
pts = pts.merge(su_c, left_on='su_key', right_index=True, how='left')

_su_points = pts.copy()
for _coord in ('lon', 'lat'):
    _su_points[_coord] = pd.to_numeric(_su_points[_coord], errors='coerce')
_su_points = (_su_points.dropna(subset=['mean_c_su', 'lon', 'lat'])
              .groupby('su_key', as_index=False)
              .agg(lon=('lon', 'mean'), lat=('lat', 'mean'), mean_c_su=('mean_c_su', 'first')))

try:
    from nfi_esda_expanded import points_gdf, global_moran_i, getis_ord_gi_star
except Exception as e:
    print('ESDA modules unavailable; skipping spatial autocorrelation.', e)
else:
    if len(_su_points) < 9:
        print(f'ESDA skipped: only {len(_su_points)} SUs with coordinates/carbon (need >=9).')
        mi = {'status': 'skipped', 'reason': 'insufficient_su'}
    else:
        try:
            gdf = points_gdf(_su_points, 'lon', 'lat')
            print('ESDA points', len(gdf))
            mi = global_moran_i(gdf, 'mean_c_su', k_neighbors=8)
            print(mi)
            pd.DataFrame([mi]).to_csv(EXP_OUT / 'tables' / 'esda_global_moran_mean_c_su.csv', index=False)
            gi = getis_ord_gi_star(gdf, 'mean_c_su', k_neighbors=8)
            print('Gi*', gi.get('status'), gi.get('reason'))
            if gi.get('status') == 'ok':
                gi['gdf'][['su_key', 'mean_c_su', 'gi_star', 'gi_p']].to_csv(
                    EXP_OUT / 'tables' / 'esda_gi_star_mean_c_su.csv', index=False
                )
        except Exception as e:
            print('ESDA failed; continuing without spatial stats.', e)
            mi = {'status': 'error', 'reason': str(e)}
"""
            )
            break

    # --- E11: soft guards ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "code" and "optimism_gap_rmse" in src and "GroupKFold" in src:
            cells[i]["source"] = as_src(
                r"""# E11 · Height model with SU-blocked CV (soft-fail if sample is thin)
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupKFold, KFold
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

gap = None
cv = pd.DataFrame()
X = trees_m[[dbh_col]].to_numpy()
y = trees_m[ht_col].to_numpy()
groups = trees_m['su_key'].astype(str).to_numpy()

def cv_scores(splitter, X, y, groups=None):
    rows = []
    splits = splitter.split(X, y, groups) if groups is not None else splitter.split(X, y)
    for fold, (tr, te) in enumerate(splits, 1):
        rf = RandomForestRegressor(n_estimators=200, random_state=RS, n_jobs=-1, min_samples_leaf=5)
        rf.fit(X[tr], y[tr])
        pred = rf.predict(X[te])
        rows.append({
            'fold': fold,
            'r2': float(r2_score(y[te], pred)),
            'rmse': float(np.sqrt(mean_squared_error(y[te], pred))),
            'mae': float(mean_absolute_error(y[te], pred)),
        })
    return pd.DataFrame(rows)

if len(trees_m) < 10 or trees_m['su_key'].nunique() < 5:
    print('Height CV skipped: need >=10 trees and >=5 SUs.')
elif not (np.isfinite(X).all() and np.isfinite(y).all()):
    print('Height CV skipped: non-finite measurements present.')
else:
    rand = cv_scores(KFold(5, shuffle=True, random_state=RS), X, y)
    grp = cv_scores(GroupKFold(5), X, y, groups)
    rand['scheme'] = 'random_kfold'
    grp['scheme'] = 'group_kfold_su'
    cv = pd.concat([rand, grp], ignore_index=True)
    display(cv.groupby('scheme')[['r2', 'rmse', 'mae']].mean())
    gap = float(grp.rmse.mean() - rand.rmse.mean())
    print('optimism_gap_rmse (group - random)', gap)
    cv.to_csv(EXP_OUT / 'tables' / 'ml_height_cv_random_vs_group.csv', index=False)
    pd.DataFrame([{'optimism_gap_rmse': gap}]).to_csv(EXP_OUT / 'tables' / 'ml_optimism_gap.csv', index=False)
"""
            )
            break

    # --- E12: guard pts ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "code" and "map_lulc_acceptance.png" in src:
            cells[i]["source"] = as_src(
                r"""# E12 · Cartography on LULC / carbon surfaces
(EXP_OUT / 'maps').mkdir(parents=True, exist_ok=True)

fig, ax = plt.subplots(figsize=(9, 8), dpi=130)
sc = ax.scatter(
    plot_lulc['lon'], plot_lulc['lat'],
    c=plot_lulc['validation_true'].astype(int),
    s=4, cmap='RdYlGn', alpha=0.4,
)
plt.colorbar(sc, ax=ax, label='validation_true (1=accepted)')
ax.set_title('Map: national LULC acceptance at office points')
ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(EXP_OUT / 'maps' / 'map_lulc_acceptance.png', dpi=200)
plt.show()
plt.close(fig)

if 'pts' not in globals():
    pts = plot_lulc.copy()
    pts['su_key'] = pts['su_no'].astype(str).str.strip()
    su_c = trees_m.groupby('su_key')['carbon_mg_provisional'].mean().rename('mean_c_su')
    pts = pts.merge(su_c, left_on='su_key', right_index=True, how='left')

fig, ax = plt.subplots(figsize=(9, 8), dpi=130)
m = pts['mean_c_su'].notna() if 'mean_c_su' in pts.columns else pd.Series(False, index=pts.index)
if m.any():
    sc = ax.scatter(pts.loc[m, 'lon'], pts.loc[m, 'lat'], c=pts.loc[m, 'mean_c_su'], s=6, cmap='YlGn', alpha=0.5)
    plt.colorbar(sc, ax=ax, label='SU mean provisional tree carbon (Mg)')
else:
    ax.scatter(plot_lulc['lon'], plot_lulc['lat'], s=4, c='#94a3b8', alpha=0.4)
    ax.set_title('Map: no SU carbon join available')
ax.set_title('Map: SU mean provisional carbon (sample; not design-based)')
ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(EXP_OUT / 'maps' / 'map_su_mean_provisional_carbon.png', dpi=200)
plt.show()
plt.close(fig)
"""
            )
            break

    # --- E13: tolerate missing mi/gap ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "code" and "expansion_run_summary.json" in src:
            cells[i]["source"] = as_src(
                r"""summary = {
    'project': CFG['project']['name'],
    'preserved_foundation': 'NFI_GeoAI_Data_Preparation_V4_Refined.ipynb (Part A = Asir 430-SU subset)',
    'national_kingdom_block': 'PART C / outputs_national_v5',
    'lulc_key_numbers': kn if 'kn' in globals() else None,
    'n_trees_metrics': int(len(trees_m)) if 'trees_m' in globals() else None,
    'shrub_note': shrub_note if 'shrub_note' in globals() else 'not processed',
    'esda_moran': mi if 'mi' in globals() else {'status': 'not_run'},
    'optimism_gap_rmse': gap if 'gap' in globals() else None,
    'lulc_conflict_keys': int(len(_conflicts)) if '_conflicts' in globals() else None,
    'policy': CFG.get('policy'),
    'limitations': [
        'Part A regional SU board is the Asir GIS 430-SU frame, not all KSA regions.',
        'Design-based national totals blocked without weights/SU area.',
        'Carbon labeled provisional (calc-doc constants).',
        'Shrub log base assumed natural (open question).',
        'Conflicting LULC plot keys are resolved by validation_true / field_forest preference and logged.',
        'ESDA and height CV skip cleanly when packages or sample support are insufficient.',
    ],
}
(EXP_OUT / 'logs').mkdir(parents=True, exist_ok=True)
(EXP_OUT / 'logs' / 'expansion_run_summary.json').write_text(
    json.dumps(summary, indent=2, default=str), encoding='utf-8'
)
print(json.dumps(summary, indent=2, default=str))
print('V6 expansion block complete. Continue to PART C for the entire Kingdom.')
"""
            )
            break

    # --- E7 markdown note ---
    for i, c in enumerate(cells):
        src = "".join(c.get("source") or [])
        if c.get("cell_type") == "markdown" and "## E7 · Land-use proportions" in src:
            cells[i]["source"] = as_src(
                """## E7 · Land-use proportions by SU using Final LULC (calc doc section 5)

Uses the national LULC validation table. If a few plot keys carry conflicting `final_lulc` labels, conflicts are **logged and resolved** (prefer `validation_true`, then field forest source) so the expansion can continue. This is still plot-level LULC evidence, not the Asir 430-SU Gate board from Part A.
"""
            )
            break

    NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Updated", NB.name, "cells", len(cells))


if __name__ == "__main__":
    main()
