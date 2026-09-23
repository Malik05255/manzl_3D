from app.cloud_ocr import labels_from_google_vision_response


def _word(text,confidence=.95):
    return {
        "confidence":confidence,
        "symbols":[{"text":char} for char in text],
    }


def test_google_vision_paragraph_becomes_room_label():
    payload={
        "responses":[{
            "fullTextAnnotation":{
                "pages":[{
                    "blocks":[{
                        "paragraphs":[{
                            "confidence":.97,
                            "boundingBox":{"vertices":[
                                {"x":100,"y":120},{"x":260,"y":120},
                                {"x":260,"y":170},{"x":100,"y":170},
                            ]},
                            "words":[_word("غرفة"),_word("النوم")],
                        }]
                    }]
                }]
            }
        }]
    }
    labels=labels_from_google_vision_response(payload)
    assert len(labels)==1
    assert labels[0]["text"]=="غرفة النوم"
    assert labels[0]["kind"]=="room_name"
    assert labels[0]["confidence"]==.97
    assert labels[0]["center"]=={"x":180.0,"y":145.0}
    assert labels[0]["provenance"]=="cloud-ocr"


def test_google_vision_metric_paragraph_is_dimension():
    payload={
        "responses":[{
            "fullTextAnnotation":{
                "pages":[{
                    "blocks":[{
                        "paragraphs":[{
                            "boundingBox":{"vertices":[
                                {"x":10,"y":20},{"x":110,"y":20},
                                {"x":110,"y":45},{"x":10,"y":45},
                            ]},
                            "words":[_word("420"),_word("cm")],
                        }]
                    }]
                }]
            }
        }]
    }
    labels=labels_from_google_vision_response(payload)
    assert labels[0]["text"]=="420 cm"
    assert labels[0]["kind"]=="dimension"


def test_google_vision_empty_response_is_safe():
    assert labels_from_google_vision_response({"responses":[{}]})==[]
