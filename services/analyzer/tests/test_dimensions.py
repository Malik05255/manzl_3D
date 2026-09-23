import cv2
import numpy as np

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
    assert item.get("spanA") is None


def test_distant_dimension_stays_unassociated_instead_of_forcing_wall():
    dimensions=extract_dimension_evidence([label("4.20 m",250,400)],[wall()],1000,800)
    assert dimensions[0]["referenceWallId"] is None
    assert dimensions[0]["orientation"]=="unknown"


def test_pdf_vector_dimension_line_split_around_text_gets_real_span():
    vectors=[
        {"a":{"x":100.0,"y":70.0},"b":{"x":175.0,"y":70.0},"widthPx":1.0},
        {"a":{"x":225.0,"y":70.0},"b":{"x":300.0,"y":70.0},"widthPx":1.0},
        {"a":{"x":100.0,"y":70.0},"b":{"x":100.0,"y":125.0},"widthPx":1.0},
        {"a":{"x":300.0,"y":70.0},"b":{"x":300.0,"y":125.0},"widthPx":1.0},
    ]
    dimensions=extract_dimension_evidence(
        [label("4.00 m",200,62)],
        [wall()],
        500,400,
        vector_lines=vectors,
    )
    item=dimensions[0]
    assert item["orientation"]=="horizontal"
    assert item["spanA"]["x"]==100.0
    assert item["spanB"]["x"]==300.0
    assert item["spanA"]["y"]==70.0
    assert item["spanB"]["y"]==70.0


def test_raster_dimension_line_can_be_detected_without_using_wall_length():
    ink=np.zeros((400,500),dtype=np.uint8)
    cv2.line(ink,(100,70),(175,70),255,2)
    cv2.line(ink,(225,70),(300,70),255,2)
    cv2.line(ink,(100,65),(100,125),255,2)
    cv2.line(ink,(300,65),(300,125),255,2)
    dimensions=extract_dimension_evidence(
        [label("4.00 m",200,62)],
        [wall()],
        500,400,
        ink=ink,
    )
    item=dimensions[0]
    assert item.get("spanA") is not None
    assert item.get("spanB") is not None
    assert abs(item["spanA"]["x"]-100)<=6
    assert abs(item["spanB"]["x"]-300)<=6


def test_wall_itself_is_not_promoted_to_dimension_span():
    vectors=[
        {"a":{"x":50.0,"y":100.0},"b":{"x":450.0,"y":100.0},"widthPx":10.0},
        {"a":{"x":50.0,"y":50.0},"b":{"x":50.0,"y":150.0},"widthPx":10.0},
        {"a":{"x":450.0,"y":50.0},"b":{"x":450.0,"y":150.0},"widthPx":10.0},
    ]
    dimensions=extract_dimension_evidence(
        [label("4.00 m",250,90)],
        [wall()],
        1000,800,
        vector_lines=vectors,
    )
    assert dimensions[0].get("spanA") is None
