import fitz

from app.edits import build_proposals
from app.local_analysis import analyze_document_bytes_local
from app.models import EditRequest,FloorPlan
from app.topology import canonicalize_plan
from app.validation import validate_plan


def synthetic_pdf_bytes():
    document=fitz.open()
    page=document.new_page(width=420,height=320)
    shape=page.new_shape()
    for a,b in [
        ((60,55),(360,55)),
        ((360,55),(360,265)),
        ((360,265),(60,265)),
        ((60,265),(60,55)),
        ((210,55),(210,265)),
    ]:
        shape.draw_line(a,b)
    shape.finish(width=8,color=(0,0,0))
    shape.commit()
    data=document.tobytes()
    document.close()
    return data


def test_core_e2e_analysis_preview_save_restore_cycle():
    analyzed=analyze_document_bytes_local(
        synthetic_pdf_bytes(),
        "application/pdf",
        project_id="e2e-project",
        filename="e2e.pdf",
    )
    plan=FloorPlan.model_validate(analyzed)
    assert len(plan.walls)>=4

    baseline_json=plan.model_dump_json()
    proposal_response=build_proposals(EditRequest(
        project_id=plan.id,
        command="إعادة بناء الغرف من الجدران",
        plan=plan,
    ))
    assert proposal_response.proposals

    preview=proposal_response.proposals[0].previewPlan
    canonical=canonicalize_plan(preview)
    report=validate_plan(canonical)
    assert not any(item.severity=="critical" for item in report.findings)

    saved_json=canonical.model_dump_json()
    saved=FloorPlan.model_validate_json(saved_json)
    assert saved.id==plan.id
    assert len(saved.walls)==len(canonical.walls)

    restored=FloorPlan.model_validate_json(baseline_json)
    assert restored.id==plan.id
    assert restored.model_dump()==plan.model_dump()



def synthetic_slanted_pdf_bytes():
    document=fitz.open()
    page=document.new_page(width=420,height=420)
    shape=page.new_shape()
    for a,b in [
        ((210,45),(375,210)),
        ((375,210),(210,375)),
        ((210,375),(45,210)),
        ((45,210),(210,45)),
    ]:
        shape.draw_line(a,b)
    shape.finish(width=9,color=(0,0,0))
    shape.commit()
    page.insert_text((180,210),"LIVING",fontsize=12)
    data=document.tobytes()
    document.close()
    return data


def test_core_e2e_preserves_slanted_pdf_geometry_into_room_topology():
    analyzed=analyze_document_bytes_local(
        synthetic_slanted_pdf_bytes(),
        "application/pdf",
        project_id="slanted-e2e",
        filename="slanted.pdf",
    )
    plan=FloorPlan.model_validate(analyzed)
    slanted=[
        wall for wall in plan.walls
        if abs(wall.b.x-wall.a.x)>80 and abs(wall.b.y-wall.a.y)>80
    ]
    assert len(slanted)>=4
    assert plan.rooms

    room=max(plan.rooms,key=lambda item:item.areaM2 or 0)
    xs={round(point.x) for point in room.polygon}
    ys={round(point.y) for point in room.polygon}
    assert len(xs)>=3
    assert len(ys)>=3
    assert len(room.boundaryWallIds)>=3
