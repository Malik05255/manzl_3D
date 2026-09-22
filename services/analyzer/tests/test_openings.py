import cv2
import numpy as np

from app.openings import _door_arc_evidence_details,_door_subtype_from_evidence,detect_doors,detect_windows,fuse_ai_opening_detections,normalize_opening_hosts,resolve_opening_conflicts


def wall(wall_id,x1,y1,x2,y2):
    return {
        "id":wall_id,
        "a":{"x":float(x1),"y":float(y1)},
        "b":{"x":float(x2),"y":float(y2)},
        "thicknessPx":4.0,
        "confidence":0.9,
    }


def test_detects_door_gap_when_swing_leaf_is_visible():
    image=np.full((260,320,3),255,dtype=np.uint8)
    cv2.line(image,(30,130),(120,130),(0,0,0),5)
    cv2.line(image,(170,130),(290,130),(0,0,0),5)
    cv2.line(image,(120,130),(165,88),(0,0,0),4)

    doors=detect_doors(
        image,
        [wall("left",30,130,120,130),wall("right",170,130,290,130)],
        meters_per_pixel=0.02,
    )

    assert len(doors)==1
    assert doors[0]["kind"]=="door"
    assert doors[0]["doorSubtype"]=="single_swing"
    assert doors[0]["doorSwingSide"]=="negative"
    assert doors[0]["doorSwingDepthPx"]>30
    assert doors[0]["confidence"]>=0.76


def test_plain_wall_gap_without_door_evidence_is_not_auto_accepted():
    image=np.full((260,320,3),255,dtype=np.uint8)
    cv2.line(image,(30,130),(120,130),(0,0,0),5)
    cv2.line(image,(170,130),(290,130),(0,0,0),5)

    doors=detect_doors(
        image,
        [wall("left",30,130,120,130),wall("right",170,130,290,130)],
        meters_per_pixel=0.02,
    )

    assert doors==[]


def test_detects_window_gap_with_parallel_glazing_lines():
    image=np.full((280,360,3),255,dtype=np.uint8)
    cv2.line(image,(25,140),(120,140),(0,0,0),5)
    cv2.line(image,(220,140),(335,140),(0,0,0),5)
    cv2.line(image,(122,134),(218,134),(0,0,0),3)
    cv2.line(image,(122,146),(218,146),(0,0,0),3)

    windows=detect_windows(
        image,
        [wall("left",25,140,120,140),wall("right",220,140,335,140)],
        meters_per_pixel=0.02,
    )

    assert len(windows)==1
    assert windows[0]["kind"]=="window"
    assert windows[0]["confidence"]>=0.80


def test_blank_gap_is_not_window():
    image=np.full((280,360,3),255,dtype=np.uint8)
    cv2.line(image,(25,140),(120,140),(0,0,0),5)
    cv2.line(image,(220,140),(335,140),(0,0,0),5)

    windows=detect_windows(
        image,
        [wall("left",25,140,120,140),wall("right",220,140,335,140)],
        meters_per_pixel=0.02,
    )

    assert windows==[]


def test_normalizes_detected_gap_into_one_host_wall():
    image=np.full((260,320,3),255,dtype=np.uint8)
    cv2.line(image,(30,130),(120,130),(0,0,0),5)
    cv2.line(image,(170,130),(290,130),(0,0,0),5)
    cv2.line(image,(120,130),(165,88),(0,0,0),4)
    walls=[wall("left",30,130,120,130),wall("right",170,130,290,130)]
    doors=detect_doors(image,walls,meters_per_pixel=.02)

    normalized,doors,_=normalize_opening_hosts(walls,doors,[])
    assert len(normalized)==1
    host=normalized[0]
    assert min(host["a"]["x"],host["b"]["x"])==30
    assert max(host["a"]["x"],host["b"]["x"])==290
    assert doors[0]["wallId"]==host["id"]
    assert min(doors[0]["a"]["x"],doors[0]["b"]["x"])>=30
    assert max(doors[0]["a"]["x"],doors[0]["b"]["x"])<=290


def test_multiple_openings_merge_one_collinear_wall_chain():
    walls=[
        wall("s1",0,100,100,100),
        wall("s2",150,100,250,100),
        wall("s3",300,100,400,100),
    ]
    doors=[
        {"id":"d1","kind":"door","wallId":"s1","a":{"x":100.0,"y":100.0},"b":{"x":150.0,"y":100.0},"confidence":.9},
        {"id":"d2","kind":"door","wallId":"s2","a":{"x":250.0,"y":100.0},"b":{"x":300.0,"y":100.0},"confidence":.9},
    ]
    normalized,doors,_=normalize_opening_hosts(walls,doors,[])
    assert len(normalized)==1
    host=normalized[0]
    assert min(host["a"]["x"],host["b"]["x"])==0
    assert max(host["a"]["x"],host["b"]["x"])==400
    assert {item["wallId"] for item in doors}=={host["id"]}


def test_detects_door_gap_on_slanted_wall():
    image=np.full((420,520,3),255,dtype=np.uint8)
    cv2.line(image,(80,100),(200,190),(0,0,0),5)
    cv2.line(image,(260,235),(430,363),(0,0,0),5)
    # Door leaf rotates away from the wall direction.
    cv2.line(image,(200,190),(255,150),(0,0,0),4)

    doors=detect_doors(
        image,
        [wall("left",80,100,200,190),wall("right",260,235,430,363)],
        meters_per_pixel=.02,
    )
    assert len(doors)==1
    assert doors[0]["kind"]=="door"
    assert abs(doors[0]["a"]["x"]-200)<8
    assert abs(doors[0]["b"]["x"]-260)<8


def test_detects_window_gap_on_slanted_wall():
    image=np.full((460,560,3),255,dtype=np.uint8)
    cv2.line(image,(70,100),(190,190),(0,0,0),5)
    cv2.line(image,(300,273),(470,400),(0,0,0),5)

    # Two glazing strokes parallel to the host wall across the gap.
    cv2.line(image,(195,184),(295,259),(0,0,0),3)
    cv2.line(image,(188,195),(288,270),(0,0,0),3)

    windows=detect_windows(
        image,
        [wall("left",70,100,190,190),wall("right",300,273,470,400)],
        meters_per_pixel=.02,
    )
    assert len(windows)==1
    assert windows[0]["kind"]=="window"


def test_normalizes_slanted_opening_gap_into_single_host_wall():
    walls=[
        wall("left",80,100,200,190),
        wall("right",260,235,430,363),
    ]
    doors=[{
        "id":"door","kind":"door","wallId":"left",
        "a":{"x":200.0,"y":190.0},
        "b":{"x":260.0,"y":235.0},
        "confidence":.9,
    }]
    normalized,doors,_=normalize_opening_hosts(walls,doors,[])
    assert len(normalized)==1
    assert doors[0]["wallId"]==normalized[0]["id"]
    dx=normalized[0]["b"]["x"]-normalized[0]["a"]["x"]
    dy=normalized[0]["b"]["y"]-normalized[0]["a"]["y"]
    assert abs(dx)>200 and abs(dy)>140


def test_single_parallel_stroke_is_not_window():
    image=np.full((280,360,3),255,dtype=np.uint8)
    cv2.line(image,(25,140),(120,140),(0,0,0),5)
    cv2.line(image,(220,140),(335,140),(0,0,0),5)
    # A single thick line can yield two Hough edges. It must not become a window.
    cv2.line(image,(122,140),(218,140),(0,0,0),4)

    windows=detect_windows(
        image,
        [wall("left",25,140,120,140),wall("right",220,140,335,140)],
        meters_per_pixel=.02,
    )
    assert windows==[]


def test_unanchored_diagonal_annotation_is_not_door_leaf():
    image=np.full((260,320,3),255,dtype=np.uint8)
    cv2.line(image,(30,130),(120,130),(0,0,0),5)
    cv2.line(image,(170,130),(290,130),(0,0,0),5)
    # Diagonal annotation/text-like stroke is near the gap but not hinged at either edge.
    cv2.line(image,(137,95),(157,115),(0,0,0),3)

    doors=detect_doors(
        image,
        [wall("left",30,130,120,130),wall("right",170,130,290,130)],
        meters_per_pixel=.02,
    )
    assert doors==[]


def test_detects_double_swing_door_from_two_hinged_leaves():
    image=np.full((300,360,3),255,dtype=np.uint8)
    cv2.line(image,(30,150),(120,150),(0,0,0),5)
    cv2.line(image,(210,150),(330,150),(0,0,0),5)
    cv2.line(image,(120,150),(158,108),(0,0,0),4)
    cv2.line(image,(210,150),(172,108),(0,0,0),4)

    doors=detect_doors(
        image,
        [wall("left",30,150,120,150),wall("right",210,150,330,150)],
        meters_per_pixel=.02,
    )
    assert len(doors)==1
    assert doors[0]["doorSubtype"]=="double_swing"
    assert doors[0]["doorSwingSide"]=="negative"
    assert doors[0]["doorSwingDepthPx"]>30



def test_arc_only_swing_is_detected_from_hinge_center():
    image=np.full((320,380,3),255,dtype=np.uint8)
    cv2.line(image,(30,150),(120,150),(0,0,0),5)
    cv2.line(image,(210,150),(350,150),(0,0,0),5)
    # Quarter-circle swing arc centred on the left hinge. No door-leaf line.
    cv2.ellipse(image,(120,150),(86,86),0,270,360,(0,0,0),3)

    evidence,hinges,side,depth=_door_arc_evidence_details(
        image,
        {"x":120.0,"y":150.0},
        {"x":210.0,"y":150.0},
        90.0,
    )
    assert evidence>=1
    assert "a" in hinges
    assert side=="negative"
    assert depth>55

    doors=detect_doors(
        image,
        [wall("left",30,150,120,150),wall("right",210,150,350,150)],
        meters_per_pixel=.01,
    )
    assert len(doors)==1
    assert doors[0]["doorSubtype"]=="single_swing"
    assert doors[0]["doorSwingSide"]=="negative"
    assert doors[0]["doorSwingDepthPx"]>55



def test_nearby_parallel_annotation_lines_are_not_window():
    image=np.full((300,380,3),255,dtype=np.uint8)
    cv2.line(image,(25,150),(120,150),(0,0,0),5)
    cv2.line(image,(220,150),(355,150),(0,0,0),5)
    # Two parallel annotation lines sit near the opening but too far from the
    # wall centreline to represent glazing.
    cv2.line(image,(125,105),(215,105),(0,0,0),2)
    cv2.line(image,(125,115),(215,115),(0,0,0),2)

    windows=detect_windows(
        image,
        [wall("left",25,150,120,150),wall("right",220,150,355,150)],
        meters_per_pixel=.02,
    )
    assert windows==[]


def test_short_parallel_marks_inside_gap_are_not_window():
    image=np.full((300,380,3),255,dtype=np.uint8)
    cv2.line(image,(25,150),(120,150),(0,0,0),5)
    cv2.line(image,(220,150),(355,150),(0,0,0),5)
    cv2.line(image,(150,143),(185,143),(0,0,0),2)
    cv2.line(image,(150,157),(185,157),(0,0,0),2)

    windows=detect_windows(
        image,
        [wall("left",25,150,120,150),wall("right",220,150,355,150)],
        meters_per_pixel=.02,
    )
    assert windows==[]



def test_same_gap_door_suppresses_window_duplicate():
    doors=[{
        "id":"door-1","kind":"door",
        "a":{"x":100.0,"y":150.0},"b":{"x":190.0,"y":150.0},
        "confidence":.84,
    }]
    windows=[{
        "id":"window-1","kind":"window",
        "a":{"x":103.0,"y":151.0},"b":{"x":188.0,"y":151.0},
        "confidence":.91,
    }]
    kept_doors,kept_windows=resolve_opening_conflicts(doors,windows)
    assert kept_doors==doors
    assert kept_windows==[]


def test_adjacent_window_is_not_suppressed_by_door():
    doors=[{
        "id":"door-1","kind":"door",
        "a":{"x":100.0,"y":150.0},"b":{"x":190.0,"y":150.0},
        "confidence":.84,
    }]
    windows=[{
        "id":"window-1","kind":"window",
        "a":{"x":230.0,"y":150.0},"b":{"x":330.0,"y":150.0},
        "confidence":.91,
    }]
    _,kept_windows=resolve_opening_conflicts(doors,windows)
    assert kept_windows==windows


def test_different_length_centered_openings_are_not_forced_same_gap():
    doors=[{
        "id":"door-1","kind":"door",
        "a":{"x":140.0,"y":150.0},"b":{"x":200.0,"y":150.0},
        "confidence":.84,
    }]
    windows=[{
        "id":"window-1","kind":"window",
        "a":{"x":70.0,"y":150.0},"b":{"x":270.0,"y":150.0},
        "confidence":.91,
    }]
    _,kept_windows=resolve_opening_conflicts(doors,windows)
    assert kept_windows==windows



def test_ai_single_door_box_projects_onto_nearest_wall():
    walls=[wall("host",20,120,300,120)]
    doors,windows=fuse_ai_opening_detections(
        walls,[],[],
        [{
            "class":"single_door",
            "bbox":[105,75,175,145],
            "confidence":.91,
        }],
        min_confidence=.55,
    )
    assert windows==[]
    assert len(doors)==1
    door=doors[0]
    assert door["wallId"]=="host"
    assert door["doorSubtype"]=="single_swing"
    assert door["provenance"]=="ai"
    assert abs(door["a"]["y"]-120)<1
    assert abs(door["b"]["y"]-120)<1
    assert door["doorSwingDepthPx"] is not None
    assert door["doorSwingDepthPx"]>20


def test_ai_sliding_door_preserves_subtype_without_fake_swing_depth():
    walls=[wall("host",20,120,300,120)]
    doors,_=fuse_ai_opening_detections(
        walls,[],[],
        [{"class":"sliding_door","bbox":[100,100,180,140],"confidence":.89}],
    )
    assert len(doors)==1
    assert doors[0]["doorSubtype"]=="sliding"
    assert doors[0]["doorSwingDepthPx"] is None


def test_ai_window_box_projects_onto_wall():
    walls=[wall("host",20,120,300,120)]
    doors,windows=fuse_ai_opening_detections(
        walls,[],[],
        [{"class":"bay_window","bbox":[190,108,255,132],"confidence":.88}],
    )
    assert doors==[]
    assert len(windows)==1
    assert windows[0]["wallId"]=="host"
    assert windows[0]["provenance"]=="ai"


def test_ai_opening_without_nearby_wall_is_rejected():
    walls=[wall("host",20,120,300,120)]
    doors,windows=fuse_ai_opening_detections(
        walls,[],[],
        [{"class":"single_door","bbox":[110,260,180,320],"confidence":.95}],
    )
    assert doors==[]
    assert windows==[]


def test_ai_opening_does_not_duplicate_geometry_detection():
    walls=[wall("host",20,120,300,120)]
    geometry=[{
        "id":"door-1",
        "kind":"door",
        "doorSubtype":"single_swing",
        "doorSwingSide":"negative",
        "doorSwingDepthPx":60.0,
        "wallId":"host",
        "a":{"x":110.0,"y":120.0},
        "b":{"x":170.0,"y":120.0},
        "confidence":.90,
        "reviewed":False,
        "provenance":"opencv",
    }]
    doors,_=fuse_ai_opening_detections(
        walls,geometry,[],
        [{"class":"single_door","bbox":[106,80,174,146],"confidence":.96}],
    )
    assert len(doors)==1
    assert doors[0]["id"]=="door-1"
    assert doors[0]["provenance"]=="opencv"



def test_strong_ai_window_can_correct_weaker_opencv_door():
    door={
        "id":"door-weak",
        "kind":"door",
        "doorSubtype":"double_swing",
        "doorSwingSide":"unknown",
        "doorSwingDepthPx":8.0,
        "wallId":"host",
        "a":{"x":100.0,"y":120.0},
        "b":{"x":170.0,"y":120.0},
        "confidence":.78,
        "reviewed":False,
        "provenance":"opencv",
    }
    window={
        "id":"window-ai",
        "kind":"window",
        "wallId":"host",
        "a":{"x":102.0,"y":120.0},
        "b":{"x":169.0,"y":120.0},
        "confidence":.91,
        "reviewed":False,
        "provenance":"ai",
    }
    doors,windows=resolve_opening_conflicts([door],[window])
    assert doors==[]
    assert [item["id"] for item in windows]==["window-ai"]


def test_convincing_geometric_swing_beats_close_ai_window():
    door={
        "id":"door-strong",
        "kind":"door",
        "doorSubtype":"single_swing",
        "doorSwingSide":"negative",
        "doorSwingDepthPx":62.0,
        "wallId":"host",
        "a":{"x":100.0,"y":120.0},
        "b":{"x":170.0,"y":120.0},
        "confidence":.86,
        "reviewed":False,
        "provenance":"opencv",
    }
    window={
        "id":"window-ai",
        "kind":"window",
        "wallId":"host",
        "a":{"x":102.0,"y":120.0},
        "b":{"x":169.0,"y":120.0},
        "confidence":.94,
        "reviewed":False,
        "provenance":"ai",
    }
    doors,windows=resolve_opening_conflicts([door],[window])
    assert [item["id"] for item in doors]==["door-strong"]
    assert windows==[]



def test_mixed_leaf_and_opposite_arc_does_not_create_double_swing():
    image=np.full((320,380,3),255,dtype=np.uint8)
    cv2.line(image,(30,150),(120,150),(0,0,0),5)
    cv2.line(image,(210,150),(350,150),(0,0,0),5)
    # One hinged leaf on the left.
    cv2.line(image,(120,150),(160,105),(0,0,0),4)
    # Arc-like evidence centred on the opposite hinge. Mixed evidence should
    # not be enough for a true double swing.
    cv2.ellipse(image,(210,150),(72,72),0,180,270,(0,0,0),3)

    doors=detect_doors(
        image,
        [wall("left",30,150,120,150),wall("right",210,150,350,150)],
        meters_per_pixel=.02,
    )
    assert len(doors)==1
    assert doors[0]["doorSubtype"]=="single_swing"


def test_strong_glazing_survives_one_spurious_leaf_chord_without_arc():
    image=np.full((320,420,3),255,dtype=np.uint8)
    cv2.line(image,(30,160),(120,160),(0,0,0),5)
    cv2.line(image,(260,160),(390,160),(0,0,0),5)
    # Three separated glazing strokes across the opening.
    for y in (150,160,170):
        cv2.line(image,(125,y),(255,y),(0,0,0),2)
    # One short diagonal chord can be produced by nearby annotation/detailing.
    cv2.line(image,(120,160),(172,118),(0,0,0),3)

    windows=detect_windows(
        image,
        [wall("left",30,160,120,160),wall("right",260,160,390,160)],
        meters_per_pixel=.02,
    )
    assert len(windows)==1


def test_real_swing_arc_still_blocks_window_even_with_parallel_strokes():
    image=np.full((320,420,3),255,dtype=np.uint8)
    cv2.line(image,(30,160),(120,160),(0,0,0),5)
    cv2.line(image,(260,160),(390,160),(0,0,0),5)
    for y in (150,160,170):
        cv2.line(image,(125,y),(255,y),(0,0,0),2)
    cv2.ellipse(image,(120,160),(100,100),0,270,360,(0,0,0),3)

    windows=detect_windows(
        image,
        [wall("left",30,160,120,160),wall("right",260,160,390,160)],
        meters_per_pixel=.02,
    )
    assert windows==[]



def test_double_swing_requires_two_visible_leaf_hinges():
    assert _door_subtype_from_evidence({"a","b"},set())=="double_swing"
    assert _door_subtype_from_evidence({"a"},{"a","b"})=="single_swing"
    assert _door_subtype_from_evidence(set(),{"a","b"})=="single_swing"


