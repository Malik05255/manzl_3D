from __future__ import annotations

import math

from .models import FloorPlan


def _point(item):
    if isinstance(item,dict):
        return float(item["x"]),float(item["y"])
    return float(item.x),float(item.y)


def _wall_value(wall,name):
    return wall[name] if isinstance(wall,dict) else getattr(wall,name)


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
