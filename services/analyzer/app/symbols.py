from __future__ import annotations

import os

import cv2
import httpx
import numpy as np


KINDS={"sink","toilet","bathtub","shower","cooktop","stairs"}
ALIASES={
    "sink":"sink",
    "basin":"sink",
    "lavatory":"sink",
    "toilet":"toilet",
    "wc":"toilet",
    "bathtub":"bathtub",
    "bath":"bathtub",
    "tub":"bathtub",
    "shower":"shower",
    "cooktop":"cooktop",
    "cooktops":"cooktop",
    "stove":"cooktop",
    "hob":"cooktop",
    "stairs":"stairs",
    "stair":"stairs",
}


def _normalize_kind(value:object)->str|None:
    text=str(value or "").strip().lower().replace("_"," ").replace("-"," ")
    text=" ".join(text.split())
    compact=text.replace(" ","")
    return ALIASES.get(text) or ALIASES.get(compact)


def _bbox(item:dict,width:int,height:int)->tuple[float,float,float,float]|None:
    value=item.get("bbox")
    if isinstance(value,(list,tuple)) and len(value)==4:
        try:
            x1,y1,x2,y2=map(float,value)
        except (TypeError,ValueError):
            return None
    elif isinstance(value,dict):
        try:
            x1=float(value.get("x",value.get("x1")))
            y1=float(value.get("y",value.get("y1")))
            if value.get("x2") is not None:
                x2=float(value["x2"])
                y2=float(value["y2"])
            else:
                x2=x1+float(value["width"])
                y2=y1+float(value["height"])
        except (KeyError,TypeError,ValueError):
            return None
    else:
        return None

    x1=max(0.0,min(float(width),x1))
    y1=max(0.0,min(float(height),y1))
    x2=max(0.0,min(float(width),x2))
    y2=max(0.0,min(float(height),y2))
    if x2<x1:
        x1,x2=x2,x1
    if y2<y1:
        y1,y2=y2,y1
    if x2-x1<4 or y2-y1<4:
        return None
    return x1,y1,x2,y2


def _iou(left:dict,right:dict)->float:
    ax1,ay1=left["a"]["x"],left["a"]["y"]
    ax2,ay2=left["b"]["x"],left["b"]["y"]
    bx1,by1=right["a"]["x"],right["a"]["y"]
    bx2,by2=right["b"]["x"],right["b"]["y"]
    intersection=max(0.0,min(ax2,bx2)-max(ax1,bx1))*max(0.0,min(ay2,by2)-max(ay1,by1))
    if intersection<=0:
        return 0.0
    area_a=max(0.0,ax2-ax1)*max(0.0,ay2-ay1)
    area_b=max(0.0,bx2-bx1)*max(0.0,by2-by1)
    return intersection/max(1e-9,area_a+area_b-intersection)


def normalize_symbol_response(payload:object,width:int,height:int,min_confidence:float=.78)->list[dict]:
    if isinstance(payload,dict):
        raw=payload.get("symbols",payload.get("detections",[]))
    else:
        raw=payload
    if not isinstance(raw,list):
        return []

    candidates=[]
    for item in raw:
        if not isinstance(item,dict):
            continue
        kind=_normalize_kind(item.get("kind",item.get("class",item.get("label"))))
        if kind not in KINDS:
            continue
        try:
            confidence=float(item.get("confidence",item.get("score",0.0)))
        except (TypeError,ValueError):
            continue
        if not min_confidence<=confidence<=1.0:
            continue
        box=_bbox(item,width,height)
        if box is None:
            continue
        x1,y1,x2,y2=box
        candidates.append({
            "kind":kind,
            "a":{"x":x1,"y":y1},
            "b":{"x":x2,"y":y2},
            "confidence":round(confidence,4),
            "reviewed":False,
            "provenance":"ai",
        })

    accepted=[]
    for candidate in sorted(candidates,key=lambda item:item["confidence"],reverse=True):
        if any(
            existing["kind"]==candidate["kind"] and _iou(existing,candidate)>=.55
            for existing in accepted
        ):
            continue
        accepted.append(candidate)

    for index,item in enumerate(accepted,start=1):
        item["id"]=f"symbol-{index}"
    return accepted


async def extract_symbol_detections(image:np.ndarray)->list[dict]:
    url=os.getenv("SYMBOL_DETECTOR_URL","").strip()
    if not url:
        return []
    token=os.getenv("SYMBOL_DETECTOR_TOKEN","").strip()
    try:
        min_confidence=float(os.getenv("SYMBOL_MIN_CONFIDENCE",".78") or ".78")
    except ValueError:
        min_confidence=.78
    min_confidence=max(.50,min(.99,min_confidence))

    ok,encoded=cv2.imencode(".png",image)
    if not ok:
        return []
    headers={"content-type":"image/png","accept":"application/json"}
    if token:
        headers["authorization"]=f"Bearer {token}"

    timeout=float(os.getenv("SYMBOL_DETECTOR_TIMEOUT_SECONDS","45") or "45")
    async with httpx.AsyncClient(timeout=max(5.0,min(120.0,timeout))) as client:
        response=await client.post(url,headers=headers,content=encoded.tobytes())
        response.raise_for_status()
        payload=response.json()
    h,w=image.shape[:2]
    return normalize_symbol_response(payload,w,h,min_confidence)
