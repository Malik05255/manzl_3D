from __future__ import annotations

import math

import cv2
import numpy as np


def _merge_axis_lines(
    lines:list[tuple[int,int,int,int]],
    *,
    axis_tol:int=8,
    gap_tol:int=3,
)->list[tuple[int,int,int,int]]:
    """Merge overlapping H/V Hough fragments into full centerlines.

    The old dedupe path kept the first/longest segment and discarded overlapping
    fragments, which could lose a real wall extension. Here overlapping pieces
    are unioned. Only tiny raster gaps are bridged; architectural opening-sized
    gaps stay separate for door/window detection.
    """
    pending=[]
    for x1,y1,x2,y2 in lines:
        horizontal=abs(y2-y1)<=abs(x2-x1)
        if horizontal:
            axis=int(round((y1+y2)/2))
            start=min(x1,x2); end=max(x1,x2)
        else:
            axis=int(round((x1+x2)/2))
            start=min(y1,y2); end=max(y1,y2)
        pending.append({
            "horizontal":horizontal,
            "axis":float(axis),
            "start":float(start),
            "end":float(end),
            "weight":max(1.0,float(end-start)),
        })

    changed=True
    while changed:
        changed=False
        merged=[]
        used=[False]*len(pending)
        for index,item in enumerate(pending):
            if used[index]:
                continue
            current=dict(item)
            for j in range(index+1,len(pending)):
                if used[j]:
                    continue
                other=pending[j]
                if current["horizontal"]!=other["horizontal"]:
                    continue
                if abs(current["axis"]-other["axis"])>=axis_tol:
                    continue
                if other["end"]<current["start"]:
                    gap=current["start"]-other["end"]
                elif other["start"]>current["end"]:
                    gap=other["start"]-current["end"]
                else:
                    gap=0.0
                if gap>gap_tol:
                    continue

                total=current["weight"]+other["weight"]
                current["axis"]=(
                    current["axis"]*current["weight"]
                    +other["axis"]*other["weight"]
                )/max(1.0,total)
                current["weight"]=total
                current["start"]=min(current["start"],other["start"])
                current["end"]=max(current["end"],other["end"])
                used[j]=True
                changed=True
            used[index]=True
            merged.append(current)
        pending=merged

    result=[]
    for item in pending:
        axis=int(round(item["axis"]))
        start=int(round(item["start"]))
        end=int(round(item["end"]))
        if item["horizontal"]:
            result.append((start,axis,end,axis))
        else:
            result.append((axis,start,axis,end))
    return sorted(
        result,
        key=lambda p:math.hypot(p[2]-p[0],p[3]-p[1]),
        reverse=True,
    )


def _dedupe(lines:list[tuple[int,int,int,int]],tol:int=8)->list[tuple[int,int,int,int]]:
    # Compatibility wrapper used by older tests/callers.
    return _merge_axis_lines(lines,axis_tol=tol)


def _collapse_parallel_wall_bands(
    ink:np.ndarray,
    lines:list[tuple[int,int,int,int]],
)->list[tuple[int,int,int,int]]:
    """Collapse multiple Hough centerlines produced by one thick wall band.

    Lines must substantially overlap along their run. Axial gaps are never
    bridged here, so door/window gaps remain available to opening detection.
    """
    pending=[tuple(line) for line in lines]
    changed=True
    while changed:
        changed=False
        result=[]
        used=[False]*len(pending)
        for index,left in enumerate(pending):
            if used[index]:
                continue
            current=left
            for j in range(index+1,len(pending)):
                if used[j]:
                    continue
                right=pending[j]
                lh=abs(current[3]-current[1])<=abs(current[2]-current[0])
                rh=abs(right[3]-right[1])<=abs(right[2]-right[0])
                if lh!=rh:
                    continue

                if lh:
                    c_axis=(current[1]+current[3])/2
                    r_axis=(right[1]+right[3])/2
                    cs,ce=sorted((current[0],current[2]))
                    rs,re=sorted((right[0],right[2]))
                else:
                    c_axis=(current[0]+current[2])/2
                    r_axis=(right[0]+right[2])/2
                    cs,ce=sorted((current[1],current[3]))
                    rs,re=sorted((right[1],right[3]))

                shared=max(0.0,min(ce,re)-max(cs,rs))
                overlap=shared/max(1.0,min(ce-cs,re-rs))
                if overlap<.62:
                    continue

                c_thickness=_estimate_thickness(ink,current)
                r_thickness=_estimate_thickness(ink,right)
                axis_tol=max(4.0,(c_thickness+r_thickness)*.60)
                if abs(c_axis-r_axis)>axis_tol:
                    continue

                c_len=max(1.0,ce-cs)
                r_len=max(1.0,re-rs)
                axis=(c_axis*c_len+r_axis*r_len)/(c_len+r_len)
                start=min(cs,rs)
                end=max(ce,re)
                if lh:
                    y=int(round(axis))
                    current=(int(round(start)),y,int(round(end)),y)
                else:
                    x=int(round(axis))
                    current=(x,int(round(start)),x,int(round(end)))
                used[j]=True
                changed=True
            used[index]=True
            result.append(current)
        pending=result
    return sorted(
        pending,
        key=lambda p:math.hypot(p[2]-p[0],p[3]-p[1]),
        reverse=True,
    )


def _estimate_thickness(ink:np.ndarray,line:tuple[int,int,int,int])->float:
    x1,y1,x2,y2=line
    h,w=ink.shape[:2]
    horizontal=abs(y2-y1)<=abs(x2-x1)
    max_radius=max(6,min(36,min(h,w)//45))

    if horizontal:
        axis=int(round((y1+y2)/2))
        start=max(0,min(x1,x2))
        end=min(w,max(x1,x2)+1)
        if end-start<6:
            return 4.0
        trim=max(1,int((end-start)*0.12))
        start=min(end-1,start+trim)
        end=max(start+1,end-trim)
        top=max(0,axis-max_radius)
        bottom=min(h,axis+max_radius+1)
        strip=ink[top:bottom,start:end]
        if strip.size==0:
            return 4.0
        density=np.mean(strip>0,axis=1)
        active=np.where(density>=0.10)[0]
        center=axis-top
    else:
        axis=int(round((x1+x2)/2))
        start=max(0,min(y1,y2))
        end=min(h,max(y1,y2)+1)
        if end-start<6:
            return 4.0
        trim=max(1,int((end-start)*0.12))
        start=min(end-1,start+trim)
        end=max(start+1,end-trim)
        left=max(0,axis-max_radius)
        right=min(w,axis+max_radius+1)
        strip=ink[start:end,left:right]
        if strip.size==0:
            return 4.0
        density=np.mean(strip>0,axis=0)
        active=np.where(density>=0.10)[0]
        center=axis-left

    if active.size==0:
        return 4.0
    active=active[np.abs(active-center)<=max_radius]
    if active.size==0:
        return 4.0
    thickness=float(active.max()-active.min()+1)
    return max(2.0,min(32.0,thickness))


def _point(item:dict)->tuple[float,float]:
    return float(item["x"]),float(item["y"])


def _segment_geometry(line:dict)->tuple[float,float,float,float,float,float,float]:
    ax,ay=_point(line["a"])
    bx,by=_point(line["b"])
    dx=bx-ax
    dy=by-ay
    length=math.hypot(dx,dy)
    if length<=1e-9:
        return ax,ay,bx,by,0.0,0.0,0.0
    ux=dx/length
    uy=dy/length
    if ux<0 or (abs(ux)<1e-9 and uy<0):
        ux=-ux
        uy=-uy
    return ax,ay,bx,by,length,ux,uy


def _angle_difference(left:dict,right:dict)->float:
    *_,llen,lux,luy=_segment_geometry(left)
    *_,rlen,rux,ruy=_segment_geometry(right)
    if llen<=1e-9 or rlen<=1e-9:
        return 180.0
    cosine=max(-1.0,min(1.0,abs(lux*rux+luy*ruy)))
    return math.degrees(math.acos(cosine))


def _frame(line:dict)->tuple[float,float,float,float,float,float]:
    *_,length,ux,uy=_segment_geometry(line)
    nx=-uy
    ny=ux
    ax,ay=_point(line["a"])
    bx,by=_point(line["b"])
    ta=ax*ux+ay*uy
    tb=bx*ux+by*uy
    offset=((ax+bx)/2)*nx+((ay+by)/2)*ny
    return min(ta,tb),max(ta,tb),offset,length,ux,uy


def _point_from_frame(t:float,offset:float,ux:float,uy:float)->dict:
    nx=-uy
    ny=ux
    return {"x":float(ux*t+nx*offset),"y":float(uy*t+ny*offset)}


def _parallel_pair_candidate(
    left:dict,
    right:dict,
    *,
    min_length:float,
    max_separation:float,
    min_overlap_ratio:float=.70,
    max_angle_deg:float=4.0,
)->dict|None:
    if _angle_difference(left,right)>max_angle_deg:
        return None
    ls,le,lo,llen,ux,uy=_frame(left)
    if llen<min_length:
        return None

    # Project the second segment into the first segment's frame.
    rax,ray=_point(right["a"])
    rbx,rby=_point(right["b"])
    nx=-uy
    ny=ux
    rs=min(rax*ux+ray*uy,rbx*ux+rby*uy)
    re=max(rax*ux+ray*uy,rbx*ux+rby*uy)
    ro=((rax+rbx)/2)*nx+((ray+rby)/2)*ny
    rlen=re-rs
    if rlen<min_length:
        return None

    separation=abs(ro-lo)
    if separation<2.0 or separation>max_separation:
        return None
    shared=max(0.0,min(le,re)-max(ls,rs))
    overlap_ratio=shared/max(1.0,min(le-ls,re-rs))
    if overlap_ratio<min_overlap_ratio or shared<min_length:
        return None
    if separation/max(shared,1.0)>0.10:
        return None

    start=max(ls,rs)
    end=min(le,re)
    center_offset=(lo+ro)/2
    stroke=(float(left.get("widthPx",1.0))+float(right.get("widthPx",1.0)))/2
    thickness=max(2.0,min(48.0,separation+stroke))
    confidence=min(0.985,0.90+0.075*overlap_ratio)
    return {
        "a":_point_from_frame(start,center_offset,ux,uy),
        "b":_point_from_frame(end,center_offset,ux,uy),
        "thicknessPx":round(thickness,2),
        "confidence":round(confidence,3),
        "reviewed":False,
    }


def _wall_duplicate(candidate:dict,existing:dict)->bool:
    if _angle_difference(candidate,existing)>5.0:
        return False
    cs,ce,co,clen,ux,uy=_frame(candidate)
    eax,eay=_point(existing["a"])
    ebx,eby=_point(existing["b"])
    nx=-uy
    ny=ux
    es=min(eax*ux+eay*uy,ebx*ux+eby*uy)
    ee=max(eax*ux+eay*uy,ebx*ux+eby*uy)
    eo=((eax+ebx)/2)*nx+((eay+eby)/2)*ny
    shared=max(0.0,min(ce,ee)-max(cs,es))
    if shared<=0:
        return False
    overlap_ratio=shared/max(1.0,min(clen,ee-es))
    axis_tol=max(
        6.0,
        float(candidate.get("thicknessPx",4.0))*1.6,
        float(existing.get("thicknessPx",4.0))*1.6,
    )
    return abs(co-eo)<=axis_tol and overlap_ratio>=0.55


def _merge_near_collinear_candidates(candidates:list[dict])->list[dict]:
    """Merge Hough fragments on the same wall while preserving real openings.

    Only overlap or very small axial gaps are merged. Door/window-sized gaps
    remain separate segments so the opening detector can still observe them.
    """
    pending=[dict(item) for item in candidates]
    changed=True
    while changed:
        changed=False
        result=[]
        used=[False]*len(pending)
        for index,left in enumerate(pending):
            if used[index]:
                continue
            current=dict(left)
            for j in range(index+1,len(pending)):
                if used[j]:
                    continue
                right=pending[j]
                if _angle_difference(current,right)>4.0:
                    continue
                cs,ce,co,clen,ux,uy=_frame(current)
                rax,ray=_point(right["a"])
                rbx,rby=_point(right["b"])
                nx=-uy
                ny=ux
                rs=min(rax*ux+ray*uy,rbx*ux+rby*uy)
                re=max(rax*ux+ray*uy,rbx*ux+rby*uy)
                ro=((rax+rbx)/2)*nx+((ray+rby)/2)*ny
                thickness=max(
                    float(current.get("thicknessPx",4.0)),
                    float(right.get("thicknessPx",4.0)),
                )
                axis_tol=max(5.0,thickness*.85)
                if abs(co-ro)>axis_tol:
                    continue
                if re<cs:
                    axial_gap=cs-re
                elif rs>ce:
                    axial_gap=rs-ce
                else:
                    axial_gap=0.0
                gap_tol=max(5.0,min(12.0,thickness*.80))
                if axial_gap>gap_tol:
                    continue

                start=min(cs,rs)
                end=max(ce,re)
                left_len=max(1.0,clen)
                right_len=max(1.0,re-rs)
                total=left_len+right_len
                offset=(co*left_len+ro*right_len)/total
                confidence=max(
                    float(current.get("confidence",0.0)),
                    float(right.get("confidence",0.0)),
                )
                provenance=current.get("provenance") if current.get("provenance")==right.get("provenance") else "mixed"
                current={
                    **current,
                    "a":_point_from_frame(start,offset,ux,uy),
                    "b":_point_from_frame(end,offset,ux,uy),
                    "thicknessPx":round((
                        float(current.get("thicknessPx",4.0))*left_len
                        +float(right.get("thicknessPx",4.0))*right_len
                    )/total,2),
                    "confidence":round(confidence,3),
                    "reviewed":bool(current.get("reviewed",False)) and bool(right.get("reviewed",False)),
                    "provenance":provenance or "opencv",
                }
                used[j]=True
                changed=True
            used[index]=True
            result.append(current)
        pending=result
    return pending


def _detect_slanted_wall_candidates(ink:np.ndarray)->list[dict]:
    h,w=ink.shape[:2]
    min_side=float(max(1,min(h,w)))
    min_length=max(55.0,min_side*0.055)
    max_separation=max(9.0,min(40.0,min_side*0.024))

    edges=cv2.Canny(ink,45,135)
    raw=cv2.HoughLinesP(
        edges,
        1,
        np.pi/360,
        threshold=max(26,int(min_side/30)),
        minLineLength=int(min_length),
        maxLineGap=max(6,int(min_side/110)),
    )
    if raw is None:
        return []

    segments=[]
    for x1,y1,x2,y2 in raw[:,0]:
        dx=float(x2-x1)
        dy=float(y2-y1)
        length=math.hypot(dx,dy)
        if length<min_length:
            continue
        angle=abs(math.degrees(math.atan2(dy,dx)))%180
        acute=min(angle,180-angle)
        # Orthogonal walls are handled by the morphology path; keep only
        # materially slanted segments here.
        if acute<7 or abs(acute-90)<7:
            continue
        segments.append({
            "a":{"x":float(x1),"y":float(y1)},
            "b":{"x":float(x2),"y":float(y2)},
            "widthPx":1.0,
        })

    candidates=[]
    for index,left in enumerate(segments):
        for right in segments[index+1:]:
            candidate=_parallel_pair_candidate(
                left,right,
                min_length=min_length,
                max_separation=max_separation,
                min_overlap_ratio=.68,
                max_angle_deg=3.5,
            )
            if candidate is None:
                continue
            candidate["confidence"]=min(.93,float(candidate["confidence"]))
            candidate["provenance"]="opencv"
            candidates.append(candidate)

    candidates=_merge_near_collinear_candidates(candidates)
    accepted=[]
    for candidate in sorted(
        candidates,
        key=lambda item:(
            -float(item["confidence"]),
            -math.hypot(
                item["b"]["x"]-item["a"]["x"],
                item["b"]["y"]-item["a"]["y"],
            ),
        ),
    ):
        if any(_wall_duplicate(candidate,item) for item in accepted):
            continue
        accepted.append(candidate)
    return accepted


def detect_walls(ink:np.ndarray)->tuple[list[dict],np.ndarray]:
    h,w=ink.shape[:2]
    min_side=max(1,min(h,w))
    # Keep morphology scale sublinear enough for large scanned sheets. The old
    # /45 and /18 thresholds could erase short but real partitions at 4K.
    hk=max(14,min(90,w//70))
    vk=max(14,min(90,h//70))
    horizontal=cv2.morphologyEx(
        ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(hk,1))
    )
    vertical=cv2.morphologyEx(
        ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,vk))
    )
    mask=cv2.bitwise_or(horizontal,vertical)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    conservative_length=max(35,min_side//18)
    raw=cv2.HoughLinesP(
        mask,1,np.pi/180,
        threshold=max(28,min_side//45),
        minLineLength=max(26,min_side//40),
        maxLineGap=max(8,min(24,min_side//250)),
    )
    lines=[]
    if raw is not None:
        for item in raw[:,0]:
            x1,y1,x2,y2=map(int,item)
            dx,dy=abs(x2-x1),abs(y2-y1)
            candidate=None
            if dx>=dy*4:
                y=int(round((y1+y2)/2))
                candidate=(min(x1,x2),y,max(x1,x2),y)
            elif dy>=dx*4:
                x=int(round((x1+x2)/2))
                candidate=(x,min(y1,y2),x,max(y1,y2))
            if candidate is None:
                continue

            length=math.hypot(
                candidate[2]-candidate[0],
                candidate[3]-candidate[1],
            )
            # The extra short-wall pass must have thickness evidence. This
            # suppresses dimension/text strokes while retaining short partitions.
            if length<conservative_length and _estimate_thickness(ink,candidate)<3.0:
                continue
            lines.append(candidate)

    deduped=_collapse_parallel_wall_bands(ink,_merge_axis_lines(lines))
    walls=[]
    for i,(x1,y1,x2,y2) in enumerate(deduped,start=1):
        thickness=round(_estimate_thickness(ink,(x1,y1,x2,y2)),2)
        length=math.hypot(x2-x1,y2-y1)
        confidence=0.80 if length>=conservative_length else 0.74
        walls.append({
            "id":f"wall-{i}",
            "a":{"x":float(x1),"y":float(y1)},
            "b":{"x":float(x2),"y":float(y2)},
            "thicknessPx":thickness,
            "confidence":confidence,
            "reviewed":False,
            "provenance":"opencv",
        })

    slanted=_detect_slanted_wall_candidates(ink)
    existing=[*walls]
    next_index=len(walls)+1
    for candidate in slanted:
        if any(_wall_duplicate(candidate,item) for item in existing):
            continue
        candidate={**candidate,"id":f"wall-{next_index}"}
        next_index+=1
        walls.append(candidate)
        existing.append(candidate)

    return walls,mask


def enrich_walls_with_vector(walls:list[dict],vector_lines:list[dict])->list[dict]:
    if not walls or not vector_lines:
        return walls

    result=[]
    for wall in walls:
        ws,we,wo,wlen,ux,uy=_frame(wall)
        if wlen<=1e-9:
            result.append(wall)
            continue
        nx=-uy
        ny=ux
        best=0.0
        for vector in vector_lines:
            if _angle_difference(wall,vector)>5.0:
                continue
            vax,vay=_point(vector["a"])
            vbx,vby=_point(vector["b"])
            vs=min(vax*ux+vay*uy,vbx*ux+vby*uy)
            ve=max(vax*ux+vay*uy,vbx*ux+vby*uy)
            vo=((vax+vbx)/2)*nx+((vay+vby)/2)*ny
            axis_tol=max(4.0,float(wall.get("thicknessPx",4.0))*1.8)
            axis_distance=abs(vo-wo)
            if axis_distance>axis_tol:
                continue
            shared=max(0.0,min(we,ve)-max(ws,vs))
            overlap_ratio=shared/max(1.0,min(wlen,ve-vs))
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


def _candidate_near_dimension_label(
    candidate:dict,
    labels:list[dict],
    min_side:float,
)->bool:
    if not labels:
        return False
    start,end,offset,length,ux,uy=_frame(candidate)
    if length<=1e-9:
        return False
    nx=-uy
    ny=ux
    thickness=max(2.0,float(candidate.get("thicknessPx",4.0)))
    normal_tolerance=max(18.0,min(min_side*.035,thickness*5.0))
    axial_margin=max(14.0,min(length*.18,min_side*.04))

    for label in labels:
        if str(label.get("kind",""))!="dimension":
            continue
        try:
            confidence=float(label.get("confidence",0.0))
            cx=float(label["center"]["x"])
            cy=float(label["center"]["y"])
        except (KeyError,TypeError,ValueError):
            continue
        if confidence<.55:
            continue
        along=cx*ux+cy*uy
        normal=cx*nx+cy*ny
        if start-axial_margin<=along<=end+axial_margin and abs(normal-offset)<=normal_tolerance:
            return True
    return False


def quarantine_dimension_aligned_walls(
    walls:list[dict],
    labels:list[dict],
    height:int,
    width:int,
)->set[str]:
    """Downgrade thin extracted lines that align with explicit dimension text.

    The wall remains in the canonical model for review, but callers can exclude
    its id from automatic room/opening topology.
    """
    min_side=float(max(1,min(height,width)))
    thin_limit=max(4.5,min(8.0,min_side*.0045))
    quarantined:set[str]=set()
    for wall in walls:
        try:
            thickness=float(wall.get("thicknessPx",4.0))
            wall_id=str(wall.get("id",""))
        except (TypeError,ValueError):
            continue
        if not wall_id or thickness>thin_limit:
            continue
        if not _candidate_near_dimension_label(wall,labels,min_side):
            continue
        wall["confidence"]=min(float(wall.get("confidence",0.0)),0.64)
        quarantined.add(wall_id)
    return quarantined


def add_vector_wall_candidates(
    walls:list[dict],
    vector_lines:list[dict],
    height:int,
    width:int,
    labels:list[dict]|None=None,
)->list[dict]:
    """Add wall centerlines from native PDF vectors at any angle.

    Close parallel vector pairs are preferred. A single vector is promoted only
    when it is unusually thick and long, which keeps ordinary dimension and guide
    strokes out of the canonical wall model.
    """
    if not vector_lines:
        return walls

    min_side=float(max(1,min(height,width)))
    min_length=max(45.0,min_side*0.04)
    max_separation=max(10.0,min(42.0,min_side*0.025))

    widths=[
        max(0.1,float(line.get("widthPx",1.0)))
        for line in vector_lines
        if math.isfinite(float(line.get("widthPx",1.0)))
    ]
    median_stroke=float(np.median(widths)) if widths else 1.0
    thick_stroke_threshold=max(7.0,min_side*0.0035)
    candidates=[]

    for vector in vector_lines:
        *_,length,_,_=_segment_geometry(vector)
        stroke=max(0.1,float(vector.get("widthPx",1.0)))
        unusually_thick=stroke>=thick_stroke_threshold and (
            median_stroke>=thick_stroke_threshold*0.70
            or stroke>=median_stroke*1.8
        )
        if length<min_length*1.35 or not unusually_thick:
            continue
        candidates.append({
            "a":dict(vector["a"]),
            "b":dict(vector["b"]),
            "thicknessPx":round(max(2.0,min(48.0,stroke)),2),
            "confidence":0.91,
            "reviewed":False,
            "provenance":"pdf-vector",
        })

    for index,left in enumerate(vector_lines):
        for right in vector_lines[index+1:]:
            candidate=_parallel_pair_candidate(
                left,right,
                min_length=min_length,
                max_separation=max_separation,
                min_overlap_ratio=.72,
                max_angle_deg=3.0,
            )
            if candidate is None:
                continue
            candidate["provenance"]="pdf-vector"
            candidates.append(candidate)

    result=[dict(wall) for wall in walls]
    candidates=_merge_near_collinear_candidates(candidates)
    for candidate in candidates:
        if _candidate_near_dimension_label(candidate,labels or [],min_side):
            candidate["confidence"]=min(float(candidate.get("confidence",0.0)),0.64)
    accepted=[]
    for candidate in sorted(
        candidates,
        key=lambda item:(
            -float(item["confidence"]),
            -math.hypot(
                item["b"]["x"]-item["a"]["x"],
                item["b"]["y"]-item["a"]["y"],
            ),
        ),
    ):
        if any(_wall_duplicate(candidate,existing) for existing in [*result,*accepted]):
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


def rasterize_wall_mask(
    walls:list[dict],
    height:int,
    width:int,
    base_mask:np.ndarray|None=None,
    min_pdf_vector_confidence:float|None=None,
    excluded_wall_ids:set[str]|None=None,
)->np.ndarray:
    """Build a room-separation barrier from canonical wall centerlines."""
    if base_mask is None:
        mask=np.zeros((height,width),dtype=np.uint8)
    else:
        if base_mask.shape[:2]!=(height,width):
            raise ValueError("WALL_MASK_SHAPE")
        mask=base_mask.copy()

    excluded=excluded_wall_ids or set()
    for wall in walls:
        if str(wall.get("id","")) in excluded:
            continue
        if (
            min_pdf_vector_confidence is not None
            and str(wall.get("provenance",""))=="pdf-vector"
            and float(wall.get("confidence",0.0))<min_pdf_vector_confidence
        ):
            continue
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
