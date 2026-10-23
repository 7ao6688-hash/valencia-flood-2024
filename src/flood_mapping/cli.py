from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from .detect import area_km2, flood_mask, mndwi, otsu_threshold
from .landsat import load_scene, read_scene, save_scene


def scene(scene_id: str, bbox, cache: Path, local_dir: str | None):
    path = cache / f"{scene_id}.npz"
    if path.exists():
        return load_scene(path, scene_id)
    s = read_scene(scene_id, bbox, local_dir, bands=("SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "QA_PIXEL"))
    cache.mkdir(parents=True, exist_ok=True)
    save_scene(s, path)
    return s


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flood-map", description="Newly flooded land and exposed buildings from Landsat")
    p.add_argument("case", type=Path, help="case.json with scene IDs, area of interest and settings")
    p.add_argument("--buildings", help="Building footprints (any OGR format, e.g. Geofabrik OSM shapefile)")
    p.add_argument("--local-dir", help="Read scenes from USGS downloads here instead of Planetary Computer")
    p.add_argument("--cache", type=Path, default=Path("data/cache"))
    p.add_argument("--output-dir", type=Path)
    args = p.parse_args(argv)

    case = json.loads(args.case.read_text(encoding="utf-8-sig"))
    out = args.output_dir or args.case.parent / "results"
    out.mkdir(parents=True, exist_ok=True)
    bbox = tuple(case["bbox_lonlat"])
    try:
        pre = scene(case["pre_scene"], bbox, args.cache, args.local_dir)
        post = scene(case["post_scene"], bbox, args.cache, args.local_dir)
    except (OSError, KeyError) as exc:
        print(f"Could not read scenes: {exc}", file=sys.stderr)
        return 1
    if pre.clear.shape != post.clear.shape or tuple(pre.transform) != tuple(post.transform):
        print("Pre and post scenes must share a grid (use the same WRS-2 path/row).", file=sys.stderr)
        return 1

    pixel = abs(post.transform.a)
    clear = pre.clear & post.clear
    pre_w = mndwi(pre.bands["SR_B3"], pre.bands["SR_B6"])
    post_w = mndwi(post.bands["SR_B3"], post.bands["SR_B6"])
    threshold = case.get("threshold") or otsu_threshold(post_w[clear])
    mask = flood_mask(pre_w, post_w, clear, threshold)

    exposed, buildings_total = None, None
    if args.buildings:
        from .exposure import exposed_buildings, read_buildings

        buildings = read_buildings(args.buildings, bbox)
        buildings_total = len(buildings)
        exposed = exposed_buildings(buildings, mask, post.transform, post.crs)

    rows = []
    for t in np.round(np.arange(threshold - 0.15, threshold + 0.151, 0.05), 3):
        m = flood_mask(pre_w, post_w, clear, t)
        row = {"threshold": float(t), "flooded_km2": round(area_km2(m, pixel), 2)}
        if args.buildings:
            row["buildings"] = int(len(exposed_buildings(buildings, m, post.transform, post.crs)))
        rows.append(row)

    stats = {
        "event": case["event"],
        "pre_scene": case["pre_scene"],
        "post_scene": case["post_scene"],
        "bbox_lonlat": list(bbox),
        "pixel_m": pixel,
        "clear_fraction_both": round(float(clear.mean()), 3),
        "threshold": round(float(threshold), 3),
        "threshold_method": "fixed" if case.get("threshold") else "Otsu on post-event MNDWI (clear pixels)",
        "flooded_km2": round(area_km2(mask, pixel), 2),
    }
    if exposed is not None:
        stats.update({"buildings": int(len(exposed)), "buildings_in_aoi": buildings_total,
                      "exposed_footprint_km2": round(float(exposed.footprint_m2.sum()) / 1e6, 3),
                      "buildings_source": case.get("buildings_source", "")})
    stats["sensitivity"] = rows
    (out / "summary.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    np.savez_compressed(out / "flood_mask.npz", mask=mask, transform=np.array(post.transform)[:6], crs=str(post.crs))

    if exposed is not None:
        from . import report

        h, w = mask.shape
        extent = [0, w * pixel / 1000, 0, h * pixel / 1000]
        report.overview(out, pre, post, mask, extent, case["title"], tuple(case["labels"]), stats)
        report.flood_map(out, post, mask, exposed, extent, post.transform, stats)
        report.sensitivity(out, rows, threshold)

    print(f"Threshold {threshold:.3f} | newly flooded {stats['flooded_km2']} km²"
          + (f" | exposed buildings {stats['buildings']:,} of {buildings_total:,}" if exposed is not None else ""))
    for r in rows:
        print("  ", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
