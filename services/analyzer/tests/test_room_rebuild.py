from app.edits import build_proposals
from app.models import EditRequest,FloorPlan,Point,Quality,Room,Source,Wall
from app.room_rebuild import build_room_rebuild_proposal


def plan_with_stale_single_room():
    return FloorPlan(
        id="p",
        widthPx=600,
        heightPx=400,
        metersPerPixel=.01,
        calibrationConfidence=1,
        walls=[
            Wall(id="top",a=Point(x=100,y=80),b=Point(x=500,y=80),thicknessPx=10,confidence=.95,reviewed=True,provenance="manual"),
            Wall(id="bottom",a=Point(x=100,y=320),b=Point(x=500,y=320),thicknessPx=10,confidence=.95,reviewed=True,provenance="manual"),
            Wall(id="left",a=Point(x=100,y=80),b=Point(x=100,y=320),thicknessPx=10,confidence=.95,reviewed=True,provenance="manual"),
            Wall(id="right",a=Point(x=500,y=80),b=Point(x=500,y=320),thicknessPx=10,confidence=.95,reviewed=True,provenance="manual"),
            Wall(id="split",a=Point(x=300,y=80),b=Point(x=300,y=320),thicknessPx=10,confidence=.95,reviewed=True,provenance="manual"),
        ],
        rooms=[
            Room(
                id="room-old",
                name="غرفة كبيرة",
                polygon=[Point(x=100,y=80),Point(x=500,y=80),Point(x=500,y=320),Point(x=100,y=320)],
                confidence=.9,
                areaM2=9.6,
                reviewed=True,
                provenance="mixed",
            )
        ],
        doors=[],
        windows=[],
        labels=[],
        dimensions=[],
        quality=Quality(overall=.9,walls=.95,rooms=.8,text=.7,dimensions=.7,needsCalibration=False,warnings=[]),
        source=Source(fileName="plan.png",mimeType="image/png",page=1),
    )


def test_room_rebuild_detects_split_closed_spaces():
    plan=plan_with_stale_single_room()
    response=build_room_rebuild_proposal(plan,"إعادة بناء الغرف من الجدران")
    assert response.proposals
    preview=response.proposals[0].previewPlan
    assert len(preview.rooms)==2
    assert any(room.id=="room-old" for room in preview.rooms)
    assert all(room.boundaryWallIds for room in preview.rooms)
    assert all(room.reviewed is False for room in preview.rooms)


def test_room_rebuild_command_is_available_through_engineer():
    plan=plan_with_stale_single_room()
    response=build_proposals(EditRequest(
        project_id="p",
        command="إعادة بناء الغرف من الجدران",
        plan=plan,
    ))
    assert response.proposals
    assert response.proposals[0].id.startswith("rebuild-rooms:")


def test_room_rebuild_requires_enough_wall_geometry():
    plan=plan_with_stale_single_room()
    plan.walls=plan.walls[:2]
    response=build_room_rebuild_proposal(plan,"إعادة بناء الغرف من الجدران")
    assert not response.proposals
    assert "جدران كافية" in (response.needsClarification or "")
