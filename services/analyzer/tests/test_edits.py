from app.commands import parse_target_size
from app.edits import build_proposals
from app.models import EditRequest,FloorPlan,Point,Quality,Room,Source,Wall


def sample_plan(scale=0.01):
    return FloorPlan(
        id="project-1",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=scale,
        calibrationConfidence=0.9 if scale else None,
        walls=[
            Wall(id="w1",a=Point(x=500,y=100),b=Point(x=500,y=500),thicknessPx=4,confidence=0.9)
        ],
        rooms=[
            Room(
                id="bed",
                name="غرفة النوم",
                polygon=[Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=500),Point(x=100,y=500)],
                confidence=0.95,
                areaM2=16,
            ),
            Room(
                id="hall",
                name="الصالة",
                polygon=[Point(x=500,y=100),Point(x=900,y=100),Point(x=900,y=500),Point(x=500,y=500)],
                confidence=0.95,
                areaM2=16,
            ),
        ],
        doors=[],
        windows=[],
        labels=[],
        quality=Quality(overall=0.9,walls=0.9,rooms=0.9,text=0.9,dimensions=0.9,needsCalibration=scale is None,warnings=[]),
        source=Source(fileName="plan.png",mimeType="image/png",page=1),
    )


def room_width(room,scale):
    xs=[point.x for point in room.polygon]
    return (max(xs)-min(xs))*scale


def test_arabic_digits_are_understood():
    assert parse_target_size("عدل غرفة النوم إلى ٥×٥") == (5.0,5.0)


def test_resize_builds_visible_preview_and_shrinks_neighbor():
    request=EditRequest(project_id="project-1",command="عدل غرفة النوم إلى 5×4",plan=sample_plan())
    response=build_proposals(request)
    assert response.needsClarification is None
    assert response.proposals
    preview=response.proposals[0].previewPlan
    bed=next(room for room in preview.rooms if room.id=="bed")
    hall=next(room for room in preview.rooms if room.id=="hall")
    assert round(room_width(bed,0.01),2)==5.0
    assert round(room_width(hall,0.01),2)==3.0
    assert any("الصالة" in impact.text for impact in response.proposals[0].impacts)


def test_metric_edit_requires_calibration():
    request=EditRequest(project_id="project-1",command="عدل غرفة النوم إلى 5×4",plan=sample_plan(None))
    response=build_proposals(request)
    assert not response.proposals
    assert "مقياس" in (response.needsClarification or "")
