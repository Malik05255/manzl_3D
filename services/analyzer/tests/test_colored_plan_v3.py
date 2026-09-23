import cv2
import numpy as np

from app.document import preprocess
from app.rooms import build_room_barrier,detect_rooms
from app.structural import extract_structural_wall_mask,filter_walls_by_structural_support
from app.walls import detect_walls,fuse_region_wall_candidates,rasterize_wall_mask


def _colored_residential_plan():
    image=np.full((760,920,3),255,dtype=np.uint8)

    # BGR blue structural walls.
    wall=(215,105,45)
    cv2.rectangle(image,(90,90),(830,670),wall,18)

    # Center partition with a normal doorway gap.
    cv2.line(image,(455,90),(455,320),wall,18)
    cv2.line(image,(455,410),(455,670),wall,18)

    # Green dimensions outside the shell.
    dim=(45,150,65)
    cv2.line(image,(90,42),(830,42),dim,2)
    for x in (90,455,830):
        cv2.line(image,(x,31),(x,54),dim,2)

    # Red room-name strokes/text-like noise inside the rooms.
    red=(55,55,190)
    cv2.putText(image,"ROOM",(190,260),cv2.FONT_HERSHEY_SIMPLEX,1.0,red,2,cv2.LINE_AA)
    cv2.putText(image,"HALL",(575,260),cv2.FONT_HERSHEY_SIMPLEX,1.0,red,2,cv2.LINE_AA)

    labels=[
        {"id":"l","text":"غرفة","center":{"x":250.0,"y":360.0},"confidence":.95,"kind":"room_name"},
        {"id":"r","text":"صالة","center":{"x":650.0,"y":360.0},"confidence":.95,"kind":"room_name"},
    ]
    return image,labels


def test_colored_plan_v3_reconstructs_rooms_without_dimension_pollution():
    image,labels=_colored_residential_plan()
    _,ink=preprocess(image)
    structural=extract_structural_wall_mask(image,ink)

    # The external green dimension rule must not be classified as a wall band.
    assert cv2.countNonZero(structural[34:50,120:800])<500

    walls,_=detect_walls(ink)
    walls=fuse_region_wall_candidates(walls,structural)
    accepted,_=filter_walls_by_structural_support(walls,structural,minimum_support=.34)
    assert len(accepted)>=5
    assert any(wall.get("provenance") in {"structural-mask","mixed"} for wall in accepted)

    barrier=rasterize_wall_mask(
        accepted,image.shape[0],image.shape[1],
        base_mask=structural,
    )
    segmentation=build_room_barrier(barrier)
    rooms=detect_rooms(
        segmentation,labels,None,
        min_area_ratio=.01,max_area_ratio=.80,
    )

    assert len(rooms)==2
    assert {room["name"] for room in rooms}=={"غرفة","صالة"}
    # Both room centroids must remain inside the architectural shell rather
    # than leaking into the dimension area above it.
    assert all(min(p["y"] for p in room["polygon"])>80 for room in rooms)
