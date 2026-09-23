from __future__ import annotations

import math
from statistics import median


def _dimension_scale_candidates(dimensions:list[dict])->list[tuple[float,bool,float]]:
    candidates:list[tuple[float,bool,float]]=[]
    for dimension in dimensions:
        value=dimension.get("valueM")
        span_a=dimension.get("spanA")
        span_b=dimension.get("spanB")
        unit=str(dimension.get("unit") or "unknown")
        if value is None or span_a is None or span_b is None:
            continue
        try:
            value_m=float(value)
            ax=float(span_a["x"]); ay=float(span_a["y"])
            bx=float(span_b["x"]); by=float(span_b["y"])
            confidence=float(dimension.get("confidence",0.5))
        except (TypeError,ValueError,KeyError):
            continue
        pixels=math.hypot(bx-ax,by-ay)
        if not math.isfinite(value_m) or not 0.05<=value_m<=1000:
            continue
        if not math.isfinite(pixels) or pixels<5:
            continue
        ratio=value_m/pixels
        if not 0.00005<=ratio<=10:
            continue
        explicit=unit in ("m","cm","mm")
        if not explicit:
            continue
        candidates.append((ratio,explicit,max(0.0,min(1.0,confidence))))
    return candidates


def estimate_scale_with_diagnostics(dimensions:list[dict],width:int,height:int)->tuple[float|None,float|None,list[str]]:
    del width,height
    candidates=_dimension_scale_candidates(dimensions)
    if not candidates:
        return None,None,[]

    ratios=[ratio for ratio,_,_ in candidates]
    center=median(ratios)
    filtered=[
        item for item in candidates
        if abs(item[0]-center)/max(center,1e-9)<=0.12
    ]

    if len(candidates)>=2 and not filtered:
        return None,None,["الأبعاد المكتشفة تعطي مقاييس متعارضة؛ يلزم تثبيت المقياس يدويًا قبل التعديل بالمتر."]

    if len(candidates)>=3 and len(filtered)/len(candidates)<0.60:
        return None,None,["هناك تعارض كبير بين نطاقات الأبعاد المكتشفة؛ لم يعتمد النظام مقياسًا تلقائيًا."]

    if not filtered:
        filtered=candidates

    rejected=len(candidates)-len(filtered)
    warnings:list[str]=[]
    if rejected:
        warnings.append(f"تم تجاهل {rejected} نطاق أبعاد متعارض عند حساب مقياس الرسم.")

    filtered_ratios=[ratio for ratio,_,_ in filtered]
    result=median(filtered_ratios)
    deviations=[abs(value-result)/max(result,1e-9) for value in filtered_ratios]
    spread=median(deviations) if deviations else 0.0
    evidence_confidence=median([confidence for _,_,confidence in filtered])

    if len(filtered)==1:
        confidence=0.52+0.34*evidence_confidence
    else:
        confidence=0.66+min(0.16,0.05*(len(filtered)-2))+0.16*evidence_confidence
        confidence-=min(0.22,spread*1.8)

    if spread>0.06:
        warnings.append("يوجد تباين ملحوظ بين نطاقات الأبعاد المستخدمة في المعايرة؛ راجع المقياس بصريًا.")

    confidence=max(0.55,min(0.96,confidence))
    return result,confidence,warnings


def estimate_scale(dimensions:list[dict],width:int,height:int)->tuple[float|None,float|None]:
    scale,confidence,_=estimate_scale_with_diagnostics(dimensions,width,height)
    return scale,confidence
