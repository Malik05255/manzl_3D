from __future__ import annotations

import math
import re

import cv2
import numpy as np

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


def _line(axis:str,start:float,end:float,cross:float,source:str)->dict:
    if start>end:
        start,end=end,start
    return {"axis":axis,"start":float(start),"end":float(end),"cross":float(cross),"source":source}


def _vector_candidates(vector_lines:list[dict]|None)->list[dict]:
    result=[]
    for item in vector_lines or []:
        try:
            ax=float(item["a"]["x"]); ay=float(item["a"]["y"])
            bx=float(item["b"]["x"]); by=float(item["b"]["y"])
        except (KeyError,TypeError,ValueError):
            continue
        dx=abs(bx-ax); dy=abs(by-ay)
        if dx>=max(8.0,dy*6.0):
            result.append(_line("horizontal",ax,bx,(ay+by)/2,"pdf-vector"))
        elif dy>=max(8.0,dx*6.0):
            result.append(_line("vertical",ay,by,(ax+bx)/2,"pdf-vector"))
    return result


def _raster_candidates(ink:np.ndarray|None,width:int,height:int)->list[dict]:
    if ink is None or ink.size==0:
        return []
    h,w=ink.shape[:2]
    if h!=height or w!=width:
        height,width=h,w
    min_side=max(1,min(width,height))
    min_length=max(20,int(round(min_side*0.025)))
    threshold=max(14,int(round(min_side*0.018)))
    gap=max(5,int(round(min_side*0.010)))
    hk=max(9,int(round(min_side*0.012)))
    vk=hk
    result=[]
    for axis,kernel in (
        ("horizontal",cv2.getStructuringElement(cv2.MORPH_RECT,(hk,1))),
        ("vertical",cv2.getStructuringElement(cv2.MORPH_RECT,(1,vk))),
    ):
        mask=cv2.morphologyEx(ink,cv2.MORPH_OPEN,kernel)
        raw=cv2.HoughLinesP(mask,1,np.pi/180,threshold=threshold,minLineLength=min_length,maxLineGap=gap)
        if raw is None:
            continue
        for x1,y1,x2,y2 in raw[:,0]:
            dx=abs(int(x2)-int(x1)); dy=abs(int(y2)-int(y1))
            if axis=="horizontal" and dx>=max(min_length,dy*6):
                result.append(_line(axis,x1,x2,(y1+y2)/2,"raster"))
            elif axis=="vertical" and dy>=max(min_length,dx*6):
                result.append(_line(axis,y1,y2,(x1+x2)/2,"raster"))
    return result


def _dedupe_segments(lines:list[dict],axis_tol:float=4.0,end_tol:float=8.0)->list[dict]:
    result=[]
    for item in sorted(lines,key=lambda x:(x["axis"],x["cross"],x["start"],x["end"])):
        duplicate=None
        for existing in result:
            if existing["axis"]!=item["axis"]:
                continue
            if abs(existing["cross"]-item["cross"])>axis_tol:
                continue
            if abs(existing["start"]-item["start"])<=end_tol and abs(existing["end"]-item["end"])<=end_tol:
                duplicate=existing
                break
        if duplicate is None:
            result.append(dict(item))
        elif duplicate["source"]=="raster" and item["source"]=="pdf-vector":
            duplicate.update(item)
    return result


def _projection_for_label(line:dict,cx:float,cy:float)->tuple[float,float]:
    if line["axis"]=="horizontal":
        return cx,abs(cy-line["cross"])
    return cy,abs(cx-line["cross"])


def _endpoint_marker_score(line:dict,lines:list[dict],tol:float)->float:
    perpendicular="vertical" if line["axis"]=="horizontal" else "horizontal"
    hits=0
    for endpoint in (line["start"],line["end"]):
        for other in lines:
            if other["axis"]!=perpendicular:
                continue
            if line["axis"]=="horizontal":
                endpoint_distance=abs(other["cross"]-endpoint)
                crosses=other["start"]-tol<=line["cross"]<=other["end"]+tol
            else:
                endpoint_distance=abs(other["cross"]-endpoint)
                crosses=other["start"]-tol<=line["cross"]<=other["end"]+tol
            if endpoint_distance<=tol and crosses:
                hits+=1
                break
    return hits/2.0


def _wall_overlap_penalty(line:dict,walls:list[dict])->float:
    length=max(1.0,line["end"]-line["start"])
    best=0.0
    for wall in walls:
        try:
            ax=float(wall["a"]["x"]); ay=float(wall["a"]["y"])
            bx=float(wall["b"]["x"]); by=float(wall["b"]["y"])
            thickness=max(2.0,float(wall.get("thicknessPx",4.0)))
        except (KeyError,TypeError,ValueError):
            continue
        dx=abs(bx-ax); dy=abs(by-ay)
        wall_axis="horizontal" if dx>=dy else "vertical"
        if wall_axis!=line["axis"]:
            continue
        if wall_axis=="horizontal":
            start,end=min(ax,bx),max(ax,bx); cross=(ay+by)/2
        else:
            start,end=min(ay,by),max(ay,by); cross=(ax+bx)/2
        if abs(cross-line["cross"])>max(5.0,thickness*1.5):
            continue
        shared=max(0.0,min(end,line["end"])-max(start,line["start"]))
        best=max(best,shared/length)
    return min(0.55,best*0.55)


def _merged_candidates_for_label(lines:list[dict],cx:float,cy:float,min_side:float)->list[dict]:
    result=list(lines)
    max_gap=max(64.0,min_side*0.16)
    axis_tol=max(4.0,min_side*0.006)
    for i,left in enumerate(lines):
        label_projection,label_perp=_projection_for_label(left,cx,cy)
        if label_perp>max(42.0,min_side*0.05):
            continue
        for right in lines[i+1:]:
            if right["axis"]!=left["axis"] or abs(right["cross"]-left["cross"])>axis_tol:
                continue
            first,second=(left,right) if left["start"]<=right["start"] else (right,left)
            gap=second["start"]-first["end"]
            if gap<1 or gap>max_gap:
                continue
            if not first["end"]-axis_tol<=label_projection<=second["start"]+axis_tol:
                continue
            merged=_line(
                left["axis"],first["start"],second["end"],
                (left["cross"]+right["cross"])/2,
                "pdf-vector" if "pdf-vector" in (left["source"],right["source"]) else "raster",
            )
            merged["splitAroundText"]=True
            result.append(merged)
    return result


def _detect_span_for_label(
    cx:float,cy:float,walls:list[dict],width:int,height:int,lines:list[dict]
)->tuple[dict|None,float]:
    if not lines:
        return None,0.0
    min_side=float(max(1,min(width,height)))
    candidates=_merged_candidates_for_label(lines,cx,cy,min_side)
    max_perp=max(22.0,min_side*0.050)
    marker_tol=max(7.0,min_side*0.010)
    min_length=max(28.0,min_side*0.035)
    best=None
    best_score=0.0

    for line in candidates:
        length=line["end"]-line["start"]
        if length<min_length:
            continue
        projection,perp=_projection_for_label(line,cx,cy)
        if perp>max_perp:
            continue
        margin=max(12.0,length*0.12)
        if projection<line["start"]-margin or projection>line["end"]+margin:
            continue

        perp_score=max(0.0,1.0-perp/max_perp)
        midpoint=(line["start"]+line["end"])/2
        center_score=max(0.0,1.0-abs(projection-midpoint)/max(length*0.60,1.0))
        marker_score=_endpoint_marker_score(line,lines,marker_tol)
        split_bonus=0.18 if line.get("splitAroundText") else 0.0
        source_bonus=0.10 if line["source"]=="pdf-vector" else 0.0
        score=0.38*perp_score+0.22*center_score+0.30*marker_score+split_bonus+source_bonus
        score-=_wall_overlap_penalty(line,walls)
        score=max(0.0,min(1.0,score))
        if score>best_score:
            best_score=score
            best=line

    if best is None or best_score<0.58:
        return None,best_score
    if best["axis"]=="horizontal":
        span={"a":{"x":best["start"],"y":best["cross"]},"b":{"x":best["end"],"y":best["cross"]},"orientation":"horizontal"}
    else:
        span={"a":{"x":best["cross"],"y":best["start"]},"b":{"x":best["cross"],"y":best["end"]},"orientation":"vertical"}
    return span,best_score


def extract_dimension_evidence(
    labels:list[dict],walls:list[dict],width:int,height:int,
    ink:np.ndarray|None=None,vector_lines:list[dict]|None=None,
)->list[dict]:
    result=[]
    max_distance=max(18.0,min(width,height)*0.065)
    lines=_dedupe_segments([*_vector_candidates(vector_lines),*_raster_candidates(ink,width,height)])

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

        span,span_confidence=_detect_span_for_label(cx,cy,walls,width,height,lines)
        span_a=None
        span_b=None
        if span is not None and value_m is not None:
            span_a=span["a"]
            span_b=span["b"]
            orientation=span["orientation"]

        label_confidence=float(label.get("confidence",0.5))
        confidence=label_confidence
        if span is not None:
            confidence=min(0.99,0.62*label_confidence+0.38*span_confidence)

        item={
            "id":f"dimension-{len(result)+1}",
            "sourceLabelId":label.get("id"),
            "text":text,
            "center":{"x":cx,"y":cy},
            "valueM":value_m,
            "unit":unit,
            "orientation":orientation,
            "referenceWallId":reference_wall_id,
            "confidence":round(max(0.0,min(1.0,confidence)),3),
            "reviewed":bool(label.get("reviewed",False)),
            "provenance":label.get("provenance"),
        }
        if span_a is not None and span_b is not None:
            item["spanA"]=span_a
            item["spanB"]=span_b
        result.append(item)
    return result
