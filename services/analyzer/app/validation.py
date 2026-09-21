from __future__ import annotations

from .edit_geometry import bbox,is_rectangular_room,minimum_clear_span_m
from .models import FloorPlan,ValidationFinding,ValidationReport


def _rect_overlap_area(a,b)->float:
    ax1,ay1,ax2,ay2=bbox(a)
    bx1,by1,bx2,by2=bbox(b)
    return max(0.0,min(ax2,bx2)-max(ax1,bx1))*max(0.0,min(ay2,by2)-max(ay1,by1))


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

    wall_ids={wall.id for wall in plan.walls}
    for opening in [*plan.doors,*plan.windows]:
        if opening.wallId and opening.wallId not in wall_ids:
            findings.append(ValidationFinding(
                code="opening_orphaned",
                severity="warning",
                text=f"يوجد {('باب' if opening.kind=='door' else 'نافذة')} غير مرتبط بجدار صالح.",
                roomIds=[],
            ))
        if mpp and mpp>0 and opening.kind=="door":
            dx=opening.b.x-opening.a.x
            dy=opening.b.y-opening.a.y
            width=(dx*dx+dy*dy)**0.5*mpp
            if width<0.60:
                findings.append(ValidationFinding(
                    code="door_too_narrow",
                    severity="warning",
                    text=f"عرض باب مكتشف يقارب {width:.2f} م ويحتاج مراجعة.",
                    roomIds=[],
                ))
            elif width>2.40:
                findings.append(ValidationFinding(
                    code="door_too_wide",
                    severity="warning",
                    text=f"فتحة باب مكتشفة بعرض {width:.2f} م؛ تحقق من صحة القراءة.",
                    roomIds=[],
                ))

    weights={"critical":0.28,"warning":0.07,"info":0.02}
    penalty=sum(weights[item.severity] for item in findings)
    score=max(0.0,min(1.0,1.0-penalty))
    return ValidationReport(score=round(score,3),findings=findings)
