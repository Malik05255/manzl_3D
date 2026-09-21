from __future__ import annotations
from itertools import product
from uuid import uuid4

from .commands import find_target_room,parse_target_size
from .edit_geometry import apply_side,bbox
from .models import EditRequest,Impact,Proposal,ProposalResponse

def build_proposals(req:EditRequest)->ProposalResponse:
    size=parse_target_size(req.command)
    if not size:
        return ProposalResponse(command=req.command,proposals=[],needsClarification="حدد المقاس بصيغة مثل 5×5.")

    target=find_target_room(req.command,req.plan.rooms)
    if target is None:
        return ProposalResponse(command=req.command,proposals=[],needsClarification="لم أستطع تحديد الغرفة المقصودة بثقة. اذكر اسمها كما يظهر في المخطط.")

    mpp=req.plan.metersPerPixel
    if not mpp or mpp<=0:
        return ProposalResponse(command=req.command,proposals=[],needsClarification="يجب تثبيت مقياس المخطط أولًا قبل تنفيذ تعديل بالمتر.")

    x1,y1,x2,y2=bbox(target)
    current_w=(x2-x1)*mpp; current_h=(y2-y1)*mpp
    target_w,target_h=size
    dx=(target_w-current_w)/mpp; dy=(target_h-current_h)/mpp
    x_sides=[None] if abs(target_w-current_w)<=0.03 else ["right","left"]
    y_sides=[None] if abs(target_h-current_h)<=0.03 else ["bottom","top"]
    direction={"right":"اليمين","left":"اليسار","bottom":"الأسفل","top":"الأعلى"}

    proposals=[]
    for x_side,y_side in product(x_sides,y_sides):
        plan=req.plan.model_copy(deep=True)
        room=next(r for r in plan.rooms if r.id==target.id)
        impacts=[]; affected=[]; valid=True

        if x_side:
            valid,changes,name=apply_side(plan,room,x_side,dx,mpp)
            impacts.extend(changes)
            if name: affected.append(name)
        if valid and y_side:
            valid,changes,name=apply_side(plan,room,y_side,dy,mpp)
            impacts.extend(changes)
            if name: affected.append(name)
        if not valid: continue

        affected=list(dict.fromkeys(affected))
        dirs=" + ".join(direction[s] for s in (x_side,y_side) if s) or "بدون تحريك"
        summary=f"تصبح {target.name} {target_w:g}×{target_h:g} م"
        if affected: summary+=f" مع تعديل {' و'.join(affected)}"
        plan.quality.warnings=list(dict.fromkeys([*plan.quality.warnings,"راجع الأبواب ومسارات الحركة بصريًا قبل اعتماد التعديل."]))
        proposals.append(Proposal(
            id=str(uuid4()),title=f"التعديل باتجاه {dirs}",summary=summary,
            confidence=max(0.55,min(0.95,req.plan.quality.overall)),
            impacts=[Impact(kind="room_resize",text=f"تغيير {target.name} من {current_w:.2f}×{current_h:.2f} م إلى {target_w:g}×{target_h:g} م"),*impacts],
            warnings=[],previewPlan=plan
        ))
        if len(proposals)>=4: break

    if not proposals:
        return ProposalResponse(command=req.command,proposals=[],needsClarification="لا توجد مساحة مجاورة كافية لتنفيذ المقاس المطلوب دون تغيير حدود المبنى.")
    return ProposalResponse(command=req.command,proposals=proposals)
