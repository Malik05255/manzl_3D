from app.dimensions import extract_dimension_evidence,parse_metric_length


def label(text,x=250,y=90,confidence=.9,provenance="ocr"):
    return {
        "id":"label-1","text":text,"center":{"x":x,"y":y},
        "confidence":confidence,"kind":"dimension","reviewed":False,"provenance":provenance,
    }


def wall():
    return {
        "id":"wall-1","a":{"x":50.0,"y":100.0},"b":{"x":450.0,"y":100.0},
        "thicknessPx":10.0,"confidence":.9,
    }


def test_parses_explicit_metric_units_without_guessing_unitless_values():
    assert parse_metric_length("4.20 m")==(4.2,"m")
    assert parse_metric_length("420 cm")==(4.2,"cm")
    assert parse_metric_length("4200 mm")==(4.2,"mm")
    assert parse_metric_length("٤٢٠ سم")==(4.2,"cm")
    assert parse_metric_length("4200")==(None,"unknown")


def test_room_size_pair_is_not_misread_as_single_dimension():
    assert parse_metric_length("5 × 4 m")==(None,"unknown")


def test_dimension_evidence_links_nearby_wall_and_preserves_provenance():
    dimensions=extract_dimension_evidence([label("4.20 m")],[wall()],1000,800)
    assert len(dimensions)==1
    item=dimensions[0]
    assert item["valueM"]==4.2
    assert item["unit"]=="m"
    assert item["referenceWallId"]=="wall-1"
    assert item["orientation"]=="horizontal"
    assert item["provenance"]=="ocr"


def test_distant_dimension_stays_unassociated_instead_of_forcing_wall():
    dimensions=extract_dimension_evidence([label("4.20 m",250,400)],[wall()],1000,800)
    assert dimensions[0]["referenceWallId"] is None
    assert dimensions[0]["orientation"]=="unknown"
