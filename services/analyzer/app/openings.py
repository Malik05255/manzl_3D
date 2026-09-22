from __future__ import annotations

import math
import os

import cv2
import numpy as np


def _point(item:dict)->tuple[float,float]:
    return float(item["x"]),float(item["y"])


def _segment_geometry(item:dict)->tuple[float,float,float,float,float]:
    ax,ay=_point(item["a"])
    bx,by=_point(item["b"])
    dx=bx-ax
    dy=by-ay
    length=math.hypot(dx,dy)
    if length<=1e-9:
        return 0.0,0.0,0.0,0.0,0.0
    ux=dx/length
    uy=dy/length
    if ux<0 or (abs(ux)<1e-9 and uy<0):
        ux=-ux
        uy=-uy
    nx=-uy
    ny=ux
    return length,ux,uy,nx,ny


def _angle_difference(left:dict,right:dict)->float:
    llen,lux,luy,_,_=_segment_geometry(left)
    rlen,rux,ruy,_,_=_segment_geometry(right)
    if llen<=1e-9 or rlen<=1e-9:
        return 180.0
    cosine=max(-1.0,min(1.0,abs(lux*rux+luy*ruy)))
    return math.degrees(math.acos(cosine))


def _projection_interval(item:dict,ux:float,uy:float)->tuple[float,float]:
    ax,ay=_point(item["a"])
    bx,by=_point(item["b"])
    first=ax*ux+ay*uy
    second=bx*ux+by*uy
    return min(first,second),max(first,second)


def _line_offset(item:dict,nx:float,ny:float)->float:
    ax,ay=_point(item["a"])
    bx,by=_point(item["b"])
    return ((ax+bx)/2)*nx+((ay+by)/2)*ny


def _point_from_frame(t:float,offset:float,ux:float,uy:float)->dict:
    nx=-uy
    ny=ux
    return {"x":float(ux*t+nx*offset),"y":float(uy*t+ny*offset)}


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


def _angle_delta_degrees(angle:float,reference:float)->float:
    delta=abs((angle-reference)%180.0)
    return min(delta,180.0-delta)


def _opening_roi(image:np.ndarray,a:dict,b:dict,gap_px:float)->tuple[np.ndarray,int,int]:
    h,w=image.shape[:2]
    cx=(float(a["x"])+float(b["x"]))/2
    cy=(float(a["y"])+float(b["y"]))/2
    radius=max(20,int(round(gap_px*1.05)))
    x1=max(0,int(math.floor(cx-radius)))
    x2=min(w,int(math.ceil(cx+radius)))
    y1=max(0,int(math.floor(cy-radius)))
    y2=min(h,int(math.ceil(cy+radius)))
    return image[y1:y2,x1:x2],x1,y1


def _hough_segments(roi:np.ndarray,gap_px:float)->list[tuple[int,int,int,int]]:
    if roi.size==0:
        return []
    gray=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,55,155)
    raw=cv2.HoughLinesP(
        edges,
        1,
        np.pi/360,
        threshold=max(8,int(gap_px*0.16)),
        minLineLength=max(7,int(gap_px*0.25)),
        maxLineGap=max(3,int(gap_px*0.10)),
    )
    return [] if raw is None else [tuple(map(int,item)) for item in np.asarray(raw).reshape(-1,4)]


def _door_leaf_evidence_details(
    image:np.ndarray,
    a:dict,
    b:dict,
    gap_px:float,
    wall_angle_deg:float,
)->tuple[int,set[str],str,float]:
    roi,offset_x,offset_y=_opening_roi(image,a,b,gap_px)
    evidence=0
    hinges:set[str]=set()
    hinge_tolerance=max(8.0,gap_px*0.28)
    ax,ay=_point(a)
    bx,by=_point(b)
    gap_length=max(1e-9,math.hypot(bx-ax,by-ay))
    ux=(bx-ax)/gap_length
    uy=(by-ay)/gap_length
    nx=-uy
    ny=ux
    accepted=[]
    signed_depths=[]
    for x1,y1,x2,y2 in _hough_segments(roi,gap_px):
        dx=float(x2-x1)
        dy=float(y2-y1)
        length=math.hypot(dx,dy)
        # A door leaf is normally a substantial fraction of the opening width.
        # Short Hough chords cut from a curved swing arc must not count as a
        # second leaf/hinge.
        if length<gap_px*0.45 or length>gap_px*1.75:
            continue
        angle=math.degrees(math.atan2(dy,dx))%180.0
        delta=_angle_delta_degrees(angle,wall_angle_deg)
        if not 18<=delta<=82:
            continue

        endpoints=[
            (float(offset_x+x1),float(offset_y+y1)),
            (float(offset_x+x2),float(offset_y+y2)),
        ]
        distance_a=[math.hypot(px-ax,py-ay) for px,py in endpoints]
        distance_b=[math.hypot(px-bx,py-by) for px,py in endpoints]
        nearest_a=min(distance_a)
        nearest_b=min(distance_b)
        nearest=min(nearest_a,nearest_b)
        if nearest>hinge_tolerance:
            continue
        hinge="a" if nearest_a<=nearest_b else "b"
        hx,hy=(ax,ay) if hinge=="a" else (bx,by)
        far=max(endpoints,key=lambda point:math.hypot(point[0]-hx,point[1]-hy))

        # Hough can return both edges of the same leaf. Collapse near-identical
        # angle/hinge evidence before classifying a double-swing door.
        key=(hinge,round(angle/6.0))
        if key in accepted:
            continue
        accepted.append(key)
        evidence+=1
        hinges.add(hinge)
        signed_depths.append((far[0]-hx)*nx+(far[1]-hy)*ny)

    if not signed_depths:
        return evidence,hinges,"unknown",0.0
    positive=sum(abs(value) for value in signed_depths if value>0)
    negative=sum(abs(value) for value in signed_depths if value<0)
    total=positive+negative
    if total<=1e-9 or abs(positive-negative)/total<.18:
        swing_side="unknown"
    else:
        swing_side="positive" if positive>negative else "negative"
    swing_depth=max(abs(value) for value in signed_depths)
    return evidence,hinges,swing_side,float(swing_depth)


def _door_leaf_evidence(
    image:np.ndarray,
    a:dict,
    b:dict,
    gap_px:float,
    wall_angle_deg:float,
)->int:
    evidence,_,_,_=_door_leaf_evidence_details(image,a,b,gap_px,wall_angle_deg)
    return evidence

def _arc_roi_limit(default:float=640.0)->float:
    try:
        value=float(os.getenv("OPENING_ARC_MAX_ROI",str(default)) or str(default))
    except ValueError:
        value=default
    return max(0.0,min(4096.0,value))


def _door_arc_evidence_details(
    image:np.ndarray,
    a:dict,
    b:dict,
    gap_px:float,
)->tuple[int,set[str],str,float]:
    """Detect a door swing arc whose circle centre sits near a wall-gap hinge."""
    roi,offset_x,offset_y=_opening_roi(image,a,b,gap_px)
    if roi.size==0:
        return 0,set(),"unknown",0.0

    max_roi=_arc_roi_limit()
    roi_h,roi_w=roi.shape[:2]
    max_dim=max(roi_h,roi_w)
    work_scale=(
        min(1.0,max_roi/max(1.0,float(max_dim)))
        if max_roi>0
        else 1.0
    )
    if work_scale<.999:
        work=cv2.resize(
            roi,
            (
                max(1,int(round(roi_w*work_scale))),
                max(1,int(round(roi_h*work_scale))),
            ),
            interpolation=cv2.INTER_AREA,
        )
    else:
        work=roi

    gray=cv2.cvtColor(work,cv2.COLOR_BGR2GRAY)
    blurred=cv2.GaussianBlur(gray,(5,5),1.2)
    scaled_gap=max(1.0,gap_px*work_scale)
    min_radius=max(5,int(round(scaled_gap*.25)))
    max_radius=max(min_radius+2,int(round(scaled_gap*1.60)))
    circles=cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(10.0,scaled_gap*.35),
        param1=120,
        param2=max(12.0,min(24.0,scaled_gap*.20)),
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return 0,set(),"unknown",0.0

    edges=cv2.Canny(gray,55,150)
    edge_y,edge_x=np.nonzero(edges)
    if not len(edge_x):
        return 0,set(),"unknown",0.0

    inverse_scale=1.0/max(work_scale,1e-9)
    ax,ay=_point(a)
    bx,by=_point(b)
    gap_length=max(1e-9,math.hypot(bx-ax,by-ay))
    ux=(bx-ax)/gap_length
    uy=(by-ay)/gap_length
    nx=-uy
    ny=ux
    hinge_tolerance=max(10.0,gap_px*.30)
    ring_tolerance=max(3.0,scaled_gap*.065)
    by_hinge:dict[str,tuple[float,float]]={}

    for raw_cx,raw_cy,raw_radius in circles[0]:
        cx=float(raw_cx)
        cy=float(raw_cy)
        radius=float(raw_radius)
        global_cx=float(offset_x)+cx*inverse_scale
        global_cy=float(offset_y)+cy*inverse_scale
        distance_a=math.hypot(global_cx-ax,global_cy-ay)
        distance_b=math.hypot(global_cx-bx,global_cy-by)
        nearest=min(distance_a,distance_b)
        if nearest>hinge_tolerance:
            continue

        hinge="a" if distance_a<=distance_b else "b"
        hx,hy=(ax,ay) if hinge=="a" else (bx,by)

        radial=np.sqrt(
            (edge_x.astype(np.float32)-cx)**2
            +(edge_y.astype(np.float32)-cy)**2
        )
        selected=np.abs(radial-radius)<=ring_tolerance
        if int(np.count_nonzero(selected))<12:
            continue

        sx=edge_x[selected].astype(np.float32)
        sy=edge_y[selected].astype(np.float32)
        angles=np.arctan2(sy-cy,sx-cx)
        angle_bins=np.floor((angles+math.pi)/(math.pi/18.0)).astype(np.int32)
        coverage=len(np.unique(angle_bins))/36.0
        if coverage<.10 or coverage>.82:
            continue

        global_x=float(offset_x)+sx*inverse_scale
        global_y=float(offset_y)+sy*inverse_scale
        signed=(global_x-hx)*nx+(global_y-hy)*ny
        significant=signed[np.abs(signed)>=gap_px*.10]
        if not len(significant):
            continue

        positive=float(np.sum(np.abs(significant[significant>0])))
        negative=float(np.sum(np.abs(significant[significant<0])))
        signed_depth=float(significant[np.argmax(np.abs(significant))])
        side_balance=abs(positive-negative)/max(1e-9,positive+negative)
        if side_balance<.20:
            continue

        strength=coverage*(1.0-nearest/max(hinge_tolerance,1.0))
        if strength<.04:
            continue
        previous=by_hinge.get(hinge)
        if previous is None or strength>previous[0]:
            by_hinge[hinge]=(strength,signed_depth)

    if not by_hinge:
        return 0,set(),"unknown",0.0

    signed=[item[1] for item in by_hinge.values()]
    positive=sum(abs(value) for value in signed if value>0)
    negative=sum(abs(value) for value in signed if value<0)
    total=positive+negative
    if total<=1e-9 or abs(positive-negative)/total<.18:
        side="unknown"
    else:
        side="positive" if positive>negative else "negative"
    depth=max(abs(value) for value in signed)
    hinges=set(by_hinge)
    return len(hinges),hinges,side,float(depth)

def _door_arc_evidence(image:np.ndarray,a:dict,b:dict,gap_px:float)->int:
    evidence,_,_,_=_door_arc_evidence_details(image,a,b,gap_px)
    return evidence


def _parallel_window_evidence(
    image:np.ndarray,
    a:dict,
    b:dict,
    gap_px:float,
    wall_angle_deg:float,
)->int:
    roi,offset_x,offset_y=_opening_roi(image,a,b,gap_px)
    ax,ay=_point(a)
    bx,by=_point(b)
    vx=bx-ax
    vy=by-ay
    gap_length=max(1e-9,math.hypot(vx,vy))
    ux=vx/gap_length
    uy=vy/gap_length
    gap_start=min(ax*ux+ay*uy,bx*ux+by*uy)
    gap_end=max(ax*ux+ay*uy,bx*ux+by*uy)
    nx=-uy
    ny=ux
    wall_offset=(ax+bx)/2*nx+(ay+by)/2*ny
    max_normal_distance=max(8.0,gap_px*.18)
    offsets=[]
    for x1,y1,x2,y2 in _hough_segments(roi,gap_px):
        gx1=float(offset_x+x1); gy1=float(offset_y+y1)
        gx2=float(offset_x+x2); gy2=float(offset_y+y2)
        dx=gx2-gx1
        dy=gy2-gy1
        length=math.hypot(dx,dy)
        if length<gap_px*0.42:
            continue
        angle=math.degrees(math.atan2(dy,dx))%180.0
        if _angle_delta_degrees(angle,wall_angle_deg)>8:
            continue

        first=gx1*ux+gy1*uy
        second=gx2*ux+gy2*uy
        line_start=min(first,second)
        line_end=max(first,second)
        shared=max(0.0,min(line_end,gap_end)-max(line_start,gap_start))
        # Real glazing traverses a meaningful portion of the actual opening.
        # A nearby annotation underline whose midpoint happens to land inside
        # the gap should not become a window.
        if shared<gap_length*.48:
            continue

        mx=(gx1+gx2)/2
        my=(gy1+gy2)/2
        normal_offset=mx*nx+my*ny
        if abs(normal_offset-wall_offset)>max_normal_distance:
            continue
        offsets.append(normal_offset)

    if not offsets:
        return 0

    # Hough frequently returns both edges of one thick stroke. Count separated
    # glazing centerlines rather than raw Hough segments.
    cluster_distance=max(5.0,gap_px*.04)
    clusters=[]
    for value in sorted(offsets):
        if not clusters or abs(value-clusters[-1][-1])>cluster_distance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return len(clusters)


def _gap_between_walls(
    left:dict,
    right:dict,
    axis_tol:float,
)->tuple[dict,dict,float,float,float,float,float,float]|None:
    if _angle_difference(left,right)>5.0:
        return None
    length,ux,uy,nx,ny=_segment_geometry(left)
    if length<=1e-9:
        return None

    ls,le=_projection_interval(left,ux,uy)
    rs,re=_projection_interval(right,ux,uy)
    lo=_line_offset(left,nx,ny)
    ro=_line_offset(right,nx,ny)
    if abs(lo-ro)>axis_tol:
        return None

    first,second=left,right
    fs,fe=ls,le
    ss,se=rs,re
    fo,so=lo,ro
    if rs<ls:
        first,second=right,left
        fs,fe=rs,re
        ss,se=ls,le
        fo,so=ro,lo

    gap=ss-fe
    if gap<=0:
        return None
    offset=(fo+so)/2
    return first,second,fs,fe,ss,se,gap,offset


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


def _door_subtype_from_evidence(
    leaf_hinges:set[str],
    arc_hinges:set[str],
)->str:
    # Double swing is only trusted when two independently visible leaves are
    # anchored at opposite sides of the opening. Dual arcs without two leaves
    # are too ambiguous on real architectural drawings.
    return "double_swing" if {"a","b"}.issubset(leaf_hinges) else "single_swing"


def detect_doors(
    image:np.ndarray,
    walls:list[dict],
    meters_per_pixel:float|None,
)->list[dict]:
    min_gap,max_gap,axis_tol=_door_gap_limits(image,meters_per_pixel)
    candidates=[]

    for index,left in enumerate(walls):
        length,ux,uy,_,_=_segment_geometry(left)
        if length<=1e-9:
            continue
        wall_angle=math.degrees(math.atan2(uy,ux))%180.0
        for right in walls[index+1:]:
            gap_data=_gap_between_walls(left,right,axis_tol)
            if gap_data is None:
                continue
            first,second,fs,fe,ss,se,gap,offset=gap_data
            if gap<min_gap or gap>max_gap:
                continue
            a=_point_from_frame(fe,offset,ux,uy)
            b=_point_from_frame(ss,offset,ux,uy)

            leaf_evidence,leaf_hinges,leaf_side,leaf_depth=_door_leaf_evidence_details(image,a,b,gap,wall_angle)
            arc_evidence,arc_hinges,arc_side,arc_depth=_door_arc_evidence_details(image,a,b,gap)
            if leaf_evidence<1 and arc_evidence<1:
                continue

            evidence=leaf_evidence+arc_evidence
            # A true double-swing should show two independent leaves or two
            # independent hinge-centred arcs. Mixing one leaf on one side with
            # an unrelated arc on the other side caused excessive double-door
            # classifications on real AEC sheets.
            door_subtype=_door_subtype_from_evidence(leaf_hinges,arc_hinges)
            swing_side=leaf_side if leaf_side!="unknown" else arc_side
            swing_depth=max(leaf_depth,arc_depth)
            confidence=min(
                0.95,
                0.69+0.065*leaf_evidence+0.035*arc_evidence+(0.05 if meters_per_pixel else 0.0),
            )
            if confidence<0.76:
                continue

            first_len=abs(fe-fs)
            second_len=abs(se-ss)
            wall_id=first["id"] if first_len>=second_len else second["id"]
            candidates.append({
                "id":f"door-candidate-{len(candidates)+1}",
                "kind":"door",
                "doorSubtype":door_subtype,
                "doorSwingSide":swing_side,
                "doorSwingDepthPx":round(swing_depth,2) if swing_depth>0 else None,
                "wallId":wall_id,
                "a":a,
                "b":b,
                "confidence":round(confidence,3),
                "reviewed":False,
                "provenance":"opencv",
            })

    result=_dedupe(candidates,max(min_gap*0.6,8.0))
    for index,item in enumerate(result,start=1):
        item["id"]=f"door-{index}"
    return result


def _vector_window_candidates(
    vector_lines:list[dict],
    walls:list[dict],
    image_shape:tuple[int,...],
    meters_per_pixel:float|None,
)->list[dict]:
    """Recover window glazing from native PDF vector linework.

    Real CAD PDFs often preserve several overlapping/parallel glazing strokes
    even when the raster Hough pass cannot see them reliably. Candidate lines
    are bucketed by angle and ordered by projected centre so the search stays
    local instead of comparing every vector line with every other line.
    """
    if not vector_lines or not walls:
        return []

    h,w=image_shape[:2]
    base=float(min(h,w))
    if meters_per_pixel and meters_per_pixel>0:
        min_length=max(18.0,0.35/meters_per_pixel)
        max_length=max(min_length+8.0,3.60/meters_per_pixel)
    else:
        min_length=max(18.0,base*.010)
        max_length=max(min_length+8.0,base*.090)

    features=[]
    buckets:dict[int,list[int]]={}
    bucket_width=5.0
    bucket_count=int(round(180.0/bucket_width))

    for raw in vector_lines:
        try:
            ax,ay=_point(raw["a"])
            bx,by=_point(raw["b"])
            width_px=float(raw.get("widthPx",1.0) or 1.0)
        except (KeyError,TypeError,ValueError):
            continue
        dx=bx-ax
        dy=by-ay
        length=math.hypot(dx,dy)
        if length<min_length or length>max_length:
            continue
        if width_px>8.0:
            continue
        angle=math.degrees(math.atan2(dy,dx))%180.0
        ux=math.cos(math.radians(angle))
        uy=math.sin(math.radians(angle))
        if ux<0 or (abs(ux)<1e-9 and uy<0):
            ux=-ux
            uy=-uy
        nx=-uy
        ny=ux
        t1=ax*ux+ay*uy
        t2=bx*ux+by*uy
        start=min(t1,t2)
        end=max(t1,t2)
        offset=((ax+bx)/2)*nx+((ay+by)/2)*ny
        center=(start+end)/2
        item={
            "a":{"x":ax,"y":ay},"b":{"x":bx,"y":by},
            "length":length,"angle":angle,
            "ux":ux,"uy":uy,"nx":nx,"ny":ny,
            "start":start,"end":end,"offset":offset,"center":center,
            "widthPx":width_px,
        }
        index=len(features)
        features.append(item)
        bucket=int(round(angle/bucket_width))%bucket_count
        buckets.setdefault(bucket,[]).append(index)

    if len(features)<3:
        return []

    for values in buckets.values():
        values.sort(key=lambda idx:features[idx]["center"])

    raw_candidates=[]
    used_keys=set()
    max_center_delta=max_length*.42

    for seed_index,seed in enumerate(features):
        seed_bucket=int(round(seed["angle"]/bucket_width))%bucket_count
        possible=[]
        for bucket in (
            (seed_bucket-1)%bucket_count,
            seed_bucket,
            (seed_bucket+1)%bucket_count,
        ):
            possible.extend(buckets.get(bucket,[]))

        peers=[]
        sux=float(seed["ux"]); suy=float(seed["uy"])
        snx=float(seed["nx"]); sny=float(seed["ny"])
        seed_start=float(seed["start"]); seed_end=float(seed["end"])
        seed_length=float(seed["length"])
        seed_offset=float(seed["offset"])
        seed_center=float(seed["center"])

        for peer_index in possible:
            if peer_index==seed_index:
                continue
            peer=features[peer_index]
            if _angle_delta_degrees(float(peer["angle"]),float(seed["angle"]))>4.0:
                continue
            peer_length=float(peer["length"])
            if min(seed_length,peer_length)/max(seed_length,peer_length)<.64:
                continue

            pax,pay=_point(peer["a"])
            pbx,pby=_point(peer["b"])
            p1=pax*sux+pay*suy
            p2=pbx*sux+pby*suy
            pstart=min(p1,p2); pend=max(p1,p2)
            pcenter=(pstart+pend)/2
            if abs(pcenter-seed_center)>max_center_delta:
                continue
            overlap=max(0.0,min(seed_end,pend)-max(seed_start,pstart))
            if overlap<min(seed_length,peer_length)*.64:
                continue
            poffset=((pax+pbx)/2)*snx+((pay+pby)/2)*sny
            separation=abs(poffset-seed_offset)
            max_separation=min(90.0,max(12.0,min(seed_length,peer_length)*.48))
            if separation>max_separation:
                continue
            peers.append((peer_index,pstart,pend,poffset))

        if len(peers)<2:
            continue

        group=[(seed_index,seed_start,seed_end,seed_offset),*peers]
        starts=[float(item[1]) for item in group]
        ends=[float(item[2]) for item in group]
        offsets=[float(item[3]) for item in group]
        start=float(np.median(np.asarray(starts,dtype=np.float32)))
        end=float(np.median(np.asarray(ends,dtype=np.float32)))
        offset=float(np.median(np.asarray(offsets,dtype=np.float32)))
        span=end-start
        if span<min_length or span>max_length:
            continue

        # Three raw strokes at effectively the same normal offset can be duplicate
        # PDF drawing commands. Require at least two distinct glazing offsets.
        clustered=[]
        for value in sorted(offsets):
            if not clustered or abs(value-clustered[-1][-1])>2.5:
                clustered.append([value])
            else:
                clustered[-1].append(value)
        if len(clustered)<2:
            continue
        normal_span=max(offsets)-min(offsets)
        if normal_span>min(90.0,max(14.0,span*.48)):
            continue

        a=_point_from_frame(start,offset,sux,suy)
        b=_point_from_frame(end,offset,sux,suy)
        cx=(a["x"]+b["x"])/2
        cy=(a["y"]+b["y"])/2

        best=None
        for wall in walls:
            wall_length,wux,wuy,wnx,wny=_segment_geometry(wall)
            if wall_length<=1e-9:
                continue
            wall_angle=math.degrees(math.atan2(wuy,wux))%180.0
            if _angle_delta_degrees(float(seed["angle"]),wall_angle)>6.0:
                continue
            normal_distance=_point_infinite_line_distance({"x":cx,"y":cy},wall)
            tolerance=max(
                18.0,
                float(wall.get("thicknessPx",4.0) or 4.0)*4.5,
                normal_span*1.6,
            )
            if normal_distance>tolerance:
                continue
            wall_start,wall_end=_projection_interval(wall,sux,suy)
            if wall_end<start:
                along_gap=start-wall_end
            elif end<wall_start:
                along_gap=wall_start-end
            else:
                along_gap=0.0
            if along_gap>max(36.0,span*.85):
                continue
            score=normal_distance/max(1.0,tolerance)+along_gap/max(1.0,span)
            if best is None or score<best[0]:
                best=(score,wall)

        if best is None:
            continue

        _,host=best
        key=(
            round(cx/max(8.0,span*.18)),
            round(cy/max(8.0,span*.18)),
            round(float(seed["angle"])/5.0),
        )
        if key in used_keys:
            continue
        used_keys.add(key)
        confidence=min(.94,.80+.025*min(5,len(group)))
        raw_candidates.append({
            "id":f"window-vector-{len(raw_candidates)+1}",
            "kind":"window",
            "wallId":str(host["id"]),
            "a":a,
            "b":b,
            "confidence":round(confidence,3),
            "reviewed":False,
            "provenance":"pdf-vector",
        })

    return raw_candidates


def detect_windows(
    image:np.ndarray,
    walls:list[dict],
    meters_per_pixel:float|None,
    vector_lines:list[dict]|None=None,
)->list[dict]:
    min_gap,max_gap,axis_tol=_window_gap_limits(image,meters_per_pixel)
    candidates=[]

    for index,left in enumerate(walls):
        length,ux,uy,_,_=_segment_geometry(left)
        if length<=1e-9:
            continue
        wall_angle=math.degrees(math.atan2(uy,ux))%180.0
        for right in walls[index+1:]:
            gap_data=_gap_between_walls(left,right,axis_tol)
            if gap_data is None:
                continue
            first,second,fs,fe,ss,se,gap,offset=gap_data
            if gap<min_gap or gap>max_gap:
                continue
            a=_point_from_frame(fe,offset,ux,uy)
            b=_point_from_frame(ss,offset,ux,uy)

            leaf_evidence=_door_leaf_evidence(image,a,b,gap,wall_angle)
            evidence=_parallel_window_evidence(image,a,b,gap,wall_angle)
            if evidence<2:
                continue
            arc_evidence=_door_arc_evidence(image,a,b,gap)
            # Strong glazing evidence can survive one spurious Hough leaf chord
            # when no swing arc exists. Two leaf hits or any real arc remain
            # decisive door evidence.
            if arc_evidence>0 or leaf_evidence>=2:
                continue
            if leaf_evidence==1 and evidence<3:
                continue

            confidence=min(
                0.95,
                0.70+0.055*evidence+(0.04 if meters_per_pixel else 0.0)
                -(0.04 if leaf_evidence==1 else 0.0),
            )
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
                "reviewed":False,
                "provenance":"opencv",
            })

    if vector_lines:
        candidates.extend(
            _vector_window_candidates(
                vector_lines,walls,image.shape,meters_per_pixel,
            )
        )
    result=_dedupe(candidates,max(min_gap*0.55,8.0))
    for index,item in enumerate(result,start=1):
        item["id"]=f"window-{index}"
    return result


def _same_opening_gap(left:dict,right:dict)->bool:
    if _angle_difference(left,right)>8.0:
        return False
    llen,*_=_segment_geometry(left)
    rlen,*_=_segment_geometry(right)
    if llen<=1e-9 or rlen<=1e-9:
        return False
    lcx=(float(left["a"]["x"])+float(left["b"]["x"]))/2
    lcy=(float(left["a"]["y"])+float(left["b"]["y"]))/2
    rcx=(float(right["a"]["x"])+float(right["b"]["x"]))/2
    rcy=(float(right["a"]["y"])+float(right["b"]["y"]))/2
    center_distance=math.hypot(lcx-rcx,lcy-rcy)
    if center_distance>max(8.0,min(llen,rlen)*.28):
        return False
    ratio=min(llen,rlen)/max(llen,rlen)
    return ratio>=.58


def resolve_opening_conflicts(
    doors:list[dict],
    windows:list[dict],
)->tuple[list[dict],list[dict]]:
    """Resolve door/window collisions using geometry plus detector confidence.

    Geometry remains the default source of truth, but a strong AI window may
    correct a weaker OpenCV door classification on the same hosted opening.
    This is important for casement/sliding-window symbols that can look like a
    double-swing door to line/arc heuristics.
    """
    if not doors or not windows:
        return doors,windows

    rejected_doors:set[str]=set()
    rejected_windows:set[str]=set()
    for door in doors:
        for window in windows:
            if not _same_opening_gap(door,window):
                continue
            door_conf=float(door.get("confidence",0.0))
            window_conf=float(window.get("confidence",0.0))
            door_ai=str(door.get("provenance",""))=="ai"
            window_ai=str(window.get("provenance",""))=="ai"

            if window_ai and not door_ai:
                subtype=str(door.get("doorSubtype") or "unknown")
                swing_depth=float(door.get("doorSwingDepthPx") or 0.0)
                # A strong geometric swing still wins close calls. A detector
                # window can override when the geometric door is materially
                # weaker or lacks a convincing swing envelope.
                margin=.14 if subtype in {"single_swing","double_swing"} and swing_depth>12 else .04
                if window_conf>=door_conf+margin:
                    rejected_doors.add(str(door.get("id","")))
                else:
                    rejected_windows.add(str(window.get("id","")))
                continue

            if door_ai and not window_ai:
                if door_conf>=window_conf+.08:
                    rejected_windows.add(str(window.get("id","")))
                else:
                    rejected_doors.add(str(door.get("id","")))
                continue

            # Preserve the geometry-first behavior when both candidates come
            # from the same kind of evidence. AI-vs-geometry arbitration is
            # handled explicitly above.
            rejected_windows.add(str(window.get("id","")))

    kept_doors=[
        item for item in doors
        if str(item.get("id","")) not in rejected_doors
    ]
    kept_windows=[
        item for item in windows
        if str(item.get("id","")) not in rejected_windows
        and not any(
            _same_opening_gap(door,item)
            for door in kept_doors
        )
    ]
    return kept_doors,kept_windows


def _endpoint_distance(wall:dict,point:dict)->float:
    return min(
        math.hypot(
            float(wall["a"]["x"])-float(point["x"]),
            float(wall["a"]["y"])-float(point["y"]),
        ),
        math.hypot(
            float(wall["b"]["x"])-float(point["x"]),
            float(wall["b"]["y"])-float(point["y"]),
        ),
    )


def _point_infinite_line_distance(point:dict,wall:dict)->float:
    ax,ay=_point(wall["a"])
    bx,by=_point(wall["b"])
    px,py=_point(point)
    vx=bx-ax
    vy=by-ay
    length=math.hypot(vx,vy)
    if length<=1e-9:
        return math.hypot(px-ax,py-ay)
    return abs(vy*px-vx*py+bx*ay-by*ax)/length


def _point_line_metrics(point:dict,wall:dict)->tuple[float,float]:
    ax,ay=_point(wall["a"])
    bx,by=_point(wall["b"])
    px,py=_point(point)
    vx=bx-ax
    vy=by-ay
    length_sq=vx*vx+vy*vy
    if length_sq<=1e-9:
        return math.hypot(px-ax,py-ay),0.0
    t=((px-ax)*vx+(py-ay)*vy)/length_sq
    cx=ax+max(0.0,min(1.0,t))*vx
    cy=ay+max(0.0,min(1.0,t))*vy
    return math.hypot(px-cx,py-cy),t


_AI_OPENING_CLASSES={
    "door":("door","unknown"),
    "door2":("door","unknown"),
    "single door":("door","single_swing"),
    "single swing door":("door","single_swing"),
    "double door":("door","double_swing"),
    "double swing door":("door","double_swing"),
    "sliding door":("door","sliding"),
    "window":("window",None),
    "bay window":("window",None),
    "blind window":("window",None),
}


def _normalize_ai_opening_class(value:object)->tuple[str,str|None]|None:
    text=str(value or "").strip().lower().replace("_"," ").replace("-"," ")
    text=" ".join(text.split())
    return _AI_OPENING_CLASSES.get(text)


def _raw_detection_box(item:dict)->tuple[float,float,float,float]|None:
    value=item.get("bbox",item.get("box"))
    if not isinstance(value,(list,tuple)) or len(value)!=4:
        return None
    try:
        x1,y1,x2,y2=map(float,value)
    except (TypeError,ValueError):
        return None
    x1,x2=min(x1,x2),max(x1,x2)
    y1,y2=min(y1,y2),max(y1,y2)
    if x2-x1<4 or y2-y1<4:
        return None
    return x1,y1,x2,y2


def _opening_duplicate(candidate:dict,existing:list[dict])->bool:
    clen,*_=_segment_geometry(candidate)
    ccx=(float(candidate["a"]["x"])+float(candidate["b"]["x"]))/2
    ccy=(float(candidate["a"]["y"])+float(candidate["b"]["y"]))/2
    for item in existing:
        if _same_opening_gap(candidate,item):
            return True
        ilen,*_=_segment_geometry(item)
        icx=(float(item["a"]["x"])+float(item["b"]["x"]))/2
        icy=(float(item["a"]["y"])+float(item["b"]["y"]))/2
        if math.hypot(ccx-icx,ccy-icy)<=max(10.0,min(clen,ilen)*.30):
            return True
    return False


def fuse_ai_opening_detections(
    walls:list[dict],
    doors:list[dict],
    windows:list[dict],
    detections:list[dict],
    *,
    min_confidence:float=.55,
)->tuple[list[dict],list[dict]]:
    """Add ONNX door/window detections only when they can be hosted by a wall.

    Geometry-derived openings keep priority. AI boxes are projected onto the
    nearest canonical wall and are used only as recall fallback.
    """
    result_doors=[dict(item) for item in doors]
    result_windows=[dict(item) for item in windows]
    if not walls or not detections:
        return result_doors,result_windows

    for raw in sorted(
        detections,
        key=lambda item:float(item.get("confidence",0.0)),
        reverse=True,
    ):
        mapped=_normalize_ai_opening_class(
            raw.get("class",raw.get("label",raw.get("name")))
        )
        if mapped is None:
            continue
        kind,subtype=mapped
        try:
            confidence=float(raw.get("confidence",raw.get("score",0.0)))
        except (TypeError,ValueError):
            continue
        if confidence<min_confidence or confidence>1.0:
            continue
        box=_raw_detection_box(raw)
        if box is None:
            continue
        x1,y1,x2,y2=box
        cx=(x1+x2)/2
        cy=(y1+y2)/2
        box_span=max(x2-x1,y2-y1)

        best=None
        for wall in walls:
            length,ux,uy,nx,ny=_segment_geometry(wall)
            if length<=1e-9:
                continue
            distance,t=_point_line_metrics({"x":cx,"y":cy},wall)
            tolerance=max(
                12.0,
                float(wall.get("thicknessPx",4.0))*4.0,
                min(80.0,box_span*.65),
            )
            if distance>tolerance or t<-.12 or t>1.12:
                continue
            score=distance/max(1.0,tolerance)
            if best is None or score<best[0]:
                best=(score,wall,length,ux,uy,nx,ny)
        if best is None:
            continue

        _,wall,length,ux,uy,nx,ny=best
        offset=_line_offset(wall,nx,ny)
        wall_start,wall_end=_projection_interval(wall,ux,uy)
        corners=((x1,y1),(x2,y1),(x2,y2),(x1,y2))
        projections=[x*ux+y*uy for x,y in corners]
        start=max(wall_start,min(projections))
        end=min(wall_end,max(projections))
        if end-start<4:
            continue
        # Prevent a coarse detector box from becoming an implausibly huge
        # opening relative to its host wall.
        if end-start>length*.72:
            center=(start+end)/2
            half=length*.36
            start=max(wall_start,center-half)
            end=min(wall_end,center+half)

        a=_point_from_frame(start,offset,ux,uy)
        b=_point_from_frame(end,offset,ux,uy)
        candidate={
            "id":"",
            "kind":kind,
            "wallId":str(wall["id"]),
            "a":a,
            "b":b,
            "confidence":round(confidence,3),
            "reviewed":False,
            "provenance":"ai",
        }
        if kind=="door":
            normal_depth=max(
                abs(x*nx+y*ny-offset)
                for x,y in corners
            )
            candidate.update({
                "doorSubtype":subtype or "unknown",
                "doorSwingSide":"unknown",
                "doorSwingDepthPx":(
                    round(normal_depth,2)
                    if subtype in {"single_swing","double_swing"} and normal_depth>0
                    else None
                ),
            })
            if _opening_duplicate(candidate,result_doors):
                continue
            candidate["id"]=f"door-ai-{len(result_doors)+1}"
            result_doors.append(candidate)
        else:
            if _opening_duplicate(candidate,result_windows):
                continue
            candidate["id"]=f"window-ai-{len(result_windows)+1}"
            result_windows.append(candidate)

    return resolve_opening_conflicts(result_doors,result_windows)


def normalize_opening_hosts(
    walls:list[dict],
    doors:list[dict],
    windows:list[dict],
)->tuple[list[dict],list[dict],list[dict]]:
    doors,windows=resolve_opening_conflicts(doors,windows)
    openings=[*doors,*windows]
    if not walls or not openings:
        return walls,doors,windows

    by_id={str(wall["id"]):wall for wall in walls}
    parent={wall_id:wall_id for wall_id in by_id}

    def find(value:str)->str:
        root=value
        while parent[root]!=root:
            root=parent[root]
        while parent[value]!=value:
            next_value=parent[value]
            parent[value]=root
            value=next_value
        return root

    def union(left:str,right:str):
        a=find(left)
        b=find(right)
        if a!=b:
            parent[b]=a

    for opening in openings:
        nearby=[]
        for wall in walls:
            if _angle_difference(wall,opening)>6.0:
                continue
            tolerance=max(10.0,float(wall.get("thicknessPx",4.0))*3.0)
            cx=(float(opening["a"]["x"])+float(opening["b"]["x"]))/2
            cy=(float(opening["a"]["y"])+float(opening["b"]["y"]))/2
            distance=_point_infinite_line_distance({"x":cx,"y":cy},wall)
            if distance>tolerance:
                continue
            touches_a=_endpoint_distance(wall,opening["a"])<=tolerance*1.5
            touches_b=_endpoint_distance(wall,opening["b"])<=tolerance*1.5
            if touches_a or touches_b:
                nearby.append(str(wall["id"]))
        if len(nearby)>=2:
            first=nearby[0]
            for other in nearby[1:]:
                union(first,other)

    groups:dict[str,list[dict]]={}
    for wall in walls:
        groups.setdefault(find(str(wall["id"])),[]).append(wall)

    replacement:dict[str,str]={}
    normalized=[]
    for group in groups.values():
        if len(group)==1:
            normalized.append(group[0])
            continue

        canonical=max(
            group,
            key=lambda wall:(math.hypot(
                float(wall["b"]["x"])-float(wall["a"]["x"]),
                float(wall["b"]["y"])-float(wall["a"]["y"]),
            ),str(wall["id"])),
        )
        length,ux,uy,nx,ny=_segment_geometry(canonical)
        if length<=1e-9:
            normalized.extend(group)
            continue

        weighted=[]
        starts=[]
        ends=[]
        for wall in group:
            wall_length,*_=_segment_geometry(wall)
            start,end=_projection_interval(wall,ux,uy)
            offset=_line_offset(wall,nx,ny)
            weighted.append((max(1.0,wall_length),offset,wall))
            starts.append(start)
            ends.append(end)

        total_length=sum(item[0] for item in weighted)
        offset=sum(weight*value for weight,value,_ in weighted)/max(total_length,1.0)
        start=min(starts)
        end=max(ends)
        thickness=sum(
            float(wall.get("thicknessPx",4.0))*weight
            for weight,_,wall in weighted
        )/max(total_length,1.0)
        confidence=sum(
            float(wall.get("confidence",0.0))*weight
            for weight,_,wall in weighted
        )/max(total_length,1.0)
        provenances={wall.get("provenance") for _,_,wall in weighted if wall.get("provenance")}
        provenance=next(iter(provenances)) if len(provenances)==1 else "mixed"
        merged={
            **canonical,
            "a":_point_from_frame(start,offset,ux,uy),
            "b":_point_from_frame(end,offset,ux,uy),
            "thicknessPx":round(thickness,2),
            "confidence":round(max(0.0,min(1.0,confidence)),3),
            "reviewed":all(bool(wall.get("reviewed",False)) for _,_,wall in weighted),
            "provenance":provenance or "opencv",
        }
        normalized.append(merged)
        canonical_id=str(canonical["id"])
        for wall in group:
            replacement[str(wall["id"])]=canonical_id

    normalized_by_id={str(wall["id"]):wall for wall in normalized}
    for opening in openings:
        wall_id=str(opening.get("wallId") or "")
        if wall_id in replacement:
            opening["wallId"]=replacement[wall_id]
            continue

        best=None
        for candidate in normalized_by_id.values():
            if _angle_difference(candidate,opening)>6.0:
                continue
            tolerance=max(10.0,float(candidate.get("thicknessPx",4.0))*3.0)
            cx=(float(opening["a"]["x"])+float(opening["b"]["x"]))/2
            cy=(float(opening["a"]["y"])+float(opening["b"]["y"]))/2
            distance,t=_point_line_metrics({"x":cx,"y":cy},candidate)
            if distance<=tolerance and -.08<=t<=1.08:
                if best is None or distance<best[0]:
                    best=(distance,str(candidate["id"]))
        if best is not None:
            opening["wallId"]=best[1]

    return normalized,doors,windows
