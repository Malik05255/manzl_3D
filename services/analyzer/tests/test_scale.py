from app.scale import estimate_scale,estimate_scale_with_diagnostics


def dimension(value_m,ax,ay,bx,by,unit="m",confidence=.9):
    return {
        "id":"d",
        "valueM":value_m,
        "unit":unit,
        "spanA":{"x":float(ax),"y":float(ay)},
        "spanB":{"x":float(bx),"y":float(by)},
        "confidence":confidence,
    }


def test_dimension_without_detected_span_does_not_calibrate():
    scale,confidence=estimate_scale(
        [{"id":"d1","valueM":4.0,"unit":"m","confidence":.95}],
        1000,800,
    )
    assert scale is None
    assert confidence is None


def test_single_explicit_dimension_span_is_allowed():
    scale,confidence=estimate_scale(
        [dimension(4.0,100,70,500,70)],
        1000,800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.55


def test_centimeter_value_is_already_normalized_to_meters():
    scale,confidence=estimate_scale(
        [dimension(4.0,100,70,500,70,unit="cm")],
        1000,800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.55


def test_unitless_dimension_span_is_not_assumed_to_be_meters():
    scale,confidence=estimate_scale(
        [dimension(4.0,100,70,500,70,unit="unknown")],
        1000,800,
    )
    assert scale is None
    assert confidence is None


def test_scale_uses_actual_dimension_span_not_nearby_wall_length():
    scale,confidence=estimate_scale(
        [dimension(4.0,100,70,300,70)],
        1000,800,
    )
    assert round(scale,4)==0.02
    assert confidence is not None


def test_consistent_explicit_spans_calibrate_plan():
    scale,confidence=estimate_scale(
        [
            dimension(4.0,100,70,500,70),
            dimension(6.0,100,170,700,170),
        ],
        1000,800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None and confidence>=0.7


def test_conflicting_explicit_spans_require_manual_calibration():
    scale,confidence,warnings=estimate_scale_with_diagnostics(
        [
            dimension(4.0,100,70,500,70),
            dimension(8.0,100,170,500,170),
        ],
        1000,800,
    )
    assert scale is None
    assert confidence is None
    assert warnings and "متعارضة" in warnings[0]


def test_noisy_outlier_is_rejected_when_majority_agrees():
    scale,confidence,warnings=estimate_scale_with_diagnostics(
        [
            dimension(4.0,100,70,500,70),
            dimension(6.0,100,170,700,170),
            dimension(9.0,100,270,700,270),
            dimension(5.0,100,370,600,370),
        ],
        1000,800,
    )
    assert round(scale,4)==0.01
    assert confidence is not None
    assert warnings and "تجاهل" in warnings[0]
