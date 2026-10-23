"""Newly flooded land from a pre/post pair, with a data-driven threshold and its sensitivity."""

from __future__ import annotations

import numpy as np


def mndwi(green: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    """Modified Normalised Difference Water Index (Xu, 2006): water > 0, land < 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return (green - swir1) / (green + swir1)


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    """Threshold that best separates a two-peaked distribution (Otsu, 1979)."""
    values = values[np.isfinite(values)]
    hist, edges = np.histogram(values, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    weight1 = np.cumsum(hist)
    weight2 = weight1[-1] - weight1
    mean1 = np.cumsum(hist * centres) / np.maximum(weight1, 1)
    mean2 = (np.sum(hist * centres) - np.cumsum(hist * centres)) / np.maximum(weight2, 1)
    between = (weight1 * weight2 * (mean1 - mean2) ** 2)[:-1]
    # When classes are fully separated many cut points tie; take the middle of the tied run, not its edge.
    best = np.flatnonzero(between >= between.max() * (1 - 1e-9))
    return float(centres[best].mean())


def flood_mask(pre_mndwi: np.ndarray, post_mndwi: np.ndarray, clear: np.ndarray, threshold: float,
               pre_water: float = 0.0) -> np.ndarray:
    """Water after the event that was not water before (sea, lakes and canals drop out)."""
    return clear & (post_mndwi > threshold) & (pre_mndwi <= pre_water)


def area_km2(mask: np.ndarray, pixel_m: float) -> float:
    return float(mask.sum()) * pixel_m**2 / 1e6
