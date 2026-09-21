from __future__ import annotations
from itertools import product
from .commands import find_target_room,normalize_arabic,resolve_target_size
from .edit_geometry import absorb_neighbor,adjacent,apply_side,bbox,is_rectangular_room,minimum_clear_span_m
from .models import EditRequest,FloorPlan,Impact,Proposal,ProposalResponse,Room
from .validation import validate_plan

SERVICE_ROOM_WORDS=("حمام","دوره مياه","دورة مياه","مطبخ","درج","مصعد","غسيل")

def _service_rooms(names:list[str])->list[str]:
    result=[]
    for name in names:
        normalized=normalize_arabic(name)
        if any(normalize_arabic(word) in normalized for word in SERVICE_ROOM_WORDS):
            result.append(name)
    return result

def _absorb_service_alternative(plan:FloorPlan,target:Room,target_w:float,target_h:float,command:str)->Proposal|None:
    mpp=plan.metersPerPixel
    if not mpp:
        return None
    x1,y1,x2,y2=bbox(target)
    current_w=(x2-x1)*mpp
    current_h=(y2-y1)*mpp
    dx=(target_w-current_w)/mpp
    dy=(target_h-current_h)/mpp

    # Conservative first version: consume exactly one full-width/full-height service room
    # only when one dimension changes. This avoids creating unassigned or overlapping space.
    if abs(dx)>=1 and abs(dy)<1:
        sides=["right","left"]
        delta=dx
    elif abs(dy)>=1 and abs(dx)<1:
        sides=["bottom","top"]
        delta=dy
    else:
        return None

    tol=max(6.0,0.18/mpp)
    for side in sides:
        candidate=plan.model_copy(deep=True)
        candidate_target=next(room for room in candidate.rooms if room.id==target.id)
        neighbors=adjacent(candidate,candidate_target,side,tol)
        if len(neighbors)!=1 or not _service_rooms([neighbors[0].name]):
            continue
        service=neighbors[0]
        ok,impacts=absorb_neighbor(candidate,candidate_target,service,side,delta,mpp)
        if not ok:
            continue
        validation=validate_plan(candidate)
        if any(item.severity=="critical" for item in validation.findings):
            continue
        warnings=[
            f"هذا خيار جذري: سيتم إلغاء {service.name} بالكامل وضم مساحته إلى {target.name}.",
            *[item.text for item in validation.findings if item.severity=="warning"],
        ]
        return Proposal(
            id=f"absorb:{target.id}:{service.id}:{side}:{target_w:g}x{target_h:g}",
            title=f"إلغاء {service.name} وضم مساحته",
            summary=f"تصبح {target.name} {target_w:g}×{target_h:g} م عبر ضم {service.name}",
            confidence=max(0.55,min(0.78,plan.quality.overall-0.16)),
            validationScore=validation.score,
            impacts=[
                Impact(kind="room_resize",text=f"تغيير {target.name} من {current_w:.2f}×{current_h:.2f} م إلى {target_w:g}×{target_h:g} م"),
                *impacts,
            ],
            warnings=list(dict.fromkeys(warnings)),
            previewPlan=candidate,
        )
    return None

def build_resize_proposals(plan:FloorPlan,target:Room,target_w:float,target_h:float,command:str)->ProposalResponse:
    mpp=plan.metersPerPixel
    if not mpp or mpp<=0:
        return ProposalResponse(command=command,proposals=[],needsClarification="يجب تثبيت مقياس المخطط أولًا قبل تنفيذ تعديل بالمتر.")

    if not is_rectangular_room(target):
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="هذه الغرفة ذات شكل غير مستطيل. لن أختصر هندستها إلى مستطيل تلقائيًا؛ استخدم التعديل اليدوي حتى يدعم المحرك التحريك متعدد الأضلاع.",
        )

    if not (0.8<=target_w<=50 and 0.8<=target_h<=50):
        return ProposalResponse(command=command,proposals=[],needsClarification="المقاس المطلوب خارج النطاق الهندسي المدعوم.")

    x1,y1,x2,y2=bbox(target)
    current_w=(x2-x1)*mpp
    current_h=(y2-y1)*mpp
    recommended_min=minimum_clear_span_m(target)
    target_size_warning=None
    if min(target_w,target_h)<recommended_min:
        target_size_warning=f"المقاس المطلوب يجعل أحد أبعاد {target.name} أقل من {recommended_min:g} م؛ هذا تنبيه استخدامي وليس تحقق كود بناء."

    dx=(target_w-current_w)/mpp
    dy=(target_h-current_h)/mpp
    x_sides=[None] if abs(target_w-current_w)<=0.03 else ["right","left"]
    y_sides=[None] if abs(target_h-current_h)<=0.03 else ["bottom","top"]
    direction={"right":"اليمين","left":"اليسار","bottom":"الأسفل","top":"الأعلى"}

    ranked=[]
    for x_side,y_side in product(x_sides,y_sides):
        candidate=plan.model_copy(deep=True)
        room=next((r for r in candidate.rooms if r.id==target.id),None)
        if room is None:
            continue
        impacts=[]
        affected=[]
        valid=True

        if x_side:
            valid,changes,names=apply_side(candidate,room,x_side,dx,mpp)
            impacts.extend(changes)
            affected.extend(names)

        if valid and y_side:
            room=next(r for r in candidate.rooms if r.id==target.id)
            valid,changes,names=apply_side(candidate,room,y_side,dy,mpp)
            impacts.extend(changes)
            affected.extend(names)

        if not valid:
            continue

        affected=list(dict.fromkeys(affected))
        dirs=" + ".join(direction[s] for s in (x_side,y_side) if s) or "بدون تحريك"
        summary=f"تصبح {target.name} {target_w:g}×{target_h:g} م"
        if affected:
            summary+=f" مع تعديل {' و'.join(affected)}"

        candidate.quality.warnings=list(dict.fromkeys([
            *candidate.quality.warnings,
            "راجع الأبواب ومسارات الحركة بصريًا قبل اعتماد التعديل."
        ]))
        proposal_id=f"resize:{target.id}:{x_side or 'same'}:{y_side or 'same'}:{target_w:g}x{target_h:g}"
        service_rooms=_service_rooms(affected)
        effect_titles=[impact.text for impact in impacts if impact.kind=="room_resize"]
        if len(effect_titles)==1:
            title=effect_titles[0]
        elif affected:
            title=f"إعادة توزيع {' و'.join(affected)}"
        else:
            title=f"التعديل باتجاه {dirs}"

        validation=validate_plan(candidate)
        if any(finding.severity=="critical" for finding in validation.findings):
            continue

        warnings=[]
        if target_size_warning:
            warnings.append(target_size_warning)
        if service_rooms:
            warnings.append(f"هذا الخيار يغيّر فراغ خدمة: {' و'.join(service_rooms)}.")
        warnings.extend(finding.text for finding in validation.findings if finding.severity=="warning")
        warnings=list(dict.fromkeys(warnings))
        validation_penalty=max(0.0,1.0-validation.score)*0.35
        penalty=0.14*len(service_rooms)+0.04*max(0,len(affected)-1)+validation_penalty
        confidence=max(0.55,min(0.95,plan.quality.overall-penalty))
        proposal=Proposal(
            id=proposal_id,
            title=title,
            summary=summary,
            confidence=confidence,
            validationScore=validation.score,
            impacts=[
                Impact(
                    kind="room_resize",
                    text=f"تغيير {target.name} من {current_w:.2f}×{current_h:.2f} م إلى {target_w:g}×{target_h:g} م"
                ),
                *impacts
            ],
            warnings=warnings,
            previewPlan=candidate
        )
        ranked.append((penalty,len(affected),proposal))

    absorb=_absorb_service_alternative(plan,target,target_w,target_h,command)
    if absorb is not None:
        ranked.append((0.26,1,absorb))

    if not ranked:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="لا توجد مساحة مجاورة كافية لتنفيذ المقاس المطلوب دون تغيير حدود المبنى أو جعل فراغ مجاور غير صالح للاستخدام."
        )

    ranked.sort(key=lambda item:(item[0],item[1],-item[2].confidence))
    return ProposalResponse(command=command,proposals=[item[2] for item in ranked[:4]])

def build_proposals(req:EditRequest)->ProposalResponse:
    target=find_target_room(req.command,req.plan.rooms)
    if target is None:
        names="، ".join(room.name for room in req.plan.rooms[:10])
        detail=f" الغرف المقروءة: {names}." if names else ""
        return ProposalResponse(command=req.command,proposals=[],needsClarification="لم أستطع تحديد الغرفة المقصودة بثقة."+detail)

    mpp=req.plan.metersPerPixel
    if not mpp or mpp<=0:
        return ProposalResponse(command=req.command,proposals=[],needsClarification="يجب تثبيت مقياس المخطط أولًا قبل تنفيذ تعديل بالمتر.")

    x1,y1,x2,y2=bbox(target)
    current_w=(x2-x1)*mpp
    current_h=(y2-y1)*mpp
    size=resolve_target_size(req.command,current_w,current_h)
    if not size:
        return ProposalResponse(
            command=req.command,
            proposals=[],
            needsClarification="حدد المقاس مثل 5×4، أو قل: اجعل العرض 5 متر والعمق 4 متر، أو: زد العرض متر."
        )

    return build_resize_proposals(req.plan,target,size[0],size[1],req.command)
