from app.ocr import _merge_labels,_restore_rotated_labels,classify_text,order_line_words


def test_arabic_line_is_ordered_right_to_left():
    words=[
        {"text":"نوم","x":100},
        {"text":"غرفة","x":180},
    ]
    ordered=order_line_words(words)
    assert [word["text"] for word in ordered]==["غرفة","نوم"]


def test_english_line_is_ordered_left_to_right():
    words=[
        {"text":"room","x":180},
        {"text":"bed","x":100},
    ]
    ordered=order_line_words(words)
    assert [word["text"] for word in ordered]==["bed","room"]


def test_room_classification_survives_arabic_phrase():
    assert classify_text("غرفة نوم")=="room_name"


def test_dimension_pass_replaces_lower_confidence_duplicate():
    primary=[{
        "id":"a",
        "text":"5.00 m",
        "center":{"x":100.0,"y":100.0},
        "confidence":0.55,
        "kind":"dimension",
    }]
    secondary=[{
        "id":"b",
        "text":"5.00 m",
        "center":{"x":103.0,"y":101.0},
        "confidence":0.91,
        "kind":"dimension",
    }]
    merged=_merge_labels(primary,secondary,12)
    assert len(merged)==1
    assert merged[0]["confidence"]==0.91


def test_dimension_classification_supports_cm_and_mm():
    assert classify_text("420 cm")=="dimension"
    assert classify_text("420 سم")=="dimension"
    assert classify_text("4200 mm")=="dimension"
    assert classify_text("4200 مم")=="dimension"


def test_clockwise_ocr_coordinates_restore_to_original_image():
    labels=[{
        "id":"rotated",
        "text":"4.20 m",
        "center":{"x":79.0,"y":30.0},
        "confidence":0.9,
        "kind":"dimension",
    }]
    restored=_restore_rotated_labels(labels,original_h=100,original_w=200,direction="cw")
    assert restored[0]["center"]=={"x":30.0,"y":20.0}


def test_counterclockwise_ocr_coordinates_restore_to_original_image():
    labels=[{
        "id":"rotated",
        "text":"4.20 m",
        "center":{"x":20.0,"y":169.0},
        "confidence":0.9,
        "kind":"dimension",
    }]
    restored=_restore_rotated_labels(labels,original_h=100,original_w=200,direction="ccw")
    assert restored[0]["center"]=={"x":30.0,"y":20.0}


def test_text_duplicate_prefers_higher_confidence_provider():
    primary=[{
        "id":"local",
        "text":"غرفة النوم",
        "center":{"x":220.0,"y":180.0},
        "confidence":0.62,
        "kind":"room_name",
        "provenance":"ocr",
    }]
    secondary=[{
        "id":"cloud",
        "text":"غرفة النوم",
        "center":{"x":224.0,"y":181.0},
        "confidence":0.97,
        "kind":"room_name",
        "provenance":"cloud-ocr",
    }]
    merged=_merge_labels(primary,secondary,14)
    assert len(merged)==1
    assert merged[0]["confidence"]==0.97
    assert merged[0]["provenance"]=="cloud-ocr"



def test_architectural_area_labels_are_room_names():
    for text in ["Balcony","SHAFT","Elevator","Stairs","شرفة","مصعد","درج"]:
        assert classify_text(text)=="room_name"
