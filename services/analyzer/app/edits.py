from __future__ import annotations
from itertools import product
from .commands import find_target_room,normalize_arabic,parse_merge_rooms,resize_neighbor_constraints,resolve_target_size
from .edit_geometry import absorb_neighbor,adjacent,apply_side,bbox,is_orthogonal_room,is_rectangular_room,merge_neighbor,minimum_clear_span_m
from .element_edits import build_selected_element_proposals
from .models import EditRequest,FloorPlan,Impact,Proposal,ProposalResponse,Room
from .provenance import mark_ai_changes
from .room_rebuild import build_room_rebuild_proposal
from .topology import canonicalize_plan
from .validation import introduced_critical_findings,validate_plan

SERVICE_ROOM_WORDS=("حمام","دوره مياه","دورة مياه","مطبخ","درج","مصعد","غسيل")
ROOM_EDIT_CONFIDENCE_MIN=0.78

def _service_rooms(names:list[str])->list[str]:
    result=[]
    for name in names:
        normalized=normalize_arabic(name)
        if any(normalize_arabic(word) in normalized for word in SERVICE_ROOM_WORDS):
            result.append(name)
    return result

def _absorb_service_alternative(plan:FloorPlan,target:Room,target_w:float,target_h:float,command:str,baseline_validation=None)->Proposal|None:
    mpp=plan.metersPerPixel
    if not mpp:
        return None
    x1,y1,x2,y2=bbox(target)
    current_w=(x2-x1)*mpp
    current_h=(y2-y1)*mpp
    preferred_neighbors,excluded_neighbors=resize_neighbor_constraints(command,plan.rooms,target)
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
        mark_ai_changes(plan,candidate)
        candidate=canonicalize_plan(candidate)
        validation=validate_plan(candidate)
        baseline=baseline_validation or validate_plan(plan)
        if introduced_critical_findings(baseline,validation):
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
    baseline_validation=validate_plan(plan)
    if not target.reviewed and target.confidence<ROOM_EDIT_CONFIDENCE_MIN:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification=f"قراءة {target.name} منخفضة الثقة. أكد الغرفة من قسم مراجعة القراءة أو صحح حدودها أولًا قبل تعديلها بالذكاء.",
        )
    mpp=plan.metersPerPixel
    if not mpp or mpp<=0:
        return ProposalResponse(command=command,proposals=[],needsClarification="يجب تثبيت مقياس المخطط أولًا قبل تنفيذ تعديل بالمتر.")

    if not is_orthogonal_room(target):
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="شكل الغرفة غير متعامد ولا يمكن تحريك حدوده بأمان تلقائيًا حاليًا. استخدم التعديل اليدوي لهذه الحالة.",
        )

    if not (0.8<=target_w<=50 and 0.8<=target_h<=50):
        return ProposalResponse(command=command,proposals=[],needsClarification="المقاس المطلوب خارج النطاق الهندسي المدعوم.")

    x1,y1,x2,y2=bbox(target)
    current_w=(x2-x1)*mpp
    current_h=(y2-y1)*mpp
    preferred_neighbors,excluded_neighbors=resize_neighbor_constraints(command,plan.rooms,target)
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
        affected_ids={
            room.id for room in candidate.rooms
            if any(normalize_arabic(room.name)==normalize_arabic(name) for name in affected)
        }
        if excluded_neighbors & affected_ids:
            continue
        if preferred_neighbors and not preferred_neighbors.issubset(affected_ids):
            continue

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

        mark_ai_changes(plan,candidate)
        candidate=canonicalize_plan(candidate)
        validation=validate_plan(candidate)
        if introduced_critical_findings(baseline_validation,validation):
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
        if preferred_neighbors:
            penalty=max(0.0,penalty-0.10)
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

    absorb=_absorb_service_alternative(plan,target,target_w,target_h,command,baseline_validation)
    if absorb is not None:
        parts=absorb.id.split(":")
        absorbed_id=parts[2] if len(parts)>2 else ""
        if absorbed_id not in excluded_neighbors and (not preferred_neighbors or absorbed_id in preferred_neighbors):
            ranked.append((0.26 if not preferred_neighbors else 0.12,1,absorb))

    if not ranked:
        if preferred_neighbors:
            names=[room.name for room in plan.rooms if room.id in preferred_neighbors]
            return ProposalResponse(
                command=command,
                proposals=[],
                needsClarification=f"لا يمكن تنفيذ المقاس المطلوب على حساب {' و'.join(names)} دون إنشاء تعارض أو جعل الفراغ غير صالح."
            )
        if excluded_neighbors:
            names=[room.name for room in plan.rooms if room.id in excluded_neighbors]
            return ProposalResponse(
                command=command,
                proposals=[],
                needsClarification=f"لا يوجد حل صالح يحقق المقاس المطلوب مع إبقاء {' و'.join(names)} دون تغيير."
            )
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="لا توجد مساحة مجاورة كافية لتنفيذ المقاس المطلوب دون تغيير حدود المبنى أو جعل فراغ مجاور غير صالح للاستخدام."
        )

    ranked.sort(key=lambda item:(item[0],item[1],-item[2].confidence))
    return ProposalResponse(command=command,proposals=[item[2] for item in ranked[:4]])

def build_merge_proposal(plan:FloorPlan,source:Room,target:Room,command:str)->ProposalResponse:
    uncertain=[room.name for room in (source,target) if not room.reviewed and room.confidence<ROOM_EDIT_CONFIDENCE_MIN]
    if uncertain:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification=f"قراءة {' و'.join(uncertain)} منخفضة الثقة. أكد الغرف من مراجعة القراءة قبل الدمج أو الحذف.",
        )
    if not plan.metersPerPixel:
        return ProposalResponse(command=command,proposals=[],needsClarification="يجب تثبيت مقياس المخطط قبل دمج الغرف.")

    candidate=plan.model_copy(deep=True)
    candidate_source=next((room for room in candidate.rooms if room.id==source.id),None)
    candidate_target=next((room for room in candidate.rooms if room.id==target.id),None)
    if candidate_source is None or candidate_target is None:
        return ProposalResponse(command=command,proposals=[],needsClarification="تعذر العثور على الغرف المطلوب دمجها.")

    ok,impacts=merge_neighbor(candidate,candidate_target,candidate_source,plan.metersPerPixel)
    if not ok:
        return ProposalResponse(
            command=command,
            proposals=[],
            needsClarification="لا يمكن دمج الغرفتين تلقائيًا دون إنشاء شكل غير منتظم أو فراغ غير مغطى. استخدم التعديل اليدوي لهذه الحالة.",
        )

    mark_ai_changes(plan,candidate)
    candidate=canonicalize_plan(candidate)
    baseline_validation=validate_plan(plan)
    validation=validate_plan(candidate)
    if introduced_critical_findings(baseline_validation,validation):
        return ProposalResponse(command=command,proposals=[],needsClarification="نتيجة الدمج تسببت في تعارض هندسي جديد، لذلك لم يتم اقتراحها.")

    warnings=[
        f"سيتم حذف {source.name} كغرفة مستقلة وضم مساحتها بالكامل إلى {target.name}.",
        *[item.text for item in validation.findings if item.severity=="warning"],
    ]
    proposal=Proposal(
        id=f"merge:{source.id}:into:{target.id}",
        title=f"ضم {source.name} إلى {target.name}",
        summary=f"إلغاء الحد الفاصل واعتبار المساحتين غرفة واحدة باسم {target.name}",
        confidence=max(0.55,min(0.82,plan.quality.overall-0.12)),
        validationScore=validation.score,
        impacts=impacts,
        warnings=list(dict.fromkeys(warnings)),
        previewPlan=candidate,
    )
    return ProposalResponse(command=command,proposals=[proposal])


def build_proposals(req:EditRequest)->ProposalResponse:
    normalized=normalize_arabic(req.command)
    if any(phrase in normalized for phrase in (
        "اعاده بناء الغرف",
        "اعاده بناء الفراغات",
        "استخرج الغرف من الجدران",
        "استخراج الغرف من الجدران",
        "ابن الغرف من الجدران",
    )):
        return build_room_rebuild_proposal(req.plan,req.command)

    merge=parse_merge_rooms(req.command,req.plan.rooms)
    if merge is not None:
        source,target=merge
        return build_merge_proposal(req.plan,source,target,req.command)

    # An explicitly named room always wins over a selected wall/opening context.
    explicit_target=find_target_room(req.command,req.plan.rooms)
    if explicit_target is not None:
        mpp=req.plan.metersPerPixel
        if not mpp or mpp<=0:
            return ProposalResponse(command=req.command,proposals=[],needsClarification="يجب تثبيت مقياس المخطط أولًا قبل تنفيذ تعديل بالمتر.")
        x1,y1,x2,y2=bbox(explicit_target)
        size=resolve_target_size(req.command,(x2-x1)*mpp,(y2-y1)*mpp)
        if size:
            return build_resize_proposals(req.plan,explicit_target,size[0],size[1],req.command)

    element_result=build_selected_element_proposals(req)
    if element_result is not None:
        return element_result

    target=explicit_target
    if target is None and req.target_room_id:
        target=next((room for room in req.plan.rooms if room.id==req.target_room_id),None)
    if target is None:
        names="، ".join(room.name for room in req.plan.rooms[:10])
        detail=f" الغرف المقروءة: {names}." if names else ""
        return ProposalResponse(command=req.command,proposals=[],needsClarification="لم أستطع تحديد العنصر المقصود بثقة."+detail)

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
            needsClarification="حدد المقاس مثل 5×4، أو قل: اجعل العرض 5 متر والعمق 4 متر، أو اختر جدارًا أو فتحة ثم اكتب التعديل المطلوب."
        )

    return build_resize_proposals(req.plan,target,size[0],size[1],req.command)
