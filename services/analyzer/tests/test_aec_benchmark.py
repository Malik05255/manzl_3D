from app.aec_benchmark import plan_to_aec_prediction


def test_floorplan_converts_to_aec_prediction_frame():
    plan={
        "widthPx":1000,
        "heightPx":500,
        "walls":[
            {
                "id":"w",
                "a":{"x":100.0,"y":100.0},
                "b":{"x":900.0,"y":100.0},
                "thicknessPx":20.0,
            }
        ],
        "rooms":[
            {
                "id":"r",
                "polygon":[
                    {"x":100.0,"y":100.0},
                    {"x":900.0,"y":100.0},
                    {"x":900.0,"y":400.0},
                    {"x":100.0,"y":400.0},
                ],
            }
        ],
        "doors":[
            {
                "id":"d",
                "a":{"x":300.0,"y":100.0},
                "b":{"x":400.0,"y":100.0},
            }
        ],
        "windows":[
            {
                "id":"x",
                "a":{"x":600.0,"y":100.0},
                "b":{"x":750.0,"y":100.0},
            }
        ],
        "symbols":[
            {
                "id":"fixture",
                "kind":"toilet",
                "a":{"x":700.0,"y":250.0},
                "b":{"x":760.0,"y":330.0},
                "confidence":.95,
            }
        ],
    }
    prediction=plan_to_aec_prediction(plan,sheet="sheet_01",width=2000,height=1000)
    assert prediction["sheet"]=="sheet_01"
    assert {item["class"] for item in prediction["objects"]}=={"Single Swing Door","Window","Toilet"}
    assert prediction["areas"][0][0]==[200.0,200.0]
    assert len(prediction["walls"][0])==4
    assert prediction["objects"][0]["bbox"][0]<600


def test_slanted_wall_becomes_polygon_not_axis_line():
    plan={
        "widthPx":500,
        "heightPx":500,
        "walls":[
            {
                "id":"diag",
                "a":{"x":100.0,"y":100.0},
                "b":{"x":400.0,"y":400.0},
                "thicknessPx":12.0,
            }
        ],
        "rooms":[],
        "doors":[],
        "windows":[],
    }
    prediction=plan_to_aec_prediction(plan,sheet="sheet",width=500,height=500)
    polygon=prediction["walls"][0]
    assert len(polygon)==4
    assert len({round(point[0],3) for point in polygon})==4
    assert len({round(point[1],3) for point in polygon})==4
