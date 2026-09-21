import cv2
import numpy as np

from app.openings import detect_doors,detect_windows


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
