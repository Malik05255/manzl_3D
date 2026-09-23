import cv2
import numpy as np

from app.rooms import build_room_barrier,detect_rooms


def _two_room_mask()->np.ndarray:
    mask=np.zeros((500,700),dtype=np.uint8)
    # Exterior shell.
    cv2.rectangle(mask,(70,70),(630,430),255,12)
    # Center partition with a 66 px doorway.
    cv2.line(mask,(350,70),(350,214),255,12)
    cv2.line(mask,(350,280),(350,430),255,12)
    return mask


def test_room_barrier_seals_standard_door_gap_for_segmentation():
    raw=_two_room_mask()
    labels=[
        {"id":"a","text":"غرفة","center":{"x":210.0,"y":250.0},"confidence":.95,"kind":"room_name"},
        {"id":"b","text":"صالة","center":{"x":490.0,"y":250.0},"confidence":.95,"kind":"room_name"},
    ]

    raw_rooms=detect_rooms(raw,labels,None,min_area_ratio=.01,max_area_ratio=.80)
    sealed=build_room_barrier(raw)
    sealed_rooms=detect_rooms(sealed,labels,None,min_area_ratio=.01,max_area_ratio=.80)

    assert len(raw_rooms)<=1
    assert len(sealed_rooms)==2
    assert {room["name"] for room in sealed_rooms}=={"غرفة","صالة"}


def test_room_barrier_does_not_close_large_open_plan_connection():
    mask=np.zeros((500,700),dtype=np.uint8)
    cv2.rectangle(mask,(70,70),(630,430),255,12)
    # Partition has a very wide 190 px connection.
    cv2.line(mask,(350,70),(350,150),255,12)
    cv2.line(mask,(350,340),(350,430),255,12)

    sealed=build_room_barrier(mask)
    # The center of the intentionally large opening must remain open.
    assert sealed[245,350]==0
