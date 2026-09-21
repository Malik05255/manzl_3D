from app.models import FloorPlan,Point,Quality,Room,Source,Wall
from app.topology import canonicalize_plan,classify_wall_roles,link_room_boundaries,relink_plan_boundaries,room_boundary_coverage


def test_links_rectangular_room_to_four_nearby_walls():
    rooms=[{
        "id":"room-1","name":"غرفة","polygon":[
            {"x":110.0,"y":110.0},{"x":490.0,"y":110.0},
            {"x":490.0,"y":490.0},{"x":110.0,"y":490.0},
        ],"confidence":.9,"areaM2":14.44,
    }]
    walls=[
        {"id":"top","a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":100.0},"thicknessPx":10.0,"confidence":.9},
        {"id":"right","a":{"x":500.0,"y":100.0},"b":{"x":500.0,"y":500.0},"thicknessPx":10.0,"confidence":.9},
        {"id":"bottom","a":{"x":100.0,"y":500.0},"b":{"x":500.0,"y":500.0},"thicknessPx":10.0,"confidence":.9},
        {"id":"left","a":{"x":100.0,"y":100.0},"b":{"x":100.0,"y":500.0},"thicknessPx":10.0,"confidence":.9},
        {"id":"far","a":{"x":700.0,"y":100.0},"b":{"x":900.0,"y":100.0},"thicknessPx":10.0,"confidence":.9},
    ]
    link_room_boundaries(rooms,walls)
    assert set(rooms[0]["boundaryWallIds"])=={"top","right","bottom","left"}


def test_relink_removes_deleted_boundary_wall_reference():
    plan=FloorPlan(
        id="p",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=.01,
        calibrationConfidence=1,
        walls=[
            Wall(id="top",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=10,confidence=.9),
            Wall(id="left",a=Point(x=100,y=100),b=Point(x=100,y=500),thicknessPx=10,confidence=.9),
        ],
        rooms=[
            Room(
                id="r",name="غرفة",
                polygon=[Point(x=110,y=110),Point(x=490,y=110),Point(x=490,y=490),Point(x=110,y=490)],
                confidence=.9,areaM2=14.44,boundaryWallIds=["top","left","deleted"],
            )
        ],
        doors=[],windows=[],labels=[],
        quality=Quality(overall=.9,walls=.9,rooms=.9,text=.9,dimensions=.9,needsCalibration=False,warnings=[]),
        source=Source(fileName="x.png",mimeType="image/png",page=1),
    )
    relink_plan_boundaries(plan)
    assert set(plan.rooms[0].boundaryWallIds)=={"top","left"}


def test_classifies_shared_wall_as_interior_and_envelope_as_exterior():
    rooms=[
        {
            "id":"left","polygon":[
                {"x":110.0,"y":110.0},{"x":500.0,"y":110.0},{"x":500.0,"y":490.0},{"x":110.0,"y":490.0}
            ],"boundaryWallIds":["outer-left","shared"],
        },
        {
            "id":"right","polygon":[
                {"x":500.0,"y":110.0},{"x":890.0,"y":110.0},{"x":890.0,"y":490.0},{"x":500.0,"y":490.0}
            ],"boundaryWallIds":["shared","outer-right"],
        },
    ]
    walls=[
        {"id":"outer-left","a":{"x":100.0,"y":100.0},"b":{"x":100.0,"y":500.0},"thicknessPx":10.0,"confidence":.9},
        {"id":"shared","a":{"x":500.0,"y":100.0},"b":{"x":500.0,"y":500.0},"thicknessPx":10.0,"confidence":.9},
        {"id":"outer-right","a":{"x":900.0,"y":100.0},"b":{"x":900.0,"y":500.0},"thicknessPx":10.0,"confidence":.9},
    ]
    classify_wall_roles(walls,rooms)
    by_id={wall["id"]:wall for wall in walls}
    assert by_id["shared"]["role"]=="interior"
    assert by_id["shared"]["locked"] is False
    assert by_id["outer-left"]["role"]=="exterior"
    assert by_id["outer-left"]["locked"] is True
    assert by_id["outer-right"]["role"]=="exterior"
    assert by_id["outer-right"]["locked"] is True


def test_canonicalize_refreshes_area_and_boundaries_without_overwriting_user_metadata():
    plan=FloorPlan(
        id="p",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=.01,
        calibrationConfidence=1,
        walls=[
            Wall(id="top",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=10,confidence=.9,role="structural",locked=True,reviewed=True,provenance="mixed"),
            Wall(id="right",a=Point(x=500,y=100),b=Point(x=500,y=500),thicknessPx=10,confidence=.9),
            Wall(id="bottom",a=Point(x=100,y=500),b=Point(x=500,y=500),thicknessPx=10,confidence=.9),
            Wall(id="left",a=Point(x=100,y=100),b=Point(x=100,y=500),thicknessPx=10,confidence=.9),
        ],
        rooms=[
            Room(
                id="r",name="غرفة",
                polygon=[Point(x=110,y=110),Point(x=490,y=110),Point(x=490,y=490),Point(x=110,y=490)],
                confidence=.9,areaM2=999,boundaryWallIds=["deleted"],reviewed=True,provenance="mixed",
            )
        ],
        doors=[],windows=[],labels=[],
        quality=Quality(overall=.9,walls=.9,rooms=.9,text=.9,dimensions=.9,needsCalibration=False,warnings=[]),
        source=Source(fileName="x.png",mimeType="image/png",page=1),
    )

    canonical=canonicalize_plan(plan)

    assert canonical.rooms[0].areaM2==14.44
    assert set(canonical.rooms[0].boundaryWallIds)=={"top","right","bottom","left"}
    assert canonical.rooms[0].reviewed is True
    assert canonical.rooms[0].provenance=="mixed"
    top=next(wall for wall in canonical.walls if wall.id=="top")
    assert top.role=="structural"
    assert top.locked is True
    assert top.reviewed is True
    assert top.provenance=="mixed"
    assert plan.rooms[0].areaM2==999
    assert plan.rooms[0].boundaryWallIds==["deleted"]


def test_boundary_coverage_detects_missing_room_sides():
    room={
        "id":"room-1","name":"غرفة","polygon":[
            {"x":110.0,"y":110.0},{"x":490.0,"y":110.0},
            {"x":490.0,"y":490.0},{"x":110.0,"y":490.0},
        ],"boundaryWallIds":[],
    }
    complete=[
        {"id":"top","a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":100.0},"thicknessPx":10.0},
        {"id":"right","a":{"x":500.0,"y":100.0},"b":{"x":500.0,"y":500.0},"thicknessPx":10.0},
        {"id":"bottom","a":{"x":100.0,"y":500.0},"b":{"x":500.0,"y":500.0},"thicknessPx":10.0},
        {"id":"left","a":{"x":100.0,"y":100.0},"b":{"x":100.0,"y":500.0},"thicknessPx":10.0},
    ]
    assert room_boundary_coverage(room,complete)>.95
    assert room_boundary_coverage(room,complete[:2])<.60


def test_canonicalize_clears_stale_dimension_references():
    from app.models import Dimension
    plan=plan_with_two_rooms()
    plan.dimensions=[Dimension(
        id="dimension-1",
        sourceLabelId="missing-label",
        text="4.20 m",
        center=Point(x=250,y=80),
        valueM=4.2,
        unit="m",
        orientation="horizontal",
        referenceWallId="missing-wall",
        confidence=.9,
        provenance="ocr",
    )]
    canonical=canonicalize_plan(plan)
    assert canonical.dimensions[0].referenceWallId is None
    assert canonical.dimensions[0].orientation=="unknown"
    assert canonical.dimensions[0].sourceLabelId is None
