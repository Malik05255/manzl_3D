import fitz

from app.benchmark import evaluate_floor_plan
from app.document import PDF_RENDER_SCALE
from app.local_analysis import analyze_document_bytes_local


def _pdf_bytes(lines:list[tuple[tuple[float,float],tuple[float,float]]],size=(420,320),text=None):
    document=fitz.open()
    page=document.new_page(width=size[0],height=size[1])
    shape=page.new_shape()
    for a,b in lines:
        shape.draw_line(a,b)
    shape.finish(width=8,color=(0,0,0))
    shape.commit()
    if text:
        page.insert_text(text[0],text[1],fontsize=12)
    data=document.tobytes()
    document.close()
    return data


def _segment(a,b):
    return {
        "a":{"x":a[0]*PDF_RENDER_SCALE,"y":a[1]*PDF_RENDER_SCALE},
        "b":{"x":b[0]*PDF_RENDER_SCALE,"y":b[1]*PDF_RENDER_SCALE},
    }


def _polygon(points):
    return {
        "polygon":[
            {"x":x*PDF_RENDER_SCALE,"y":y*PDF_RENDER_SCALE}
            for x,y in points
        ]
    }


def test_orthogonal_extraction_regression_gate():
    lines=[
        ((60,55),(360,55)),
        ((360,55),(360,265)),
        ((360,265),(60,265)),
        ((60,265),(60,55)),
        ((210,55),(210,265)),
    ]
    prediction=analyze_document_bytes_local(
        _pdf_bytes(lines),
        "application/pdf",
        project_id="regression-orthogonal",
        filename="orthogonal.pdf",
    )
    truth={
        "walls":[_segment(a,b) for a,b in lines],
        "rooms":[
            _polygon([(64,59),(206,59),(206,261),(64,261)]),
            _polygon([(214,59),(356,59),(356,261),(214,261)]),
        ],
        "doors":[],
        "windows":[],
        "dimensions":[],
    }
    report=evaluate_floor_plan(
        prediction,truth,
        tolerance_px=18,
        room_iou_threshold=.70,
    )
    assert report["walls"]["f1"]>=.80,report
    assert report["rooms"]["f1"]>=.80,report
    assert report["macroF1"]>=.90,report


def test_slanted_extraction_regression_gate():
    lines=[
        ((210,45),(375,210)),
        ((375,210),(210,375)),
        ((210,375),(45,210)),
        ((45,210),(210,45)),
    ]
    prediction=analyze_document_bytes_local(
        _pdf_bytes(lines,size=(420,420),text=((180,210),"LIVING")),
        "application/pdf",
        project_id="regression-slanted",
        filename="slanted.pdf",
    )
    truth={
        "walls":[_segment(a,b) for a,b in lines],
        "rooms":[_polygon([(210,53),(367,210),(210,367),(53,210)])],
        "doors":[],
        "windows":[],
        "dimensions":[],
    }
    report=evaluate_floor_plan(
        prediction,truth,
        tolerance_px=20,
        room_iou_threshold=.68,
    )
    assert report["walls"]["f1"]>=.80,report
    assert report["rooms"]["f1"]>=.80,report
    assert report["macroF1"]>=.90,report



def test_dimension_line_does_not_split_room_topology():
    document=fitz.open()
    page=document.new_page(width=420,height=320)

    shell=page.new_shape()
    for a,b in [
        ((60,55),(360,55)),
        ((360,55),(360,265)),
        ((360,265),(60,265)),
        ((60,265),(60,55)),
    ]:
        shell.draw_line(a,b)
    shell.finish(width=8,color=(0,0,0))
    shell.commit()

    dimension=page.new_shape()
    dimension.draw_line((60,160),(360,160))
    dimension.finish(width=1,color=(0,0,0))
    dimension.commit()
    page.insert_text((185,150),"4.00 m",fontsize=11)

    data=document.tobytes()
    document.close()
    prediction=analyze_document_bytes_local(
        data,
        "application/pdf",
        project_id="dimension-quarantine",
        filename="dimension-line.pdf",
    )

    assert any(
        dimension.get("valueM") is not None
        and abs(float(dimension["valueM"])-4.0)<.01
        for dimension in prediction.get("dimensions",[])
    ),prediction.get("dimensions",[])
    assert len(prediction["rooms"])==1,prediction["rooms"]

    boundary_ids=set(prediction["rooms"][0].get("boundaryWallIds",[]))
    boundary_walls=[
        wall for wall in prediction["walls"]
        if wall["id"] in boundary_ids
    ]
    assert not any(
        abs(wall["a"]["y"]-wall["b"]["y"])<4
        and abs(((wall["a"]["y"]+wall["b"]["y"])/2)-(160*PDF_RENDER_SCALE))<24
        for wall in boundary_walls
    ),boundary_walls
