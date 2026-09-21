from app.models import FloorPlan,Point,Quality,Room,Source,Wall
from app.topology import link_room_boundaries,relink_plan_boundaries


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
