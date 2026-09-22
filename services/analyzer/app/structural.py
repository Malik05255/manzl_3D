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

    # A lone dimension rule also survives a long directional opening. Require
    # the closed band to have real wall-width interior. Double-line wall
    # outlines become a filled band here; single 1-2 px rules disappear.
    band_half=max(2.2,min(4.5,short*0.0020))
    vertical=_thick_core(vertical,band_half)
    horizontal=_thick_core(horizontal,band_half)
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
    min_half = max(2.8, min(6.0, short * 0.0026))

    # Thick monochrome ink. This rejects most OCR glyphs/dimension strokes.
    solid = _thick_core(ink, min_half)

    # Saturated wall colors (blue/green/etc.). Requiring thickness prevents
    # colored room labels and dimension lines from becoming walls.
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    colored = np.where((saturation >= 48) & (value <= 248), 255, 0).astype(np.uint8)
    colored = cv2.morphologyEx(colored, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # Colored dimension/extension lines are often 1-3 px while colored wall
    # bands are materially thicker. Use a stricter core threshold for color
    # than for monochrome ink so green/blue dimensions never become walls.
    colored = _thick_core(colored, max(2.8, min_half * 1.30))

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


def wall_structural_support(mask: np.ndarray, wall: dict) -> float:
    try:
        x1 = int(round(float(wall["a"]["x"])))
        y1 = int(round(float(wall["a"]["y"])))
        x2 = int(round(float(wall["b"]["x"])))
        y2 = int(round(float(wall["b"]["y"])))
        thickness = max(2.0, float(wall.get("thicknessPx", 4.0)))
    except (KeyError, TypeError, ValueError):
        return 0.0
    h, w = mask.shape[:2]
    probe = np.zeros_like(mask)
    width = max(3, min(24, int(round(thickness * 0.65))))
    cv2.line(probe, (x1, y1), (x2, y2), 255, width, cv2.LINE_8)
    pixels = cv2.countNonZero(probe)
    if pixels <= 0:
        return 0.0
    supported = cv2.countNonZero(cv2.bitwise_and(probe, mask))
    return float(supported) / float(pixels)


def filter_walls_by_structural_support(
    walls: list[dict],
    structural_mask: np.ndarray,
    *,
    minimum_support: float = 0.34,
) -> tuple[list[dict], list[dict]]:
    """Split wall candidates into structural and rejected raster strokes.

    Native PDF-vector/mixed candidates are retained because they carry evidence
    independent of pixels. Pure OpenCV candidates must overlap the conservative
    structural-region mask; this removes dimension rules, text baselines and
    furniture strokes before the clean redraw is built.
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    for wall in walls:
        provenance = str(wall.get("provenance", "opencv"))
        support = wall_structural_support(structural_mask, wall)
        candidate = dict(wall)
        candidate["structuralSupport"] = round(support, 3)
        if provenance in {"pdf-vector", "mixed"} or support >= minimum_support:
            if provenance == "opencv":
                candidate["confidence"] = round(
                    min(0.97, max(float(candidate.get("confidence", 0.0)), 0.70 + 0.22 * support)),
                    3,
                )
            accepted.append(candidate)
        else:
            candidate["confidence"] = min(float(candidate.get("confidence", 0.0)), 0.49)
            rejected.append(candidate)
    return accepted, rejected
