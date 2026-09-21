import numpy as np

from app.pipeline import assemble_plan


def wall(wall_id,x1,y1,x2,y2,confidence=.95):
    return {
        "id":wall_id,
        "a":{"x":float(x1),"y":float(y1)},
        "b":{"x":float(x2),"y":float(y2)},
        "thicknessPx":10.0,
        "confidence":confidence,
        "reviewed":False,
        "provenance":"opencv",
    }


def room():
    return {
        "id":"room-1",
        "name":"غرفة",
        "polygon":[
            {"x":100.0,"y":100.0},
            {"x":500.0,"y":100.0},
            {"x":500.0,"y":500.0},
            {"x":100.0,"y":500.0},
        ],
        "confidence":.9,
        "areaM2":None,
        "boundaryWallIds":[],
        "reviewed":False,
        "provenance":"opencv",
    }


def complete_walls(confidence=.95):
    return [
        wall("top",100,100,500,100,confidence),
        wall("right",500,100,500,500,confidence),
        wall("bottom",100,500,500,500,confidence),
        wall("left",100,100,100,500,confidence),
    ]


def test_quality_rewards_wall_confidence_and_room_boundary_coverage():
    image=np.zeros((600,600,3),dtype=np.uint8)
    good=assemble_plan(
        image,"good","x.png","image/png",[],
        complete_walls(.95),[room()],None,None,
    )
    weak=assemble_plan(
        image,"weak","x.png","image/png",[],
        complete_walls(.35)[:2],[room()],None,None,
    )

    assert good["quality"]["walls"]>weak["quality"]["walls"]
    assert good["quality"]["rooms"]>weak["quality"]["rooms"]
    assert good["quality"]["overall"]>weak["quality"]["overall"]
    assert any("تغطية حدود" in item for item in weak["quality"]["warnings"])


def test_more_low_confidence_walls_do_not_artificially_create_high_quality():
    image=np.zeros((600,600,3),dtype=np.uint8)
    noisy=[
        wall(f"noise-{index}",20+index*10,20,20+index*10,580,.15)
        for index in range(20)
    ]
    plan=assemble_plan(
        image,"noisy","x.png","image/png",[],
        noisy,[],None,None,
    )
    assert plan["quality"]["walls"]<.40
    assert any("متوسط ثقة الجدران" in item for item in plan["quality"]["warnings"])



def test_quality_warns_when_pdf_vector_is_quarantined():
    image=np.zeros((600,600,3),dtype=np.uint8)
    suspicious=[
        {
            "id":"wall-vector-1",
            "a":{"x":100.0,"y":200.0},
            "b":{"x":500.0,"y":200.0},
            "thicknessPx":10.0,
            "confidence":.64,
            "reviewed":False,
            "provenance":"pdf-vector",
        }
    ]
    plan=assemble_plan(
        image,"vector-warning","x.pdf","application/pdf",[],
        suspicious,[],None,None,
    )
    assert any(
        "دون احتسابه كحد موثوق للغرف" in item
        for item in plan["quality"]["warnings"]
    )



def test_low_confidence_wall_cannot_inflate_room_boundary_quality():
    image=np.zeros((600,600,3),dtype=np.uint8)
    extracted_room=room()
    trusted=complete_walls(.95)[:2]
    fake=[
        wall("fake-bottom",100,500,500,500,.40),
        wall("fake-right",500,100,500,500,.40),
    ]
    mixed=assemble_plan(
        image,"mixed","x.png","image/png",[],
        [*trusted,*fake],[extracted_room],None,None,
    )
    only_trusted=assemble_plan(
        image,"trusted","x.png","image/png",[],
        trusted,[room()],None,None,
    )
    assert mixed["quality"]["rooms"]==only_trusted["quality"]["rooms"]
    assert any(
        "دون احتسابه كحد موثوق للغرف" in item
        for item in mixed["quality"]["warnings"]
    )
