from app.benchmark import evaluate_floor_plan


def base_plan():
    return {
        "walls":[
            {"a":{"x":0,"y":0},"b":{"x":100,"y":0}},
            {"a":{"x":100,"y":0},"b":{"x":100,"y":100}},
        ],
        "rooms":[
            {"polygon":[{"x":0,"y":0},{"x":100,"y":0},{"x":100,"y":100},{"x":0,"y":100}]},
        ],
        "doors":[
            {"a":{"x":30,"y":0},"b":{"x":60,"y":0}},
        ],
        "windows":[],
        "dimensions":[
            {
                "valueM":4.0,
                "center":{"x":50,"y":-15},
                "spanA":{"x":0,"y":-10},
                "spanB":{"x":100,"y":-10},
            },
        ],
    }


def test_perfect_prediction_scores_one():
    truth=base_plan()
    report=evaluate_floor_plan(truth,truth)
    assert report["macroF1"]==1.0
    assert report["walls"]["f1"]==1.0
    assert report["rooms"]["meanMatchedIoU"]==1.0
    assert report["openings"]["recall"]==1.0
    assert report["dimensions"]["precision"]==1.0


def test_reversed_segment_direction_still_matches():
    truth=base_plan()
    prediction=base_plan()
    prediction["walls"][0]={"a":{"x":100,"y":0},"b":{"x":0,"y":0}}
    report=evaluate_floor_plan(prediction,truth)
    assert report["walls"]["recall"]==1.0


def test_missing_and_false_geometry_reduce_precision_and_recall():
    truth=base_plan()
    prediction=base_plan()
    prediction["walls"]=prediction["walls"][:1]+[
        {"a":{"x":250,"y":250},"b":{"x":350,"y":250}},
    ]
    prediction["doors"]=[]
    report=evaluate_floor_plan(prediction,truth)
    assert report["walls"]["precision"]==0.5
    assert report["walls"]["recall"]==0.5
    assert report["openings"]["recall"]==0.0
    assert report["macroF1"]<1.0


def test_room_iou_rejects_large_shift():
    truth=base_plan()
    prediction=base_plan()
    prediction["rooms"]=[{
        "polygon":[{"x":80,"y":0},{"x":180,"y":0},{"x":180,"y":100},{"x":80,"y":100}],
    }]
    report=evaluate_floor_plan(prediction,truth)
    assert report["rooms"]["f1"]==0.0


def test_dimension_requires_consistent_metric_value():
    truth=base_plan()
    prediction=base_plan()
    prediction["dimensions"][0]["valueM"]=5.0
    report=evaluate_floor_plan(prediction,truth)
    assert report["dimensions"]["f1"]==0.0



def test_window_cannot_match_truth_door():
    truth=base_plan()
    prediction=base_plan()
    prediction["doors"]=[]
    prediction["windows"]=[{
        "a":{"x":30,"y":0},
        "b":{"x":60,"y":0},
    }]
    report=evaluate_floor_plan(prediction,truth)
    assert report["doors"]["recall"]==0.0
    assert report["windows"]["precision"]==0.0
    assert report["openings"]["tp"]==0
    assert report["openings"]["f1"]==0.0


def test_opening_aggregate_preserves_class_aware_matches():
    truth=base_plan()
    truth["windows"]=[{"a":{"x":70,"y":0},"b":{"x":90,"y":0}}]
    prediction=base_plan()
    prediction["windows"]=[{"a":{"x":70,"y":0},"b":{"x":90,"y":0}}]
    report=evaluate_floor_plan(prediction,truth)
    assert report["doors"]["f1"]==1.0
    assert report["windows"]["f1"]==1.0
    assert report["openings"]["f1"]==1.0
