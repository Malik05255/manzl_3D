from app.edits import build_proposals
from app.models import EditRequest,FloorPlan

def sample_plan():
    return FloorPlan.model_validate({
        "schemaVersion":1,"id":"p1","widthPx":900,"heightPx":600,"metersPerPixel":0.01,"calibrationConfidence":0.9,
        "walls":[{"id":"shared","a":{"x":400,"y":0},"b":{"x":400,"y":500},"thicknessPx":4,"confidence":0.9}],
        "rooms":[
            {"id":"bed","name":"غرفة النوم","polygon":[{"x":0,"y":0},{"x":400,"y":0},{"x":400,"y":500},{"x":0,"y":500}],"confidence":0.9,"areaM2":20},
            {"id":"hall","name":"الصالة","polygon":[{"x":400,"y":0},{"x":800,"y":0},{"x":800,"y":500},{"x":400,"y":500}],"confidence":0.9,"areaM2":20}
        ],
        "doors":[],"windows":[],"labels":[],
        "quality":{"overall":0.9,"walls":0.9,"rooms":0.9,"text":0.8,"dimensions":0.9,"needsCalibration":False,"warnings":[]},
        "source":{"fileName":"plan.png","mimeType":"image/png","page":1}
    })

def test_room_resize_creates_preview_and_moves_shared_wall():
    result=build_proposals(EditRequest(project_id="p1",command="عدل غرفة النوم إلى 5×5",plan=sample_plan()))
    assert result.proposals
    right=next(p for p in result.proposals if "اليمين" in p.title)
    bedroom=next(r for r in right.previewPlan.rooms if r.id=="bed")
    hall=next(r for r in right.previewPlan.rooms if r.id=="hall")
    assert max(p.x for p in bedroom.polygon)==500
    assert min(p.x for p in hall.polygon)==500
    assert right.previewPlan.walls[0].a.x==500
