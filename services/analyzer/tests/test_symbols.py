from app.symbols import normalize_symbol_response


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
