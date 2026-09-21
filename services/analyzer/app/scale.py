from __future__ import annotations
import math
import re
from statistics import median
from .ocr import normalize_digits


def _metric_value(text:str)->tuple[float|None,bool]:
    match=re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|مم|سم|متر|م)?\b",text)
    if not match:
        return None,False
    value=float(match.group(1))
    unit=(match.group(2) or "").lower()
    if unit in ("mm","مم"):
        value/=1000.0
    elif unit in ("cm","سم"):
        value/=100.0
    explicit=bool(unit)
    return value,explicit


def _scale_candidates(labels:list[dict],walls:list[dict],width:int,height:int)->list[tuple[float,bool]]:
    candidates:list[tuple[float,bool]]=[]
    max_distance=min(width,height)*0.12

    for label in labels:
        if label["kind"]!="dimension":
            continue
        text=normalize_digits(label["text"]).lower()
        if re.search(r"(?:m|م)\s*[²2]",text):
            continue
        value,explicit=_metric_value(text)
        if value is None or not 0.4<=value<=40:
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
                candidates.append((ratio,explicit))
    return candidates


def estimate_scale_with_diagnostics(labels:list[dict],walls:list[dict],width:int,height:int)->tuple[float|None,float|None,list[str]]:
    candidates=_scale_candidates(labels,walls,width,height)
    if not candidates:
        return None,None,[]

    explicit=[item for item in candidates if item[1]]
    working=explicit if explicit else candidates
    warnings:list[str]=[]

    if not explicit and len(working)<2:
        return None,None,[]

    ratios=[ratio for ratio,_ in working]
    center=median(ratios)
    filtered=[
        (ratio,is_explicit)
        for ratio,is_explicit in working
        if abs(ratio-center)/max(center,1e-9)<=0.18
    ]

    if len(working)>=2 and not filtered:
        return None,None,["الأبعاد المقروءة تعطي مقاييس متعارضة؛ يلزم تثبيت المقياس يدويًا قبل التعديل بالمتر."]

    # If most explicit readings disagree, do not force an automatic scale.
    if len(working)>=3 and len(filtered)/len(working)<0.60:
        return None,None,["هناك تعارض كبير بين الأبعاد المقروءة؛ لم يعتمد النظام مقياسًا تلقائيًا."]

    if not filtered:
        filtered=working

    rejected=len(working)-len(filtered)
    if rejected:
        warnings.append(f"تم تجاهل {rejected} قراءة أبعاد متعارضة عند حساب مقياس الرسم.")

    filtered_ratios=[ratio for ratio,_ in filtered]
    result=median(filtered_ratios)
    deviations=[abs(value-result)/max(result,1e-9) for value in filtered_ratios]
    spread=median(deviations) if deviations else 1.0

    if len(filtered)==1:
        confidence=0.60 if explicit else 0.0
    else:
        confidence=0.68+min(0.18,0.06*(len(filtered)-2))
        if explicit:
            confidence+=0.06
        confidence-=min(0.20,spread)

    if spread>0.08:
        warnings.append("يوجد تباين ملحوظ بين الأبعاد المستخدمة في المعايرة؛ راجع المقياس بصريًا.")

    confidence=max(0.55,min(0.95,confidence))
    return result,confidence,warnings


def estimate_scale(labels:list[dict],walls:list[dict],width:int,height:int)->tuple[float|None,float|None]:
    scale,confidence,_=estimate_scale_with_diagnostics(labels,walls,width,height)
    return scale,confidence
