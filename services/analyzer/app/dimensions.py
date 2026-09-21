from __future__ import annotations

import math
import re

from .ocr import normalize_digits


def parse_metric_length(text:str)->tuple[float|None,str]:
    normalized=normalize_digits(text).lower().strip()
    if re.search(r"(?:m|م)\s*[²2]",normalized):
        return None,"unknown"
    if re.search(r"\d+(?:\.\d+)?\s*[x×*]\s*\d+(?:\.\d+)?",normalized):
        return None,"unknown"

    match=re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(mm|cm|m|مم|سم|متر|م)?\b",normalized)
    if not match:
        return None,"unknown"
    raw=float(match.group(1))
    unit=(match.group(2) or "").lower()
    if unit in ("mm","مم"):
        return raw/1000.0,"mm"
    if unit in ("cm","سم"):
        return raw/100.0,"cm"
    if unit in ("m","م","متر"):
        return raw,"m"
    return None,"unknown"


def _point_segment_distance(cx:float,cy:float,wall:dict)->tuple[float,float]:
    ax=float(wall["a"]["x"]); ay=float(wall["a"]["y"])
    bx=float(wall["b"]["x"]); by=float(wall["b"]["y"])
    vx=bx-ax; vy=by-ay
    length_sq=vx*vx+vy*vy
    if length_sq<=1e-9:
        return math.hypot(cx-ax,cy-ay),0.0
    t=((cx-ax)*vx+(cy-ay)*vy)/length_sq
    clamped=max(0.0,min(1.0,t))
    px=ax+clamped*vx; py=ay+clamped*vy
    return math.hypot(cx-px,cy-py),t


def extract_dimension_evidence(labels:list[dict],walls:list[dict],width:int,height:int)->list[dict]:
    result=[]
    max_distance=max(18.0,min(width,height)*0.065)
    for label in labels:
        if label.get("kind")!="dimension":
            continue
        text=str(label.get("text","")).strip()
        if not text:
            continue

        value_m,unit=parse_metric_length(text)
        center=label.get("center") or {}
        try:
            cx=float(center["x"]); cy=float(center["y"])
        except (KeyError,TypeError,ValueError):
            continue

        reference_wall_id=None
        orientation="unknown"
        best=None
        for wall in walls:
            distance,t=_point_segment_distance(cx,cy,wall)
            if distance>max_distance or t<-0.20 or t>1.20:
                continue
            if best is None or distance<best[0]:
                best=(distance,wall)
        if best is not None:
            wall=best[1]
            reference_wall_id=str(wall.get("id") or "") or None
            dx=abs(float(wall["b"]["x"])-float(wall["a"]["x"]))
            dy=abs(float(wall["b"]["y"])-float(wall["a"]["y"]))
            orientation="horizontal" if dx>=dy else "vertical"

        result.append({
            "id":f"dimension-{len(result)+1}",
            "sourceLabelId":label.get("id"),
            "text":text,
            "center":{"x":cx,"y":cy},
            "valueM":value_m,
            "unit":unit,
            "orientation":orientation,
            "referenceWallId":reference_wall_id,
            "confidence":float(label.get("confidence",0.5)),
            "reviewed":bool(label.get("reviewed",False)),
            "provenance":label.get("provenance"),
        })
    return result
