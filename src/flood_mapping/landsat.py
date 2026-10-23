"""Read Landsat Collection 2 Level-2 bands for an area of interest.

Scenes come either from Microsoft Planetary Computer (free, anonymous, cloud-optimised GeoTIFFs)
or from a local folder of USGS downloads. Both return surface reflectance on the scene's own grid.
"""

from __future__ import annotations

import glob
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"
# Common names used by the Planetary Computer item assets, per USGS band number (OLI)
ASSETS = {"SR_B2": "blue", "SR_B3": "green", "SR_B4": "red", "SR_B5": "nir08", "SR_B6": "swir16", "SR_B7": "swir22",
          "QA_PIXEL": "qa_pixel"}
SR_SCALE, SR_OFFSET = 0.0000275, -0.2


@dataclass
class Scene:
    scene_id: str
    bands: dict[str, np.ndarray]   # reflectance, NaN where fill
    clear: np.ndarray              # True where not fill, cloud, cloud shadow or dilated cloud
    transform: object
    crs: object


def _get_json(url: str, data: dict | None = None) -> dict:
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def stac_item(scene_id: str) -> dict:
    return _get_json(f"{STAC}/collections/landsat-c2-l2/items/{scene_id}")


def qa_clear(qa: np.ndarray) -> np.ndarray:
    """QA_PIXEL bits: 0 fill, 1 dilated cloud, 3 cloud, 4 cloud shadow."""
    bad = (qa & 1) | ((qa >> 1) & 1) | ((qa >> 3) & 1) | ((qa >> 4) & 1)
    return bad == 0


def read_scene(scene_id: str, bbox_lonlat: tuple[float, float, float, float], local_dir: str | None = None,
               bands=("SR_B3", "SR_B4", "SR_B5", "SR_B6", "QA_PIXEL")) -> Scene:
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    if local_dir:
        def source(band: str) -> str:
            matches = glob.glob(os.path.join(local_dir, f"{scene_id}*", f"*_{band}.TIF"))
            if not matches:
                raise FileNotFoundError(f"{band} for {scene_id} not found under {local_dir}")
            return matches[0]
    else:
        item = stac_item(scene_id)
        token = _get_json(TOKEN)["token"]

        def source(band: str) -> str:
            return f"/vsicurl/{item['assets'][ASSETS[band]]['href']}?{token}"

    arrays, transform, crs = {}, None, None
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF"):
        for band in bands:
            with rasterio.open(source(band)) as src:
                window = from_bounds(*transform_bounds("EPSG:4326", src.crs, *bbox_lonlat), src.transform)
                window = window.round_offsets().round_lengths()
                arrays[band] = src.read(1, window=window, boundless=True, fill_value=0)
                transform, crs = src.window_transform(window), src.crs
    qa = arrays.pop("QA_PIXEL").astype("uint16")
    reflectance = {}
    for band, dn in arrays.items():
        r = dn.astype("float32") * SR_SCALE + SR_OFFSET
        r[dn == 0] = np.nan
        reflectance[band] = r
    return Scene(scene_id, reflectance, qa_clear(qa), transform, crs)


def save_scene(scene: Scene, path: Path) -> None:
    np.savez_compressed(path, clear=scene.clear, transform=np.array(scene.transform)[:6], crs=str(scene.crs),
                        **{k: v.astype("float32") for k, v in scene.bands.items()})


def load_scene(path: Path, scene_id: str) -> Scene:
    from affine import Affine

    with np.load(path) as z:
        bands = {k: z[k] for k in z.files if k.startswith("SR_")}
        return Scene(scene_id, bands, z["clear"], Affine(*z["transform"]), str(z["crs"]))
