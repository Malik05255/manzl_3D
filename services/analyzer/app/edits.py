from __future__ import annotations
from itertools import product
from .commands import find_target_room,normalize_arabic,resolve_target_size
from .edit_geometry import apply_side,bbox
from .models import EditRequest,Impact,Proposal,ProposalResponse

SERVICE_ROOM_WORDS=("حمام","دوره مياه","دورة مياه","مطبخ","درج","مصعد","غسيل")

def _service_rooms(names:list[str])->list[str]:
    result=[]
    for name in names:
        normalized=normalize_arabic(name)
        if any(normalize_arabic(word) in normalized for word in SERVICE_ROOM_WORDS):
            result.append(name)
    return result

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

    target_w,target_h=size
    dx=(target_w-current_w)/mpp
    dy=(target_h-current_h)/mpp
    x_sides=[None] if abs(target_w-current_w)<=0.03 else ["right","left"]
    y_sides=[None] if abs(target_h-current_h)<=0.03 else ["bottom","top"]
    direction={"right":"اليمين","left":"اليسار","bottom":"الأسفل","top":"الأعلى"}

    ranked=[]
    for x_side,y_side in product(x_sides,y_sides):
        plan=req.plan.model_copy(deep=True)
        room=next(r for r in plan.rooms if r.id==target.id)
        impacts=[]
        affected=[]
        valid=True

        if x_side:
            valid,changes,names=apply_side(plan,room,x_side,dx,mpp)
            impacts.extend(changes)
            affected.extend(names)

        if valid and y_side:
            room=next(r for r in plan.rooms if r.id==target.id)
            valid,changes,names=apply_side(plan,room,y_side,dy,mpp)
            impacts.extend(changes)
            affected.extend(names)

        if not valid:
            continue

        affected=list(dict.fromkeys(affected))
        dirs=" + ".join(direction[s] for s in (x_side,y_side) if s) or "بدون تحريك"
        summary=f"تصبح {target.name} {target_w:g}×{target_h:g} م"
        if affected:
            summary+=f" مع تعديل {' و'.join(affected)}"

        plan.quality.warnings=list(dict.fromkeys([
            *plan.quality.warnings,
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

        warnings=[]
        if service_rooms:
            warnings.append(f"هذا الخيار يغيّر فراغ خدمة: {' و'.join(service_rooms)}.")
        penalty=0.14*len(service_rooms)+0.04*max(0,len(affected)-1)
        confidence=max(0.55,min(0.95,req.plan.quality.overall-penalty))
        proposal=Proposal(
            id=proposal_id,
            title=title,
            summary=summary,
            confidence=confidence,
            impacts=[
                Impact(
                    kind="room_resize",
                    text=f"تغيير {target.name} من {current_w:.2f}×{current_h:.2f} م إلى {target_w:g}×{target_h:g} م"
                ),
                *impacts
            ],
            warnings=warnings,
            previewPlan=plan
        )
        ranked.append((penalty,len(affected),proposal))

    if not ranked:
        return ProposalResponse(
            command=req.command,
            proposals=[],
            needsClarification="لا توجد مساحة مجاورة كافية لتنفيذ المقاس المطلوب دون تغيير حدود المبنى."
        )
    ranked.sort(key=lambda item:(item[0],item[1]))
    proposals=[item[2] for item in ranked[:4]]
    return ProposalResponse(command=req.command,proposals=proposals)
