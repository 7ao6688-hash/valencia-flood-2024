"""Buildings whose footprint centre falls on flooded pixels."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from rasterio.transform import rowcol


def read_buildings(path: str, bbox_lonlat: tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    return gpd.read_file(path, bbox=bbox_lonlat)


def exposed_buildings(buildings: gpd.GeoDataFrame, mask: np.ndarray, transform, crs) -> gpd.GeoDataFrame:
    projected = buildings.to_crs(crs)
    centres = projected.geometry.representative_point()
    rows, cols = rowcol(transform, centres.x.to_numpy(), centres.y.to_numpy())
    rows, cols = np.asarray(rows), np.asarray(cols)
    inside = (rows >= 0) & (rows < mask.shape[0]) & (cols >= 0) & (cols < mask.shape[1])
    hit = np.zeros(len(projected), dtype=bool)
    hit[inside] = mask[rows[inside], cols[inside]]
    out = projected.loc[hit].copy()
    out["footprint_m2"] = out.geometry.area
    return out
