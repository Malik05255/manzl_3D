from app.ocr import _merge_labels,classify_text,order_line_words


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
