from __future__ import annotations

import cv2
import numpy as np

from .models import FloorPlan,Impact,Proposal,ProposalResponse,Room
from .rooms import detect_rooms
from .topology import canonicalize_plan
from .validation import introduced_critical_findings,validate_plan
from .walls import rasterize_wall_mask


def _points(room)->list[tuple[float,float]]:
    return [(float(point.x),float(point.y)) for point in room.polygon]


def _overlap_ratio(left:list[tuple[float,float]],right:list[tuple[float,float]],max_side:int=640)->float:
    if len(left)<3 or len(right)<3:
        return 0.0
    xs=[p[0] for p in left]+[p[0] for p in right]
    ys=[p[1] for p in left]+[p[1] for p in right]
    x1,x2=min(xs),max(xs)
    y1,y2=min(ys),max(ys)
    width=max(1.0,x2-x1)
    height=max(1.0,y2-y1)
    scale=min(1.0,max_side/max(width,height))
    w=max(4,int(np.ceil(width*scale))+4)
    h=max(4,int(np.ceil(height*scale))+4)

    def contour(points:list[tuple[float,float]])->np.ndarray:
        return np.array([
            [int(round((x-x1)*scale))+2,int(round((y-y1)*scale))+2]
            for x,y in points
        ],dtype=np.int32).reshape((-1,1,2))

    a=np.zeros((h,w),dtype=np.uint8)
    b=np.zeros((h,w),dtype=np.uint8)
    cv2.fillPoly(a,[contour(left)],255)
    cv2.fillPoly(b,[contour(right)],255)
    area_a=float(cv2.countNonZero(a))
    area_b=float(cv2.countNonZero(b))
    if min(area_a,area_b)<=0:
        return 0.0
    intersection=float(cv2.countNonZero(cv2.bitwise_and(a,b)))
    return intersection/min(area_a,area_b)


def _room_labels(plan:FloorPlan)->list[dict]:
    return [
        {
            "id":label.id,
            "text":label.text,
            "center":{"x":label.center.x,"y":label.center.y},
            "confidence":label.confidence,
            "kind":label.kind,
            "reviewed":label.reviewed,
            "provenance":label.provenance,
        }
        for label in plan.labels
    ]


def _wall_dicts(plan:FloorPlan)->list[dict]:
    return [
        {
            "id":wall.id,
            "a":{"x":wall.a.x,"y":wall.a.y},
            "b":{"x":wall.b.x,"y":wall.b.y},
            "thicknessPx":wall.thicknessPx,
            "confidence":wall.confidence,
            "reviewed":wall.reviewed,
            "provenance":wall.provenance,
        }
        for wall in plan.walls
    ]


def _prefer_existing_name(room:Room,detected_name:str)->str:
    current=room.name.strip()
    normalized=current.replace(" ","")
    generic=normalized.startswith("غرفة") and normalized[4:].isdigit()
    if room.reviewed or (current and not generic):
        return current
    return detected_name.strip() or current


def _carry_room_identity(plan:FloorPlan,detected:list[dict])->list[Room]:
    old=list(plan.rooms)
    scored=[]
    for new_index,item in enumerate(detected):
        new_points=[(float(p["x"]),float(p["y"])) for p in item.get("polygon",[])]
        for old_index,room in enumerate(old):
            score=_overlap_ratio(new_points,_points(room))
            if score>=0.35:
                scored.append((score,new_index,old_index))
    scored.sort(reverse=True)

    assigned_new=set()
    assigned_old=set()
    matches:dict[int,int]={}
    for _,new_index,old_index in scored:
        if new_index in assigned_new or old_index in assigned_old:
            continue
        assigned_new.add(new_index)
        assigned_old.add(old_index)
        matches[new_index]=old_index

    existing_ids={room.id for room in old}
    next_index=1
    result=[]
    for index,item in enumerate(detected):
        matched=old[matches[index]] if index in matches else None
        if matched is not None:
            name=_prefer_existing_name(matched,str(item.get("name") or ""))
            item={
                **item,
                "id":matched.id,
                "name":name,
                "ceilingHeightM":matched.ceilingHeightM,
                "reviewed":False,
                "provenance":"mixed",
            }
        else:
            while f"room-rebuilt-{next_index}" in existing_ids:
                next_index+=1
            item={
                **item,
                "id":f"room-rebuilt-{next_index}",
                "reviewed":False,
                "provenance":"mixed",
            }
            existing_ids.add(item["id"])
            next_index+=1
        result.append(Room.model_validate(item))
    return result


def build_room_rebuild_proposal(plan:FloorPlan,command:str)->ProposalResponse:
    if len(plan.walls)<4:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="لا توجد جدران كافية لإعادة بناء الغرف. صحح أو ارسم الحدود الرئيسية أولًا.",
        )

    mask=rasterize_wall_mask(_wall_dicts(plan),plan.heightPx,plan.widthPx)
    detected=detect_rooms(mask,_room_labels(plan),plan.metersPerPixel,min_area_ratio=0.0015,max_area_ratio=0.88)
    if not detected:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="لم تتشكل غرف مغلقة من الجدران الحالية. أكمل الفتحات أو الجدران الناقصة ثم أعد المحاولة.",
        )

    candidate=plan.model_copy(deep=True)
    candidate.rooms=_carry_room_identity(plan,detected)
    candidate=canonicalize_plan(candidate)

    before=validate_plan(plan)
    after=validate_plan(candidate)
    introduced=introduced_critical_findings(before,after)
    if introduced:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="إعادة بناء الغرف من الجدران الحالية أنشأت تعارضًا هندسيًا جديدًا؛ صحح الجدران أولًا.",
        )

    before_count=len(plan.rooms)
    after_count=len(candidate.rooms)
    impacts=[
        Impact(
            kind="info",
            text=f"إعادة اشتقاق حدود {after_count} غرفة من شبكة الجدران الحالية",
            severity="info",
        )
    ]
    if after_count>before_count:
        impacts.append(Impact(
            kind="info",
            text=f"اكتشاف {after_count-before_count} فراغ جديد بعد إغلاق الجدران",
            severity="warning",
        ))
    elif after_count<before_count:
        impacts.append(Impact(
            kind="room_remove",
            text=f"اختفاء {before_count-after_count} غرفة لم تعد مغلقة بالجدران الحالية",
            severity="warning",
        ))

    warnings=[
        "راجع أسماء الغرف وحدودها بصريًا قبل الاعتماد؛ إعادة البناء تعتمد على شبكة الجدران الحالية.",
        *[item.text for item in after.findings if item.severity=="warning"],
    ]
    average=sum(room.confidence for room in candidate.rooms)/max(1,len(candidate.rooms))
    confidence=max(0.55,min(0.93,average-(1-after.score)*0.20))
    proposal=Proposal(
        id=f"rebuild-rooms:{before_count}:{after_count}",
        title="إعادة بناء الغرف من الجدران",
        summary=f"إعادة اشتقاق الفراغات المغلقة من شبكة الجدران الحالية بدل الإبقاء على حدود غرف قديمة.",
        confidence=confidence,
        validationScore=after.score,
        impacts=impacts,
        warnings=list(dict.fromkeys(warnings)),
        previewPlan=candidate,
    )
    return ProposalResponse(command=command,proposals=[proposal])
