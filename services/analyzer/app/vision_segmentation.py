from __future__ import annotations

import os
from functools import lru_cache

import cv2
import numpy as np

CLASS_NAMES=("background","room","wall","door","window")
CLASS_INDEX={name:index for index,name in enumerate(CLASS_NAMES)}


def _enabled()->bool:
    return os.getenv("SEGMENTATION_ONNX_MODEL","").strip()!=""


@lru_cache(maxsize=2)
def _load_net(path:str):
    return cv2.dnn.readNetFromONNX(path)


def _letterbox(image:np.ndarray,size:int)->tuple[np.ndarray,float,int,int]:
    h,w=image.shape[:2]
    scale=min(size/max(1,w),size/max(1,h))
    nw=max(1,int(round(w*scale))); nh=max(1,int(round(h*scale)))
    resized=cv2.resize(image,(nw,nh),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
    canvas=np.full((size,size,3),255,dtype=np.uint8)
    left=(size-nw)//2; top=(size-nh)//2
    canvas[top:top+nh,left:left+nw]=resized
    return canvas,scale,left,top


def _softmax(logits:np.ndarray)->np.ndarray:
    shifted=logits-np.max(logits,axis=0,keepdims=True)
    exp=np.exp(shifted)
    return exp/np.maximum(np.sum(exp,axis=0,keepdims=True),1e-9)


def infer_segmentation(image:np.ndarray)->dict|None:
    """Run learned floor-plan segmentation through OpenCV DNN.

    Expected model output is NCHW logits for:
      background / room / wall / door / window.

    The model is optional. When SEGMENTATION_ONNX_MODEL is absent or inference
    fails the caller must fall back to the deterministic V3 geometry path.
    """
    path=os.getenv("SEGMENTATION_ONNX_MODEL","").strip()
    if not path:
        return None
    size=max(192,min(1024,int(os.getenv("SEGMENTATION_INPUT_SIZE","384") or "384")))
    try:
        net=_load_net(path)
        boxed,scale,left,top=_letterbox(image,size)
        rgb=cv2.cvtColor(boxed,cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
        blob=np.transpose(rgb,(2,0,1))[None,...]
        net.setInput(blob)
        out=np.asarray(net.forward())
    except Exception:
        return None

    if out.ndim!=4 or out.shape[0]!=1 or out.shape[1]<5:
        return None
    logits=out[0,:5].astype(np.float32)
    probs=_softmax(logits)
    classes=np.argmax(probs,axis=0).astype(np.uint8)
    confidence=np.max(probs,axis=0)

    h,w=image.shape[:2]
    nw=max(1,int(round(w*scale))); nh=max(1,int(round(h*scale)))
    crop_classes=classes[top:top+nh,left:left+nw]
    crop_conf=confidence[top:top+nh,left:left+nw]
    classes=cv2.resize(crop_classes,(w,h),interpolation=cv2.INTER_NEAREST)
    confidence=cv2.resize(crop_conf,(w,h),interpolation=cv2.INTER_LINEAR)

    masks={}
    class_confidence={}
    for name,index in CLASS_INDEX.items():
        mask=np.where(classes==index,255,0).astype(np.uint8)
        masks[name]=mask
        selected=confidence[classes==index]
        class_confidence[name]=float(np.mean(selected)) if selected.size else 0.0

    wall_ratio=float(cv2.countNonZero(masks["wall"]))/float(max(1,h*w))
    room_ratio=float(cv2.countNonZero(masks["room"]))/float(max(1,h*w))
    mean_conf=float(np.mean(confidence))
    plausible=.006<=wall_ratio<=.38 and .03<=room_ratio<=.92 and mean_conf>=.42
    return {
        "masks":masks,
        "confidence":confidence,
        "classConfidence":class_confidence,
        "meanConfidence":mean_conf,
        "wallRatio":wall_ratio,
        "roomRatio":room_ratio,
        "plausible":plausible,
    }


def wall_consensus_score(result:dict|None,heuristic_mask:np.ndarray|None)->float:
    """Dice agreement between learned walls and independent geometric evidence."""
    if not result or not result.get("plausible") or heuristic_mask is None:
        return 0.0
    learned=np.asarray((result.get("masks") or {}).get("wall"))
    if learned.ndim!=2 or heuristic_mask.shape!=learned.shape:
        return 0.0
    a=learned>0
    b=np.asarray(heuristic_mask)>0
    denom=int(a.sum())+int(b.sum())
    if denom<=0:
        return 0.0
    return float(2*int(np.count_nonzero(a & b))/denom)


def should_use_learned_walls(
    result:dict|None,
    heuristic_mask:np.ndarray|None,
    *,
    dominant_colored_plan:bool=False,
    minimum_consensus:float=.70,
    minimum_wall_confidence:float=.58,
)->bool:
    """Allow learned wall geometry only on high-agreement colored plans.

    General construction drawings keep V3 geometry because the synthetic model
    is not yet a universal wall replacement. Colored residential exports are a
    narrower domain: when a dominant wall hue exists and the learned mask agrees
    strongly with independent geometry, the learned mask is cleaner for redraw
    because it ignores red labels, green dimensions and furniture strokes.
    """
    if not dominant_colored_plan or not result or not result.get("plausible"):
        return False
    consensus=wall_consensus_score(result,heuristic_mask)
    wall_conf=float((result.get("classConfidence") or {}).get("wall",0.0))
    return consensus>=minimum_consensus and wall_conf>=minimum_wall_confidence


def learned_opening_detections(result:dict|None)->list[dict]:
    if not result or not result.get("plausible"):
        return []
    detections=[]
    confidence=np.asarray(result["confidence"])
    for name in ("door","window"):
        mask=np.asarray(result["masks"][name])
        count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        image_area=max(1,mask.shape[0]*mask.shape[1])
        min_area=max(12,int(round(image_area*.000015)))
        max_area=max(min_area+1,int(round(image_area*.025)))
        for index in range(1,count):
            area=int(stats[index,cv2.CC_STAT_AREA])
            if area<min_area or area>max_area:
                continue
            x=int(stats[index,cv2.CC_STAT_LEFT]); y=int(stats[index,cv2.CC_STAT_TOP])
            w=int(stats[index,cv2.CC_STAT_WIDTH]); h=int(stats[index,cv2.CC_STAT_HEIGHT])
            if max(w,h)<5:
                continue
            region=confidence[labels==index]
            score=float(np.mean(region)) if region.size else 0.0
            if score<.78:
                continue
            detections.append({
                "class":name,
                "bbox":[float(x),float(y),float(x+w),float(y+h)],
                "confidence":round(score,4),
                "provenance":"ai",
            })
    return detections


def should_use_learned_rooms(
    fallback_rooms:list[dict],
    learned_rooms:list[dict],
    labels:list[dict],
    *,
    dominant_colored_plan:bool=False,
)->bool:
    """Conservative production gate for learned room instances.

    The learned model is a rescue path, not a blanket replacement. On general
    construction drawings V3 remains stronger; on simple colored residential
    plans the learned segmentation can recover rooms that geometry misses.
    """
    fallback_count=len(fallback_rooms)
    learned_count=len(learned_rooms)
    if learned_count<2:
        return False
    if fallback_count<=1:
        return True

    room_label_count=sum(
        1 for item in labels
        if str(item.get("kind",""))=="room_name"
        and float(item.get("confidence",0.0))>=.45
    )
    if dominant_colored_plan and room_label_count>=2:
        fallback_error=abs(fallback_count-room_label_count)
        learned_error=abs(learned_count-room_label_count)
        return learned_error+1<fallback_error
    return False


def semantic_room_barrier(result:dict|None)->np.ndarray|None:
    """Build a structural barrier from learned wall/door/window classes.

    The semantic room class is intentionally *not* inverted into a barrier:
    labels and furniture can create small background holes inside an otherwise
    correct room prediction, and adjacent rooms can still touch through a weak
    door prediction. Instead the learned wall mask is primary geometry, while
    learned door/window pixels seal their host openings for room-instance
    separation. The caller may run build_room_barrier() afterwards to close any
    remaining door-sized gap.
    """
    if not result or not result.get("plausible"):
        return None
    masks=result.get("masks") or {}
    wall=np.asarray(masks.get("wall"))
    door=np.asarray(masks.get("door"))
    window=np.asarray(masks.get("window"))
    if wall.ndim!=2 or door.shape!=wall.shape or window.shape!=wall.shape:
        return None
    barrier=cv2.bitwise_or(wall,door)
    barrier=cv2.bitwise_or(barrier,window)
    # Slightly expand learned openings so a sparse door/window class actually
    # reaches the adjacent wall band and separates room components.
    opening=cv2.bitwise_or(door,window)
    if cv2.countNonZero(opening)>0:
        expanded=cv2.dilate(opening,np.ones((5,5),np.uint8),iterations=1)
        barrier=cv2.bitwise_or(barrier,expanded)
    return cv2.morphologyEx(barrier,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
