from __future__ import annotations

import math

from .commands import parse_selected_opening_action,parse_selected_wall_action
from .edit_geometry import bbox,minimum_clear_span_m,overlap
from .models import EditRequest,FloorPlan,Impact,Opening,Point,Proposal,ProposalResponse,Wall
from .validation import validate_plan

WALL_EDIT_CONFIDENCE_MIN=0.72
OPENING_EDIT_CONFIDENCE_MIN=0.84


def _point_at(wall:Wall,distance:float)->Point:
    vx=wall.b.x-wall.a.x
    vy=wall.b.y-wall.a.y
    length=math.hypot(vx,vy)
    if length<=1e-9:
        return wall.a.model_copy(deep=True)
    return Point(x=wall.a.x+vx/length*distance,y=wall.a.y+vy/length*distance)


def _project(wall:Wall,point:Point)->float:
    vx=wall.b.x-wall.a.x
    vy=wall.b.y-wall.a.y
    length=math.hypot(vx,vy)
    if length<=1e-9:
        return 0.0
    return (point.x-wall.a.x)*(vx/length)+(point.y-wall.a.y)*(vy/length)


def _wall_length(wall:Wall)->float:
    return math.hypot(wall.b.x-wall.a.x,wall.b.y-wall.a.y)


def _find_opening(plan:FloorPlan,opening_id:str)->Opening|None:
    return next((item for item in [*plan.doors,*plan.windows] if item.id==opening_id),None)


def _replace_opening(plan:FloorPlan,opening:Opening)->None:
    plan.doors=[item for item in plan.doors if item.id!=opening.id]
    plan.windows=[item for item in plan.windows if item.id!=opening.id]
    if opening.kind=="door":
        plan.doors.append(opening)
    else:
        plan.windows.append(opening)


def _opening_interval(wall:Wall,opening:Opening)->tuple[float,float]:
    first=_project(wall,opening.a)
    second=_project(wall,opening.b)
    return min(first,second),max(first,second)


def _normalize_opening_on_wall(plan:FloorPlan,opening:Opening,width_px:float,center_distance:float)->tuple[Opening|None,bool]:
    if not opening.wallId:
        return None,False
    wall=next((item for item in plan.walls if item.id==opening.wallId),None)
    if wall is None:
        return None,False
    length=_wall_length(wall)
    margin=max(4.0,wall.thicknessPx*1.25)
    usable=length-margin*2
    if usable<6 or width_px<6 or width_px>usable+1e-6:
        return None,False

    half=width_px/2
    min_center=margin+half
    max_center=length-margin-half
    clamped=max(min_center,min(max_center,center_distance))
    shifted=abs(clamped-center_distance)>0.5
    return Opening(
        id=opening.id,
        kind=opening.kind,
        wallId=wall.id,
        a=_point_at(wall,clamped-half),
        b=_point_at(wall,clamped+half),
        confidence=max(opening.confidence,0.95),
    ),shifted


def _resize_opening(plan:FloorPlan,opening_id:str,width_m:float)->tuple[bool,bool]:
    if not plan.metersPerPixel or plan.metersPerPixel<=0:
        return False,False
    opening=_find_opening(plan,opening_id)
    if opening is None or not opening.wallId:
        return False,False
    wall=next((item for item in plan.walls if item.id==opening.wallId),None)
    if wall is None:
        return False,False

    start,end=_opening_interval(wall,opening)
    center=(start+end)/2
    normalized,shifted=_normalize_opening_on_wall(plan,opening,width_m/plan.metersPerPixel,center)
    if normalized is None:
        return False,False
    _replace_opening(plan,normalized)
    return True,shifted


def _move_opening(plan:FloorPlan,opening_id:str,amount_m:float,direction:str)->tuple[bool,float,bool]:
    if not plan.metersPerPixel or plan.metersPerPixel<=0:
        return False,0.0,False
    opening=_find_opening(plan,opening_id)
    if opening is None or not opening.wallId:
        return False,0.0,False
    wall=next((item for item in plan.walls if item.id==opening.wallId),None)
    if wall is None:
        return False,0.0,False

    dx=wall.b.x-wall.a.x
    dy=wall.b.y-wall.a.y
    horizontal=abs(dx)>=abs(dy)
    if horizontal and direction not in ("left","right"):
        return False,0.0,False
    if not horizontal and direction not in ("up","down"):
        return False,0.0,False

    start,end=_opening_interval(wall,opening)
    width=end-start
    center=(start+end)/2
    center_point=_point_at(wall,center)
    delta_px=amount_m/plan.metersPerPixel
    if direction=="right":
        desired=Point(x=center_point.x+delta_px,y=center_point.y)
    elif direction=="left":
        desired=Point(x=center_point.x-delta_px,y=center_point.y)
    elif direction=="down":
        desired=Point(x=center_point.x,y=center_point.y+delta_px)
    else:
        desired=Point(x=center_point.x,y=center_point.y-delta_px)

    desired_center=_project(wall,desired)
    normalized,shifted=_normalize_opening_on_wall(plan,opening,width,desired_center)
    if normalized is None:
        return False,0.0,False

    old_center_point=center_point
    new_center=( _project(wall,normalized.a)+_project(wall,normalized.b) )/2
    new_center_point=_point_at(wall,new_center)
    actual_px=math.hypot(new_center_point.x-old_center_point.x,new_center_point.y-old_center_point.y)
    if actual_px<0.5:
        return False,0.0,shifted
    _replace_opening(plan,normalized)
    return True,actual_px*plan.metersPerPixel,shifted


def _change_opening_kind(plan:FloorPlan,opening_id:str,kind:str)->bool:
    opening=_find_opening(plan,opening_id)
    if opening is None or kind not in ("door","window"):
        return False
    next_opening=opening.model_copy(update={"kind":kind})
    _replace_opening(plan,next_opening)
    return True


def _remove_opening(plan:FloorPlan,opening_id:str)->bool:
    opening=_find_opening(plan,opening_id)
    if opening is None:
        return False
    plan.doors=[item for item in plan.doors if item.id!=opening_id]
    plan.windows=[item for item in plan.windows if item.id!=opening_id]
    return True


def _next_opening_id(plan:FloorPlan,kind:str)->str:
    existing={item.id for item in [*plan.doors,*plan.windows]}
    index=1
    while f"{kind}-ai-{index}" in existing:
        index+=1
    return f"{kind}-ai-{index}"


def _add_opening(plan:FloorPlan,wall_id:str,kind:str)->Opening|None:
    if not plan.metersPerPixel or plan.metersPerPixel<=0:
        return None
    wall=next((item for item in plan.walls if item.id==wall_id),None)
    if wall is None or kind not in ("door","window"):
        return None

    length=_wall_length(wall)
    margin=max(5.0,wall.thicknessPx*1.5)
    preferred_m=0.90 if kind=="door" else 1.20
    width_px=preferred_m/plan.metersPerPixel
    if width_px>length*0.55:
        width_px=length*0.55
    if width_px<8:
        return None

    occupied=sorted(
        [_opening_interval(wall,item) for item in [*plan.doors,*plan.windows] if item.wallId==wall_id],
        key=lambda value:value[0],
    )
    free=[]
    cursor=margin
    for start,end in occupied:
        protected_start=max(margin,start-margin)
        protected_end=min(length-margin,end+margin)
        if protected_start>cursor:
            free.append((cursor,protected_start))
        cursor=max(cursor,protected_end)
    if cursor<length-margin:
        free.append((cursor,length-margin))

    slots=[slot for slot in free if slot[1]-slot[0]>=width_px]
    if not slots:
        return None
    start,end=max(slots,key=lambda slot:slot[1]-slot[0])
    center=(start+end)/2
    opening=Opening(
        id=_next_opening_id(plan,kind),
        kind=kind,
        wallId=wall_id,
        a=_point_at(wall,center-width_px/2),
        b=_point_at(wall,center+width_px/2),
        confidence=1.0,
    )
    _replace_opening(plan,opening)
    return opening


def _polygon_area_px2(points:list[Point])->float:
    if len(points)<3:
        return 0.0
    total=0.0
    for index,point in enumerate(points):
        other=points[(index+1)%len(points)]
        total+=point.x*other.y-other.x*point.y
    return abs(total)/2.0


def _move_wall_topology(plan:FloorPlan,wall_id:str,amount_m:float,direction:str)->tuple[bool,float,list[str],int]:
    if not plan.metersPerPixel or plan.metersPerPixel<=0:
        return False,0.0,[],0
    wall=next((item for item in plan.walls if item.id==wall_id),None)
    if wall is None:
        return False,0.0,[],0

    vertical=abs(wall.a.x-wall.b.x)<=abs(wall.a.y-wall.b.y)
    if vertical and direction not in ("left","right"):
        return False,0.0,[],0
    if not vertical and direction not in ("up","down"):
        return False,0.0,[],0

    old_axis=(wall.a.x+wall.b.x)/2 if vertical else (wall.a.y+wall.b.y)/2
    sign=1.0 if direction in ("right","down") else -1.0
    desired=old_axis+sign*(amount_m/plan.metersPerPixel)
    span1=min(wall.a.y,wall.b.y) if vertical else min(wall.a.x,wall.b.x)
    span2=max(wall.a.y,wall.b.y) if vertical else max(wall.a.x,wall.b.x)
    tolerance=max(6.0,wall.thicknessPx*2)

    lower=0.0
    upper=float(plan.widthPx if vertical else plan.heightPx)
    for room in plan.rooms:
        x1,y1,x2,y2=bbox(room)
        shared=overlap(y1,y2,span1,span2) if vertical else overlap(x1,x2,span1,span2)
        if shared<=tolerance:
            continue
        minimum_px=max(28.0,minimum_clear_span_m(room)/plan.metersPerPixel)
        if vertical:
            if abs(x1-old_axis)<=tolerance:
                upper=min(upper,x2-minimum_px)
            if abs(x2-old_axis)<=tolerance:
                lower=max(lower,x1+minimum_px)
        else:
            if abs(y1-old_axis)<=tolerance:
                upper=min(upper,y2-minimum_px)
            if abs(y2-old_axis)<=tolerance:
                lower=max(lower,y1+minimum_px)

    axis=max(lower,min(upper,desired))
    delta=axis-old_axis
    if abs(delta)<0.5:
        return False,0.0,[],0

    moved_wall_ids=set()
    for item in plan.walls:
        item_vertical=abs(item.a.x-item.b.x)<=abs(item.a.y-item.b.y)
        if item_vertical!=vertical:
            continue
        item_axis=(item.a.x+item.b.x)/2 if vertical else (item.a.y+item.b.y)/2
        if abs(item_axis-old_axis)>tolerance:
            continue
        item_span1=min(item.a.y,item.b.y) if vertical else min(item.a.x,item.b.x)
        item_span2=max(item.a.y,item.b.y) if vertical else max(item.a.x,item.b.x)
        if overlap(item_span1,item_span2,span1,span2)>0:
            moved_wall_ids.add(item.id)
    moved_wall_ids.add(wall_id)

    for item in plan.walls:
        if item.id in moved_wall_ids:
            if vertical:
                item.a.x+=delta
                item.b.x+=delta
            else:
                item.a.y+=delta
                item.b.y+=delta
            continue

        item_vertical=abs(item.a.x-item.b.x)<=abs(item.a.y-item.b.y)
        if item_vertical==vertical:
            continue
        if vertical:
            if abs(item.a.x-old_axis)<=tolerance and span1-tolerance<=item.a.y<=span2+tolerance:
                item.a.x=axis
            if abs(item.b.x-old_axis)<=tolerance and span1-tolerance<=item.b.y<=span2+tolerance:
                item.b.x=axis
        else:
            if abs(item.a.y-old_axis)<=tolerance and span1-tolerance<=item.a.x<=span2+tolerance:
                item.a.y=axis
            if abs(item.b.y-old_axis)<=tolerance and span1-tolerance<=item.b.x<=span2+tolerance:
                item.b.y=axis

    affected=[]
    for room in plan.rooms:
        x1,y1,x2,y2=bbox(room)
        shared=overlap(y1,y2,span1,span2) if vertical else overlap(x1,x2,span1,span2)
        if shared<=tolerance:
            continue
        touches=(abs(x1-old_axis)<=tolerance or abs(x2-old_axis)<=tolerance) if vertical else (abs(y1-old_axis)<=tolerance or abs(y2-old_axis)<=tolerance)
        if not touches:
            continue
        changed=False
        for point in room.polygon:
            if vertical and abs(point.x-old_axis)<=tolerance:
                point.x=axis
                changed=True
            elif not vertical and abs(point.y-old_axis)<=tolerance:
                point.y=axis
                changed=True
        if changed:
            room.areaM2=round(_polygon_area_px2(room.polygon)*(plan.metersPerPixel**2),2)
            affected.append(room.name)

    moved_openings=0
    for opening in [*plan.doors,*plan.windows]:
        if opening.wallId not in moved_wall_ids:
            continue
        if vertical:
            opening.a.x+=delta
            opening.b.x+=delta
        else:
            opening.a.y+=delta
            opening.b.y+=delta
        moved_openings+=1

    return True,abs(delta)*plan.metersPerPixel,list(dict.fromkeys(affected)),moved_openings


def _finalize(plan:FloorPlan,candidate:FloorPlan,proposal_id:str,title:str,summary:str,impacts:list[Impact],confidence_penalty:float=0.04,extra_warnings:list[str]|None=None)->ProposalResponse:
    report=validate_plan(candidate)
    if any(item.severity=="critical" for item in report.findings):
        return ProposalResponse(
            command="",
            proposals=[],
            needsClarification="التعديل المطلوب يسبب تعارضًا هندسيًا جديدًا، لذلك لم يتم اقتراحه.",
        )
    warnings=list(extra_warnings or [])
    warnings.extend(item.text for item in report.findings if item.severity=="warning")
    warnings=list(dict.fromkeys(warnings))
    confidence=max(0.55,min(0.97,plan.quality.overall-confidence_penalty-(1-report.score)*0.25))
    proposal=Proposal(
        id=proposal_id,
        title=title,
        summary=summary,
        confidence=confidence,
        validationScore=report.score,
        impacts=impacts,
        warnings=warnings,
        previewPlan=candidate,
    )
    return ProposalResponse(command="",proposals=[proposal])


def build_selected_element_proposals(req:EditRequest)->ProposalResponse|None:
    if req.target_opening_id:
        opening=_find_opening(req.plan,req.target_opening_id)
        if opening is None:
            return ProposalResponse(command=req.command,proposals=[],needsClarification="الفتحة المحددة لم تعد موجودة في المخطط.")
        if opening.confidence<OPENING_EDIT_CONFIDENCE_MIN:
            return ProposalResponse(
                command=req.command,
                proposals=[],
                needsClarification="قراءة الفتحة المحددة منخفضة الثقة. أكد أنها باب أو نافذة وموقعها من مراجعة القراءة قبل تعديلها بالذكاء.",
            )
        action=parse_selected_opening_action(req.command)
        if action is None:
            return ProposalResponse(
                command=req.command,
                proposals=[],
                needsClarification="للفتحة المحددة يمكنك طلب: عرض 90 سم، حركها يمين 30 سم، حولها نافذة، أو احذفها.",
            )
        kind,payload=action
        if kind=="move_missing_direction":
            return ProposalResponse(command=req.command,proposals=[],needsClarification="حدد اتجاه تحريك الفتحة: يمين، يسار، أعلى، أو أسفل.")

        candidate=req.plan.model_copy(deep=True)
        label="الباب" if opening.kind=="door" else "النافذة"

        if kind=="remove":
            _remove_opening(candidate,opening.id)
            result=_finalize(
                req.plan,candidate,f"opening-remove:{opening.id}",
                f"حذف {label}",
                f"إزالة {label} المحدد من الجدار",
                [Impact(kind="opening_remove",text=f"إزالة {label} المحدد",severity="warning")],
                confidence_penalty=0.02,
            )
        elif kind=="kind":
            next_kind=payload["kind"]
            if next_kind==opening.kind:
                return ProposalResponse(command=req.command,proposals=[],needsClarification=f"{label} المحدد من النوع المطلوب بالفعل.")
            if not _change_opening_kind(candidate,opening.id,next_kind):
                return ProposalResponse(command=req.command,proposals=[],needsClarification="تعذر تغيير نوع الفتحة المحددة.")
            next_label="باب" if next_kind=="door" else "نافذة"
            result=_finalize(
                req.plan,candidate,f"opening-kind:{opening.id}:{next_kind}",
                f"تحويل الفتحة إلى {next_label}",
                f"تغيير نوع {label} المحدد إلى {next_label} مع إبقاء موقعه وعرضه",
                [Impact(kind="opening_update",text=f"تحويل {label} إلى {next_label}")],
            )
        elif kind=="width":
            if not req.plan.metersPerPixel:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="ثبّت مقياس المخطط أولًا قبل تعديل عرض الفتحة بالمتر.")
            width=float(payload["width_m"])
            ok,shifted=_resize_opening(candidate,opening.id,width)
            if not ok:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="العرض المطلوب لا يتسع داخل الجدار المحدد مع الحفاظ على هوامش آمنة.")
            result=_finalize(
                req.plan,candidate,f"opening-width:{opening.id}:{width:g}",
                f"تعديل عرض {label}",
                f"تغيير عرض {label} المحدد إلى {width:g} م",
                [Impact(kind="opening_update",text=f"ضبط عرض {label} إلى {width:g} م")],
                extra_warnings=["تم تحريك مركز الفتحة قليلًا لإبقائها داخل الجدار."] if shifted else None,
            )
        elif kind=="move":
            if not req.plan.metersPerPixel:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="ثبّت مقياس المخطط أولًا قبل تحريك الفتحة بمسافة مترية.")
            amount=float(payload["amount_m"])
            direction=str(payload["direction"])
            ok,actual,clamped=_move_opening(candidate,opening.id,amount,direction)
            if not ok:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="الاتجاه المطلوب لا يطابق اتجاه الجدار أو لا توجد مساحة كافية للتحريك.")
            direction_ar={"right":"يمين","left":"يسار","up":"أعلى","down":"أسفل"}[direction]
            result=_finalize(
                req.plan,candidate,f"opening-move:{opening.id}:{direction}:{amount:g}",
                f"تحريك {label} {direction_ar}",
                f"تحريك {label} المحدد {actual:.2f} م باتجاه {direction_ar}",
                [Impact(kind="opening_update",text=f"تحريك {label} {actual:.2f} م باتجاه {direction_ar}")],
                extra_warnings=["تم تقليل مسافة التحريك للوصول إلى أقرب موضع صالح على الجدار."] if clamped and actual+0.01<amount else None,
            )
        else:
            return None

        result.command=req.command
        return result

    if req.target_wall_id:
        wall=next((item for item in req.plan.walls if item.id==req.target_wall_id),None)
        if wall is None:
            return ProposalResponse(command=req.command,proposals=[],needsClarification="الجدار المحدد لم يعد موجودًا في المخطط.")
        if wall.confidence<WALL_EDIT_CONFIDENCE_MIN:
            return ProposalResponse(
                command=req.command,
                proposals=[],
                needsClarification="قراءة الجدار المحدد منخفضة الثقة. أكد الجدار من مراجعة القراءة أو صحح موضعه أولًا قبل تعديله بالذكاء.",
            )
        action=parse_selected_wall_action(req.command)
        if action is None:
            return ProposalResponse(
                command=req.command,
                proposals=[],
                needsClarification="للجدار المحدد يمكنك طلب: حركه يمين 30 سم، اجعل سماكته 20 سم، أضف باب، أو أضف نافذة.",
            )
        kind,payload=action
        if kind=="move_missing_direction":
            return ProposalResponse(command=req.command,proposals=[],needsClarification="حدد اتجاه تحريك الجدار: يمين، يسار، أعلى، أو أسفل.")

        candidate=req.plan.model_copy(deep=True)
        if kind=="thickness":
            if not req.plan.metersPerPixel:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="ثبّت مقياس المخطط أولًا قبل تعديل سماكة الجدار.")
            thickness=float(payload["thickness_m"])
            candidate_wall=next(item for item in candidate.walls if item.id==wall.id)
            candidate_wall.thicknessPx=thickness/req.plan.metersPerPixel
            result=_finalize(
                req.plan,candidate,f"wall-thickness:{wall.id}:{thickness:g}",
                "تعديل سماكة الجدار",
                f"ضبط سماكة الجدار المحدد إلى {thickness*100:.0f} سم",
                [Impact(kind="wall_update",text=f"تغيير سماكة الجدار إلى {thickness*100:.0f} سم")],
                confidence_penalty=0.02,
            )
        elif kind=="move":
            if not req.plan.metersPerPixel:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="ثبّت مقياس المخطط أولًا قبل تحريك الجدار بمسافة مترية.")
            amount=float(payload["amount_m"])
            direction=str(payload["direction"])
            ok,actual,affected,moved_openings=_move_wall_topology(candidate,wall.id,amount,direction)
            if not ok:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="الاتجاه المطلوب لا يطابق اتجاه الجدار أو لا توجد مساحة كافية لتحريكه دون إفساد الفراغات.")
            direction_ar={"right":"يمين","left":"يسار","up":"أعلى","down":"أسفل"}[direction]
            impacts=[Impact(kind="wall_move",text=f"تحريك الجدار {actual:.2f} م باتجاه {direction_ar}")]
            if affected:
                impacts.append(Impact(kind="room_resize",text=f"تعديل حدود {' و'.join(affected)} تلقائيًا",severity="warning"))
            if moved_openings:
                impacts.append(Impact(kind="door_move",text=f"تحريك {moved_openings} فتحة مرتبطة بالجدار تلقائيًا",severity="warning"))
            result=_finalize(
                req.plan,candidate,f"wall-move:{wall.id}:{direction}:{amount:g}",
                f"تحريك الجدار {direction_ar}",
                f"تحريك الجدار المحدد {actual:.2f} م مع الحفاظ على اتصال المخطط",
                impacts,
                extra_warnings=["تم تقليل مسافة التحريك للحفاظ على الحد الأدنى للفراغات المجاورة."] if actual+0.01<amount else None,
            )
        elif kind=="add_opening":
            if not req.plan.metersPerPixel:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="ثبّت مقياس المخطط أولًا قبل إضافة فتحة بمقاس هندسي.")
            opening=_add_opening(candidate,wall.id,str(payload["kind"]))
            if opening is None:
                return ProposalResponse(command=req.command,proposals=[],needsClarification="لا توجد مساحة خالية كافية على الجدار المحدد لإضافة الفتحة.")
            label="باب" if opening.kind=="door" else "نافذة"
            width=math.hypot(opening.b.x-opening.a.x,opening.b.y-opening.a.y)*req.plan.metersPerPixel
            result=_finalize(
                req.plan,candidate,f"wall-add-{opening.kind}:{wall.id}:{opening.id}",
                f"إضافة {label}",
                f"إضافة {label} بعرض تقريبي {width:.2f} م في أكبر مساحة خالية على الجدار",
                [Impact(kind="opening_update",text=f"إضافة {label} جديد بعرض {width:.2f} م")],
                confidence_penalty=0.05,
            )
        else:
            return None

        result.command=req.command
        return result

    return None
