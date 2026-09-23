import os
from pathlib import Path

import cv2
import numpy as np

from app.vision_segmentation import learned_opening_detections,semantic_room_barrier,wall_consensus_score


def test_semantic_room_barrier_uses_learned_structure_not_text_holes():
    masks={
        "room":np.zeros((120,180),dtype=np.uint8),
        "door":np.zeros((120,180),dtype=np.uint8),
        "window":np.zeros((120,180),dtype=np.uint8),
        "wall":np.zeros((120,180),dtype=np.uint8),
        "background":np.zeros((120,180),dtype=np.uint8),
    }
    masks["room"][20:100,20:160]=255
    masks["wall"][15:105,88:93]=255
    masks["door"][48:72,86:95]=255
    # Simulate a semantic/text hole inside a room. It must not become a barrier.
    masks["background"][45:60,35:55]=255
    masks["room"][45:60,35:55]=0
    result={"plausible":True,"masks":masks,"confidence":np.full((120,180),.9,dtype=np.float32)}
    barrier=semantic_room_barrier(result)
    assert barrier[52,45]==0
    assert barrier[50,90]==255
    assert barrier[60,90]==255


def test_learned_openings_emit_boxes_for_connected_components():
    masks={name:np.zeros((120,180),dtype=np.uint8) for name in ("background","room","wall","door","window")}
    masks["door"][40:55,70:95]=255
    masks["window"][75:84,20:60]=255
    confidence=np.full((120,180),.93,dtype=np.float32)
    result={"plausible":True,"masks":masks,"confidence":confidence}
    detections=learned_opening_detections(result)
    kinds={item["class"] for item in detections}
    assert kinds=={"door","window"}
    assert all(item["confidence"]>.8 for item in detections)


def test_wall_consensus_rejects_unrelated_learned_geometry():
    masks={name:np.zeros((100,100),dtype=np.uint8) for name in ("background","room","wall","door","window")}
    masks["wall"][10:20,10:90]=255
    result={"plausible":True,"masks":masks}
    heuristic=np.zeros((100,100),dtype=np.uint8)
    heuristic[70:80,10:90]=255
    assert wall_consensus_score(result,heuristic)==0.0

    heuristic[10:20,10:90]=255
    heuristic[70:80,10:90]=0
    assert wall_consensus_score(result,heuristic)>.99
