from app.models import FloorPlan,Point,Quality,Room,Source
from app.validation import validate_plan


def base_plan():
    return FloorPlan(
        id="p1",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=0.01,
        calibrationConfidence=1,
        walls=[],
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
