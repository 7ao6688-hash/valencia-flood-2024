"""Sentinel-1 radar flood mapping on the same grid as the Landsat analysis.

Calm water mirrors the radar pulse away from the satellite, so flooded fields turn dark in VV
backscatter. Radar also sees through cloud and at night, which optical imagery cannot. Data are
Sentinel-1 RTC (radiometrically terrain-corrected gamma0, 10 m) from Microsoft Planetary Computer,
averaged onto the 30 m Landsat grid, which also reduces speckle.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-rtc"


def to_db(linear: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10 * np.log10(linear)
    return np.where(np.isfinite(out), out, np.nan)


def boxcar_db(db: np.ndarray, size: int = 3) -> np.ndarray:
    """Mean filter in linear power (simple speckle reduction) that ignores missing pixels."""
    linear = np.where(np.isfinite(db), 10 ** (db / 10), 0.0)
    weight = np.isfinite(db).astype(float)
    pad = size // 2

    def window_sum(x):
        c = np.pad(np.pad(x, pad, mode="edge").cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        return c[size:, size:] - c[:-size, size:] - c[size:, :-size] + c[:-size, :-size]

    with np.errstate(divide="ignore", invalid="ignore"):
        out = to_db(window_sum(linear) / window_sum(weight))
    return np.where(np.isfinite(db), out, np.nan)


def sar_flood_mask(pre_db: np.ndarray, post_db: np.ndarray, threshold_db: float, min_drop_db: float = 3.0) -> np.ndarray:
    """Dark after the event, not dark before, and darker by at least ``min_drop_db``.

    Water that was there before (sea, lake, canals) is dark in both images and drops out, as in the
    optical method.
    """
    seen = np.isfinite(pre_db) & np.isfinite(post_db)
    with np.errstate(invalid="ignore"):
        return seen & (post_db < threshold_db) & (pre_db >= threshold_db) & (post_db - pre_db <= -min_drop_db)


def _items(ids: list[str]) -> dict[str, dict]:
    from .landsat import _get_json

    found = _get_json(f"{STAC}/search", {"collections": ["sentinel-1-rtc"], "ids": ids, "limit": len(ids)})["features"]
    missing = set(ids) - {f["id"] for f in found}
    if missing:
        raise KeyError(f"Sentinel-1 RTC items not found: {', '.join(sorted(missing))}")
    return {f["id"]: f for f in found}


def read_backscatter(frames: list[str], pol: str, transform, shape, crs, cache: Path | None = None) -> np.ndarray:
    """Mosaic one acquisition's frames (adjacent slices of the same pass) onto the target grid, in dB."""
    import rasterio
    from rasterio.warp import Resampling, reproject, transform_bounds
    from rasterio.windows import from_bounds

    path = cache / f"S1_{frames[0][17:32]}_{pol}.npz" if cache else None
    if path is not None and path.exists():
        with np.load(path) as z:
            return z["db"]
    from .landsat import _get_json

    token = _get_json(TOKEN)["token"]
    mosaic = np.full(shape, np.nan, dtype="float32")
    h, w = shape
    target = (transform.c, transform.f + transform.e * h, transform.c + transform.a * w, transform.f)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff"):
        for item in _items(frames).values():
            part = np.full(shape, np.nan, dtype="float32")
            with rasterio.open(f"/vsicurl/{item['assets'][pol]['href']}?{token}") as src:
                # Read the covering window into memory first: warping straight from the remote file
                # loses data near frame edges.
                bounds = transform_bounds(crs, src.crs, *target)
                window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
                data = src.read(1, window=window, boundless=True, fill_value=0).astype("float32")
                data[~(data > 0)] = np.nan
                reproject(data, part, src_transform=src.window_transform(window), src_crs=src.crs, src_nodata=np.nan,
                          dst_transform=transform, dst_crs=crs, dst_nodata=np.nan, resampling=Resampling.average)
            mosaic = np.where(np.isfinite(mosaic), mosaic, part)
    db = to_db(mosaic).astype("float32")
    if path is not None:
        cache.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, db=db)
    return db


def town_change(delta_db: np.ndarray, buildings, transform, crs, towns: dict[str, list[float]],
                radius_m: float = 1000.0) -> list[dict]:
    """Median VV change under building centres within ``radius_m`` of each town centre."""
    import geopandas as gpd
    from rasterio.transform import rowcol
    from shapely.geometry import Point

    centres = buildings.to_crs(crs).geometry.representative_point()
    rows, cols = (np.asarray(v) for v in rowcol(transform, centres.x.to_numpy(), centres.y.to_numpy()))
    inside = (rows >= 0) & (rows < delta_db.shape[0]) & (cols >= 0) & (cols < delta_db.shape[1])
    out = []
    for name, (lon, lat, affected) in towns.items():
        town = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(crs).iloc[0]
        near = inside & (centres.distance(town).to_numpy() <= radius_m)
        values = delta_db[rows[near], cols[near]]
        values = values[np.isfinite(values)]
        out.append({"town": name, "hit_by_flood": bool(affected), "buildings": int(near.sum()),
                    "median_vv_change_db": round(float(np.median(values)), 2) if values.size else None})
    return out
