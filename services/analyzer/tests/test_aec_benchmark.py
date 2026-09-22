import app.aec_benchmark as benchmark_module
import numpy as np
import json
import xml.etree.ElementTree as ET

from app.aec_benchmark import _write_gt_subset,parse_official_score_output,plan_to_aec_prediction,run_dataset,run_official_scorer


def test_floorplan_converts_to_aec_prediction_frame():
    plan={
        "widthPx":1000,
        "heightPx":500,
        "walls":[
            {
                "id":"w",
                "a":{"x":100.0,"y":100.0},
                "b":{"x":900.0,"y":100.0},
                "thicknessPx":20.0,
            }
        ],
        "rooms":[
            {
                "id":"r",
                "polygon":[
                    {"x":100.0,"y":100.0},
                    {"x":900.0,"y":100.0},
                    {"x":900.0,"y":400.0},
                    {"x":100.0,"y":400.0},
                ],
            }
        ],
        "doors":[
            {
                "id":"d",
                "a":{"x":300.0,"y":100.0},
                "b":{"x":400.0,"y":100.0},
            }
        ],
        "windows":[
            {
                "id":"x",
                "a":{"x":600.0,"y":100.0},
                "b":{"x":750.0,"y":100.0},
            }
        ],
        "symbols":[
            {
                "id":"fixture",
                "kind":"toilet",
                "a":{"x":700.0,"y":250.0},
                "b":{"x":760.0,"y":330.0},
                "confidence":.95,
            }
        ],
    }
    prediction=plan_to_aec_prediction(plan,sheet="sheet_01",width=2000,height=1000)
    assert prediction["sheet"]=="sheet_01"
    assert {item["class"] for item in prediction["objects"]}=={"Single Swing Door","Window","Toilet"}
    assert prediction["areas"][0][0]==[200.0,200.0]
    assert len(prediction["walls"][0])==4
    assert prediction["objects"][0]["bbox"][0]<600


def test_slanted_wall_becomes_polygon_not_axis_line():
    plan={
        "widthPx":500,
        "heightPx":500,
        "walls":[
            {
                "id":"diag",
                "a":{"x":100.0,"y":100.0},
                "b":{"x":400.0,"y":400.0},
                "thicknessPx":12.0,
            }
        ],
        "rooms":[],
        "doors":[],
        "windows":[],
    }
    prediction=plan_to_aec_prediction(plan,sheet="sheet",width=500,height=500)
    polygon=prediction["walls"][0]
    assert len(polygon)==4
    assert len({round(point[0],3) for point in polygon})==4
    assert len({round(point[1],3) for point in polygon})==4


def test_parses_official_aec_score_summary():
    output="""
Manzil H on AEC-Geometric-Bench-15

Single Swing Door      600      20     29   0.968   0.954   0.961
OBJECT MICRO           1500     96    132   0.940   0.919   0.929

wall pixel                                  0.954   0.908   0.931
area pixel                                  0.990   0.985   0.987
area instance                               0.961   0.921   0.940
"""
    report=parse_official_score_output(output)
    assert report["objectMicro"]=={
        "precision":.94,"recall":.919,"f1":.929,
        "tp":1500,"fp":96,"fn":132,
    }
    assert report["wallPixel"]["f1"]==.931
    assert report["areaPixel"]["f1"]==.987
    assert report["areaInstance"]["f1"]==.94
    assert report["macroF1"]==.9467
    assert report["classes"]["Single Swing Door"]["tp"]==600
    assert report["classes"]["Single Swing Door"]["f1"]==.961


def test_double_swing_door_maps_to_official_aec_class():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[{
            "id":"d1","kind":"door","doorSubtype":"double_swing",
            "a":{"x":100.0,"y":100.0},"b":{"x":200.0,"y":100.0},"confidence":.9,
        }],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    assert prediction["objects"][0]["class"]=="Double Swing Door"


def test_door_swing_geometry_expands_object_box():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[{
            "id":"d1","kind":"door","doorSubtype":"single_swing",
            "doorSwingSide":"negative","doorSwingDepthPx":85.0,
            "a":{"x":100.0,"y":200.0},"b":{"x":200.0,"y":200.0},"confidence":.9,
        }],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    x1,y1,x2,y2=prediction["objects"][0]["bbox"]
    assert x1<100 and x2>200
    assert y1<120
    assert y2>200


def test_sliding_door_is_not_mislabeled_as_swing_door_in_aec_taxonomy():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[{
            "id":"d1","kind":"door","doorSubtype":"sliding",
            "a":{"x":100.0,"y":200.0},"b":{"x":200.0,"y":200.0},"confidence":1,
        }],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    assert prediction["objects"]==[]



def test_stairs_symbol_maps_to_aec_area_not_object():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[],
        "windows":[],
        "symbols":[{
            "id":"stairs-1","kind":"stairs",
            "a":{"x":100.0,"y":120.0},
            "b":{"x":220.0,"y":280.0},
            "confidence":.95,
        }],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=1000,height=800)
    assert prediction["objects"]==[]
    assert prediction["areas"]==[[
        [200.0,240.0],
        [440.0,240.0],
        [440.0,560.0],
        [200.0,560.0],
    ]]



def test_subset_gt_keeps_only_selected_sheet(tmp_path):
    dataset=tmp_path/"dataset"
    dataset.mkdir()
    (dataset/"annotations_15_scoring_ready.xml").write_text(
        '<annotations>'
        '<image id="1" name="sheet_01.png" width="100" height="100"></image>'
        '<image id="2" name="sheet_02.png" width="100" height="100"></image>'
        '</annotations>',
        encoding="utf-8",
    )
    target=tmp_path/"subset"
    _write_gt_subset(dataset,target,["sheet_02"])
    root=ET.parse(target/"annotations_15_scoring_ready.xml").getroot()
    assert [image.get("name") for image in root.findall("image")]==["sheet_02.png"]


def test_official_scorer_uses_selected_subset_and_reports_each_sheet(tmp_path):
    dataset=tmp_path/"dataset"
    dataset.mkdir()
    (dataset/"annotations_15_scoring_ready.xml").write_text(
        '<annotations>'
        '<image id="1" name="sheet_01.png" width="100" height="100"></image>'
        '<image id="2" name="sheet_02.png" width="100" height="100"></image>'
        '</annotations>',
        encoding="utf-8",
    )
    predictions=tmp_path/"pred"
    predictions.mkdir()
    (predictions/"sheet_01.json").write_text(
        json.dumps({"sheet":"sheet_01","objects":[],"areas":[],"walls":[]}),
        encoding="utf-8",
    )
    scorer=tmp_path/"score.py"
    scorer.write_text(
        'import argparse,xml.etree.ElementTree as ET\n'
        'p=argparse.ArgumentParser(); p.add_argument("--pred"); p.add_argument("--gt"); p.add_argument("--name"); a=p.parse_args()\n'
        'count=len(ET.parse(a.gt+"/annotations_15_scoring_ready.xml").getroot().findall("image"))\n'
        'print(f"Single Swing Door {count} 0 0 1.000 1.000 1.000")\n'
        'print(f"OBJECT MICRO {count} 0 0 1.000 1.000 1.000")\n'
        'print("wall pixel                     1.000 1.000 1.000")\n'
        'print("area pixel                     1.000 1.000 1.000")\n'
        'print("area instance                  1.000 1.000 1.000")\n',
        encoding="utf-8",
    )
    code,_,report=run_official_scorer(
        scorer,predictions,dataset,
        sheet_names=["sheet_01"],
        include_per_sheet=True,
    )
    assert code==0
    assert report is not None
    assert report["objectMicro"]["tp"]==1
    assert report["selectedSheets"]==["sheet_01"]
    assert report["sheets"]["sheet_01"]["objectMicro"]["tp"]==1



def test_quarantined_wall_candidate_is_not_emitted_to_aec():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[
            {
                "id":"review-only",
                "a":{"x":20.0,"y":40.0},
                "b":{"x":480.0,"y":40.0},
                "thicknessPx":4.0,
                "confidence":.64,
                "provenance":"pdf-vector",
            },
            {
                "id":"accepted",
                "a":{"x":20.0,"y":120.0},
                "b":{"x":480.0,"y":120.0},
                "thicknessPx":10.0,
                "confidence":.90,
                "provenance":"mixed",
            },
        ],
        "rooms":[],
        "doors":[],
        "windows":[],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    assert len(prediction["walls"])==1
    ys={round(point[1]) for point in prediction["walls"][0]}
    assert min(ys)<120<max(ys) or 120 in ys



def test_elevator_symbol_maps_to_aec_area():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[],
        "windows":[],
        "symbols":[{
            "id":"elevator-1","kind":"elevator",
            "a":{"x":120.0,"y":100.0},
            "b":{"x":220.0,"y":260.0},
            "confidence":.94,
        }],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=1000,height=800)
    assert prediction["objects"]==[]
    assert prediction["areas"]==[[
        [240.0,200.0],
        [440.0,200.0],
        [440.0,520.0],
        [240.0,520.0],
    ]]



def test_run_dataset_honors_manifest_offset(tmp_path,monkeypatch):
    dataset=tmp_path/"dataset"
    dataset.mkdir()
    sheets=[]
    for index in range(1,6):
        pdf=f"sheet_{index:02d}.pdf"
        (dataset/pdf).write_bytes(b"pdf")
        sheets.append({
            "sheet":f"sheet_{index:02d}",
            "pdf":pdf,
            "width":100,
            "height":100,
        })
    (dataset/"manifest.json").write_text(
        json.dumps({"sheets":sheets}),
        encoding="utf-8",
    )

    def fake_plan(data,mime_type,project_id,filename):
        return {
            "widthPx":100,"heightPx":100,
            "walls":[],"rooms":[],"doors":[],"windows":[],"symbols":[],
            "source":{"page":1},
        }

    monkeypatch.setattr(benchmark_module,"analyze_document_bytes_local",fake_plan)
    monkeypatch.setattr(
        benchmark_module,
        "decode_document_with_page",
        lambda *args,**kwargs:(np.zeros((100,100,3),dtype=np.uint8),1),
    )
    monkeypatch.setattr(
        benchmark_module,
        "render_extraction_overlay",
        lambda image,plan:image,
    )
    monkeypatch.setattr(benchmark_module.cv2,"imwrite",lambda *args,**kwargs:True)

    output=tmp_path/"out"
    written=run_dataset(dataset,output,limit=2,offset=2)
    assert [path.stem for path in written]==["sheet_03","sheet_04"]
    timing=json.loads((output/"_timings"/"sheet_03.json").read_text(encoding="utf-8"))
    assert timing["sheet"]=="sheet_03"
    assert timing["totalSeconds"]>=0
    assert timing["counts"]=={
        "walls":0,"rooms":0,"doors":0,"windows":0,"symbols":0,"dimensions":0,
    }


def test_pdf_vector_window_uses_native_depth_for_aec_bbox():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[],
        "windows":[{
            "id":"w1",
            "kind":"window",
            "provenance":"pdf-vector",
            "windowDepthPx":20.0,
            "a":{"x":100.0,"y":200.0},
            "b":{"x":200.0,"y":200.0},
            "confidence":.9,
        }],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    x1,y1,x2,y2=prediction["objects"][0]["bbox"]
    assert prediction["objects"][0]["class"]=="Window"
    assert 98.0<=x1<100.0
    assert 200.0<x2<=202.0
    assert 189.0<=y1<=191.0
    assert 209.0<=y2<=211.0


def test_raster_window_keeps_generic_padding():
    source={
        "widthPx":500,
        "heightPx":400,
        "walls":[],
        "rooms":[],
        "doors":[],
        "windows":[{
            "id":"w1",
            "kind":"window",
            "provenance":"opencv",
            "a":{"x":100.0,"y":200.0},
            "b":{"x":200.0,"y":200.0},
            "confidence":.9,
        }],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(source,sheet="sheet",width=500,height=400)
    x1,y1,x2,y2=prediction["objects"][0]["bbox"]
    assert x1==95.0
    assert y1==195.0
    assert x2==205.0
    assert y2==205.0


def test_pdf_vector_window_bbox_clamps_thin_native_depth_to_wall_scale():
    source={
        "widthPx":1000,
        "heightPx":500,
        "walls":[{
            "id":"w",
            "a":{"x":100.0,"y":100.0},
            "b":{"x":900.0,"y":100.0},
            "thicknessPx":32.0,
        }],
        "rooms":[],
        "doors":[],
        "windows":[{
            "id":"x",
            "kind":"window",
            "wallId":"w",
            "a":{"x":300.0,"y":100.0},
            "b":{"x":450.0,"y":100.0},
            "windowDepthPx":8.0,
            "provenance":"pdf-vector",
            "confidence":.9,
        }],
        "symbols":[],
    }
    prediction=plan_to_aec_prediction(
        source,sheet="sheet",width=1000,height=500,
    )
    x1,y1,x2,y2=prediction["objects"][0]["bbox"]
    assert 295<=x1<300
    assert 450<x2<=455
    assert 60<=(y2-y1)<=70
