"""Exploratory spatial data analysis helpers (conditional on available packages)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def points_gdf(df: pd.DataFrame, lon_col: str, lat_col: str, crs: str = "EPSG:4326"):
    import geopandas as gpd
    from shapely.geometry import Point

    d = df.copy()
    d[lon_col] = pd.to_numeric(d[lon_col], errors="coerce")
    d[lat_col] = pd.to_numeric(d[lat_col], errors="coerce")
    d = d.dropna(subset=[lon_col, lat_col])
    gdf = gpd.GeoDataFrame(
        d,
        geometry=[Point(xy) for xy in zip(d[lon_col], d[lat_col])],
        crs=crs,
    )
    return gdf


def global_moran_i(gdf, value_col: str, k_neighbors: int = 8) -> dict:
    """Compute Global Moran's I if libpysal/esda available; else return skipped status."""
    try:
        from esda.moran import Moran
        from libpysal.weights import KNN
    except Exception as e:
        return {"status": "skipped", "reason": f"esda/libpysal unavailable: {e}"}

    d = gdf.dropna(subset=[value_col]).copy()
    if len(d) < max(30, k_neighbors + 2):
        return {"status": "skipped", "reason": f"insufficient points n={len(d)}"}
    y = pd.to_numeric(d[value_col], errors="coerce").to_numpy()
    ok = np.isfinite(y)
    d = d.loc[ok]
    y = y[ok]
    if len(d) < max(30, k_neighbors + 2):
        return {"status": "skipped", "reason": "insufficient finite values"}
    w = KNN.from_dataframe(d, k=k_neighbors)
    w.transform = "R"
    mi = Moran(y, w)
    return {
        "status": "ok",
        "I": float(mi.I),
        "EI": float(mi.EI),
        "p_norm": float(mi.p_norm),
        "z_norm": float(mi.z_norm),
        "n": int(len(y)),
        "k_neighbors": k_neighbors,
        "value_col": value_col,
    }


def getis_ord_gi_star(gdf, value_col: str, k_neighbors: int = 8) -> dict:
    try:
        from esda.getisord import G_Local
        from libpysal.weights import KNN
    except Exception as e:
        return {"status": "skipped", "reason": f"esda/libpysal unavailable: {e}"}

    d = gdf.dropna(subset=[value_col]).copy()
    y = pd.to_numeric(d[value_col], errors="coerce")
    d = d.loc[y.notna()]
    y = y.loc[y.notna()].to_numpy()
    if len(d) < max(30, k_neighbors + 2):
        return {"status": "skipped", "reason": f"insufficient points n={len(d)}"}
    w = KNN.from_dataframe(d, k=k_neighbors)
    w.transform = "R"
    g = G_Local(y, w, star=True)
    out = d.copy()
    out["gi_star"] = g.Zs
    out["gi_p"] = g.p_norm
    return {"status": "ok", "gdf": out, "n": int(len(out))}
