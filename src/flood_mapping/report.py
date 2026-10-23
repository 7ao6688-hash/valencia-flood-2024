"""Case-study figures."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    return plt


def true_colour(bands: dict, stretch: float = 0.25) -> np.ndarray:
    rgb = np.dstack([bands["SR_B4"], bands["SR_B3"], bands["SR_B2"]]) / stretch
    return np.nan_to_num(np.clip(rgb, 0, 1), nan=1.0)


def overview(out: Path, pre, post, mask: np.ndarray, extent_km: list, title: str, labels: tuple[str, str],
             stats: dict) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 3, figsize=(16, 6.6), dpi=150)
    for ax, scene, label in zip(axes[:2], (pre, post), labels):
        ax.imshow(true_colour(scene.bands), extent=extent_km)
        ax.set_title(label, loc="left", fontsize=10.5, fontweight="bold")
    axes[2].imshow(true_colour(post.bands) * 0.55 + 0.45, extent=extent_km)
    overlay = np.zeros((*mask.shape, 4))
    overlay[mask] = (0.05, 0.35, 0.85, 0.85)
    axes[2].imshow(overlay, extent=extent_km)
    axes[2].set_title(f"New standing water: {stats['flooded_km2']:.1f} km²", loc="left", fontsize=10.5,
                      fontweight="bold")
    for ax in axes:
        ax.set_xlabel("km east")
        ax.set_ylabel("km north")
    fig.suptitle(title, x=0.01, ha="left", fontsize=13.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out / "flood_overview.png")
    plt.close(fig)


def flood_map(out: Path, post, mask: np.ndarray, exposed, extent_km: list, transform, stats: dict) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8.4, 9.6), dpi=150)
    grey = np.dot(true_colour(post.bands), [0.3, 0.59, 0.11])
    ax.imshow(grey, cmap="gray", vmin=-0.2, vmax=1.4, extent=extent_km)
    overlay = np.zeros((*mask.shape, 4))
    overlay[mask] = (0.10, 0.45, 0.85, 0.8)
    ax.imshow(overlay, extent=extent_km)
    if len(exposed):
        x0, y0 = transform.c, transform.f + transform.e * mask.shape[0]
        pts = exposed.geometry.representative_point()
        ax.scatter((pts.x - x0) / 1000, (pts.y - y0) / 1000, s=0.6, color="#d7301f", alpha=0.6, linewidths=0)
    ax.scatter([], [], s=12, color="#d7301f", label=f"Building in standing water ({stats['buildings']:,}, lower bound)")
    ax.scatter([], [], s=40, marker="s", color=(0.10, 0.45, 0.85), label=f"New standing water ({stats['flooded_km2']:.1f} km²)")
    ax.legend(loc="lower left", fontsize=9, framealpha=0.95)
    ax.set_xlabel("km east")
    ax.set_ylabel("km north")
    ax.set_title(f"MNDWI > {stats['threshold']:.2f} (Otsu) after the flood, not water before · Landsat 8, 30 m",
                 loc="left", fontsize=9, color="#55606a")
    ax.annotate("Standing floodwater one day after the DANA, 30 October 2024", xy=(0, 1), xycoords="axes fraction",
                xytext=(0, 20), textcoords="offset points", fontsize=13, fontweight="bold", va="bottom")
    fig.savefig(out / "flood_extent_buildings.png", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


def sensitivity(out: Path, rows: list[dict], threshold: float) -> None:
    plt = _plt()
    t = [r["threshold"] for r in rows]
    fig, ax1 = plt.subplots(figsize=(8, 3.8), dpi=150)
    ax1.plot(t, [r["flooded_km2"] for r in rows], color="#1a73c8", marker="o", label="Flooded area (km²)")
    ax1.set_xlabel("Post-event MNDWI threshold")
    ax1.set_ylabel("Flooded area (km²)", color="#1a73c8")
    ax2 = ax1.twinx()
    ax2.plot(t, [r["buildings"] for r in rows], color="#d7301f", marker="s", label="Buildings in standing water")
    ax2.set_ylabel("Buildings in standing water", color="#d7301f")
    ax1.axvline(threshold, color="#111", ls="--", lw=1)
    ax1.text(threshold, ax1.get_ylim()[1], " Otsu", va="top", fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.set_title("How the answer depends on the water threshold", loc="left", fontsize=11.5, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "threshold_sensitivity.png")
    plt.close(fig)
