import numpy as np

from app.dimensions import extract_dimension_evidence
from app.scale import estimate_scale_with_diagnostics


def test_vector_dimension_span_drives_scale_without_wall_length_assumption():
    labels=[{
        "id":"label-1",
        "text":"4.00 m",
        "center":{"x":200.0,"y":62.0},
        "confidence":.95,
        "kind":"dimension",
        "reviewed":False,
        "provenance":"pdf-text",
    }]
    walls=[{
        "id":"wall-1",
        "a":{"x":40.0,"y":120.0},
        "b":{"x":460.0,"y":120.0},
        "thicknessPx":12.0,
        "confidence":.9,
    }]
    vectors=[
        {"a":{"x":100.0,"y":70.0},"b":{"x":175.0,"y":70.0},"widthPx":1.0},
        {"a":{"x":225.0,"y":70.0},"b":{"x":300.0,"y":70.0},"widthPx":1.0},
        {"a":{"x":100.0,"y":65.0},"b":{"x":100.0,"y":125.0},"widthPx":1.0},
        {"a":{"x":300.0,"y":65.0},"b":{"x":300.0,"y":125.0},"widthPx":1.0},
    ]
    ink=np.zeros((400,500),dtype=np.uint8)

    dimensions=extract_dimension_evidence(
        labels,walls,500,400,ink=ink,vector_lines=vectors,
    )
    scale,confidence,warnings=estimate_scale_with_diagnostics(dimensions,500,400)

    assert dimensions[0]["spanA"]["x"]==100.0
    assert dimensions[0]["spanB"]["x"]==300.0
    assert round(scale,4)==0.02
    assert confidence is not None and confidence>=.55
    assert warnings==[]
    # The nearby wall is 420 px long. If its full length were incorrectly used,
    # the scale would be roughly 0.0095 m/px instead of 0.02.
    assert abs(scale-(4.0/420.0))>.005


def test_no_detected_span_means_no_automatic_scale_even_with_nearby_wall():
    labels=[{
        "id":"label-1",
        "text":"4.00 m",
        "center":{"x":250.0,"y":90.0},
        "confidence":.95,
        "kind":"dimension",
        "reviewed":False,
        "provenance":"ocr",
    }]
    walls=[{
        "id":"wall-1",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":450.0,"y":100.0},
        "thicknessPx":10.0,
        "confidence":.9,
    }]

    dimensions=extract_dimension_evidence(labels,walls,1000,800)
    scale,confidence,warnings=estimate_scale_with_diagnostics(dimensions,1000,800)

    assert dimensions[0].get("spanA") is None
    assert scale is None
    assert confidence is None
    assert warnings==[]
