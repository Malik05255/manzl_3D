import cv2
import numpy as np

from app.openings import detect_doors,detect_windows,normalize_opening_hosts


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
