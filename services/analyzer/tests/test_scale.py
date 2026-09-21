from app.scale import estimate_scale,estimate_scale_with_diagnostics


def wall(wall_id,x1,y1,x2,y2):
    return {
        "id":wall_id,
        "a":{"x":float(x1),"y":float(y1)},
        "b":{"x":float(x2),"y":float(y2)},
        "thicknessPx":8.0,
        "confidence":0.9,
    }


def label(label_id,text,x,y,kind="dimension"):
    return {
        "id":label_id,
        "text":text,
        "center":{"x":float(x),"y":float(y)},
        "confidence":0.9,
        "kind":kind,
    }


def test_single_unitless_number_does_not_calibrate_plan():
    scale,confidence=estimate_scale(
        [label("l1","4.00",250,90)],
        [wall("w1",50,100,450,100)],
        1000,
        800,
    )
    assert scale is None
    assert confidence is None


def test_consistent_unitless_dimensions_can_calibrate_plan():
    scale,confidence=estimate_scale(
        [
            label("l1","4.00",250,90),
            label("l2","6.00",350,290),
        ],
        [
            wall("w1",50,100,450,100),
            wall("w2",50,300,650,300),
        ],
        1000,
        800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.6


def test_single_explicit_metric_dimension_is_allowed():
    scale,confidence=estimate_scale(
        [label("l1","4.00 m",250,90)],
        [wall("w1",50,100,450,100)],
        1000,
        800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.55


def test_explicit_centimeters_calibrate_in_meters():
    scale,confidence=estimate_scale(
        [label("l1","400 cm",250,90)],
        [wall("w1",50,100,450,100)],
        1000,
        800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.55


def test_explicit_millimeters_calibrate_in_meters():
    scale,confidence=estimate_scale(
        [label("l1","4000 mm",250,90)],
        [wall("w1",50,100,450,100)],
        1000,
        800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.55


def test_conflicting_explicit_dimensions_require_manual_calibration():
    scale,confidence,warnings=estimate_scale_with_diagnostics(
        [
            label("l1","4.00 m",250,90),
            label("l2","8.00 m",250,290),
        ],
        [
            wall("w1",50,100,450,100),
            wall("w2",50,300,450,300),
        ],
        1000,
        800,
    )
    assert scale is None
    assert confidence is None
    assert warnings and "متعارضة" in warnings[0]


def test_explicit_metric_reading_beats_noisy_unitless_numbers():
    scale,confidence,warnings=estimate_scale_with_diagnostics(
        [
            label("l1","4.00 m",250,90),
            label("l2","8.00",250,290),
            label("l3","2.00",250,490),
        ],
        [
            wall("w1",50,100,450,100),
            wall("w2",50,300,450,300),
            wall("w3",50,500,450,500),
        ],
        1000,
        800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.55
    assert warnings==[]


def test_room_size_pair_does_not_pollute_scale_candidates():
    scale,confidence=estimate_scale(
        [
            label("l1","5 × 4",250,90),
            label("l2","4.00",250,290),
        ],
        [
            wall("w1",50,100,450,100),
            wall("w2",50,300,450,300),
        ],
        1000,
        800,
    )
    assert scale is None
    assert confidence is None
