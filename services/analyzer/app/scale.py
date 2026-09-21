from __future__ import annotations
import math
import re
from statistics import median
from .ocr import normalize_digits

def estimate_scale(labels:list[dict],walls:list[dict],width:int,height:int)->tuple[float|None,float|None]:
    candidates=[]
    max_distance=min(width,height)*0.12
    for label in labels:
        if label["kind"]!="dimension": continue
        text=normalize_digits(label["text"]).lower()
        if re.search(r"(?:m|م)\s*[²2]",text): continue
        match=re.search(r"(\d+(?:\.\d+)?)\s*(?:m|م|متر)?",text)
        if not match: continue
        value=float(match.group(1))
        if not 0.4<=value<=40: continue
        cx,cy=label["center"]["x"],label["center"]["y"]
        best=None
        for wall in walls:
            x1,y1,x2,y2=wall["a"]["x"],wall["a"]["y"],wall["b"]["x"],wall["b"]["y"]
            length=math.hypot(x2-x1,y2-y1)
            if length<40: continue
            distance=math.hypot((x1+x2)/2-cx,(y1+y2)/2-cy)
            if distance<=max_distance and (best is None or distance<best[0]): best=(distance,length)
        if best:
            ratio=value/best[1]
            if 0.0005<=ratio<=0.25: candidates.append(ratio)
    if not candidates: return None,None
    center=median(candidates)
    deviations=[abs(v-center)/center for v in candidates]
    spread=median(deviations) if deviations else 1.0
    filtered=[v for v in candidates if abs(v-center)/center<=0.30] or candidates
    result=median(filtered)
    confidence=0.60 if len(filtered)==1 else max(0.55,min(0.94,0.90-spread))
    return result,confidence
