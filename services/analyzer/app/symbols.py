from __future__ import annotations

import base64
import json
import math
import os

import cv2
import httpx
import numpy as np


KINDS={"sink","toilet","bathtub","shower","cooktop","stairs","elevator"}
ALIASES={
    "sink":"sink",
    "basin":"sink",
    "lavatory":"sink",
    "wash basin":"sink",
    "washbasin":"sink",
    "toilet":"toilet",
    "squat toilet":"toilet",
    "squat_toilet":"toilet",
    "wc":"toilet",
    "water closet":"toilet",
    "bathtub":"bathtub",
    "bath":"bathtub",
    "bath tub":"bathtub",
    "bath_tub":"bathtub",
    "tub":"bathtub",
    "shower":"shower",
    "shower tray":"shower",
    "cooktop":"cooktop",
    "cooktops":"cooktop",
    "stove":"cooktop",
    "gas stove":"cooktop",
    "gas_stove":"cooktop",
    "hob":"cooktop",
    "range":"cooktop",
    "stairs":"stairs",
    "stair":"stairs",
    "staircase":"stairs",
    "elevator":"elevator",
    "lift":"elevator",
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
    if area_ratio>.60:
        return None
    if box_width>width*.92 or box_height>height*.92:
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
        duplicate_same_class=any(
            existing["kind"]==candidate["kind"] and _iou(existing,candidate)>=.55
            for existing in accepted
        )
        if duplicate_same_class:
            continue

        # Detectors can emit the identical fixture box under two competing
        # classes. Since candidates are confidence-sorted, keep the stronger
        # class only when the geometry is nearly identical.
        conflicting_class=any(
            existing["kind"]!=candidate["kind"] and _iou(existing,candidate)>=.78
            for existing in accepted
        )
        if conflicting_class:
            continue
        accepted.append(candidate)

    for index,item in enumerate(accepted,start=1):
        item["id"]=f"symbol-{index}"
    return accepted




_ONNX_CACHE:dict[tuple[str,int],object]={}


def _env_confidence(name:str,default:float,minimum:float=.10)->float:
    try:
        value=float(os.getenv(name,str(default)) or str(default))
    except ValueError:
        value=default
    return max(minimum,min(.99,value))


def _local_class_names()->list[str]:
    raw=os.getenv("SYMBOL_ONNX_CLASSES","").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            values=json.loads(raw)
            if isinstance(values,list):
                return [str(item).strip() for item in values]
        except Exception:
            return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _letterbox(image:np.ndarray,size:int)->tuple[np.ndarray,float,float,float]:
    h,w=image.shape[:2]
    scale=min(size/max(1,w),size/max(1,h))
    new_w=max(1,int(round(w*scale)))
    new_h=max(1,int(round(h*scale)))
    resized=cv2.resize(image,(new_w,new_h),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)
    canvas=np.full((size,size,3),114,dtype=np.uint8)
    pad_x=(size-new_w)//2
    pad_y=(size-new_h)//2
    canvas[pad_y:pad_y+new_h,pad_x:pad_x+new_w]=resized
    return canvas,scale,float(pad_x),float(pad_y)


def _prepare_yolo_rows(output:np.ndarray,class_count:int)->np.ndarray:
    value=np.asarray(output,dtype=np.float32)
    while value.ndim>2 and value.shape[0]==1:
        value=value[0]
    if value.ndim!=2:
        return np.empty((0,4+class_count),dtype=np.float32)

    v8_features=4+class_count
    v5_features=5+class_count

    # YOLOv5-style exports are expected as [detections, 5+classes].
    if value.shape[1] in {v8_features,v5_features}:
        return value

    # YOLOv8 commonly exports [4+classes, detections] and needs a transpose.
    # Do not transpose a 5+classes leading dimension: [1, 5+C, N] is
    # ambiguous and accepting it silently can turn an unrelated tensor into
    # plausible fixture detections.
    if value.shape[0]==v8_features and value.shape[1] not in {v8_features,v5_features}:
        return value.T

    return np.empty((0,v8_features),dtype=np.float32)


def _decode_yolo_output(
    output:np.ndarray,
    *,
    class_names:list[str],
    confidence_threshold:float,
    original_width:int,
    original_height:int,
    input_size:int,
    scale:float,
    pad_x:float,
    pad_y:float,
)->list[dict]:
    rows=_prepare_yolo_rows(output,len(class_names))
    if rows.size==0:
        return []
    boxes=[]
    confidences=[]
    class_ids=[]
    has_objectness=rows.shape[1]==5+len(class_names)
    for row in rows:
        cx,cy,bw,bh=map(float,row[:4])
        if has_objectness:
            objectness=float(row[4])
            scores=np.asarray(row[5:],dtype=np.float32)*objectness
        else:
            scores=np.asarray(row[4:],dtype=np.float32)
        if not len(scores):
            continue
        class_id=int(np.argmax(scores))
        confidence=float(scores[class_id])
        if confidence<confidence_threshold:
            continue
        x1=(cx-bw/2-pad_x)/max(scale,1e-9)
        y1=(cy-bh/2-pad_y)/max(scale,1e-9)
        x2=(cx+bw/2-pad_x)/max(scale,1e-9)
        y2=(cy+bh/2-pad_y)/max(scale,1e-9)
        x1=max(0.0,min(float(original_width),x1))
        y1=max(0.0,min(float(original_height),y1))
        x2=max(0.0,min(float(original_width),x2))
        y2=max(0.0,min(float(original_height),y2))
        if x2-x1<4 or y2-y1<4:
            continue
        boxes.append([x1,y1,x2-x1,y2-y1])
        confidences.append(confidence)
        class_ids.append(class_id)
    if not boxes:
        return []
    indexes=cv2.dnn.NMSBoxes(
        boxes,confidences,confidence_threshold,
        float(os.getenv("SYMBOL_ONNX_NMS_IOU",".45") or ".45"),
    )
    if indexes is None or len(indexes)==0:
        return []
    flattened=np.asarray(indexes).reshape(-1).tolist()
    payload=[]
    for index in flattened:
        x,y,w,h=boxes[int(index)]
        payload.append({
            "class":class_names[class_ids[int(index)]],
            "bbox":[x,y,x+w,y+h],
            "confidence":confidences[int(index)],
        })
    return normalize_symbol_response(
        payload,original_width,original_height,confidence_threshold,
    )


def _decode_yolo_payload(
    output:np.ndarray,
    *,
    class_names:list[str],
    confidence_threshold:float,
    original_width:int,
    original_height:int,
    input_size:int,
    scale:float,
    pad_x:float,
    pad_y:float,
)->list[dict]:
    """Return NMS-filtered raw YOLO boxes without dropping non-symbol classes."""
    rows=_prepare_yolo_rows(output,len(class_names))
    if rows.size==0:
        return []
    boxes=[]
    confidences=[]
    class_ids=[]
    has_objectness=rows.shape[1]==5+len(class_names)
    for row in rows:
        cx,cy,bw,bh=map(float,row[:4])
        if has_objectness:
            objectness=float(row[4])
            scores=np.asarray(row[5:],dtype=np.float32)*objectness
        else:
            scores=np.asarray(row[4:],dtype=np.float32)
        if not len(scores):
            continue
        class_id=int(np.argmax(scores))
        confidence=float(scores[class_id])
        if confidence<confidence_threshold:
            continue
        x1=(cx-bw/2-pad_x)/max(scale,1e-9)
        y1=(cy-bh/2-pad_y)/max(scale,1e-9)
        x2=(cx+bw/2-pad_x)/max(scale,1e-9)
        y2=(cy+bh/2-pad_y)/max(scale,1e-9)
        x1=max(0.0,min(float(original_width),x1))
        y1=max(0.0,min(float(original_height),y1))
        x2=max(0.0,min(float(original_width),x2))
        y2=max(0.0,min(float(original_height),y2))
        if x2-x1<4 or y2-y1<4:
            continue
        boxes.append([x1,y1,x2-x1,y2-y1])
        confidences.append(confidence)
        class_ids.append(class_id)
    if not boxes:
        return []
    indexes=cv2.dnn.NMSBoxes(
        boxes,confidences,confidence_threshold,
        float(os.getenv("SYMBOL_ONNX_NMS_IOU",".45") or ".45"),
    )
    if indexes is None or len(indexes)==0:
        return []
    payload=[]
    for index in np.asarray(indexes).reshape(-1).tolist():
        x,y,w,h=boxes[int(index)]
        payload.append({
            "class":class_names[class_ids[int(index)]],
            "bbox":[x,y,x+w,y+h],
            "confidence":round(float(confidences[int(index)]),4),
        })
    return payload


def _raw_box_iou(left:dict,right:dict)->float:
    try:
        ax1,ay1,ax2,ay2=map(float,left["bbox"])
        bx1,by1,bx2,by2=map(float,right["bbox"])
    except (KeyError,TypeError,ValueError):
        return 0.0
    intersection=max(0.0,min(ax2,bx2)-max(ax1,bx1))*max(0.0,min(ay2,by2)-max(ay1,by1))
    if intersection<=0:
        return 0.0
    area_a=max(0.0,ax2-ax1)*max(0.0,ay2-ay1)
    area_b=max(0.0,bx2-bx1)*max(0.0,by2-by1)
    union=area_a+area_b-intersection
    return intersection/union if union>0 else 0.0


def _dedupe_raw_detections(items:list[dict],iou_threshold:float=.55)->list[dict]:
    accepted=[]
    for item in sorted(items,key=lambda value:float(value.get("confidence",0.0)),reverse=True):
        label=str(item.get("class",""))
        if any(
            str(existing.get("class",""))==label
            and _raw_box_iou(existing,item)>=iou_threshold
            for existing in accepted
        ):
            continue
        accepted.append(item)
    return accepted


def _tile_windows(width:int,height:int,tile_size:int,overlap:float)->list[tuple[int,int,int,int]]:
    if width<=tile_size and height<=tile_size:
        return [(0,0,width,height)]
    overlap=max(0.0,min(.45,float(overlap)))
    step=max(1,int(round(tile_size*(1.0-overlap))))

    def starts(total:int)->list[int]:
        if total<=tile_size:
            return [0]
        values=list(range(0,max(1,total-tile_size+1),step))
        last=max(0,total-tile_size)
        if not values or values[-1]!=last:
            values.append(last)
        return values

    return [
        (x,y,min(width,x+tile_size),min(height,y+tile_size))
        for y in starts(height)
        for x in starts(width)
    ]


def _run_onnx_payload(
    image:np.ndarray,
    *,
    net,
    class_names:list[str],
    input_size:int,
    confidence:float,
)->list[dict]:
    boxed,scale,pad_x,pad_y=_letterbox(image,input_size)
    blob=cv2.dnn.blobFromImage(
        boxed,1/255.0,(input_size,input_size),
        swapRB=True,crop=False,
    )
    net.setInput(blob)
    raw=net.forward()
    h,w=image.shape[:2]
    return _decode_yolo_payload(
        raw,
        class_names=class_names,
        confidence_threshold=confidence,
        original_width=w,
        original_height=h,
        input_size=input_size,
        scale=scale,
        pad_x=pad_x,
        pad_y=pad_y,
    )


def extract_local_onnx_detections(image:np.ndarray)->list[dict]:
    model_path=os.getenv("SYMBOL_ONNX_MODEL","").strip()
    class_names=_local_class_names()
    if not model_path or not class_names:
        return []
    input_size=int(os.getenv("SYMBOL_ONNX_INPUT_SIZE","640") or "640")
    input_size=max(128,min(2048,input_size))
    confidence=_env_confidence("SYMBOL_ONNX_RAW_MIN_CONFIDENCE",.30,.10)

    key=(model_path,input_size)
    net=_ONNX_CACHE.get(key)
    if net is None:
        if not os.path.exists(model_path):
            return []
        net=cv2.dnn.readNetFromONNX(model_path)
        _ONNX_CACHE[key]=net

    h,w=image.shape[:2]
    trigger=int(os.getenv("SYMBOL_ONNX_TILE_TRIGGER","1800") or "1800")
    trigger=max(input_size,min(6000,trigger))
    if max(h,w)<=trigger:
        return _run_onnx_payload(
            image,
            net=net,
            class_names=class_names,
            input_size=input_size,
            confidence=confidence,
        )

    tile_size=int(os.getenv("SYMBOL_ONNX_TILE_SIZE","1600") or "1600")
    tile_size=max(input_size,min(3200,tile_size))
    overlap=float(os.getenv("SYMBOL_ONNX_TILE_OVERLAP",".18") or ".18")
    detections=[]
    for x1,y1,x2,y2 in _tile_windows(w,h,tile_size,overlap):
        tile=image[y1:y2,x1:x2]
        if tile.size==0:
            continue
        for item in _run_onnx_payload(
            tile,
            net=net,
            class_names=class_names,
            input_size=input_size,
            confidence=confidence,
        ):
            shifted=dict(item)
            bx1,by1,bx2,by2=map(float,item["bbox"])
            shifted["bbox"]=[
                bx1+x1,by1+y1,bx2+x1,by2+y1,
            ]
            detections.append(shifted)
    return _dedupe_raw_detections(
        detections,
        float(os.getenv("SYMBOL_ONNX_NMS_IOU",".45") or ".45"),
    )


def extract_local_onnx_symbols(image:np.ndarray)->list[dict]:
    h,w=image.shape[:2]
    confidence=float(os.getenv("SYMBOL_MIN_CONFIDENCE",".78") or ".78")
    confidence=max(.50,min(.99,confidence))
    return normalize_symbol_response(
        extract_local_onnx_detections(image),
        w,h,confidence,
    )


def _normalize_roboflow_fixture_response(
    payload:object,
    width:int,
    height:int,
    min_confidence:float,
)->list[dict]:
    if not isinstance(payload,dict):
        return []
    predictions=payload.get("predictions",[])
    if not isinstance(predictions,list):
        return []

    converted=[]
    for item in predictions:
        if not isinstance(item,dict):
            continue
        try:
            cx=float(item["x"])
            cy=float(item["y"])
            box_width=float(item["width"])
            box_height=float(item["height"])
        except (KeyError,TypeError,ValueError):
            continue
        converted.append({
            "class":item.get("class",item.get("class_name",item.get("label"))),
            "bbox":[cx,cy,box_width,box_height],
            "bbox_format":"cxcywh",
            "confidence":item.get("confidence",item.get("score",0.0)),
        })
    return normalize_symbol_response(
        converted,width,height,min_confidence,
    )


async def extract_roboflow_fixture_symbols(
    image:np.ndarray,
)->list[dict]|None:
    """Use an optional Roboflow fixture model without exposing its API key.

    Returns None when the provider is not configured or the request fails,
    allowing the local detector to remain the automatic fallback.
    """
    api_key=os.getenv("ROBOFLOW_API_KEY","").strip()
    model_id=os.getenv(
        "ROBOFLOW_FIXTURE_MODEL_ID",
        "floorplan-details-fork-2uqql/1",
    ).strip()
    if not api_key or not model_id:
        return None

    base_url=os.getenv(
        "ROBOFLOW_API_URL",
        "https://serverless.roboflow.com",
    ).strip().rstrip("/")
    try:
        min_confidence=float(
            os.getenv("ROBOFLOW_FIXTURE_MIN_CONFIDENCE",".35") or ".35"
        )
    except ValueError:
        min_confidence=.35
    min_confidence=max(.10,min(.95,min_confidence))

    ok,encoded=cv2.imencode(".png",image)
    if not ok:
        return None
    body=base64.b64encode(encoded.tobytes()).decode("ascii")
    timeout=float(os.getenv("ROBOFLOW_TIMEOUT_SECONDS","45") or "45")

    try:
        async with httpx.AsyncClient(
            timeout=max(5.0,min(120.0,timeout))
        ) as client:
            response=await client.post(
                f"{base_url}/{model_id}",
                params={"api_key":api_key},
                headers={"content-type":"application/x-www-form-urlencoded"},
                content=body,
            )
            response.raise_for_status()
            payload=response.json()
    except Exception:
        return None

    h,w=image.shape[:2]
    return _normalize_roboflow_fixture_response(
        payload,w,h,min_confidence,
    )


def _merge_symbol_results(*groups:list[dict])->list[dict]:
    accepted=[]
    for item in sorted(
        [item for group in groups for item in group],
        key=lambda value:float(value.get("confidence",0.0)),
        reverse=True,
    ):
        if any(
            existing.get("kind")==item.get("kind")
            and _iou(existing,item)>=.55
            for existing in accepted
        ):
            continue
        if any(
            existing.get("kind")!=item.get("kind")
            and _iou(existing,item)>=.78
            for existing in accepted
        ):
            continue
        accepted.append(dict(item))
    for index,item in enumerate(accepted,start=1):
        item["id"]=f"symbol-{index}"
    return accepted


async def extract_symbol_detections(image:np.ndarray)->list[dict]:
    # The in-process ONNX path is always available as the privacy-preserving
    # fallback. When Roboflow is configured, use it for fixture classes while
    # retaining local stairs/elevator detections that the fixture model does
    # not cover.
    try:
        local=extract_local_onnx_symbols(image)
    except Exception:
        local=[]

    roboflow=await extract_roboflow_fixture_symbols(image)
    if roboflow is not None:
        vertical=[
            item for item in local
            if item.get("kind") in {"stairs","elevator"}
        ]
        return _merge_symbol_results(roboflow,vertical)

    if local:
        return local

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
