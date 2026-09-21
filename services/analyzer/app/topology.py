from __future__ import annotations

import math

from .models import FloorPlan


def _point(item):
    if isinstance(item,dict):
        return float(item["x"]),float(item["y"])
    return float(item.x),float(item.y)


def _wall_value(wall,name):
    return wall[name] if isinstance(wall,dict) else getattr(wall,name)


def _set_wall_value(wall,name,value):
    if isinstance(wall,dict):
        wall[name]=value
    else:
        setattr(wall,name,value)


def _room_value(room,name):
    return room[name] if isinstance(room,dict) else getattr(room,name)


def _edge_wall_score(a,b,wall)->float:
    ax,ay=_point(a); bx,by=_point(b)
    wa=_wall_value(wall,"a"); wb=_wall_value(wall,"b")
    wx1,wy1=_point(wa); wx2,wy2=_point(wb)
    evx=bx-ax; evy=by-ay
    wvx=wx2-wx1; wvy=wy2-wy1
    el=math.hypot(evx,evy); wl=math.hypot(wvx,wvy)
    if el<4 or wl<4:
        return 0.0

    cosine=abs((evx*wvx+evy*wvy)/(el*wl))
    if cosine<0.985:
        return 0.0

    ux=wvx/wl; uy=wvy/wl
    mx=(ax+bx)/2; my=(ay+by)/2
    perpendicular=abs((mx-wx1)*uy-(my-wy1)*ux)
    thickness=float(_wall_value(wall,"thicknessPx"))
    tolerance=max(10.0,min(42.0,thickness*3.5))
    if perpendicular>tolerance:
        return 0.0

    p1=(ax-wx1)*ux+(ay-wy1)*uy
    p2=(bx-wx1)*ux+(by-wy1)*uy
    edge_start=min(p1,p2); edge_end=max(p1,p2)
    shared=max(0.0,min(edge_end,wl)-max(edge_start,0.0))
    minimum=max(18.0,min(el,wl)*0.28)
    if shared<minimum:
        return 0.0

    overlap_score=min(1.0,shared/max(1.0,min(el,wl)))
    distance_score=max(0.0,1.0-perpendicular/max(tolerance,1.0))
    return overlap_score*0.72+distance_score*0.28


def room_boundary_coverage(room,walls:list)->float:
    polygon=_room_value(room,"polygon")
    if len(polygon)<3:
        return 0.0
    total=0.0
    matched=0.0
    for index,point in enumerate(polygon):
        other=polygon[(index+1)%len(polygon)]
        ax,ay=_point(point); bx,by=_point(other)
        length=math.hypot(bx-ax,by-ay)
        if length<=1e-6:
            continue
        total+=length
        if any(_edge_wall_score(point,other,wall)>=0.34 for wall in walls):
            matched+=length
    if total<=1e-6:
        return 0.0
    return max(0.0,min(1.0,matched/total))


def link_room_boundaries(rooms:list,walls:list)->list:
    for room in rooms:
        polygon=_room_value(room,"polygon")
        scored=[]
        for wall in walls:
            best=0.0
            for index,point in enumerate(polygon):
                other=polygon[(index+1)%len(polygon)]
                best=max(best,_edge_wall_score(point,other,wall))
            if best>=0.34:
                scored.append((best,str(_wall_value(wall,"id"))))
        ids=[wall_id for _,wall_id in sorted(scored,key=lambda item:(-item[0],item[1]))]
        if isinstance(room,dict):
            room["boundaryWallIds"]=ids
        else:
            room.boundaryWallIds=ids
    return rooms


def relink_plan_boundaries(plan:FloorPlan)->FloorPlan:
    link_room_boundaries(plan.rooms,plan.walls)
    return plan


def classify_wall_roles(walls:list,rooms:list)->list:
    if not walls:
        return walls

    references={str(_wall_value(wall,"id")):0 for wall in walls}
    all_points=[]
    for room in rooms:
        all_points.extend(_room_value(room,"polygon"))
        for wall_id in (_room_value(room,"boundaryWallIds") if not isinstance(room,dict) else room.get("boundaryWallIds",[])):
            if wall_id in references:
                references[wall_id]+=1

    if not all_points:
        for wall in walls:
            _set_wall_value(wall,"role","unknown")
            _set_wall_value(wall,"locked",False)
        return walls

    xs=[_point(point)[0] for point in all_points]
    ys=[_point(point)[1] for point in all_points]
    min_x,max_x=min(xs),max(xs)
    min_y,max_y=min(ys),max(ys)

    for wall in walls:
        wall_id=str(_wall_value(wall,"id"))
        count=references.get(wall_id,0)
        if count>=2:
            _set_wall_value(wall,"role","interior")
            _set_wall_value(wall,"locked",False)
            continue

        ax,ay=_point(_wall_value(wall,"a"))
        bx,by=_point(_wall_value(wall,"b"))
        vertical=abs(ax-bx)<=abs(ay-by)
        axis=(ax+bx)/2 if vertical else (ay+by)/2
        thickness=float(_wall_value(wall,"thicknessPx"))
        tolerance=max(16.0,min(48.0,thickness*4.0))
        on_envelope=(
            (vertical and (abs(axis-min_x)<=tolerance or abs(axis-max_x)<=tolerance))
            or ((not vertical) and (abs(axis-min_y)<=tolerance or abs(axis-max_y)<=tolerance))
        )
        if count==1 and on_envelope:
            _set_wall_value(wall,"role","exterior")
            _set_wall_value(wall,"locked",True)
        else:
            _set_wall_value(wall,"role","unknown")
            _set_wall_value(wall,"locked",False)
    return walls


def _polygon_area_px2(points)->float:
    if len(points)<3:
        return 0.0
    total=0.0
    for index,point in enumerate(points):
        other=points[(index+1)%len(points)]
        ax,ay=_point(point)
        bx,by=_point(other)
        total+=ax*by-bx*ay
    return abs(total)/2.0


def canonicalize_plan(plan:FloorPlan)->FloorPlan:
    """Refresh derived topology without rewriting user-authored geometry."""
    candidate=plan.model_copy(deep=True)
    relink_plan_boundaries(candidate)

    if candidate.metersPerPixel and candidate.metersPerPixel>0:
        factor=candidate.metersPerPixel**2
        for room in candidate.rooms:
            room.areaM2=round(_polygon_area_px2(room.polygon)*factor,2)

    valid_wall_ids={wall.id for wall in candidate.walls}
    valid_label_ids={label.id for label in candidate.labels}
    for room in candidate.rooms:
        room.boundaryWallIds=[wall_id for wall_id in room.boundaryWallIds if wall_id in valid_wall_ids]
    for dimension in candidate.dimensions:
        if dimension.referenceWallId and dimension.referenceWallId not in valid_wall_ids:
            dimension.referenceWallId=None
            dimension.orientation="unknown"
        if dimension.sourceLabelId and dimension.sourceLabelId not in valid_label_ids:
            dimension.sourceLabelId=None

    return candidate
