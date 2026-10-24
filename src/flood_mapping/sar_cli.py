"""flood-map-sar: Sentinel-1 flood mapping on the Landsat grid, compared with the optical result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .detect import area_km2, otsu_threshold
from .sentinel1 import boxcar_db, read_backscatter, sar_flood_mask, town_change


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flood-map-sar", description="Sentinel-1 flood mapping on the Landsat grid")
    p.add_argument("case", type=Path, help="case.json with a 'sentinel1' block; run flood-map first")
    p.add_argument("--buildings", help="Building footprints (any OGR format, e.g. Geofabrik OSM shapefile)")
    p.add_argument("--cache", type=Path, default=Path("data/cache"))
    p.add_argument("--output-dir", type=Path)
    args = p.parse_args(argv)

    case = json.loads(args.case.read_text(encoding="utf-8-sig"))
    s1 = case["sentinel1"]
    out = args.output_dir or args.case.parent / "results"
    optical_path = out / "flood_mask.npz"
    if not optical_path.exists():
        print("Run flood-map on this case first: the radar map is built on its grid and compared with it.", file=sys.stderr)
        return 1
    from affine import Affine

    with np.load(optical_path) as z:
        optical = z["mask"]
        transform, crs = Affine(*z["transform"]), str(z["crs"])
    shape, pixel = optical.shape, abs(transform.a)

    def vv(frames):
        return boxcar_db(read_backscatter(frames, "vv", transform, shape, crs, args.cache))

    try:
        pre, post = vv(s1["pre"]["frames"]), vv(s1["post"]["frames"])
        later = {k: vv(v["frames"]) for k, v in s1.get("followup", {}).items()}
    except (OSError, KeyError) as exc:
        print(f"Could not read Sentinel-1 data: {exc}", file=sys.stderr)
        return 1

    threshold = s1.get("threshold_db") or otsu_threshold(post[np.isfinite(post) & (post > -30) & (post < 5)])
    drop = s1.get("min_drop_db", 3.0)
    mask = sar_flood_mask(pre, post, threshold, drop)
    both, optical_only, radar_only = optical & mask, optical & ~mask, mask & ~optical
    stats = {
        "pre": s1["pre"]["label"], "post": s1["post"]["label"],
        "threshold_db": round(float(threshold), 2),
        "threshold_method": "fixed" if s1.get("threshold_db") else "Otsu on post-event VV (dB)",
        "min_drop_db": drop,
        "flooded_km2": round(area_km2(mask, pixel), 2),
        "agreement_with_landsat": {
            "both_km2": round(area_km2(both, pixel), 2),
            "landsat_only_km2": round(area_km2(optical_only, pixel), 2),
            "radar_only_km2": round(area_km2(radar_only, pixel), 2),
            "share_of_landsat_flood_confirmed_by_radar": round(float(both.sum() / max(optical.sum(), 1)), 3),
        },
        "followup": {},
    }
    for key, img in later.items():
        f = s1["followup"][key]
        base = vv(f["pre_frames"])
        later_mask = sar_flood_mask(base, img, threshold, drop)
        stats["followup"][key] = {"label": f["label"], "flooded_km2": round(area_km2(later_mask, pixel), 2),
                                  "observed_share": round(float((np.isfinite(base) & np.isfinite(img)).mean()), 3)}

    exposed = towns = None
    if args.buildings:
        from .exposure import exposed_buildings, read_buildings

        buildings = read_buildings(args.buildings, tuple(case["bbox_lonlat"]))
        exposed = exposed_buildings(buildings, mask, transform, crs)
        stats["buildings"] = int(len(exposed))
        if s1.get("towns"):
            raw_delta = read_backscatter(s1["post"]["frames"], "vv", transform, shape, crs, args.cache) - \
                read_backscatter(s1["pre"]["frames"], "vv", transform, shape, crs, args.cache)
            towns = town_change(raw_delta, buildings, transform, crs, s1["towns"])
            stats["urban_vv_change"] = towns

    (out / "sar_summary.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    np.savez_compressed(out / "sar_flood_mask.npz", mask=mask, transform=np.array(transform)[:6], crs=crs)

    from . import sar_report

    h, w = shape
    extent = [0, w * pixel / 1000, 0, h * pixel / 1000]
    sar_report.overview(out, pre, post, optical, mask, extent, case["title"], stats)
    sar_report.timeline(out, stats, case)
    if towns:
        sar_report.towns(out, towns)
    print(f"VV threshold {threshold:.1f} dB | radar flood {stats['flooded_km2']} km2 | "
          f"Landsat flood confirmed by radar {stats['agreement_with_landsat']['share_of_landsat_flood_confirmed_by_radar']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
