from app.aec_benchmark import parse_official_score_output,plan_to_aec_prediction


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


def test_parses_official_aec_score_summary():
    output="""
Manzil H on AEC-Geometric-Bench-15

OBJECT MICRO           1500     96    132   0.940   0.919   0.929

wall pixel                                  0.954   0.908   0.931
area pixel                                  0.990   0.985   0.987
area instance                               0.961   0.921   0.940
"""
    report=parse_official_score_output(output)
    assert report["objectMicro"]=={
        "precision":.94,"recall":.919,"f1":.929,
        "tp":1500,"fp":96,"fn":132,
    }
    assert report["wallPixel"]["f1"]==.931
    assert report["areaPixel"]["f1"]==.987
    assert report["areaInstance"]["f1"]==.94
    assert report["macroF1"]==.9467


def test_double_swing_door_maps_to_official_aec_class():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[{
            "id":"d1","kind":"door","doorSubtype":"double_swing",
            "a":{"x":100.0,"y":100.0},"b":{"x":200.0,"y":100.0},"confidence":.9,
        }],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    assert prediction["objects"][0]["class"]=="Double Swing Door"


def test_door_swing_geometry_expands_object_box():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[{
            "id":"d1","kind":"door","doorSubtype":"single_swing",
            "doorSwingSide":"negative","doorSwingDepthPx":85.0,
            "a":{"x":100.0,"y":200.0},"b":{"x":200.0,"y":200.0},"confidence":.9,
        }],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    x1,y1,x2,y2=prediction["objects"][0]["bbox"]
    assert x1<100 and x2>200
    assert y1<120
    assert y2>200


def test_sliding_door_is_not_mislabeled_as_swing_door_in_aec_taxonomy():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[{
            "id":"d1","kind":"door","doorSubtype":"sliding",
            "a":{"x":100.0,"y":200.0},"b":{"x":200.0,"y":200.0},"confidence":1,
        }],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    assert prediction["objects"]==[]



def test_stairs_symbol_maps_to_aec_area_not_object():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[],
        "windows":[],
        "symbols":[{
            "id":"stairs-1","kind":"stairs",
            "a":{"x":100.0,"y":120.0},
            "b":{"x":220.0,"y":280.0},
            "confidence":.95,
        }],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=1000,height=800)
    assert prediction["objects"]==[]
    assert prediction["areas"]==[[
        [200.0,240.0],
        [440.0,240.0],
        [440.0,560.0],
        [200.0,560.0],
    ]]
