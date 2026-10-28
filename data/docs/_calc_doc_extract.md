# NFI KSA Calculation: Trees and Shrubs (document extract)

Source: `F:\1.KSA\29.NFI\NFI_ KSA Calculation_Trees&shrubs.docx`

Extraction notes:
- Extracted with python-docx / document.xml OMML parsing.
- Document contains **0 tables** and **0 embedded images**.
- Many OMML equations appear **duplicated twice** in the Word XML (same formula repeated). Duplicates are collapsed below to one copy.
- Some formulas are **split** across adjacent paragraphs (LHS in OMML, RHS in plain text, or reordered). Where reconstruction is needed, the literal fragments are shown first, then a reconstructed form labeled as such. Unclear items are marked `[UNCLEAR]`.
- Output uses only hyphens (-), commas, colons, and parentheses (no em/en dashes).

---

## Document title and scope

- **Title:** NATIONAL FOREST INVENTORY
- **Subtitle:** Data Analysis and Mapping Workflow

Workflow sections in the source (1 to 8) cover OpenForis import/export, QC, joins, land-use area, tree analysis, and shrub analysis.

---

## 1. Upstream workflow (non-formula context)

### 1.1 Import / export
1. Import regional data into OpenForis in Collect format.
2. Export required data from OpenForis as CSV files.

### 1.2 QC: Land Use / Land Cover (3.1)
Check LULC using:
- Google Earth
- Plot photographs
- Vegetation cover data
- Tree and shrub data
- NDAI
- Forest reservation layers
- Rang land layers
- Other layers

Also:
- Check consistency between land use and field observations.
- Aggregate similar land-use classes such as `((other -other land), )Annual Crop- Fallow land (` `[UNCLEAR: sentence appears truncated in source]`

### 1.3 QC: Trees, Shrubs and Natural Regeneration (3.2)
- Check DBH.
- Check tree height.
- Check blank or missing values.
- Check scientific species names.
- Check tree and stem records.
- Check abnormal or inconsistent measurements.

### 1.4 QC: Vegetation Cover (3.3)
- Check vegetation cover values.
- Make sure vegetation cover is consistent with the number of trees and shrubs recorded in the plot.
- From Collect Earth: fill `(TOF _distribution, herbaceous, plant residue and crop residue)` to complete the dataset `(if passible)` [source spelling].

### 1.5 Join main data files (4)
After data are correct and logical, join using plot/sample-unit identifiers:
- `LUCS + Plot`
- `(LUCS + Plot) + Trees`
- `(LUCS + Plot) + Shrubs`
- `(LUCS + Plot) + Natural Regeneration`
- `(LUCS + Plot) + Dead Wood`
- `(LUCS + Plot) + Litter`
- `(LUCS + Plot) + vegetation cover`

---

## 2. Land-use area formulas (section 5)

**Definition / sampling design stated:** For each sampling unit, the proportion of each land-use class is calculated based on the **five plots** within the sampling unit.

### Formulas (literal)

```
Land Use Proportion = Number of plots representing the Land Use Class ÷ 5 plots
```

```
Land Use Area within Sampling Unit = Land Use Proportion × Area of the Sampling Unit
```

```
Total Land Use Area = Σ Land Use Area of all Sampling Units
```

Process is repeated separately for each land-use class to obtain total estimated area for the analysis region.

**Units:** Area of Sampling Unit not given a numeric value in this document. `[UNCLEAR: Sampling Unit Area value/units not stated here]`

---

## 3. Tree analysis (section 6)

### 3.1 Scope and calculation chain

- Tree analysis is conducted at the **individual tree level**.
- Chain (literal):

```
Tree → Tree Basal area → Tree Volume → Above-Ground Biomass (AGB) → Below-Ground Biomass (BGB) → Total Biomass → Carbon Stock → CO₂ equivalent
```

Aggregation chain for density / composition:

```
Individual Tree → Plot → Trees/ha → Average of 5 Plots → Sampling Unit
```

### 3.2 Tree record filters / exclusions (tree-vs-shrub treatment)

**Include / select:**
- Valid **live-tree** records.
- Filter column: `(tree-stump)`
- For volume/biomass/carbon: also filter `(overall tree condition)`

**Exclude:**
- Grass and records not required for live-tree analysis.
- Explicit examples named: `(Calotropis)` and `(Palm trees)`

**Other tree processing notes:**
- Add sample units with zero trees to sample units with trees using ArcGIS.
- Create Pivot Table (or equivalent) with Sampling Unit as main grouping variable.
- Calculate for each sampling unit by spaces: Number of trees, Tree density, Species composition, Basal area, Volume, Biomass, Carbon, CO₂ equivalent.

### 3.3 Tree density formulas

**Literal OMML:**

```
average tree Density = (total trees in 5 plot) / (5)
```

```
SU tree Density(ha) = (total trees in 5 plot) / (5) × conversion factor
```

**Conversion factor for trees (section 6.4):**
- For tree calculation, sample area = **1000 (m²) = 0.1 (ha)**
- **conversion factor = 10**

### 3.4 Tree biometric inputs (data records)

- `DBH` (data record)
- `Tree height` (data record)

**Units for DBH in basal-area formula:** implied by divisor 40000 as DBH in **cm** when BA is in m² (standard). Source does not explicitly state DBH units. `[UNCLEAR: DBH unit not explicitly written; 40000 implies cm]`

**Units for height:** stated as `tree height(m)` in volume formula text.

### 3.5 R1. Basal area

**Literal OMML (source spelling "Besal"):**

```
Besal Area(m²) = (π × (DBH)²) / (40000)
```

**Normalized spelling for clarity (same formula):**

```
Basal Area (m²) = (π × (DBH)²) / 40000
```

**Unit:** m²

### 3.6 R2. Tree volume

**Literal fragments as stored (order in XML is fragmented):**
- Plain text near formula: `× tree height(m) × form factor`
- OMML: `Tree volume = Besal Area(m²)`
- Label: `R2. Tree volume`

**Reconstructed formula (from fragments + label; do not treat as invented beyond combining adjacent source pieces):**

```
Tree volume = Basal Area (m²) × tree height (m) × form factor
```

**Form factor (constant):**
- **form factor = 0.65**
- Source: "base on FRA report Saudi Arabia 2015"

**Implied unit:** m³ (used later as `tree volume (m³)`)

### 3.7 R3. Above-ground biomass (AGB)

**Literal fragments:**
- Plain text: `= tree volume (m³) × wood density × biomass expansion factor`
- OMML label: `ABG(Mg)` (source abbreviation **ABG**, elsewhere **AGB**)
- Label: `R3. Above ground biomass (Mg)`

**Reconstructed:**

```
AGB (Mg)  [source also writes ABG(Mg)] = tree volume (m³) × wood density × biomass expansion factor
```

**Constants:**
- **Wood density = 0.6** (FRA report Saudi Arabia 2015). Unit of wood density not stated. `[UNCLEAR: wood density unit; typically Mg/m³ or t/m³]`
- **Biomass expansion factor (BEF) = 2** (IPCC)

**Unit:** Mg

### 3.8 R4. Below-ground biomass (BGB)

**Method:** vegetation-specific **root:shoot ratio**

**Constant:**
- **root:shoot ratio = 0.28**
- Source: FRA guidelines and specifications (2020) for naturally regenerated tropical dry forest

**Literal / reconstructed:**

```
BGB (Mg) = Above ground biomass × 0.28
```

**Unit:** Mg

### 3.9 Total biomass

Named in the calculation chain (`Total Biomass`) and used in the carbon formula, but **no explicit equation** for Total Biomass appears in the document.

**Implied (not literal):** Total biomass = AGB + BGB. Marked because it is used but not written:

```
Total biomass = AGB + BGB   [UNCLEAR / IMPLIED: not written explicitly in source]
```

### 3.10 R5. Carbon

**Default factors (FRA 2020, naturally regenerated tropical dry forest):**
- **Carbon fraction = 0.47**
- **CO2eq = 3.67** (also used in R6)

**Literal / reconstructed:**

```
Carbon (Mg) = Total biomass × 0.47
```

**Unit:** Mg

### 3.11 R6. CO₂ equivalent

**Literal fragments:**
- Plain: `= × 3.67`
- OMML pieces: `CO₂ equivalent(Mg)`, `Carbon(Mg)`

**Reconstructed:**

```
CO₂ equivalent (Mg) = Carbon (Mg) × 3.67
```

**Unit:** Mg

### 3.12 Convert plot results to hectare (6.4)

**Literal:**

```
Value per hectare = Average value from the five plots × conversion factor
```

Also repeated as:

```
Value per hectare = Average value from the 5 plots × conversion factor
```

With:
- sample area = 1000 m² = 0.1 ha
- conversion factor = 10

### 3.13 Total value for each sampling unit (labeled 7.5 in source)

**Literal:**

```
Total value of Sampling Unit = Value per hectare × Sampling Unit Area
```

Apply for required tree variables.

---

## 4. Shrub analysis (section 8)

### 4.1 Prepare shrub dataset (8.1)

- Check shrub species names.
- Check shrub measurements.
- Check plot and sampling-unit identification.
- **Exclude the grasses**
- Check missing and abnormal values.
- Add SU with zero shrubs.

### 4.2 Indicators to calculate (8.2)

- Shrub density
- Biomass
- Carbon

Aggregation chain:

```
Individual Shrub → Plot → Shrub /ha → Average of 5 Plots → Sampling Unit
```

### 4.3 R1. Shrub density and species composition

**Literal OMML:**

```
average Shrub Density (ha) = (total Shrub in 5 plot) / (5)
```

```
Shrub Density(ha) = (total Shrub in 5 plot) / (5) × conversion factor
```

**Conversion factor for shrubs:**
- **conversion factor = 10** based on the plot area
- Source does **not** explicitly restate shrub plot area as 1000 m². Trees do. `[UNCLEAR: whether shrub plot area is identical 1000 m²; only CF=10 is stated]`

### 4.4 R2.a Shrub above-ground biomass (allometric)

**Literal OMML:**

```
AGB (Mg/ha) = (exp(-0.37 + 1.903 * (log(CD)) + 0.652 * (log(H))) + 1.403) / 1000
```

**Required input variables (literal from source):**
- Height in **cm**: field `tree_height_cm`, calculated from the original variable in meters.
- Mean crown diameter: `mean_CD_m` = mean of `crown_diameterl1` and `crown_diameterl2`.

So in the equation:
- `H` corresponds to height in **cm** (`tree_height_cm`)
- `CD` corresponds to mean crown diameter in **m** (`mean_CD_m`)

**Unit as labeled in equation:** Mg/ha

`[UNCLEAR: equation is written as AGB (Mg/ha) but inputs are per-individual shrub CD and H; document does not state whether this is applied per shrub then expanded, or already a per-ha result. Adjacent text describes individual shrub table fields.]`

**Base of log:** not stated (`log` could be ln or log10). `[UNCLEAR: log base]`

### 4.5 R2.b Shrub below-ground biomass

**Literal OMML:**

```
BGB Mg/ha = AGB × 0.28
```

**Constant:** 0.28 (same root:shoot as trees; tree text cites FRA 2020 tropical dry forest; shrub section does not re-cite).

**Unit:** Mg/ha

### 4.6 R3. Shrub carbon

**Literal OMML (exactly as parsed, including `BGB0`):**

```
carbon Mg/ha = (AGB + BGB0) × 0.47
```

`[UNCLEAR: BGB0 appears in OMML; almost certainly a typo/OCR-like artifact for BGB]`

**Carbon fraction:** 0.47 (same default as trees)

**Unit:** Mg/ha

**Shrub CO₂ equivalent:** not given an explicit formula in the shrub section. `[UNCLEAR / not stated for shrubs]`

### 4.7 Shrub results per hectare and totals (8.3, 8.4)

- Calculate the average result for the five plots within each sampling unit.
- Create Pivot Table with Sampling Unit as main grouping variable.
- Multiply the value per hectare by the area of the sampling unit.
- Calculate for each sampling unit by spaces.
- Source note at end: `Apply this process for required tree variables:` `[UNCLEAR: wording says "tree" inside shrub section]`

---

## 5. Tree vs shrub treatment (summary comparison)

| Topic | Trees | Shrubs |
| --- | --- | --- |
| Analysis grain | Individual tree | Individual shrub (then plot / SU) |
| Live filters | tree-stump; overall tree condition | (not same filters named) |
| Exclusions | grass; Calotropis; Palm trees | grasses |
| Density CF | 10 (plot 1000 m² = 0.1 ha) | 10 (plot area basis; area not restated) |
| Size metrics | DBH, height (m) | mean CD (m), height (cm) |
| Volume | BA × H × form factor 0.65 | not used |
| AGB method | volume × WD 0.6 × BEF 2 | allometric exp/log on CD, H; /1000 |
| BGB | AGB × 0.28 | AGB × 0.28 |
| Carbon | Total biomass × 0.47 | (AGB+BGB) × 0.47 [source BGB0] |
| CO2eq | Carbon × 3.67 | not stated |
| Zero SU handling | add zero-tree SUs via ArcGIS | add SU with zero shrubs |

---

## 6. Constants, thresholds, expansion factors (master list)

| Name | Value | Applies to | Source cited in doc | Notes |
| --- | --- | --- | --- | --- |
| Plots per sampling unit | 5 | LU proportion, density averages | workflow text | design constant |
| Tree plot area | 1000 m² = 0.1 ha | trees | section 6.4 | |
| Tree conversion factor | 10 | trees to per-ha | section 6.4 | 1/0.1 |
| Shrub conversion factor | 10 | shrubs to per-ha | section 8.2 | "based on the plot area" |
| Form factor | 0.65 | tree volume | FRA Saudi Arabia 2015 | |
| Wood density | 0.6 | tree AGB | FRA Saudi Arabia 2015 | unit not stated |
| Biomass expansion factor (BEF) | 2 | tree AGB | IPCC | |
| Root:shoot ratio | 0.28 | tree BGB; shrub BGB | FRA 2020 tropical dry forest (stated under trees) | |
| Carbon fraction | 0.47 | tree carbon; shrub carbon | FRA 2020 tropical dry forest | |
| CO2eq factor | 3.67 | tree CO₂ equivalent | FRA 2020 tropical dry forest | |
| Shrub AGB intercept | -0.37 | shrub allometric | equation only | |
| Shrub AGB CD coeff | 1.903 | shrub allometric | equation only | on log(CD) |
| Shrub AGB H coeff | 0.652 | shrub allometric | equation only | on log(H) |
| Shrub AGB additive term | +1.403 | shrub allometric | equation only | inside (...)+1.403 before /1000 |
| Shrub AGB scale | /1000 | shrub allometric | equation only | |

**Thresholds:** No numeric DBH/height inclusion thresholds (e.g. minimum DBH) are stated in this document. QC says "check DBH / height / abnormal values" without cutoffs. `[UNCLEAR / not present]`

---

## 7. Allometric / structural equations (compact)

### Trees (structural, not species-allometric)

1. `Basal Area (m²) = (π × (DBH)²) / 40000`
2. `Tree volume (m³) = Basal Area (m²) × tree height (m) × 0.65`
3. `AGB (Mg) = tree volume (m³) × 0.6 × 2`
4. `BGB (Mg) = AGB × 0.28`
5. `Carbon (Mg) = Total biomass × 0.47` (Total biomass not explicit)
6. `CO₂ equivalent (Mg) = Carbon × 3.67`

### Shrubs (allometric)

1. `AGB (Mg/ha) = (exp(-0.37 + 1.903 * log(CD) + 0.652 * log(H)) + 1.403) / 1000`
   - with `H = tree_height_cm`, `CD = mean_CD_m`
2. `BGB (Mg/ha) = AGB × 0.28`
3. `carbon (Mg/ha) = (AGB + BGB0) × 0.47` (literal `BGB0`)

---

## 8. Worked examples with numbers

**None found.** The document states constants and symbolic formulas only. No numeric walkthrough (no example DBH/height/CD plugged into a result) appears in paragraphs or tables.

---

## 9. Full paragraph dump (cleaned, formula-relevant order)

Below is a cleaned sequential extract of non-empty paragraphs for audit. Math duplicates collapsed. Em/en dashes not used.

1. NATIONAL FOREST INVENTORY
2. Data Analysis and Mapping Workflow
3. 1. Import the regional data into OpenForis
4. Import the regional data into OpenForis in Collect format.
5. 2. Export the data
6. Export the required data from OpenForis as CSV files.
7. 3. Quality Control and Data Cleaning
8. 3.1 Land Use / Land Cover
9. Check the land use/land cover using: Google Earth; Plot photographs; Vegetation cover data; Tree and shrub data; NDAI; Forest reservation layers; Rang land layers; Other layers
10. Check the consistency between land use and field observations.
11. Aggregate similar land-use classes such as ((other -other land), )Annual Crop- Fallow land ( `[truncated in source]`
12. 3.2 Trees, Shrubs and Natural Regeneration: Check DBH; tree height; blank/missing; scientific names; tree/stem records; abnormal measurements
13. 3.3 Vegetation Cover: check cover; consistency with tree/shrub counts; fill Collect Earth TOF/herbaceous/residue fields if possible
14. 4. Join Main Data Files: LUCS+Plot then Trees, Shrubs, Natural Regeneration, Dead Wood, Litter, vegetation cover
15. 5. Land-use proportion / area / total formulas (see section 2 above)
16. 6. Analysis of Tree Data: individual tree chain BA→Volume→AGB→BGB→Total Biomass→Carbon→CO2eq
17. 6.2 density: average over 5 plots; × conversion factor; live-tree filter tree-stump
18. 6.3 volume/biomass/carbon: filters tree-stump + overall tree condition; exclude grass, Calotropis, Palm trees; R1-R6 formulas (see section 3)
19. 6.3/6.4 pivot by SU; convert with CF=10; plot 1000 m² = 0.1 ha
20. 7.5 Total value SU = value/ha × SU area
21. 8. Shrubs: exclude grasses; density CF=10; allometric AGB; BGB×0.28; carbon×0.47; average of 5 plots; × SU area

---

## 10. Items marked unclear

1. Truncated land-use aggregation sentence.
2. DBH unit not explicit (40000 implies cm).
3. Wood density unit not stated.
4. Total biomass equation not written (only used).
5. Tree volume / AGB / CO2eq OMML fragments reordered; reconstruction from adjacent text.
6. Source uses both `ABG` and `AGB`.
7. Shrub plot area not restated (only CF=10).
8. Shrub AGB labeled Mg/ha while inputs look individual.
9. `log` base for shrub equation not stated.
10. Shrub carbon uses `BGB0` in OMML.
11. Shrub CO2eq formula absent.
12. Shrub section closing line says "tree variables".
13. No numeric inclusion thresholds (min DBH etc.).
14. No worked numeric examples.
15. Sampling Unit Area numeric value not given in this document.
