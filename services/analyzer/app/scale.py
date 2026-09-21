from __future__ import annotations
import math
import re
from statistics import median
from .ocr import normalize_digits


def _explicit_metric_unit(text:str)->bool:
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:m|م|متر)\b",text))


def estimate_scale(labels:list[dict],walls:list[dict],width:int,height:int)->tuple[float|None,float|None]:
    candidates:list[tuple[float,bool]]=[]
    max_distance=min(width,height)*0.12

    for label in labels:
        if label["kind"]!="dimension":
            continue
        text=normalize_digits(label["text"]).lower()
        if re.search(r"(?:m|م)\s*[²2]",text):
            continue
        match=re.search(r"(\d+(?:\.\d+)?)\s*(?:m|م|متر)?",text)
        if not match:
            continue
        value=float(match.group(1))
        if not 0.4<=value<=40:
            continue

        cx,cy=label["center"]["x"],label["center"]["y"]
        best=None
        for wall in walls:
            x1,y1,x2,y2=wall["a"]["x"],wall["a"]["y"],wall["b"]["x"],wall["b"]["y"]
            length=math.hypot(x2-x1,y2-y1)
            if length<40:
                continue
            distance=math.hypot((x1+x2)/2-cx,(y1+y2)/2-cy)
            if distance<=max_distance and (best is None or distance<best[0]):
                best=(distance,length)
        if best:
            ratio=value/best[1]
            if 0.0005<=ratio<=0.25:
                candidates.append((ratio,_explicit_metric_unit(text)))

    if not candidates:
        return None,None

    ratios=[ratio for ratio,_ in candidates]
    center=median(ratios)
    filtered=[
        (ratio,explicit)
        for ratio,explicit in candidates
        if abs(ratio-center)/max(center,1e-9)<=0.18
    ] or candidates

    explicit_count=sum(1 for _,explicit in filtered if explicit)
    if explicit_count==0 and len(filtered)<2:
        # A single unitless number is too ambiguous to calibrate a whole drawing.
        return None,None

    filtered_ratios=[ratio for ratio,_ in filtered]
    result=median(filtered_ratios)
    deviations=[abs(value-result)/max(result,1e-9) for value in filtered_ratios]
    spread=median(deviations) if deviations else 1.0

    if len(filtered)==1:
        confidence=0.60 if explicit_count else 0.0
    else:
        confidence=0.68+min(0.18,0.06*(len(filtered)-2))
        if explicit_count:
            confidence+=0.06
        confidence-=min(0.20,spread)
    confidence=max(0.55,min(0.95,confidence))
    return result,confidence
