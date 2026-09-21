from __future__ import annotations
import math
import cv2
import numpy as np

def _dedupe(lines:list[tuple[int,int,int,int]],tol:int=8)->list[tuple[int,int,int,int]]:
    out=[]
    for line in sorted(lines,key=lambda p:math.hypot(p[2]-p[0],p[3]-p[1]),reverse=True):
        x1,y1,x2,y2=line; horizontal=abs(y2-y1)<=abs(x2-x1); duplicate=False
        for a,b,c,d in out:
            other=abs(d-b)<=abs(c-a)
            if horizontal!=other: continue
            if horizontal:
                same=abs(((y1+y2)/2)-((b+d)/2))<tol
                overlap=max(min(x1,x2),min(a,c))<=min(max(x1,x2),max(a,c))+tol
            else:
                same=abs(((x1+x2)/2)-((a+c)/2))<tol
                overlap=max(min(y1,y2),min(b,d))<=min(max(y1,y2),max(b,d))+tol
            if same and overlap: duplicate=True; break
        if not duplicate: out.append(line)
    return out

def _estimate_thickness(ink:np.ndarray,line:tuple[int,int,int,int])->float:
    x1,y1,x2,y2=line
    h,w=ink.shape[:2]
    horizontal=abs(y2-y1)<=abs(x2-x1)
    max_radius=max(6,min(36,min(h,w)//45))

    if horizontal:
        axis=int(round((y1+y2)/2))
        start=max(0,min(x1,x2)); end=min(w,max(x1,x2)+1)
        if end-start<6:
            return 4.0
        trim=max(1,int((end-start)*0.12))
        start=min(end-1,start+trim); end=max(start+1,end-trim)
        top=max(0,axis-max_radius); bottom=min(h,axis+max_radius+1)
        strip=ink[top:bottom,start:end]
        if strip.size==0:
            return 4.0
        density=np.mean(strip>0,axis=1)
        active=np.where(density>=0.10)[0]
        center=axis-top
    else:
        axis=int(round((x1+x2)/2))
        start=max(0,min(y1,y2)); end=min(h,max(y1,y2)+1)
        if end-start<6:
            return 4.0
        trim=max(1,int((end-start)*0.12))
        start=min(end-1,start+trim); end=max(start+1,end-trim)
        left=max(0,axis-max_radius); right=min(w,axis+max_radius+1)
        strip=ink[start:end,left:right]
        if strip.size==0:
            return 4.0
        density=np.mean(strip>0,axis=0)
        active=np.where(density>=0.10)[0]
        center=axis-left

    if active.size==0:
        return 4.0

    # Only use evidence reasonably close to the detected wall axis so nearby
    # dimension lines/text do not inflate wall thickness.
    active=active[np.abs(active-center)<=max_radius]
    if active.size==0:
        return 4.0
    thickness=float(active.max()-active.min()+1)
    return max(2.0,min(32.0,thickness))


def detect_walls(ink:np.ndarray)->tuple[list[dict],np.ndarray]:
    h,w=ink.shape[:2]
    hk=max(18,w//45); vk=max(18,h//45)
    horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(hk,1)))
    vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,vk)))
    mask=cv2.bitwise_or(horizontal,vertical)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    raw=cv2.HoughLinesP(mask,1,np.pi/180,threshold=max(40,min(h,w)//18),minLineLength=max(35,min(h,w)//18),maxLineGap=12)
    lines=[]
    if raw is not None:
        for item in raw[:,0]:
            x1,y1,x2,y2=map(int,item); dx,dy=abs(x2-x1),abs(y2-y1)
            if dx>=dy*4:
                y=int(round((y1+y2)/2)); lines.append((min(x1,x2),y,max(x1,x2),y))
            elif dy>=dx*4:
                x=int(round((x1+x2)/2)); lines.append((x,min(y1,y2),x,max(y1,y2)))
    deduped=_dedupe(lines)
    walls=[{"id":f"wall-{i+1}","a":{"x":float(x1),"y":float(y1)},"b":{"x":float(x2),"y":float(y2)},"thicknessPx":round(_estimate_thickness(ink,(x1,y1,x2,y2)),2),"confidence":0.80,"reviewed":False,"provenance":"opencv"} for i,(x1,y1,x2,y2) in enumerate(deduped)]
    return walls,mask


def enrich_walls_with_vector(walls:list[dict],vector_lines:list[dict])->list[dict]:
    if not walls or not vector_lines:
        return walls

    def orientation(line:dict)->str:
        dx=abs(line["b"]["x"]-line["a"]["x"])
        dy=abs(line["b"]["y"]-line["a"]["y"])
        return "h" if dx>=dy else "v"

    def ordered(line:dict,axis:str):
        if axis=="h":
            return (
                min(line["a"]["x"],line["b"]["x"]),
                max(line["a"]["x"],line["b"]["x"]),
                (line["a"]["y"]+line["b"]["y"])/2,
            )
        return (
            min(line["a"]["y"],line["b"]["y"]),
            max(line["a"]["y"],line["b"]["y"]),
            (line["a"]["x"]+line["b"]["x"])/2,
        )

    result=[]
    for wall in walls:
        axis=orientation(wall)
        start,end,wall_axis=ordered(wall,axis)
        wall_length=max(1.0,end-start)
        best=0.0
        for vector in vector_lines:
            if orientation(vector)!=axis:
                continue
            v_start,v_end,v_axis=ordered(vector,axis)
            axis_tol=max(4.0,float(wall.get("thicknessPx",4.0))*1.8)
            axis_distance=abs(v_axis-wall_axis)
            if axis_distance>axis_tol:
                continue
            shared=max(0.0,min(end,v_end)-max(start,v_start))
            overlap_ratio=shared/max(1.0,min(wall_length,v_end-v_start))
            if overlap_ratio<0.45:
                continue
            score=overlap_ratio*(1.0-axis_distance/max(axis_tol,1.0))
            best=max(best,score)

        if best>0:
            confidence=max(float(wall.get("confidence",0.0)),min(0.97,0.88+0.09*best))
            result.append({**wall,"confidence":round(confidence,3),"provenance":"mixed"})
        else:
            result.append(wall)
    return result


def add_vector_wall_candidates(walls:list[dict],vector_lines:list[dict],height:int,width:int)->list[dict]:
    """Add high-confidence wall centerlines from native PDF vectors.

    Preferred evidence is a close parallel pair (double-line wall). A single
    vector stroke is promoted only when it is unusually thick and long enough
    to be credible wall geometry; ordinary dimension/guide lines stay ignored.
    """
    if not vector_lines:
        return walls

    min_side=float(max(1,min(height,width)))
    min_length=max(45.0,min_side*0.04)
    max_separation=max(10.0,min(42.0,min_side*0.025))

    def orientation(line:dict)->str:
        dx=abs(float(line["b"]["x"])-float(line["a"]["x"]))
        dy=abs(float(line["b"]["y"])-float(line["a"]["y"]))
        return "h" if dx>=dy else "v"

    def ordered(line:dict,axis:str)->tuple[float,float,float]:
        if axis=="h":
            return (
                min(float(line["a"]["x"]),float(line["b"]["x"])),
                max(float(line["a"]["x"]),float(line["b"]["x"])),
                (float(line["a"]["y"])+float(line["b"]["y"]))/2,
            )
        return (
            min(float(line["a"]["y"]),float(line["b"]["y"])),
            max(float(line["a"]["y"]),float(line["b"]["y"])),
            (float(line["a"]["x"])+float(line["b"]["x"]))/2,
        )

    candidates=[]
    widths=[
        max(0.1,float(line.get("widthPx",1.0)))
        for line in vector_lines
        if math.isfinite(float(line.get("widthPx",1.0)))
    ]
    median_stroke=float(np.median(widths)) if widths else 1.0
    thick_stroke_threshold=max(7.0,min_side*0.0035)

    # Some CAD/PDF exports encode walls as one heavy centerline rather than two
    # thin parallel outlines. Recover only unusually thick, long strokes.
    for vector in vector_lines:
        axis=orientation(vector)
        start,end,center_axis=ordered(vector,axis)
        length=end-start
        stroke=max(0.1,float(vector.get("widthPx",1.0)))
        unusually_thick=stroke>=thick_stroke_threshold and (
            median_stroke>=thick_stroke_threshold*0.70
            or stroke>=median_stroke*1.8
        )
        if length<min_length*1.35 or not unusually_thick:
            continue
        if axis=="h":
            a={"x":start,"y":center_axis}; b={"x":end,"y":center_axis}
        else:
            a={"x":center_axis,"y":start}; b={"x":center_axis,"y":end}
        candidates.append({
            "a":a,"b":b,
            "thicknessPx":round(max(2.0,min(48.0,stroke)),2),
            "confidence":0.91,
            "reviewed":False,
            "provenance":"pdf-vector",
        })

    for index,left in enumerate(vector_lines):
        axis=orientation(left)
        ls,le,la=ordered(left,axis)
        llen=le-ls
        if llen<min_length:
            continue
        for right in vector_lines[index+1:]:
            if orientation(right)!=axis:
                continue
            rs,re,ra=ordered(right,axis)
            rlen=re-rs
            if rlen<min_length:
                continue
            separation=abs(la-ra)
            if separation<2.0 or separation>max_separation:
                continue
            shared=max(0.0,min(le,re)-max(ls,rs))
            overlap_ratio=shared/max(1.0,min(llen,rlen))
            if overlap_ratio<0.72 or shared<min_length:
                continue
            if separation/max(shared,1.0)>0.09:
                continue

            start=max(ls,rs)
            end=min(le,re)
            center_axis=(la+ra)/2
            stroke=(float(left.get("widthPx",1.0))+float(right.get("widthPx",1.0)))/2
            thickness=max(2.0,min(48.0,separation+stroke))
            if axis=="h":
                a={"x":start,"y":center_axis}; b={"x":end,"y":center_axis}
            else:
                a={"x":center_axis,"y":start}; b={"x":center_axis,"y":end}
            confidence=min(0.98,0.91+0.07*overlap_ratio)
            candidates.append({
                "a":a,"b":b,
                "thicknessPx":round(thickness,2),
                "confidence":round(confidence,3),
                "reviewed":False,
                "provenance":"pdf-vector",
            })

    result=[dict(wall) for wall in walls]

    def duplicate(candidate:dict,existing:dict)->bool:
        axis=orientation(candidate)
        if orientation(existing)!=axis:
            return False
        cs,ce,ca=ordered(candidate,axis)
        es,ee,ea=ordered(existing,axis)
        shared=max(0.0,min(ce,ee)-max(cs,es))
        if shared<=0:
            return False
        overlap_ratio=shared/max(1.0,min(ce-cs,ee-es))
        axis_tol=max(
            6.0,
            float(candidate.get("thicknessPx",4.0))*1.5,
            float(existing.get("thicknessPx",4.0))*1.5,
        )
        return abs(ca-ea)<=axis_tol and overlap_ratio>=0.55

    accepted=[]
    for candidate in sorted(
        candidates,
        key=lambda item:(
            -float(item["confidence"]),
            -math.hypot(item["b"]["x"]-item["a"]["x"],item["b"]["y"]-item["a"]["y"]),
        ),
    ):
        if any(duplicate(candidate,existing) for existing in [*result,*accepted]):
            continue
        accepted.append(candidate)

    existing_ids={str(wall.get("id","")) for wall in result}
    next_index=1
    for candidate in accepted:
        while f"wall-vector-{next_index}" in existing_ids:
            next_index+=1
        candidate["id"]=f"wall-vector-{next_index}"
        existing_ids.add(candidate["id"])
        result.append(candidate)
        next_index+=1
    return result


def rasterize_wall_mask(walls:list[dict],height:int,width:int,base_mask:np.ndarray|None=None)->np.ndarray:
    """Build a room-separation barrier from canonical wall centerlines.

    This intentionally draws host walls continuously across doors/windows:
    openings remain semantic objects, while room extraction needs a closed
    boundary to keep adjacent spaces separate.
    """
    if base_mask is None:
        mask=np.zeros((height,width),dtype=np.uint8)
    else:
        if base_mask.shape[:2]!=(height,width):
            raise ValueError("WALL_MASK_SHAPE")
        mask=base_mask.copy()

    for wall in walls:
        try:
            x1=int(round(float(wall["a"]["x"])))
            y1=int(round(float(wall["a"]["y"])))
            x2=int(round(float(wall["b"]["x"])))
            y2=int(round(float(wall["b"]["y"])))
            thickness=float(wall.get("thicknessPx",4.0))
        except (KeyError,TypeError,ValueError):
            continue
        if math.hypot(x2-x1,y2-y1)<2:
            continue
        line_width=max(2,min(64,int(round(thickness))))
        cv2.line(mask,(x1,y1),(x2,y2),255,line_width,lineType=cv2.LINE_8)

    if walls:
        join=max(3,min(15,int(round(np.median([
            max(2.0,float(wall.get("thicknessPx",4.0)))
            for wall in walls
        ])))))
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((join,join),np.uint8))
    return mask
