from __future__ import annotations

import cv2
import numpy as np


def _point(value:dict)->tuple[int,int]:
    return int(round(float(value["x"]))),int(round(float(value["y"])))


def render_extraction_overlay(image:np.ndarray,plan:dict)->np.ndarray:
    """Render canonical extraction over the source image for benchmark review."""
    canvas=image.copy()
    if canvas.ndim==2:
        canvas=cv2.cvtColor(canvas,cv2.COLOR_GRAY2BGR)

    for room in plan.get("rooms",[]):
        polygon=room.get("polygon") or []
        if len(polygon)<3:
            continue
        contour=np.array([_point(point) for point in polygon],dtype=np.int32).reshape((-1,1,2))
        cv2.polylines(canvas,[contour],True,(40,170,40),2,cv2.LINE_AA)
        center=np.mean(contour.reshape(-1,2),axis=0)
        cv2.putText(
            canvas,
            str(room.get("id","room")),
            (int(center[0]),int(center[1])),
            cv2.FONT_HERSHEY_SIMPLEX,
            .42,
            (40,130,40),
            1,
            cv2.LINE_AA,
        )

    for wall in plan.get("walls",[]):
        a=_point(wall["a"]); b=_point(wall["b"])
        thickness=max(1,min(8,int(round(float(wall.get("thicknessPx",4.0))/3))))
        cv2.line(canvas,a,b,(20,70,230),thickness,cv2.LINE_AA)

    for collection,color in (
        (plan.get("doors",[]),(20,150,240)),
        (plan.get("windows",[]),(220,130,20)),
    ):
        for opening in collection:
            a=_point(opening["a"]); b=_point(opening["b"])
            cv2.line(canvas,a,b,color,4,cv2.LINE_AA)

    for symbol in plan.get("symbols",[]):
        a=_point(symbol["a"]); b=_point(symbol["b"])
        cv2.rectangle(canvas,a,b,(190,30,190),2,cv2.LINE_AA)
        cv2.putText(
            canvas,
            str(symbol.get("kind","symbol")),
            (a[0],max(12,a[1]-4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            .42,
            (160,20,160),
            1,
            cv2.LINE_AA,
        )

    return canvas
