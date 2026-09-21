import cv2
import numpy as np

from app.walls import _estimate_thickness,enrich_walls_with_vector,rasterize_wall_mask


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


def test_vector_evidence_boosts_matching_wall_confidence():
    detected=[{
        "id":"wall-1",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":350.0,"y":100.0},
        "thicknessPx":8.0,
        "confidence":0.80,
    }]
    vectors=[{
        "a":{"x":52.0,"y":101.0},
        "b":{"x":348.0,"y":101.0},
        "widthPx":5.0,
    }]
    enriched=enrich_walls_with_vector(detected,vectors)
    assert enriched[0]["confidence"]>0.90


def test_unrelated_vector_line_does_not_boost_wall_confidence():
    detected=[{
        "id":"wall-1",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":350.0,"y":100.0},
        "thicknessPx":8.0,
        "confidence":0.80,
    }]
    vectors=[{
        "a":{"x":52.0,"y":180.0},
        "b":{"x":348.0,"y":180.0},
        "widthPx":5.0,
    }]
    enriched=enrich_walls_with_vector(detected,vectors)
    assert enriched[0]["confidence"]==0.80


def test_rasterized_canonical_wall_closes_detected_opening_gap():
    base=np.zeros((220,420),dtype=np.uint8)
    cv2.line(base,(20,100),(160,100),255,8)
    cv2.line(base,(260,100),(400,100),255,8)
    walls=[{
        "id":"canonical",
        "a":{"x":20.0,"y":100.0},
        "b":{"x":400.0,"y":100.0},
        "thicknessPx":8.0,
        "confidence":.9,
    }]
    barrier=rasterize_wall_mask(walls,220,420,base)
    assert barrier[100,210]>0
    assert barrier[100,100]>0


def test_rasterized_wall_mask_rejects_wrong_base_shape():
    import pytest
    with pytest.raises(ValueError,match="WALL_MASK_SHAPE"):
        rasterize_wall_mask([],200,300,np.zeros((100,100),dtype=np.uint8))
