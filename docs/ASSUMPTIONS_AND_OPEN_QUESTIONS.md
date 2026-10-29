# Assumptions and open questions

1. Shrub allometric `log` treated as natural log (Word document does not state base).
2. Total biomass = AGB + BGB (implied by carbon formula; not explicit equation).
3. Wood density treated as Mg/m3 with volume in m3.
4. Sampling Unit Area numeric value not stated in calculation document → SU totals requiring area blocked nationally except where Asir/Makkah grids provide Area_H.
5. Design weights / inclusion probabilities unavailable → design-based national estimates blocked.
6. Remote height products (GEDI/CHM) are corroborative only; not written into official carbon.
7. LULC Final labels from `10.LULC_Validation` are the land-cover authority for expansion land-use proportions.
8. libpysal/esda optional; ESDA cells skip with reason if not installed.
9. National analysis frame is the cleansed SU master (all regions), not the Asir GIS clip.
10. Shrub height field `sh_height` converted to cm when unit is missing and median value is under 20 (treated as metres per calc extract).
11. Shrub CO2eq left blank: not stated in the DOCX shrub section (tree CO2eq uses 3.67).
12. Deadwood, litter, regeneration, vegetation cover: count inventory only until official equations are supplied.
13. Plot table: 18355 rows vs 18354 unique PLOT_UID (duplicate under audit; lattice still uses design 5×SU).
