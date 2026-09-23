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
        all_scored=[]
        for wall in walls:
            best=0.0
            for index,point in enumerate(polygon):
                other=polygon[(index+1)%len(polygon)]
                best=max(best,_edge_wall_score(point,other,wall))
            if best>0:
                all_scored.append((best,str(_wall_value(wall,"id"))))

        scored=[item for item in all_scored if item[0]>=0.34]

        # V3 room masks represent the inner face of a wall while canonical
        # wall lines represent its centreline. At acute/slanted corners the
        # polygon approximation can reduce the strict overlap score on one or
        # two real boundary walls. If an otherwise valid enclosure links to
        # fewer than three walls, recover only the strongest nearby candidates
        # from a lower-confidence band. This is deliberately bounded so an
        # interior wall cannot cause an unbounded topology fan-out.
        if len(scored)<3 and len(polygon)>=3:
            seen={wall_id for _,wall_id in scored}
            fallback=[
                item for item in sorted(all_scored,key=lambda item:(-item[0],item[1]))
                if item[1] not in seen and item[0]>=0.14
            ]
            needed=max(0,3-len(scored))
            scored.extend(fallback[:needed])

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

    def convex_hull(points):
        unique=sorted(set((_point(point) for point in points)))
        if len(unique)<=2:
            return unique

        def cross(origin,a,b):
            return (a[0]-origin[0])*(b[1]-origin[1])-(a[1]-origin[1])*(b[0]-origin[0])

        lower=[]
        for point in unique:
            while len(lower)>=2 and cross(lower[-2],lower[-1],point)<=0:
                lower.pop()
            lower.append(point)
        upper=[]
        for point in reversed(unique):
            while len(upper)>=2 and cross(upper[-2],upper[-1],point)<=0:
                upper.pop()
            upper.append(point)
        return lower[:-1]+upper[:-1]

    hull=convex_hull(all_points)

    def on_outer_hull(wall):
        if len(hull)<2:
            return False
        for index,a in enumerate(hull):
            b=hull[(index+1)%len(hull)]
            edge_a={"x":a[0],"y":a[1]}
            edge_b={"x":b[0],"y":b[1]}
            if _edge_wall_score(edge_a,edge_b,wall)>=0.30:
                return True
        return False

    for wall in walls:
        wall_id=str(_wall_value(wall,"id"))
        count=references.get(wall_id,0)
        if count>=2:
            _set_wall_value(wall,"role","interior")
            _set_wall_value(wall,"locked",False)
            continue

        if count==1 and on_outer_hull(wall):
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


def _point_in_polygon_xy(x:float,y:float,polygon)->bool:
    points=[_point(point) for point in polygon]
    if len(points)<3:
        return False
    inside=False
    previous=points[-1]
    for current in points:
        x1,y1=previous
        x2,y2=current
        # Treat points on an edge as inside.
        dx=x2-x1; dy=y2-y1
        length_sq=dx*dx+dy*dy
        if length_sq>1e-9:
            t=((x-x1)*dx+(y-y1)*dy)/length_sq
            if -1e-6<=t<=1+1e-6:
                px=x1+max(0.0,min(1.0,t))*dx
                py=y1+max(0.0,min(1.0,t))*dy
                if math.hypot(x-px,y-py)<=1.5:
                    return True
        if ((y1>y)!=(y2>y)):
            crossing=x1+(y-y1)*(x2-x1)/max(1e-12,(y2-y1))
            if crossing>=x:
                inside=not inside
        previous=current
    return inside


def _polygon_nested_inside(inner,outer)->bool:
    inner_points=[_point(point) for point in inner]
    if len(inner_points)<3:
        return False
    return all(_point_in_polygon_xy(x,y,outer) for x,y in inner_points)


def filter_nonarchitectural_enclosures(
    rooms:list,
    walls:list,
    width:int,
    height:int,
)->list:
    """Drop tiny unlabeled enclosures bounded only by furniture-thin strokes.

    The rule is deliberately relative to the drawing's own wall thickness so it
    remains scale-independent. Named spaces and reviewed rooms are never removed.
    """
    if not rooms or not walls:
        return rooms
    wall_by_id={
        str(_wall_value(wall,"id")):wall
        for wall in walls
    }
    architectural_thicknesses=sorted(
        float(_wall_value(wall,"thicknessPx"))
        for wall in walls
        if float(_wall_value(wall,"confidence") or 0.0)>=.70
        and float(_wall_value(wall,"thicknessPx"))>0
    )
    if not architectural_thicknesses:
        return rooms
    median=architectural_thicknesses[len(architectural_thicknesses)//2]
    if median<5.0:
        return rooms

    page_area=max(1.0,float(width)*float(height))
    room_areas={
        id(room):_polygon_area_px2(_room_value(room,"polygon"))
        for room in rooms
    }
    kept=[]
    for room in rooms:
        name=str(_room_value(room,"name") or "").strip()
        generated=(
            name.startswith("غرفة ")
            and name.removeprefix("غرفة ").strip().isdigit()
        )
        reviewed=bool(
            room.get("reviewed",False)
            if isinstance(room,dict)
            else room.reviewed
        )
        ids=(
            room.get("boundaryWallIds",[])
            if isinstance(room,dict)
            else room.boundaryWallIds
        )
        boundaries=[
            wall_by_id[wall_id]
            for wall_id in ids
            if wall_id in wall_by_id
        ]
        if not generated or reviewed:
            kept.append(room)
            continue

        room_polygon=_room_value(room,"polygon")
        room_area=room_areas[id(room)]
        nested_in_larger=any(
            other is not room
            and room_areas[id(other)]>=room_area*1.8
            and _polygon_nested_inside(
                room_polygon,
                _room_value(other,"polygon"),
            )
            for other in rooms
        )
        # Free-space connected components around closed furniture often produce
        # a large room contour that ignores the furniture hole plus a second
        # tiny contour inside that hole. A legitimate architectural room should
        # not be geometrically contained by another detected room. Named rooms
        # were already protected above.
        if nested_in_larger:
            continue

        if len(boundaries)<2:
            kept.append(room)
            continue

        area_ratio=room_area/page_area
        boundary_thicknesses=sorted(
            float(_wall_value(wall,"thicknessPx"))
            for wall in boundaries
        )
        boundary_median=boundary_thicknesses[len(boundary_thicknesses)//2]
        coverage=room_boundary_coverage(room,walls)
        furniture_thin=(
            boundary_median<=max(4.5,median*.34)
            and max(boundary_thicknesses)<=max(6.5,median*.48)
        )
        # Thin furniture rectangles often get only two canonical wall links
        # after Hough deduplication even though the raster barrier closes the
        # contour. Keep named/reviewed spaces, but reject a small unlabeled
        # enclosure when the available boundary evidence is consistently much
        # thinner than the drawing's architectural walls.
        min_coverage=.48 if len(boundaries)==2 else .68
        if area_ratio<.018 and coverage>=min_coverage and furniture_thin:
            continue
        kept.append(room)
    return kept


def recalibrate_extracted_room_confidence(
    rooms:list,
    walls:list,
    width:int,
    height:int,
)->list:
    """Lower confidence for small unlabeled enclosures supported only by PDF vectors.

    These shapes are retained for review rather than deleted because they can be
    closets, shafts or other legitimate small spaces.
    """
    wall_by_id={
        str(_wall_value(wall,"id")):wall
        for wall in walls
    }
    page_area=max(1.0,float(width)*float(height))

    for room in rooms:
        polygon=_room_value(room,"polygon")
        area_ratio=_polygon_area_px2(polygon)/page_area
        ids=(
            room.get("boundaryWallIds",[])
            if isinstance(room,dict)
            else room.boundaryWallIds
        )
        boundaries=[
            wall_by_id[wall_id]
            for wall_id in ids
            if wall_id in wall_by_id
        ]
        name=str(_room_value(room,"name") or "").strip()
        generated_name=(
            name.startswith("غرفة ")
            and name.removeprefix("غرفة ").strip().isdigit()
        )
        vector_only=bool(boundaries) and all(
            str(_wall_value(wall,"provenance") or "")=="pdf-vector"
            for wall in boundaries
        )
        coverage=room_boundary_coverage(room,walls)
        current=float(_room_value(room,"confidence"))

        if (
            generated_name
            and vector_only
            and area_ratio<0.012
            and coverage>=0.65
        ):
            adjusted=min(current,max(0.45,0.50+coverage*0.12))
            if isinstance(room,dict):
                room["confidence"]=round(adjusted,3)
            else:
                room.confidence=round(adjusted,3)
        elif coverage>=0.88 and current<0.94:
            adjusted=min(0.94,current+0.025)
            if isinstance(room,dict):
                room["confidence"]=round(adjusted,3)
            else:
                room.confidence=round(adjusted,3)

    return rooms


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
