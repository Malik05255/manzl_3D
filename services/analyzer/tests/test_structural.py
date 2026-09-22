import cv2
import numpy as np

from app.structural import extract_structural_wall_mask


def test_structural_mask_keeps_thick_walls_and_rejects_thin_dimensions():
    image = np.full((700, 900, 3), 255, dtype=np.uint8)

    # Thick blue room shell and partition.
    blue = (220, 110, 40)
    cv2.rectangle(image, (80, 80), (820, 620), blue, 16)
    cv2.line(image, (450, 80), (450, 620), blue, 16)

    # Thin green dimension line with ticks outside the plan.
    green = (55, 145, 55)
    cv2.line(image, (80, 35), (820, 35), green, 2)
    cv2.line(image, (80, 25), (80, 45), green, 2)
    cv2.line(image, (820, 25), (820, 45), green, 2)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 11
    )

    mask = extract_structural_wall_mask(image, ink)

    # Wall regions survive.
    assert cv2.countNonZero(mask[70:95, 100:800]) > 3000
    assert cv2.countNonZero(mask[100:600, 440:460]) > 3000

    # Thin dimension guide must not become a long structural wall.
    assert cv2.countNonZero(mask[28:42, 100:800]) < 900


def test_structural_mask_recovers_double_line_black_wall():
    image = np.full((500, 700, 3), 255, dtype=np.uint8)
    # Two thin parallel outlines with white wall fill.
    cv2.line(image, (100, 100), (600, 100), (0, 0, 0), 2)
    cv2.line(image, (100, 112), (600, 112), (0, 0, 0), 2)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)[1]
    mask = extract_structural_wall_mask(image, ink)

    assert cv2.countNonZero(mask[98:115, 120:580]) > 2500
