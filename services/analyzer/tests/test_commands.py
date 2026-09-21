from app.commands import parse_target_size,room_match

def test_parses_arabic_dimensions():
    assert parse_target_size("عدل غرفة النوم إلى ٥×٥") == (5.0,5.0)

def test_matches_arabic_room():
    assert room_match("كبر غرفة النوم إلى 5×5","غرفة النوم") == 1.0
