import math

from app.edits import build_proposals
from app.models import EditRequest,FloorPlan,Opening,Point,Quality,Room,Source,Wall


def sample_plan():
    return FloorPlan(
        id="p1",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=0.01,
        calibrationConfidence=1,
        walls=[
            Wall(id="left",a=Point(x=100,y=100),b=Point(x=100,y=500),thicknessPx=10,confidence=.95),
            Wall(id="shared",a=Point(x=500,y=100),b=Point(x=500,y=500),thicknessPx=10,confidence=.95),
            Wall(id="right",a=Point(x=900,y=100),b=Point(x=900,y=500),thicknessPx=10,confidence=.95),
            Wall(id="top-left",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=10,confidence=.95),
            Wall(id="top-right",a=Point(x=500,y=100),b=Point(x=900,y=100),thicknessPx=10,confidence=.95),
            Wall(id="bottom-left",a=Point(x=100,y=500),b=Point(x=500,y=500),thicknessPx=10,confidence=.95),
            Wall(id="bottom-right",a=Point(x=500,y=500),b=Point(x=900,y=500),thicknessPx=10,confidence=.95),
        ],
        rooms=[
            Room(
                id="bed",name="غرفة النوم",
                polygon=[Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=500),Point(x=100,y=500)],
                confidence=.95,areaM2=16,
            ),
            Room(
                id="hall",name="الصالة",
                polygon=[Point(x=500,y=100),Point(x=900,y=100),Point(x=900,y=500),Point(x=500,y=500)],
                confidence=.95,areaM2=16,
            ),
        ],
        doors=[
            Opening(id="door-1",kind="door",wallId="top-left",a=Point(x=200,y=100),b=Point(x=290,y=100),confidence=.95)
        ],
        windows=[],
        labels=[],
        quality=Quality(overall=.95,walls=.95,rooms=.95,text=.9,dimensions=.95,needsCalibration=False,warnings=[]),
        source=Source(fileName="plan.png",mimeType="image/png",page=1),
    )


def opening_width_m(plan,opening_id):
    opening=next(item for item in [*plan.doors,*plan.windows] if item.id==opening_id)
    return math.hypot(opening.b.x-opening.a.x,opening.b.y-opening.a.y)*plan.metersPerPixel


def test_selected_opening_width_command_builds_preview():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="اجعل عرضه 1.2 متر",target_opening_id="door-1",plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    assert round(opening_width_m(preview,"door-1"),2)==1.2
    assert response.proposals[0].id.startswith("opening-width:")


def test_selected_opening_move_command_moves_along_wall():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="حركه يمين 30 سم",target_opening_id="door-1",plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    opening=next(item for item in preview.doors if item.id=="door-1")
    assert round(opening.a.x-plan.doors[0].a.x,1)==30.0
    assert opening.a.y==100


def test_selected_opening_delete_command_removes_only_opening():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="احذفه",target_opening_id="door-1",plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    assert not preview.doors
    assert len(preview.rooms)==2
    assert len(preview.walls)==7


def test_selected_wall_thickness_command_is_metric():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="اجعل سماكته 20 سم",target_wall_id="shared",plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    wall=next(item for item in preview.walls if item.id=="shared")
    assert round(wall.thicknessPx*preview.metersPerPixel*100,1)==20.0


def test_selected_wall_add_window_uses_free_slot():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="اضف نافذة",target_wall_id="top-left",plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    assert len(preview.windows)==1
    window=preview.windows[0]
    assert window.wallId=="top-left"
    assert opening_width_m(preview,window.id)>0.5


def test_selected_shared_wall_move_updates_rooms_and_connected_walls():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="حركه يمين 50 سم",target_wall_id="shared",plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    shared=next(item for item in preview.walls if item.id=="shared")
    top_left=next(item for item in preview.walls if item.id=="top-left")
    top_right=next(item for item in preview.walls if item.id=="top-right")
    bed=next(item for item in preview.rooms if item.id=="bed")
    hall=next(item for item in preview.rooms if item.id=="hall")
    assert shared.a.x==550
    assert top_left.b.x==550
    assert top_right.a.x==550
    assert bed.areaM2==18
    assert hall.areaM2==14


def test_incompatible_wall_direction_requires_clarification():
    plan=sample_plan()
    response=build_proposals(EditRequest(
        project_id="p1",command="حركه فوق 20 سم",target_wall_id="shared",plan=plan,
    ))
    assert not response.proposals
    assert response.needsClarification


def test_low_confidence_opening_requires_confirmation():
    plan=sample_plan()
    plan.doors[0].confidence=.60
    response=build_proposals(EditRequest(
        project_id="p1",command="اجعل عرضه 1 متر",target_opening_id="door-1",plan=plan,
    ))
    assert not response.proposals
    assert "منخفضة الثقة" in (response.needsClarification or "")


def test_low_confidence_wall_requires_confirmation():
    plan=sample_plan()
    wall=next(item for item in plan.walls if item.id=="shared")
    wall.confidence=.50
    response=build_proposals(EditRequest(
        project_id="p1",command="حركه يمين 20 سم",target_wall_id="shared",plan=plan,
    ))
    assert not response.proposals
    assert "منخفضة الثقة" in (response.needsClarification or "")


def test_reviewed_low_confidence_wall_can_be_edited():
    plan=sample_plan()
    wall=next(item for item in plan.walls if item.id=="shared")
    wall.confidence=.50
    wall.reviewed=True
    response=build_proposals(EditRequest(
        project_id="p1",command="حركه يمين 20 سم",target_wall_id="shared",plan=plan,
    ))
    assert response.proposals


def test_reviewed_low_confidence_opening_can_be_edited():
    plan=sample_plan()
    plan.doors[0].confidence=.60
    plan.doors[0].reviewed=True
    response=build_proposals(EditRequest(
        project_id="p1",command="اجعل عرضه 1 متر",target_opening_id="door-1",plan=plan,
    ))
    assert response.proposals


def test_opening_geometry_edit_preserves_review_metadata():
    plan=sample_plan()
    plan.doors[0].confidence=.60
    plan.doors[0].reviewed=True
    plan.doors[0].provenance="opencv"
    response=build_proposals(EditRequest(
        project_id="p1",command="اجعل عرضه 1 متر",target_opening_id="door-1",plan=plan,
    ))
    assert response.proposals
    opening=response.proposals[0].previewPlan.doors[0]
    assert opening.reviewed is True
    assert opening.provenance=="opencv"
