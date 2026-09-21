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
    "wash basin":"sink",
    "washbasin":"sink",
    "toilet":"toilet",
    "wc":"toilet",
    "water closet":"toilet",
    "bathtub":"bathtub",
    "bath":"bathtub",
    "tub":"bathtub",
    "shower":"shower",
    "shower tray":"shower",
    "cooktop":"cooktop",
    "cooktops":"cooktop",
    "stove":"cooktop",
    "hob":"cooktop",
    "range":"cooktop",
    "stairs":"stairs",
    "stair":"stairs",
    "staircase":"stairs",
}


def _normalize_kind(value:object)->str|None:
    text=str(value or "").strip().lower().replace("_"," ").replace("-"," ")
    text=" ".join(text.split())
    compact=text.replace(" ","")
    return ALIASES.get(text) or ALIASES.get(compact)


def _raw_bbox(item:dict)->tuple[float,float,float,float]|None:
    value=item.get("bbox",item.get("box"))
    if isinstance(value,(list,tuple)) and len(value)==4:
        try:
            first,second,third,fourth=map(float,value)
        except (TypeError,ValueError):
            return None
        fmt=str(item.get("bbox_format",item.get("format","xyxy"))).strip().lower()
        if fmt in {"xywh","x_y_width_height"}:
            return first,second,first+third,second+fourth
        if fmt in {"cxcywh","center"}:
            return first-third/2,second-fourth/2,first+third/2,second+fourth/2
        return first,second,third,fourth

    if isinstance(value,dict):
        try:
            if value.get("cx") is not None and value.get("cy") is not None:
                cx=float(value["cx"]); cy=float(value["cy"])
                width=float(value["width"]); height=float(value["height"])
                return cx-width/2,cy-height/2,cx+width/2,cy+height/2
            x1=float(value.get("x",value.get("x1",value.get("left"))))
            y1=float(value.get("y",value.get("y1",value.get("top"))))
            if value.get("x2") is not None or value.get("right") is not None:
                x2=float(value.get("x2",value.get("right")))
                y2=float(value.get("y2",value.get("bottom")))
            else:
                x2=x1+float(value["width"])
                y2=y1+float(value["height"])
            return x1,y1,x2,y2
        except (KeyError,TypeError,ValueError):
            return None

    # Some detectors return top-level coordinates instead of bbox.
    if any(key in item for key in ("x1","left","cx")):
        return _raw_bbox({"bbox":item,"bbox_format":item.get("bbox_format","xyxy")})
    return None


def _bbox(item:dict,width:int,height:int)->tuple[float,float,float,float]|None:
    raw=_raw_bbox(item)
    if raw is None:
        return None
    x1,y1,x2,y2=raw

    explicit_normalized=bool(item.get("normalized",False))
    coordinate_space=str(item.get("coordinate_space","")).lower()
    inferred_normalized=(
        min(x1,y1,x2,y2)>=-0.05
        and max(x1,y1,x2,y2)<=1.05
    )
    if explicit_normalized or coordinate_space in {"normalized","relative","0-1"} or inferred_normalized:
        x1*=width; x2*=width
        y1*=height; y2*=height

    x1=max(0.0,min(float(width),x1))
    y1=max(0.0,min(float(height),y1))
    x2=max(0.0,min(float(width),x2))
    y2=max(0.0,min(float(height),y2))
    x1,x2=min(x1,x2),max(x1,x2)
    y1,y2=min(y1,y2),max(y1,y2)

    box_width=x2-x1
    box_height=y2-y1
    if box_width<4 or box_height<4:
        return None
    area_ratio=(box_width*box_height)/max(1.0,float(width*height))
    if area_ratio>.35:
        return None
    if box_width>width*.80 or box_height>height*.80:
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
        raw=payload.get("symbols",payload.get("detections",payload.get("predictions",[])))
    else:
        raw=payload
    if not isinstance(raw,list):
        return []

    candidates=[]
    for item in raw:
        if not isinstance(item,dict):
            continue
        kind=_normalize_kind(item.get("kind",item.get("class",item.get("label",item.get("name")))))
        if kind not in KINDS:
            continue
        try:
            confidence=float(item.get("confidence",item.get("score",item.get("probability",0.0))))
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
