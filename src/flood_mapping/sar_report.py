"""Figures for the Sentinel-1 analysis."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .report import _plt

BOTH, OPTICAL, RADAR = (0.10, 0.45, 0.85, 0.9), (0.95, 0.65, 0.15, 0.9), (0.80, 0.15, 0.35, 0.9)


def overview(out: Path, pre_db, post_db, optical, radar, extent_km: list, title: str, stats: dict) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 3, figsize=(16, 6.6), dpi=150)
    for ax, img, label in zip(axes[:2], (pre_db, post_db), (stats["pre"], stats["post"])):
        ax.imshow(img, cmap="gray", vmin=-22, vmax=2, extent=extent_km)
        ax.set_title(f"{label}: VV backscatter", loc="left", fontsize=10.5, fontweight="bold")
    axes[2].imshow(post_db, cmap="gray", vmin=-22, vmax=2, extent=extent_km, alpha=0.45)
    overlay = np.zeros((*radar.shape, 4))
    overlay[optical & ~radar] = OPTICAL
    overlay[radar & ~optical] = RADAR
    overlay[optical & radar] = BOTH
    axes[2].imshow(overlay, extent=extent_km)
    a = stats["agreement_with_landsat"]
    for colour, label in ((BOTH, f"Both ({a['both_km2']:.0f} km²)"), (OPTICAL, f"Landsat only, 30 Oct ({a['landsat_only_km2']:.0f} km²)"),
                          (RADAR, f"Radar only, 1 Nov ({a['radar_only_km2']:.0f} km²)")):
        axes[2].scatter([], [], s=40, marker="s", color=colour, label=label)
    axes[2].legend(loc="lower left", fontsize=8.5, framealpha=0.95)
    axes[2].set_title(f"Radar flood {stats['flooded_km2']:.0f} km² vs. Landsat", loc="left", fontsize=10.5, fontweight="bold")
    for ax in axes:
        ax.set_xlabel("km east")
        ax.set_ylabel("km north")
    fig.suptitle(f"{title}: Sentinel-1 radar", x=0.01, ha="left", fontsize=13.5, fontweight="bold")
    fig.text(0.01, 0.925, f"Dark after (VV < {stats['threshold_db']:.1f} dB, Otsu), "
             f"not dark before, and ≥ {stats['min_drop_db']:.0f} dB darker · Sentinel-1 RTC averaged to the 30 m Landsat grid",
             fontsize=9, color="#55606a")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out / "sar_overview.png", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


def timeline(out: Path, stats: dict, case: dict) -> None:
    plt = _plt()
    labels = [f"Landsat 8\n{case['labels'][1].split(': ')[-1].split(' (')[0]}", f"Sentinel-1\n{stats['post']}"]
    values = [None, stats["flooded_km2"]]
    for f in stats["followup"].values():
        labels.append(f"Sentinel-1\n{f['label']}")
        values.append(f["flooded_km2"])
    import json

    values[0] = json.loads((out / "summary.json").read_text(encoding="utf-8"))["flooded_km2"]
    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=150)
    colours = ["#f2a541"] + ["#1a73c8"] * (len(values) - 1)
    ax.bar(range(len(values)), values, color=colours, width=0.6)
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.0f} km²", ha="center", va="bottom", fontsize=9.5)
    ax.set_xticks(range(len(values)), labels, fontsize=9)
    ax.set_ylabel("Open floodwater (km²)")
    ax.set_title("How long the water stayed: open floodwater after the DANA", loc="left", fontsize=11.5, fontweight="bold")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "sar_timeline.png")
    plt.close(fig)


def towns(out: Path, rows: list[dict]) -> None:
    plt = _plt()
    rows = sorted(rows, key=lambda r: (not r["hit_by_flood"], -(r["median_vv_change_db"] or 0)))
    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=150)
    colours = ["#c0392b" if r["hit_by_flood"] else "#7f8c8d" for r in rows]
    vals = [r["median_vv_change_db"] or 0 for r in rows]
    ax.barh(range(len(rows)), vals, color=colours)
    for i, r in enumerate(rows):
        ax.text(vals[i] + 0.05, i, f"{vals[i]:+.1f} dB · {r['buildings']:,} bldgs", va="center", fontsize=8.5)
    ax.set_yticks(range(len(rows)), [r["town"] for r in rows])
    ax.invert_yaxis()
    ax.axvline(0, color="#111", lw=0.8)
    ax.set_xlim(min(0, min(vals)) - 0.3, max(vals) + 1.6)
    ax.set_xlabel("Median change in VV backscatter under buildings (dB, before → after)")
    ax.scatter([], [], color="#c0392b", marker="s", label="Town hit by the flood")
    ax.scatter([], [], color="#7f8c8d", marker="s", label="Comparison area")
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Flooded towns brightened slightly on radar (mud, debris, wet walls)", loc="left", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "sar_towns.png")
    plt.close(fig)
