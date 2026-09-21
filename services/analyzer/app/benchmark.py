from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def _point(item:dict,key:str)->tuple[float,float]:
    value=item[key]
    return float(value["x"]),float(value["y"])


def _distance(a:tuple[float,float],b:tuple[float,float])->float:
    return math.hypot(a[0]-b[0],a[1]-b[1])


def _segment_distance(left:dict,right:dict)->float:
    la,lb=_point(left,"a"),_point(left,"b")
    ra,rb=_point(right,"a"),_point(right,"b")
    direct=(_distance(la,ra)+_distance(lb,rb))/2
    reverse=(_distance(la,rb)+_distance(lb,ra))/2
    return min(direct,reverse)


def _metrics(tp:int,predicted:int,truth:int)->dict:
    precision=tp/predicted if predicted else (1.0 if truth==0 else 0.0)
    recall=tp/truth if truth else 1.0
    f1=(2*precision*recall/(precision+recall)) if precision+recall else 0.0
    return {
        "tp":tp,
        "predicted":predicted,
        "truth":truth,
        "precision":round(precision,4),
        "recall":round(recall,4),
        "f1":round(f1,4),
    }


def _greedy_segment_metrics(predicted:list[dict],truth:list[dict],tolerance_px:float)->dict:
    remaining=set(range(len(truth)))
    matches=0
    for item in predicted:
        best=None
        for index in remaining:
            score=_segment_distance(item,truth[index])
            if score<=tolerance_px and (best is None or score<best[0]):
                best=(score,index)
        if best is not None:
            remaining.remove(best[1])
            matches+=1
    return _metrics(matches,len(predicted),len(truth))


def _polygon_mask(points:list[dict],bounds:tuple[float,float,float,float],scale:float)->np.ndarray:
    x1,y1,x2,y2=bounds
    width=max(3,int(math.ceil((x2-x1)*scale))+3)
    height=max(3,int(math.ceil((y2-y1)*scale))+3)
    mask=np.zeros((height,width),dtype=np.uint8)
    contour=np.array([
        [int(round((float(point["x"])-x1)*scale))+1,int(round((float(point["y"])-y1)*scale))+1]
        for point in points
    ],dtype=np.int32).reshape((-1,1,2))
    if len(contour)>=3:
        cv2.fillPoly(mask,[contour],255)
    return mask


def _room_iou(left:dict,right:dict,max_side:int=700)->float:
    lp=left.get("polygon") or []
    rp=right.get("polygon") or []
    if len(lp)<3 or len(rp)<3:
        return 0.0
    xs=[float(p["x"]) for p in [*lp,*rp]]
    ys=[float(p["y"]) for p in [*lp,*rp]]
    bounds=(min(xs),min(ys),max(xs),max(ys))
    width=max(1.0,bounds[2]-bounds[0]); height=max(1.0,bounds[3]-bounds[1])
    scale=min(1.0,max_side/max(width,height))
    lm=_polygon_mask(lp,bounds,scale)
    rm=_polygon_mask(rp,bounds,scale)
    intersection=cv2.countNonZero(cv2.bitwise_and(lm,rm))
    union=cv2.countNonZero(cv2.bitwise_or(lm,rm))
    return float(intersection)/float(union) if union else 0.0


def _room_metrics(predicted:list[dict],truth:list[dict],iou_threshold:float)->dict:
    remaining=set(range(len(truth)))
    matches=0
    ious=[]
    for room in predicted:
        best=None
        for index in remaining:
            score=_room_iou(room,truth[index])
            if score>=iou_threshold and (best is None or score>best[0]):
                best=(score,index)
        if best is not None:
            remaining.remove(best[1])
            matches+=1
            ious.append(best[0])
    result=_metrics(matches,len(predicted),len(truth))
    result["meanMatchedIoU"]=round(sum(ious)/len(ious),4) if ious else 0.0
    return result


def _symbol_box_iou(left:dict,right:dict)->float:
    try:
        lax,lay=_point(left,"a"); lbx,lby=_point(left,"b")
        rax,ray=_point(right,"a"); rbx,rby=_point(right,"b")
    except (KeyError,TypeError,ValueError):
        return 0.0
    lx1,lx2=sorted((lax,lbx)); ly1,ly2=sorted((lay,lby))
    rx1,rx2=sorted((rax,rbx)); ry1,ry2=sorted((ray,rby))
    intersection=max(0.0,min(lx2,rx2)-max(lx1,rx1))*max(0.0,min(ly2,ry2)-max(ly1,ry1))
    if intersection<=0:
        return 0.0
    left_area=max(0.0,lx2-lx1)*max(0.0,ly2-ly1)
    right_area=max(0.0,rx2-rx1)*max(0.0,ry2-ry1)
    union=left_area+right_area-intersection
    return intersection/union if union>0 else 0.0


def _symbol_metrics(predicted:list[dict],truth:list[dict],iou_threshold:float=.50)->tuple[dict,dict]:
    kinds=sorted({
        str(item.get("kind",""))
        for item in [*predicted,*truth]
        if str(item.get("kind",""))
    })
    by_kind={}
    total_tp=0
    for kind in kinds:
        pred=[item for item in predicted if str(item.get("kind",""))==kind]
        expected=[item for item in truth if str(item.get("kind",""))==kind]
        remaining=set(range(len(expected)))
        matches=0
        for item in pred:
            best=None
            for index in remaining:
                score=_symbol_box_iou(item,expected[index])
                if score>=iou_threshold and (best is None or score>best[0]):
                    best=(score,index)
            if best is not None:
                remaining.remove(best[1])
                matches+=1
        by_kind[kind]=_metrics(matches,len(pred),len(expected))
        total_tp+=matches
    aggregate=_metrics(total_tp,len(predicted),len(truth))
    return aggregate,by_kind


def _dimension_distance(left:dict,right:dict,tolerance_px:float)->float|None:
    lv=left.get("valueM"); rv=right.get("valueM")
    if lv is None or rv is None:
        return None
    lv=float(lv); rv=float(rv)
    if abs(lv-rv)>max(0.05,abs(rv)*0.03):
        return None
    if left.get("spanA") and left.get("spanB") and right.get("spanA") and right.get("spanB"):
        candidate={
            "a":left["spanA"],"b":left["spanB"],
        }
        reference={
            "a":right["spanA"],"b":right["spanB"],
        }
        score=_segment_distance(candidate,reference)
        return score if score<=tolerance_px else None
    lc=left.get("center"); rc=right.get("center")
    if lc and rc:
        score=_distance((float(lc["x"]),float(lc["y"])),(float(rc["x"]),float(rc["y"])))
        return score if score<=tolerance_px*2 else None
    return 0.0


def _dimension_metrics(predicted:list[dict],truth:list[dict],tolerance_px:float)->dict:
    remaining=set(range(len(truth)))
    matches=0
    for item in predicted:
        best=None
        for index in remaining:
            score=_dimension_distance(item,truth[index],tolerance_px)
            if score is not None and (best is None or score<best[0]):
                best=(score,index)
        if best is not None:
            remaining.remove(best[1])
            matches+=1
    return _metrics(matches,len(predicted),len(truth))


def evaluate_floor_plan(
    prediction:dict,
    truth:dict,
    *,
    tolerance_px:float=12.0,
    room_iou_threshold:float=0.65,
)->dict:
    walls=_greedy_segment_metrics(prediction.get("walls",[]),truth.get("walls",[]),tolerance_px)
    doors=_greedy_segment_metrics(
        prediction.get("doors",[]),
        truth.get("doors",[]),
        tolerance_px,
    )
    windows=_greedy_segment_metrics(
        prediction.get("windows",[]),
        truth.get("windows",[]),
        tolerance_px,
    )
    openings=_metrics(
        int(doors["tp"])+int(windows["tp"]),
        len(prediction.get("doors",[]))+len(prediction.get("windows",[])),
        len(truth.get("doors",[]))+len(truth.get("windows",[])),
    )
    rooms=_room_metrics(prediction.get("rooms",[]),truth.get("rooms",[]),room_iou_threshold)
    dimensions=_dimension_metrics(prediction.get("dimensions",[]),truth.get("dimensions",[]),tolerance_px)
    symbols,symbol_classes=_symbol_metrics(
        prediction.get("symbols",[]),
        truth.get("symbols",[]),
    )
    categories={"walls":walls,"rooms":rooms,"openings":openings,"dimensions":dimensions}
    if prediction.get("symbols") or truth.get("symbols"):
        categories["symbols"]=symbols
    macro_f1=sum(float(item["f1"]) for item in categories.values())/len(categories)
    return {
        **categories,
        "symbols":symbols,
        "symbolClasses":symbol_classes,
        "doors":doors,
        "windows":windows,
        "macroF1":round(macro_f1,4),
        "settings":{
            "tolerancePx":tolerance_px,
            "roomIoUThreshold":room_iou_threshold,
        },
    }


def main()->int:
    parser=argparse.ArgumentParser(description="Evaluate Manzil H floor-plan extraction against ground truth JSON.")
    parser.add_argument("--prediction",required=True)
    parser.add_argument("--truth",required=True)
    parser.add_argument("--tolerance-px",type=float,default=12.0)
    parser.add_argument("--room-iou",type=float,default=0.65)
    args=parser.parse_args()

    prediction=json.loads(Path(args.prediction).read_text(encoding="utf-8"))
    truth=json.loads(Path(args.truth).read_text(encoding="utf-8"))
    report=evaluate_floor_plan(
        prediction,truth,
        tolerance_px=max(0.1,args.tolerance_px),
        room_iou_threshold=max(0.0,min(1.0,args.room_iou)),
    )
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
