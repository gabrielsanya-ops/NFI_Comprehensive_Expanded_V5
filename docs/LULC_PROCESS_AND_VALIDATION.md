# KSA NFI LULC office-point validation

## 1. Objective

Validate the field label int lucs label at office/database plot coordinates using independent 10 m land-cover maps and August 2024 dry NDVI. Write New LCU as the refined description.

## 2. Decision rule

| Field | Rule |
|---|---|
| Validation true | True if int lucs label corresponds to ESA or ESRI or both (codes and official class names) |
| field matches esa and esri | Keep original int lucs label in New LCU |
| field matches esa not esri | Keep original int lucs label in New LCU |
| field matches esri not esa | Keep original int lucs label in New LCU |
| impute level2 esa esri ndvi | Write LUCS Field Manual Level 2 to New LCU |
| inside_forest_reserved_boundary | Office plot inside refined forest reserved polygon: Final LULC / New LCU = Forest |

Worked examples:

- Natural Grassland + ESA Bare/sparse + ESRI Rangeland -> field matches esri not esa, lastcode Natural Grassland.
- Built up area + ESA Bare/sparse + ESRI Built Area -> field matches esri not esa, lastcode Built up area.
- Built up area + ESA Built-up + ESRI Built Area -> field matches esa and esri, lastcode Built up area.
- Built up area + ESA Bare/sparse + ESRI Rangeland -> impute level2 esa esri ndvi, lastcode from Level 2.

Accepted (True): **12,155 (66.2%)**. Updated Final LULC (False): **6,205 (33.8%)**. Inside forest reserves: **152** (Final LULC = Forest).

## 3. Join and generation of plot points

1. `lucs1.xlsx`: rename nfi of ksa program su su no to su no, plot plot id1 to plot no.
2. `plot.xlsx`: same keys; office coordinates plot info1 coor db x/y only (EPSG:4326). Field GPS not used.
3. Exact join on (su no, plot no), many LUCS segments to one plot. Duplicate plot rows dropped (keep first).
4. Unique office points: **18,354** plots, **18,360** LUCS rows.
5. Points written to `office_plot_points.csv` and converted to Earth Engine Point([lon, lat], EPSG:4326).

## 4. Earth Engine sampling

Office points were sampled in Earth Engine at 10 m with reduceRegions and Reducer.first() against ESA WorldCover v200 plus August 2024 Sentinel-2 L2A median NDVI (cloud probability under 40; SCL 3/8/9/10/11 masked). The national mosaic export Saudi 2024 Dry NDVI Median was cancelled; the point sample is the equivalent dry-season NDVI.

Python API used to construct the FeatureCollection and sample:

```python
import ee

ee.Initialize(project="ee-gabrielsanya2")

def fc_from_points(pts):
    feats = []
    for row in pts.itertuples(index=False):
        feats.append(
            ee.Feature(
                ee.Geometry.Point([float(row.lon), float(row.lat)], "EPSG:4326"),
                {
                    "plot_uid": row.plot_uid,
                    "su_no": int(row.su_no),
                    "plot_no": int(row.plot_no),
                },
            )
        )
    return ee.FeatureCollection(feats)

esa = (
    ee.ImageCollection("ESA/WorldCover/v200")
    .first()
    .select("Map")
    .rename("esa_code")
)
stack = esa.addBands(dry_ndvi_median_image())
sampled = stack.reduceRegions(
    collection=fc,
    reducer=ee.Reducer.first(),
    scale=10,
    tileScale=4,
)
```

Equivalent Code Editor script (`office_point_esa_ndvi_sample.js`):

```javascript
// KSA NFI LULC validation: Earth Engine sampling at office plot points
// Operational run used the Earth Engine Python API with the same collections,
// dates, mask, reducer and scale. This is the equivalent Code Editor script.
//
// Inputs
//   plots: ee.FeatureCollection of office/database coordinates (EPSG:4326)
//          properties: plot_uid, su_no, plot_no
// Outputs
//   esa_code: ESA WorldCover v200 Map class at 10 m
//   dry_ndvi_median: August 2024 Sentinel-2 L2A cloud-masked median NDVI

var esa = ee.ImageCollection('ESA/WorldCover/v200')
  .first()
  .select('Map')
  .rename('esa_code');

var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterDate('2024-08-01', '2024-09-01')
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60));

var cp = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY')
  .filterDate('2024-08-01', '2024-09-01');

var joinedS2 = ee.ImageCollection(
  ee.Join.saveFirst('cloud_prob').apply({
    primary: s2,
    secondary: cp,
    condition: ee.Filter.equals({
      leftField: 'system:index',
      rightField: 'system:index'
    })
  })
);

function prepDryNdvi(img) {
  var cloud = ee.Image(img.get('cloud_prob')).select('probability');
  var scl = img.select('SCL');
  var mask = cloud.lt(40)
    .and(scl.neq(3))
    .and(scl.neq(8))
    .and(scl.neq(9))
    .and(scl.neq(10))
    .and(scl.neq(11));
  var ndvi = img.normalizedDifference(['B8', 'B4']).rename('dry_ndvi_median');
  return ndvi.updateMask(mask);
}

var dryNdvi = joinedS2.map(prepDryNdvi)
  .median()
  .rename('dry_ndvi_median')
  .set({
    product: 'Saudi_2024_Dry_NDVI_Median',
    period: '2024-08',
    note: 'Point-sampled equivalent of cancelled national mosaic export'
  });

var stack = esa.addBands(dryNdvi);

// plots must already exist as a FeatureCollection of office lon/lat points.
var sampled = stack.reduceRegions({
  collection: plots,
  reducer: ee.Reducer.first(),
  scale: 10,
  tileScale: 4
});

Map.addLayer(esa, {min: 10, max: 100}, 'ESA WorldCover v200');
Map.addLayer(dryNdvi, {min: 0, max: 0.6, palette: ['#f7f1e1', '#2a9d8f']}, 'Dry NDVI Aug 2024');
Map.addLayer(plots, {color: 'red'}, 'Office plot points');
print('Sampled features', sampled.limit(20));
```

ESRI/IO LULC 2023 was sampled outside Earth Engine, from Planetary Computer io-lulc-annual-v02 at native 10 m in UTM.

## 5. Results

- Corresponds to ESA: **55.6%** (kappa 0.052)
- Corresponds to ESRI: **38.1%** (kappa 0.085)
- Corresponds to both: **27.4%**
- ESA only / ESRI only: **28.2%** / **10.7%**

### Error matrices (compact)

| Comparison | OA | Cohen κ |
|---|---:|---:|
| Field vs ESA | 0.555 | 0.052 |
| Field vs ESRI | 0.381 | 0.085 |
| Field vs Final LULC | 0.662 | 0.505 |

See Section 7 in `LULC_VALIDATION_REPORT.html` and `error_matrices_compact/`.


### Validation rule counts

| Validation rule | Rows | Percent | True | False |
|---|---:|---:|---:|---:|
| field_matches_esa_and_esri | 5,034 | 27.4% | 5,034 | 0 |
| field_matches_esa_not_esri | 5,174 | 28.2% | 5,174 | 0 |
| field_matches_esri_not_esa | 1,966 | 10.7% | 1,966 | 0 |
| impute_level2_esa_esri_ndvi | 6,186 | 33.7% | 0 | 6,186 |

### New LCU distribution

| New LCU | Rows | Percent |
|---|---:|---:|
| Barren Land | 9,967 | 54.3% |
| Natural | 5,824 | 31.7% |
| Natural Grassland | 1,762 | 9.6% |
| Built up area | 376 | 2.0% |
| Wooded grassland | 197 | 1.1% |
| Annual Crop | 163 | 0.9% |
| Cultivated | 33 | 0.2% |
| Other woodedland | 16 | 0.1% |
| Inland water | 8 | 0.0% |
| Lake | 3 | 0.0% |
| Perennial crop | 3 | 0.0% |
| Pond | 3 | 0.0% |
| Natural regenerated forest | 2 | 0.0% |
| Forest | 2 | 0.0% |
| Raffia/Palms - | 1 | 0.0% |

### New LCU among false rows

| New LCU when false | Rows | Percent of false |
|---|---:|---:|
| Natural | 5,824 | 94.1% |
| Wooded grassland | 187 | 3.0% |
| Built up area | 134 | 2.2% |
| Cultivated | 33 | 0.5% |
| Lake | 3 | 0.0% |
| Pond | 3 | 0.0% |
| Natural regenerated forest | 2 | 0.0% |

## 6. Figures

### Workflow

![Workflow](figures/16_workflow.png)

### Processing stack

![Processing stack](figures/08_software_sources.png)

### Accepted versus imputed

![Accepted versus imputed](figures/01_validation_true_false.png)

### Validation rule distribution

![Validation rule distribution](figures/15_validation_rule.png)

### Original field labels

![Original field labels](figures/02_int_lucs_label_distribution.png)

### New LCU

![New LCU](figures/03_final_lulc_distribution.png)

### ESA / ESRI correspondence

![ESA / ESRI correspondence](figures/06_rs_agreement_percent.png)

### Dry NDVI by outcome

![Dry NDVI by outcome](figures/05_ndvi_by_validation.png)

### Level 2 imputations

![Level 2 imputations](figures/07_top_replacements.png)

## 7. Outputs

Single deliverable report:

- `LULC_VALIDATION_REPORT.html` (open locally with `forest_reserved_layers.js` and `saudi_country_admin.js` in the same folder)
- Admin outlines: country black outline and province gray outlines from `F:/1.KSA/shapefile/Admin`

Supporting data:

- Validated table: `lucs_office_validated_esa_esri_ndvi.csv`
- Validated Excel: `lucs_office_validated_esa_esri_ndvi.xlsx`
- Office points: `office_plot_points.csv`, `office_plot_points_validated.gpkg`
- Process note: `PROCESS_AND_VALIDATION.md`
- Earth Engine script: `gee/office_point_esa_ndvi_sample.js`

Word and PDF copies of the report are not maintained. Use the HTML file only.

Imputed names are restricted to LUCS Field Manual Level 2. Accepted names remain the original field wording.


## 8. Spatial forest reserved rule

After the ESA/ESRI/NDVI office-point decision, each plot is tested against the refined forest reserved polygons (topology-corrected national forest reserves).

- If the office/database point falls inside a reserve polygon, Final LULC / New LCU / validation_target = **Forest**.
- validation_rule = `inside_forest_reserved_boundary`.
- final_lulc_source = `forest_reserved_boundary`.
- label_changed = True when the original int lucs label was not Forest.
- Rows inside reserves (after 2026-10-08 NCVC regions + topology-refined national union): **163**. Final LULC Forest count: **742**.
- Forest reserved inventory (original / refined / corrections, with `source` = FAO or NCVC) lives in `../2.Data/Forest_Reserved/Forest_Reserved_Library/`.


## 9. How Final LULC Forest is decided

1. **Inside a forest reserve.** If the sample plot falls inside a forest reserved boundary, Final LULC is Forest.
2. **Outside the reserve, but named Forest in the field.** The Final LULC remains Forest.
3. **Inaccessible plots.** Final LULC is imputed from ESA, ESRI and dry NDVI (Level 2 method). If the field label was already Forest, rule 2 still applies.
4. **All other plots.** Keep the previous ESA/ESRI correspondence or Level 2 imputation.

Field Forest kept: **617**. Inaccessible imputed: **833**. Final Forest total: **742**.
Accuracy panels (inside reserve; outside Final Forest vs ESA/ESRI) are in LULC_VALIDATION_REPORT.html and igures/forest_accuracy/.

## 9. Final LULC Forest priority rules (2026-10-08)

- **Priority 1:** inside forest reserved boundary → Forest (`inside_forest_reserved_boundary`).
- **Priority 2:** field Forest outside reserve → Forest (`field_forest_retained`).
- **Priority 3:** inaccessible (codes 3-7), outside reserve, not field Forest → Level 2 from ESA/ESRI/NDVI (`inaccessible_impute_level2_esa_esri_ndvi`).
- Inside reserve: **163**. Field Forest kept (outside): **581**. Inaccessible imputed: **831**. Final Forest total: **744**.
- Accuracy is Forest-only (inside reserve; outside Final Forest vs ESA/ESRI) in `LULC_VALIDATION_REPORT.html` and `figures/forest_accuracy/`.
