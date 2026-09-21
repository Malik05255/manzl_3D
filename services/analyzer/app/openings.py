from __future__ import annotations
import math
import cv2
import numpy as np


def _orientation(wall:dict)->str:
    dx=abs(wall["b"]["x"]-wall["a"]["x"])
    dy=abs(wall["b"]["y"]-wall["a"]["y"])
    return "h" if dx>=dy else "v"


def _ordered_segment(wall:dict)->tuple[float,float,float]:
    if _orientation(wall)=="h":
        start=min(wall["a"]["x"],wall["b"]["x"])
        end=max(wall["a"]["x"],wall["b"]["x"])
        axis=(wall["a"]["y"]+wall["b"]["y"])/2
    else:
        start=min(wall["a"]["y"],wall["b"]["y"])
        end=max(wall["a"]["y"],wall["b"]["y"])
        axis=(wall["a"]["x"]+wall["b"]["x"])/2
    return start,end,axis


def _door_gap_limits(image:np.ndarray,meters_per_pixel:float|None)->tuple[float,float,float]:
    h,w=image.shape[:2]
    base=float(min(h,w))
    if meters_per_pixel and meters_per_pixel>0:
        return 0.65/meters_per_pixel,1.80/meters_per_pixel,max(5.0,0.10/meters_per_pixel)
    return base*0.018,base*0.11,max(5.0,base*0.006)

def _window_gap_limits(image:np.ndarray,meters_per_pixel:float|None)->tuple[float,float,float]:
    h,w=image.shape[:2]
    base=float(min(h,w))
    if meters_per_pixel and meters_per_pixel>0:
        return 0.50/meters_per_pixel,3.50/meters_per_pixel,max(5.0,0.10/meters_per_pixel)
    return base*0.015,base*0.18,max(5.0,base*0.006)


def _diagonal_evidence(image:np.ndarray,a:dict,b:dict,gap_px:float,orientation:str)->int:
    h,w=image.shape[:2]
    cx=(a["x"]+b["x"])/2
    cy=(a["y"]+b["y"])/2
    radius=max(18,int(round(gap_px*0.95)))
    x1=max(0,int(cx-radius)); x2=min(w,int(cx+radius))
    y1=max(0,int(cy-radius)); y2=min(h,int(cy+radius))
    roi=image[y1:y2,x1:x2]
    if roi.size==0:
        return 0

    gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,60,160)
    raw=cv2.HoughLinesP(
        edges,
        1,
        np.pi/180,
        threshold=max(10,int(gap_px*0.20)),
        minLineLength=max(8,int(gap_px*0.30)),
        maxLineGap=max(3,int(gap_px*0.10)),
    )
    if raw is None:
        return 0

    evidence=0
    for x1l,y1l,x2l,y2l in raw[:,0]:
        dx=abs(int(x2l)-int(x1l))
        dy=abs(int(y2l)-int(y1l))
        length=math.hypot(dx,dy)
        if length<gap_px*0.28 or length>gap_px*1.65:
            continue
        angle=math.degrees(math.atan2(dy,dx+1e-9))
        # Door leaves / swing geometry create a strong non-axis-aligned stroke near the wall gap.
        if 18<=angle<=72:
            evidence+=1
    return evidence


def _parallel_window_evidence(image:np.ndarray,a:dict,b:dict,gap_px:float,orientation:str)->int:
    h,w=image.shape[:2]
    margin=max(1,int(round(gap_px*0.06)))
    band=max(8,int(round(gap_px*0.28)))

    if orientation=="h":
        x1=max(0,int(min(a["x"],b["x"])+margin))
        x2=min(w,int(max(a["x"],b["x"])-margin))
        cy=int(round((a["y"]+b["y"])/2))
        y1=max(0,cy-band); y2=min(h,cy+band)
    else:
        y1=max(0,int(min(a["y"],b["y"])+margin))
        y2=min(h,int(max(a["y"],b["y"])-margin))
        cx=int(round((a["x"]+b["x"])/2))
        x1=max(0,cx-band); x2=min(w,cx+band)

    if x2-x1<8 or y2-y1<8:
        return 0
    roi=image[y1:y2,x1:x2]
    gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,55,150)
    raw=cv2.HoughLinesP(
        edges,
        1,
        np.pi/180,
        threshold=max(8,int(gap_px*0.18)),
        minLineLength=max(7,int(gap_px*0.48)),
        maxLineGap=max(3,int(gap_px*0.08)),
    )
    if raw is None:
        return 0

    evidence=0
    for x1l,y1l,x2l,y2l in raw[:,0]:
        dx=abs(int(x2l)-int(x1l))
        dy=abs(int(y2l)-int(y1l))
        length=math.hypot(dx,dy)
        if length<gap_px*0.48:
            continue
        if orientation=="h" and dx>=max(6,dy*5):
            evidence+=1
        elif orientation=="v" and dy>=max(6,dx*5):
            evidence+=1
    return evidence


def _dedupe(openings:list[dict],distance:float)->list[dict]:
    result=[]
    for opening in sorted(openings,key=lambda item:item["confidence"],reverse=True):
        cx=(opening["a"]["x"]+opening["b"]["x"])/2
        cy=(opening["a"]["y"]+opening["b"]["y"])/2
        duplicate=False
        for existing in result:
            ex=(existing["a"]["x"]+existing["b"]["x"])/2
            ey=(existing["a"]["y"]+existing["b"]["y"])/2
            if math.hypot(cx-ex,cy-ey)<=distance:
                duplicate=True
                break
        if not duplicate:
            result.append(opening)
    return result


def detect_doors(image:np.ndarray,walls:list[dict],meters_per_pixel:float|None)->list[dict]:
    min_gap,max_gap,axis_tol=_door_gap_limits(image,meters_per_pixel)
    candidates=[]

    for index,left in enumerate(walls):
        orientation=_orientation(left)
        ls,le,la=_ordered_segment(left)
        for right in walls[index+1:]:
            if _orientation(right)!=orientation:
                continue
            rs,re,ra=_ordered_segment(right)
            if abs(la-ra)>axis_tol:
                continue

            first,second=(left,right)
            fs,fe,fa=(ls,le,la)
            ss,se,sa=(rs,re,ra)
            if rs<ls:
                first,second=(right,left)
                fs,fe,fa=(rs,re,ra)
                ss,se,sa=(ls,le,la)

            gap=ss-fe
            if gap<min_gap or gap>max_gap:
                continue

            axis=(fa+sa)/2
            if orientation=="h":
                a={"x":float(fe),"y":float(axis)}
                b={"x":float(ss),"y":float(axis)}
            else:
                a={"x":float(axis),"y":float(fe)}
                b={"x":float(axis),"y":float(ss)}

            evidence=_diagonal_evidence(image,a,b,gap,orientation)
            if evidence<1:
                continue

            confidence=min(0.93,0.69+0.07*evidence+(0.05 if meters_per_pixel else 0.0))
            if confidence<0.76:
                continue

            first_len=abs(fe-fs)
            second_len=abs(se-ss)
            wall_id=first["id"] if first_len>=second_len else second["id"]
            candidates.append({
                "id":f"door-candidate-{len(candidates)+1}",
                "kind":"door",
                "wallId":wall_id,
                "a":a,
                "b":b,
                "confidence":round(confidence,3),
            })

    dedupe_distance=max(min_gap*0.6,8.0)
    result=_dedupe(candidates,dedupe_distance)
    for index,item in enumerate(result,start=1):
        item["id"]=f"door-{index}"
    return result


def detect_windows(image:np.ndarray,walls:list[dict],meters_per_pixel:float|None)->list[dict]:
    min_gap,max_gap,axis_tol=_window_gap_limits(image,meters_per_pixel)
    candidates=[]

    for index,left in enumerate(walls):
        orientation=_orientation(left)
        ls,le,la=_ordered_segment(left)
        for right in walls[index+1:]:
            if _orientation(right)!=orientation:
                continue
            rs,re,ra=_ordered_segment(right)
            if abs(la-ra)>axis_tol:
                continue

            first,second=(left,right)
            fs,fe,fa=(ls,le,la)
            ss,se,sa=(rs,re,ra)
            if rs<ls:
                first,second=(right,left)
                fs,fe,fa=(rs,re,ra)
                ss,se,sa=(ls,le,la)

            gap=ss-fe
            if gap<min_gap or gap>max_gap:
                continue

            axis=(fa+sa)/2
            if orientation=="h":
                a={"x":float(fe),"y":float(axis)}
                b={"x":float(ss),"y":float(axis)}
            else:
                a={"x":float(axis),"y":float(fe)}
                b={"x":float(axis),"y":float(ss)}

            if _diagonal_evidence(image,a,b,gap,orientation)>0:
                continue
            evidence=_parallel_window_evidence(image,a,b,gap,orientation)
            if evidence<2:
                continue

            confidence=min(0.94,0.70+0.055*evidence+(0.04 if meters_per_pixel else 0.0))
            if confidence<0.80:
                continue

            first_len=abs(fe-fs)
            second_len=abs(se-ss)
            wall_id=first["id"] if first_len>=second_len else second["id"]
            candidates.append({
                "id":f"window-candidate-{len(candidates)+1}",
                "kind":"window",
                "wallId":wall_id,
                "a":a,
                "b":b,
                "confidence":round(confidence,3),
            })

    result=_dedupe(candidates,max(min_gap*0.55,8.0))
    for index,item in enumerate(result,start=1):
        item["id"]=f"window-{index}"
    return result
