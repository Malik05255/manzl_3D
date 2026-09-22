import numpy as np

from app.symbols import _env_confidence,_decode_yolo_output,_dedupe_raw_detections,_prepare_yolo_rows,_tile_windows,normalize_symbol_response


def test_normalizes_supported_symbol_classes_and_boxes():
    result=normalize_symbol_response({
        "symbols":[
            {"class":"WC","bbox":[10,20,50,80],"score":.93},
            {"class":"Sink","bbox":{"x":70,"y":30,"width":40,"height":25},"confidence":.88},
            {"class":"unknown fixture","bbox":[1,1,20,20],"confidence":.99},
        ]
    },200,150)
    assert [item["kind"] for item in result]==["toilet","sink"]
    assert result[0]["a"]=={"x":10.0,"y":20.0}
    assert result[0]["b"]=={"x":50.0,"y":80.0}
    assert result[0]["provenance"]=="ai"
    assert result[0]["reviewed"] is False


def test_rejects_low_confidence_and_invalid_boxes():
    result=normalize_symbol_response([
        {"kind":"toilet","bbox":[10,10,40,40],"confidence":.40},
        {"kind":"sink","bbox":[10,10,11,11],"confidence":.99},
        {"kind":"bathtub","bbox":[80,80,20,20],"confidence":.90},
    ],100,100,min_confidence=.78)
    assert len(result)==1
    assert result[0]["kind"]=="bathtub"
    assert result[0]["a"]=={"x":20.0,"y":20.0}
    assert result[0]["b"]=={"x":80.0,"y":80.0}


def test_nms_keeps_highest_confidence_duplicate():
    result=normalize_symbol_response({
        "detections":[
            {"label":"sink","bbox":[10,10,60,60],"confidence":.91},
            {"label":"basin","bbox":[12,12,61,61],"confidence":.84},
            {"label":"sink","bbox":[100,10,150,60],"confidence":.82},
        ]
    },200,100)
    assert len(result)==2
    assert result[0]["confidence"]==.91
    assert result[1]["a"]["x"]==100.0


def test_accepts_normalized_xyxy_boxes():
    result=normalize_symbol_response({
        "predictions":[
            {"name":"toilet","bbox":[.10,.20,.30,.55],"score":.92,"normalized":True},
        ]
    },1000,800)
    assert len(result)==1
    assert result[0]["a"]=={"x":100.0,"y":160.0}
    assert result[0]["b"]=={"x":300.0,"y":440.00000000000006}


def test_accepts_xywh_and_center_box_formats():
    result=normalize_symbol_response([
        {"label":"sink","bbox":[100,120,80,40],"bbox_format":"xywh","confidence":.90},
        {"label":"cooktop","bbox":[300,220,100,60],"bbox_format":"cxcywh","confidence":.91},
    ],800,600)
    assert len(result)==2
    by_kind={item["kind"]:item for item in result}
    assert by_kind["sink"]["a"]=={"x":100.0,"y":120.0}
    assert by_kind["sink"]["b"]=={"x":180.0,"y":160.0}
    assert by_kind["cooktop"]["a"]=={"x":250.0,"y":190.0}
    assert by_kind["cooktop"]["b"]=={"x":350.0,"y":250.0}


def test_rejects_page_sized_symbol_detection():
    result=normalize_symbol_response([
        {"label":"toilet","bbox":[0,0,950,780],"confidence":.99},
    ],1000,800)
    assert result==[]



def test_decodes_yolov8_onnx_output():
    # YOLOv8-style tensor: [1, 4 + classes, detections].
    output=np.array([[
        [160.0,500.0],
        [180.0,500.0],
        [80.0,40.0],
        [100.0,40.0],
        [0.94,0.10],
        [0.06,0.91],
    ]],dtype=np.float32)
    result=_decode_yolo_output(
        output,
        class_names=["toilet","sink"],
        confidence_threshold=.78,
        original_width=640,
        original_height=640,
        input_size=640,
        scale=1.0,
        pad_x=0.0,
        pad_y=0.0,
    )
    assert [item["kind"] for item in result]==["toilet","sink"]
    assert result[0]["a"]=={"x":120.0,"y":130.0}
    assert result[0]["b"]=={"x":200.0,"y":230.0}


def test_decodes_yolo_objectness_output_and_applies_confidence():
    # YOLOv5-style row: cx, cy, w, h, objectness, class scores...
    output=np.array([
        [200.0,200.0,100.0,80.0,.90,.05,.95],
        [400.0,400.0,60.0,60.0,.50,.99,.01],
    ],dtype=np.float32)
    result=_decode_yolo_output(
        output,
        class_names=["toilet","sink"],
        confidence_threshold=.78,
        original_width=640,
        original_height=640,
        input_size=640,
        scale=1.0,
        pad_x=0.0,
        pad_y=0.0,
    )
    assert len(result)==1
    assert result[0]["kind"]=="sink"
    assert result[0]["confidence"]>0.85


def test_rejects_unknown_yolo_tensor_shape():
    rows=_prepare_yolo_rows(np.zeros((1,8,12),dtype=np.float32),2)
    assert rows.shape==(0,6)



def test_cross_class_near_duplicate_keeps_stronger_prediction():
    result=normalize_symbol_response([
        {"label":"toilet","bbox":[20,20,80,90],"confidence":.94},
        {"label":"sink","bbox":[22,22,79,89],"confidence":.86},
    ],200,160)
    assert len(result)==1
    assert result[0]["kind"]=="toilet"
    assert result[0]["confidence"]==.94


def test_cross_class_partial_overlap_keeps_distinct_fixtures():
    result=normalize_symbol_response([
        {"label":"toilet","bbox":[20,20,80,90],"confidence":.94},
        {"label":"sink","bbox":[65,30,125,80],"confidence":.90},
    ],200,160)
    assert {item["kind"] for item in result}=={"toilet","sink"}



def test_tile_windows_cover_large_page_with_overlap():
    windows=_tile_windows(6222,4148,1600,.18)
    assert len(windows)>1
    assert windows[0]==(0,0,1600,1600)
    assert windows[-1][2:]==(6222,4148)
    # Every page corner is covered and adjacent tiles overlap.
    assert any(x1==0 and y1==0 for x1,y1,_,_ in windows)
    assert any(x2==6222 and y2==4148 for _,_,x2,y2 in windows)
    first_row=[item for item in windows if item[1]==0]
    assert first_row[1][0]<first_row[0][2]


def test_raw_tile_dedupe_keeps_best_same_class_detection():
    result=_dedupe_raw_detections([
        {"class":"sink","bbox":[100,100,180,180],"confidence":.91},
        {"class":"sink","bbox":[104,103,181,181],"confidence":.83},
        {"class":"toilet","bbox":[104,103,181,181],"confidence":.88},
    ],.45)
    assert len(result)==2
    sink=next(item for item in result if item["class"]=="sink")
    assert sink["confidence"]==.91
    assert {item["class"] for item in result}=={"sink","toilet"}



def test_normalizes_elevator_symbol_class():
    result=normalize_symbol_response([
        {"class":"elevator","bbox":[30,40,130,180],"confidence":.92},
    ],300,240)
    assert len(result)==1
    assert result[0]["kind"]=="elevator"



def test_raw_onnx_threshold_can_be_lower_than_fixture_threshold(monkeypatch):
    monkeypatch.setenv("SYMBOL_ONNX_RAW_MIN_CONFIDENCE","0.27")
    assert _env_confidence("SYMBOL_ONNX_RAW_MIN_CONFIDENCE",.30,.10)==.27

    monkeypatch.setenv("SYMBOL_ONNX_RAW_MIN_CONFIDENCE","0.01")
    assert _env_confidence("SYMBOL_ONNX_RAW_MIN_CONFIDENCE",.30,.10)==.10
