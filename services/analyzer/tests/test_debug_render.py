import numpy as np

from app.debug_render import render_extraction_overlay


def test_overlay_draws_all_canonical_geometry_without_resizing_source():
    image=np.full((220,300,3),255,dtype=np.uint8)
    plan={
        "walls":[{
            "id":"w","a":{"x":30.0,"y":40.0},"b":{"x":270.0,"y":40.0},
            "thicknessPx":9.0,
        }],
        "rooms":[{
            "id":"r","polygon":[
                {"x":40.0,"y":50.0},{"x":260.0,"y":50.0},
                {"x":260.0,"y":190.0},{"x":40.0,"y":190.0},
            ],
        }],
        "doors":[{
            "id":"d","a":{"x":100.0,"y":40.0},"b":{"x":145.0,"y":40.0},
        }],
        "windows":[{
            "id":"x","a":{"x":180.0,"y":40.0},"b":{"x":230.0,"y":40.0},
        }],
        "symbols":[{
            "id":"s","kind":"toilet",
            "a":{"x":80.0,"y":90.0},"b":{"x":120.0,"y":140.0},
        }],
    }
    overlay=render_extraction_overlay(image,plan)
    assert overlay.shape==image.shape
    assert np.any(overlay!=image)
    assert np.all(image==255)
