import cv2
import numpy as np

from app.rooms import _component_polygon,detect_rooms


def test_near_rectangle_is_canonicalized_to_four_points():
    mask=np.zeros((120,160),dtype=np.uint8)
    cv2.rectangle(mask,(10,10),(150,110),255,-1)
    polygon,area=_component_polygon(mask,20,30)
    assert len(polygon)==4
    assert area>10000


def test_l_shaped_room_keeps_its_real_polygon():
    mask=np.zeros((180,180),dtype=np.uint8)
    cv2.rectangle(mask,(10,10),(70,165),255,-1)
    cv2.rectangle(mask,(10,105),(165,165),255,-1)
    polygon,area=_component_polygon(mask,0,0)

    xs=[p["x"] for p in polygon]
    ys=[p["y"] for p in polygon]
    bbox_area=(max(xs)-min(xs))*(max(ys)-min(ys))
    assert len(polygon)>4
    assert area<bbox_area*0.8


def test_detect_rooms_preserves_slanted_closed_room():
    mask=np.zeros((600,600),dtype=np.uint8)
    diamond=np.array([[300,90],[510,300],[300,510],[90,300]],dtype=np.int32)
    cv2.polylines(mask,[diamond],True,255,10)

    rooms=detect_rooms(mask,[],meters_per_pixel=.01)
    assert len(rooms)==1
    polygon=rooms[0]["polygon"]
    assert len(polygon)>=4

    xs={round(point["x"]) for point in polygon}
    ys={round(point["y"]) for point in polygon}
    # A bounding-box regression would have only two x and two y levels.
    assert len(xs)>=3
    assert len(ys)>=3
    assert 7.5<rooms[0]["areaM2"]<10.0
