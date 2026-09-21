from __future__ import annotations

import math

from .edit_geometry import bbox,is_rectangular_room,minimum_clear_span_m
from .models import FloorPlan,Point,ValidationFinding,ValidationReport


def _rect_overlap_area(a,b)->float:
    ax1,ay1,ax2,ay2=bbox(a)
    bx1,by1,bx2,by2=bbox(b)
    return max(0.0,min(ax2,bx2)-max(ax1,bx1))*max(0.0,min(ay2,by2)-max(ay1,by1))


def _polygon_area_px2(points:list[Point])->float:
    if len(points)<3:
        return 0.0
    total=0.0
    for index,point in enumerate(points):
        other=points[(index+1)%len(points)]
        total+=point.x*other.y-other.x*point.y
    return abs(total)/2.0


def _point_segment_metrics(point:Point,a:Point,b:Point)->tuple[float,float]:
    vx=b.x-a.x
    vy=b.y-a.y
    length_sq=vx*vx+vy*vy
    if length_sq<=1e-9:
        return math.hypot(point.x-a.x,point.y-a.y),0.0
    t=((point.x-a.x)*vx+(point.y-a.y)*vy)/length_sq
    clamped=max(0.0,min(1.0,t))
    cx=a.x+clamped*vx
    cy=a.y+clamped*vy
    return math.hypot(point.x-cx,point.y-cy),t


def _opening_interval(opening,wall)->tuple[float,float]:
    vx=wall.b.x-wall.a.x
    vy=wall.b.y-wall.a.y
    length=math.hypot(vx,vy)
    if length<=1e-9:
        return 0.0,0.0
    ux=vx/length
    uy=vy/length
    def project(point):
        return (point.x-wall.a.x)*ux+(point.y-wall.a.y)*uy
    first=project(opening.a)
    second=project(opening.b)
    return min(first,second),max(first,second)


def validate_plan(plan:FloorPlan)->ValidationReport:
    findings:list[ValidationFinding]=[]
    mpp=plan.metersPerPixel

    if not mpp or mpp<=0:
        findings.append(ValidationFinding(
            code="scale_missing",
            severity="warning",
            text="مقياس المخطط غير مثبت؛ لا يمكن التحقق من الأبعاد بالمتر.",
            roomIds=[],
        ))

    for wall in plan.walls:
        length_px=math.hypot(wall.b.x-wall.a.x,wall.b.y-wall.a.y)
        if length_px<2:
            findings.append(ValidationFinding(
                code="wall_collapsed",
                severity="critical",
                text="يوجد جدار منهار هندسيًا ويحتاج تصحيحًا قبل الحفظ.",
                wallIds=[wall.id],
            ))
            continue

        outside=any((
            wall.a.x<-2,wall.a.y<-2,wall.b.x<-2,wall.b.y<-2,
            wall.a.x>plan.widthPx+2,wall.b.x>plan.widthPx+2,
            wall.a.y>plan.heightPx+2,wall.b.y>plan.heightPx+2,
        ))
        if outside:
            findings.append(ValidationFinding(
                code="wall_outside_canvas",
                severity="warning",
                text="يوجد جدار يتجاوز حدود صفحة المخطط.",
                wallIds=[wall.id],
            ))

        if mpp and mpp>0:
            length_m=length_px*mpp
            thickness_m=wall.thicknessPx*mpp
            if length_m<0.15:
                findings.append(ValidationFinding(
                    code="wall_too_short",
                    severity="warning",
                    text=f"طول جدار يقارب {length_m:.2f} م ويحتاج مراجعة.",
                    wallIds=[wall.id],
                ))
            if thickness_m<0.04 or thickness_m>0.80:
                findings.append(ValidationFinding(
                    code="wall_thickness_suspicious",
                    severity="warning",
                    text=f"سماكة جدار تقارب {thickness_m*100:.1f} سم وتحتاج مراجعة.",
                    wallIds=[wall.id],
                ))

    for room in plan.rooms:
        if len(room.polygon)<4:
            findings.append(ValidationFinding(
                code="room_geometry_invalid",
                severity="critical",
                text=f"هندسة {room.name} غير مكتملة.",
                roomIds=[room.id],
            ))
            continue

        x1,y1,x2,y2=bbox(room)
        width_px=max(0.0,x2-x1)
        height_px=max(0.0,y2-y1)
        if width_px<2 or height_px<2:
            findings.append(ValidationFinding(
                code="room_collapsed",
                severity="critical",
                text=f"{room.name} انهارت إلى مساحة غير قابلة للاستخدام.",
                roomIds=[room.id],
            ))
            continue

        if x1<-2 or y1<-2 or x2>plan.widthPx+2 or y2>plan.heightPx+2:
            findings.append(ValidationFinding(
                code="room_outside_canvas",
                severity="warning",
                text=f"{room.name} تتجاوز حدود صفحة المخطط.",
                roomIds=[room.id],
            ))

        if mpp and mpp>0:
            width=width_px*mpp
            height=height_px*mpp
            minimum=minimum_clear_span_m(room)
            if min(width,height)<minimum:
                findings.append(ValidationFinding(
                    code="room_clear_span_low",
                    severity="warning",
                    text=f"أحد أبعاد {room.name} أقل من {minimum:g} م المقترحة للاستخدام المريح.",
                    roomIds=[room.id],
                ))

            calculated_area=_polygon_area_px2(room.polygon)*(mpp**2)
            if room.areaM2 is not None:
                difference=abs(calculated_area-room.areaM2)
                relative=difference/max(calculated_area,room.areaM2,0.01)
                if difference>0.50 and relative>0.12:
                    findings.append(ValidationFinding(
                        code="room_area_mismatch",
                        severity="warning",
                        text=f"مساحة {room.name} المسجلة لا تطابق هندستها الحالية وتحتاج إعادة حساب.",
                        roomIds=[room.id],
                    ))

    if mpp and mpp>0:
        rectangular=[room for room in plan.rooms if is_rectangular_room(room)]
        for index,left in enumerate(rectangular):
            for right in rectangular[index+1:]:
                overlap_px2=_rect_overlap_area(left,right)
                overlap_m2=overlap_px2*(mpp**2)
                if overlap_m2>0.08:
                    findings.append(ValidationFinding(
                        code="rooms_overlap",
                        severity="critical",
                        text=f"يوجد تداخل هندسي بين {left.name} و{right.name} بمساحة تقارب {overlap_m2:.2f} م².",
                        roomIds=[left.id,right.id],
                    ))

    walls_by_id={wall.id:wall for wall in plan.walls}
    openings=[*plan.doors,*plan.windows]
    for opening in openings:
        wall=walls_by_id.get(opening.wallId) if opening.wallId else None
        if opening.wallId and wall is None:
            findings.append(ValidationFinding(
                code="opening_orphaned",
                severity="warning",
                text=f"يوجد {('باب' if opening.kind=='door' else 'نافذة')} غير مرتبط بجدار صالح.",
                openingIds=[opening.id],
            ))

        if wall is not None:
            distance_a,t_a=_point_segment_metrics(opening.a,wall.a,wall.b)
            distance_b,t_b=_point_segment_metrics(opening.b,wall.a,wall.b)
            tolerance_px=max(
                wall.thicknessPx*1.5,
                (0.08/mpp) if mpp and mpp>0 else 8.0,
            )
            if max(distance_a,distance_b)>tolerance_px:
                findings.append(ValidationFinding(
                    code="opening_detached",
                    severity="warning",
                    text=f"يوجد {('باب' if opening.kind=='door' else 'نافذة')} مبتعد عن الجدار المرتبط به.",
                    wallIds=[wall.id],
                    openingIds=[opening.id],
                ))
            if min(t_a,t_b)<-0.03 or max(t_a,t_b)>1.03:
                findings.append(ValidationFinding(
                    code="opening_outside_wall",
                    severity="warning",
                    text=f"يوجد {('باب' if opening.kind=='door' else 'نافذة')} يتجاوز نهاية الجدار.",
                    wallIds=[wall.id],
                    openingIds=[opening.id],
                ))

        if mpp and mpp>0:
            dx=opening.b.x-opening.a.x
            dy=opening.b.y-opening.a.y
            width=math.hypot(dx,dy)*mpp
            if opening.kind=="door":
                if width<0.60:
                    findings.append(ValidationFinding(
                        code="door_too_narrow",
                        severity="warning",
                        text=f"عرض باب مكتشف يقارب {width:.2f} م ويحتاج مراجعة.",
                        openingIds=[opening.id],
                        wallIds=[opening.wallId] if opening.wallId else [],
                    ))
                elif width>2.40:
                    findings.append(ValidationFinding(
                        code="door_too_wide",
                        severity="warning",
                        text=f"فتحة باب مكتشفة بعرض {width:.2f} م؛ تحقق من صحة القراءة.",
                        openingIds=[opening.id],
                        wallIds=[opening.wallId] if opening.wallId else [],
                    ))
            elif width<0.30 or width>5.00:
                findings.append(ValidationFinding(
                    code="window_width_suspicious",
                    severity="warning",
                    text=f"عرض نافذة مكتشفة يقارب {width:.2f} م ويحتاج مراجعة.",
                    openingIds=[opening.id],
                    wallIds=[opening.wallId] if opening.wallId else [],
                ))

    by_wall:dict[str,list]= {}
    for opening in openings:
        if opening.wallId and opening.wallId in walls_by_id:
            by_wall.setdefault(opening.wallId,[]).append(opening)
    for wall_id,items in by_wall.items():
        wall=walls_by_id[wall_id]
        intervals=[(opening,*_opening_interval(opening,wall)) for opening in items]
        intervals.sort(key=lambda item:item[1])
        for index,left in enumerate(intervals):
            for right in intervals[index+1:]:
                overlap_px=max(0.0,min(left[2],right[2])-max(left[1],right[1]))
                threshold_px=(0.08/mpp) if mpp and mpp>0 else 8.0
                if overlap_px>threshold_px:
                    findings.append(ValidationFinding(
                        code="openings_overlap",
                        severity="warning",
                        text="يوجد تداخل بين فتحتين على الجدار نفسه.",
                        wallIds=[wall_id],
                        openingIds=[left[0].id,right[0].id],
                    ))

    weights={"critical":0.28,"warning":0.07,"info":0.02}
    penalty=sum(weights[item.severity] for item in findings)
    score=max(0.0,min(1.0,1.0-penalty))
    return ValidationReport(score=round(score,3),findings=findings)
