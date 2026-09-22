from __future__ import annotations

import cv2
import numpy as np


def _keep_large_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = np.zeros_like(mask)
    for index in range(1, count):
        if int(stats[index, cv2.CC_STAT_AREA]) >= min_area:
            out[labels == index] = 255
    return out


def _thick_core(mask: np.ndarray, min_half_thickness: float) -> np.ndarray:
    if not np.any(mask):
        return np.zeros_like(mask)
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    core = (distance >= float(min_half_thickness)).astype(np.uint8) * 255
    radius = max(2, int(round(min_half_thickness * 1.45)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    return cv2.dilate(core, kernel, iterations=1)


def _outlined_wall_bands(ink: np.ndarray) -> np.ndarray:
    h, w = ink.shape[:2]
    short = max(1, min(h, w))
    pair_gap = max(5, min(24, int(round(short * 0.012))))
    run = max(28, min(120, int(round(short * 0.055))))

    # Parallel thin outlines are common in architectural drawings. Close only
    # across the wall thickness, then require a long run in the wall direction.
    vertical_filled = cv2.morphologyEx(
        ink,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (pair_gap, 1)),
    )
    vertical = cv2.morphologyEx(
        vertical_filled,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, run)),
    )

    horizontal_filled = cv2.morphologyEx(
        ink,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, pair_gap)),
    )
    horizontal = cv2.morphologyEx(
        horizontal_filled,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (run, 1)),
    )
    return cv2.bitwise_or(vertical, horizontal)


def extract_structural_wall_mask(image: np.ndarray, ink: np.ndarray) -> np.ndarray:
    """Return a conservative wall-region mask for reconstruction.

    This deliberately separates structural strokes from text, dimensions and
    furniture before room segmentation. It handles:
      * filled/thick black walls via distance-transform cores,
      * colored structural walls (common in exported plans),
      * double-line wall outlines via parallel-band reconstruction.

    The result is a *region* mask, not a list of centerlines. Openings remain
    gaps so doors/windows can still be inferred downstream.
    """
    if image.ndim != 3 or ink.ndim != 2:
        raise ValueError("STRUCTURAL_MASK_SHAPE")
    h, w = ink.shape[:2]
    if image.shape[:2] != (h, w):
        raise ValueError("STRUCTURAL_MASK_SHAPE")

    short = max(1, min(h, w))
    min_half = max(1.8, min(6.0, short * 0.0022))

    # Thick monochrome ink. This rejects most OCR glyphs/dimension strokes.
    solid = _thick_core(ink, min_half)

    # Saturated wall colors (blue/green/etc.). Requiring thickness prevents
    # colored room labels and dimension lines from becoming walls.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    colored = np.where((saturation >= 48) & (value <= 248), 255, 0).astype(np.uint8)
    colored = cv2.morphologyEx(colored, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    colored = _thick_core(colored, max(1.6, min_half * 0.82))

    outlined = _outlined_wall_bands(ink)

    mask = cv2.bitwise_or(solid, colored)
    mask = cv2.bitwise_or(mask, outlined)

    # Suppress tiny isolated blobs while preserving short partitions.
    min_component = max(24, int(round(short * short * 0.000025)))
    mask = _keep_large_components(mask, min_component)

    # Only seal raster pinholes; never bridge an architectural opening.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return mask


def structural_mask_metrics(mask: np.ndarray) -> dict[str, float]:
    h, w = mask.shape[:2]
    ratio = float(cv2.countNonZero(mask)) / float(max(1, h * w))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    components = sum(
        1 for index in range(1, count)
        if int(stats[index, cv2.CC_STAT_AREA]) >= max(20, int(h * w * 0.00002))
    )
    return {
        "wallRegionRatio": round(ratio, 5),
        "structuralComponents": float(components),
    }
