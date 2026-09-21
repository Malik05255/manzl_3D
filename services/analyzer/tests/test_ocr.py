from app.ocr import classify_text,order_line_words


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
