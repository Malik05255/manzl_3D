import cv2
import numpy as np

from app.walls import _estimate_thickness


def test_estimates_filled_horizontal_wall_thickness():
    ink=np.zeros((120,220),dtype=np.uint8)
    cv2.rectangle(ink,(20,50),(200,62),255,-1)
    thickness=_estimate_thickness(ink,(20,56,200,56))
    assert 11<=thickness<=15


def test_estimates_filled_vertical_wall_thickness():
    ink=np.zeros((220,120),dtype=np.uint8)
    cv2.rectangle(ink,(50,20),(62,200),255,-1)
    thickness=_estimate_thickness(ink,(56,20,56,200))
    assert 11<=thickness<=15
