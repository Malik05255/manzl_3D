from app.models import FloorPlan,Point,Quality,Room,Source
from app.validation import validate_plan


def base_plan():
    return FloorPlan(
        id="p1",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=0.01,
        calibrationConfidence=1,
        walls=[
            __import__("app.models",fromlist=["Wall"]).Wall(id="left",a=Point(x=100,y=100),b=Point(x=100,y=500),thicknessPx=10,confidence=.9),
            __import__("app.models",fromlist=["Wall"]).Wall(id="top",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=10,confidence=.9),
            __import__("app.models",fromlist=["Wall"]).Wall(id="bottom-left",a=Point(x=100,y=500),b=Point(x=500,y=500),thicknessPx=10,confidence=.9),
            __import__("app.models",fromlist=["Wall"]).Wall(id="shared",a=Point(x=500,y=100),b=Point(x=500,y=500),thicknessPx=10,confidence=.9),
            __import__("app.models",fromlist=["Wall"]).Wall(id="top-right",a=Point(x=500,y=100),b=Point(x=900,y=100),thicknessPx=10,confidence=.9),
            __import__("app.models",fromlist=["Wall"]).Wall(id="bottom-right",a=Point(x=500,y=500),b=Point(x=900,y=500),thicknessPx=10,confidence=.9),
            __import__("app.models",fromlist=["Wall"]).Wall(id="right",a=Point(x=900,y=100),b=Point(x=900,y=500),thicknessPx=10,confidence=.9),
        ],
        rooms=[
            Room(
                id="a",
                name="غرفة نوم",
                polygon=[Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=500),Point(x=100,y=500)],
                confidence=.9,
                areaM2=16,
            ),
            Room(
                id="b",
                name="الصالة",
                polygon=[Point(x=500,y=100),Point(x=900,y=100),Point(x=900,y=500),Point(x=500,y=500)],
                confidence=.9,
                areaM2=16,
            ),
        ],
        doors=[],
        windows=[],
        labels=[],
        quality=Quality(overall=.9,walls=.9,rooms=.9,text=.9,dimensions=.9,needsCalibration=False,warnings=[]),
        source=Source(fileName="x.png",mimeType="image/png",page=1),
    )


def test_clean_rectangular_plan_has_no_critical_findings():
    report=validate_plan(base_plan())
    assert not any(item.severity=="critical" for item in report.findings)
    assert report.score>0.7


def test_overlapping_rooms_are_critical():
    plan=base_plan()
    plan.rooms[1].polygon=[
        Point(x=450,y=100),Point(x=850,y=100),Point(x=850,y=500),Point(x=450,y=500)
    ]
    report=validate_plan(plan)
    assert any(item.code=="rooms_overlap" and item.severity=="critical" for item in report.findings)


def test_narrow_bedroom_is_warned():
    plan=base_plan()
    plan.rooms[0].polygon=[
        Point(x=100,y=100),Point(x=300,y=100),Point(x=300,y=500),Point(x=100,y=500)
    ]
    report=validate_plan(plan)
    assert any(item.code=="room_clear_span_low" for item in report.findings)


def test_collapsed_wall_is_critical_and_targeted():
    plan=base_plan()
    from app.models import Wall
    plan.walls=[Wall(id="bad-wall",a=Point(x=100,y=100),b=Point(x=100.5,y=100.5),thicknessPx=8,confidence=.9)]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="wall_collapsed")
    assert finding.severity=="critical"
    assert finding.wallIds==["bad-wall"]


def test_detached_opening_points_to_wall_and_opening():
    from app.models import Opening,Wall
    plan=base_plan()
    plan.walls=[Wall(id="wall-1",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=8,confidence=.9)]
    plan.doors=[Opening(
        id="door-1",kind="door",wallId="wall-1",
        a=Point(x=180,y=180),b=Point(x=270,y=180),confidence=.9,
    )]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="opening_detached")
    assert finding.wallIds==["wall-1"]
    assert finding.openingIds==["door-1"]


def test_overlapping_openings_are_warned():
    from app.models import Opening,Wall
    plan=base_plan()
    plan.walls=[Wall(id="wall-1",a=Point(x=100,y=100),b=Point(x=600,y=100),thicknessPx=8,confidence=.9)]
    plan.doors=[
        Opening(id="door-1",kind="door",wallId="wall-1",a=Point(x=180,y=100),b=Point(x=300,y=100),confidence=.9),
        Opening(id="door-2",kind="door",wallId="wall-1",a=Point(x=250,y=100),b=Point(x=360,y=100),confidence=.9),
    ]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="openings_overlap")
    assert set(finding.openingIds)=={"door-1","door-2"}


def test_area_mismatch_is_warned_for_changed_room_geometry():
    plan=base_plan()
    plan.rooms[0].areaM2=40
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="room_area_mismatch")
    assert finding.roomIds==["a"]


def test_self_intersecting_room_is_critical():
    plan=base_plan()
    plan.rooms[0].polygon=[
        Point(x=100,y=100),Point(x=500,y=500),Point(x=500,y=100),Point(x=100,y=500)
    ]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="room_self_intersection")
    assert finding.severity=="critical"
    assert finding.roomIds==["a"]


def test_irregular_room_overlap_is_critical():
    plan=base_plan()
    plan.rooms=[
        Room(
            id="l",
            name="غرفة L",
            polygon=[
                Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=300),
                Point(x=300,y=300),Point(x=300,y=500),Point(x=100,y=500),
            ],
            confidence=.9,
            areaM2=12,
        ),
        Room(
            id="b",
            name="غرفة متداخلة",
            polygon=[
                Point(x=250,y=250),Point(x=650,y=250),Point(x=650,y=450),Point(x=250,y=450),
            ],
            confidence=.9,
            areaM2=8,
        ),
    ]
    report=validate_plan(plan)
    assert any(item.code=="rooms_overlap" and item.severity=="critical" for item in report.findings)


def test_irregular_rooms_sharing_boundary_are_not_overlap():
    plan=base_plan()
    plan.rooms=[
        Room(
            id="l",
            name="غرفة L",
            polygon=[
                Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=300),
                Point(x=300,y=300),Point(x=300,y=500),Point(x=100,y=500),
            ],
            confidence=.9,
            areaM2=12,
        ),
        Room(
            id="adj",
            name="غرفة مجاورة",
            polygon=[
                Point(x=500,y=100),Point(x=800,y=100),Point(x=800,y=300),Point(x=500,y=300),
            ],
            confidence=.9,
            areaM2=6,
        ),
    ]
    report=validate_plan(plan)
    assert not any(item.code=="rooms_overlap" for item in report.findings)


def test_missing_room_boundary_wall_is_critical():
    plan=base_plan()
    plan.rooms[0].boundaryWallIds=["missing-wall"]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="room_boundary_wall_missing")
    assert finding.severity=="critical"
    assert finding.roomIds==["a"]
    assert finding.wallIds==["missing-wall"]


def test_incomplete_room_boundary_emits_warning():
    from app.models import Wall
    plan=base_plan()
    plan.walls=[
        Wall(id="top",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=10,confidence=.9),
        Wall(id="left",a=Point(x=100,y=100),b=Point(x=100,y=500),thicknessPx=10,confidence=.9),
    ]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="room_boundary_incomplete" and "a" in item.roomIds)
    assert finding.severity=="warning"
    assert finding.roomIds==["a"]


def test_source_dimension_mismatch_is_warning():
    from app.models import Dimension
    plan=base_plan()
    plan.dimensions=[Dimension(
        id="dimension-1",
        text="5.00 m",
        center=Point(x=300,y=80),
        valueM=5.0,
        unit="m",
        orientation="horizontal",
        referenceWallId="top",
        confidence=.95,
        provenance="pdf-text",
    )]
    report=validate_plan(plan)
    finding=next(item for item in report.findings if item.code=="source_dimension_mismatch")
    assert finding.severity=="warning"
    assert finding.wallIds==["top"]


def test_matching_source_dimension_does_not_warn():
    from app.models import Dimension
    plan=base_plan()
    wall=next(item for item in plan.walls if item.id=="top")
    expected=((wall.b.x-wall.a.x)**2+(wall.b.y-wall.a.y)**2)**0.5*plan.metersPerPixel
    plan.dimensions=[Dimension(
        id="dimension-1",
        text=f"{expected:.2f} m",
        center=Point(x=300,y=80),
        valueM=expected,
        unit="m",
        orientation="horizontal",
        referenceWallId="top",
        confidence=.95,
        provenance="pdf-text",
    )]
    report=validate_plan(plan)
    assert not any(item.code=="source_dimension_mismatch" for item in report.findings)
