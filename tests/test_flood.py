import unittest

import geopandas as gpd
import numpy as np
from affine import Affine
from shapely.geometry import box

from flood_mapping.detect import area_km2, flood_mask, mndwi, otsu_threshold
from flood_mapping.exposure import exposed_buildings
from flood_mapping.landsat import qa_clear


class DetectTests(unittest.TestCase):
    def test_mndwi_sign(self):
        self.assertGreater(float(mndwi(np.array([0.1]), np.array([0.02]))[0]), 0)   # water
        self.assertLess(float(mndwi(np.array([0.1]), np.array([0.25]))[0]), 0)      # dry soil

    def test_otsu_splits_two_peaks(self):
        rng = np.random.default_rng(0)
        land, water = rng.normal(-0.3, 0.05, 5000), rng.normal(0.4, 0.05, 3000)
        t = otsu_threshold(np.concatenate([land, water]))
        self.assertTrue(land.max() < t < water.min())
        self.assertAlmostEqual(t, (land.max() + water.min()) / 2, delta=0.05)  # centred in the gap

    def test_flood_mask_excludes_permanent_water_and_cloud(self):
        pre = np.array([[-0.4, 0.8, -0.4, -0.4]])
        post = np.array([[0.5, 0.9, -0.3, 0.5]])
        clear = np.array([[True, True, True, False]])
        self.assertEqual(flood_mask(pre, post, clear, 0.0).tolist(), [[True, False, False, False]])
        self.assertAlmostEqual(area_km2(np.ones((10, 10), bool), 30), 0.09)

    def test_qa_bits(self):
        qa = np.array([0b1000000, 0b1, 0b10, 0b1000, 0b10000], dtype="uint16")  # clear, fill, dilated, cloud, shadow
        self.assertEqual(qa_clear(qa).tolist(), [True, False, False, False, False])


class ExposureTests(unittest.TestCase):
    def test_buildings_on_flooded_pixels(self):
        mask = np.zeros((10, 10), bool)
        mask[:, :5] = True                               # west half flooded
        transform = Affine(30, 0, 0, 0, -30, 300)        # 30 m pixels, top-left at (0, 300)
        buildings = gpd.GeoDataFrame(geometry=[box(10, 200, 20, 210), box(250, 200, 260, 210), box(900, 900, 910, 910)],
                                     crs="EPSG:32631")
        hit = exposed_buildings(buildings, mask, transform, "EPSG:32631")
        self.assertEqual(len(hit), 1)
        self.assertAlmostEqual(float(hit.footprint_m2.iloc[0]), 100.0)


if __name__ == "__main__":
    unittest.main()
