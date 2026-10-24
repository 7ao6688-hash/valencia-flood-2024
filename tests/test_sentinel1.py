import unittest

import geopandas as gpd
import numpy as np
from affine import Affine
from shapely.geometry import box

from flood_mapping.detect import otsu_threshold
from flood_mapping.sentinel1 import boxcar_db, sar_flood_mask, to_db, town_change


class Sentinel1Tests(unittest.TestCase):
    def test_db_conversion(self):
        out = to_db(np.array([1.0, 0.1, 0.0]))
        self.assertAlmostEqual(float(out[0]), 0.0)
        self.assertAlmostEqual(float(out[1]), -10.0)
        self.assertTrue(np.isnan(out[2]))

    def test_boxcar_averages_in_linear_power_and_keeps_gaps(self):
        db = np.full((5, 5), -10.0)
        db[2, 2] = 0.0  # one bright pixel: 1.0 linear among 0.1s
        db[0, 0] = np.nan
        out = boxcar_db(db)
        self.assertAlmostEqual(float(out[2, 2]), 10 * np.log10((1.0 + 8 * 0.1) / 9), places=6)
        self.assertTrue(np.isnan(out[0, 0]))

    def test_flood_mask_rules(self):
        pre = np.array([-8.0, -20.0, -8.0, -8.0, np.nan])
        post = np.array([-18.0, -21.0, -12.0, -16.0, -18.0])
        # new water | already water | not dark enough | dark but only 8 dB... | no pre-event data
        self.assertEqual(sar_flood_mask(pre, post, threshold_db=-15.0, min_drop_db=3.0).tolist(),
                         [True, False, False, True, False])
        self.assertEqual(sar_flood_mask(pre, post, -15.0, min_drop_db=9.0).tolist(), [True, False, False, False, False])

    def test_otsu_separates_water_and_land_backscatter(self):
        rng = np.random.default_rng(2)
        values = np.concatenate([rng.normal(-20, 1.5, 3000), rng.normal(-8, 1.5, 7000)])
        self.assertTrue(-16 < otsu_threshold(values) < -12)

    def test_town_change_uses_buildings_near_each_town(self):
        delta = np.zeros((100, 100))
        delta[:, :50] = 2.0  # western half brightened by 2 dB
        transform = Affine(30, 0, 500_000, 0, -30, 4_400_000)
        from pyproj import Transformer

        to_lonlat = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
        west = to_lonlat.transform(500_000 + 20 * 30, 4_400_000 - 50 * 30)
        east = to_lonlat.transform(500_000 + 80 * 30, 4_400_000 - 50 * 30)
        buildings = gpd.GeoDataFrame(geometry=[box(500_000 + c * 30, 4_400_000 - 51 * 30, 500_000 + c * 30 + 10, 4_400_000 - 50 * 30 - 20)
                                               for c in range(0, 100, 5)], crs="EPSG:32631")
        rows = town_change(delta, buildings, transform, "EPSG:32631",
                           {"West": [*west, True], "East": [*east, False]}, radius_m=400)
        self.assertEqual(rows[0]["median_vv_change_db"], 2.0)
        self.assertEqual(rows[1]["median_vv_change_db"], 0.0)
        self.assertGreater(rows[0]["buildings"], 0)


if __name__ == "__main__":
    unittest.main()
