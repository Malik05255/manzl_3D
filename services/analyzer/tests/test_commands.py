from app.commands import parse_selected_opening_action,parse_selected_wall_action,parse_target_size,room_match

def test_parses_arabic_dimensions():
    assert parse_target_size("عدل غرفة النوم إلى ٥×٥") == (5.0,5.0)

def test_matches_arabic_room():
    assert room_match("كبر غرفة النوم إلى 5×5","غرفة النوم") == 1.0


def test_parses_selected_opening_commands():
    assert parse_selected_opening_action("اجعل عرضه 90 سم")==("width",{"width_m":0.9})
    assert parse_selected_opening_action("حركه يمين 30 سم")==("move",{"amount_m":0.3,"direction":"right"})
    assert parse_selected_opening_action("حوله نافذة")==("kind",{"kind":"window"})
    assert parse_selected_opening_action("احذفه")==("remove",{})


def test_parses_selected_wall_commands():
    assert parse_selected_wall_action("اجعل سماكته 20 سم")==("thickness",{"thickness_m":0.2})
    assert parse_selected_wall_action("حركه يسار 50 سم")==("move",{"amount_m":0.5,"direction":"left"})
    assert parse_selected_wall_action("اضف باب")==("add_opening",{"kind":"door"})
