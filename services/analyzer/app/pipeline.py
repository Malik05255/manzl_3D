from __future__ import annotations
import numpy as np
from .document import preprocess
from .ocr import extract_ocr_labels
from .rooms import detect_rooms
from .scale import estimate_scale
from .walls import detect_walls

def analyze_image(image:np.ndarray,project_id:str,filename:str,mime_type:str)->dict:
    h,w=image.shape[:2]
    _,ink=preprocess(image)
    labels=extract_ocr_labels(image)
    walls,wall_mask=detect_walls(ink)
    scale,scale_confidence=estimate_scale(labels,walls,w,h)
    rooms=detect_rooms(wall_mask,labels,scale)

    wall_score=min(0.96,0.35+len(walls)/35)
    room_score=min(0.94,0.35+len(rooms)/16)
    text_score=sum(x["confidence"] for x in labels)/len(labels) if labels else 0.20
    dimensions=[x for x in labels if x["kind"]=="dimension"]
    dimension_score=min(0.95,(scale_confidence or 0.25)+(0.08 if len(dimensions)>1 else 0))
    overall=0.34*wall_score+0.28*room_score+0.20*text_score+0.18*dimension_score

    warnings=[]
    if scale is None:
        warnings.append("لم يتم تثبيت مقياس الرسم تلقائيًا بثقة كافية.")
    warnings.append("العناصر منخفضة الثقة لا تُثبت تلقائيًا؛ يجب تأكيد الأبواب والنوافذ بصريًا.")

    return {
        "schemaVersion":1,"id":project_id,"widthPx":w,"heightPx":h,
        "metersPerPixel":scale,"calibrationConfidence":scale_confidence,
        "walls":walls,"rooms":rooms,"doors":[],"windows":[],"labels":labels,
        "quality":{
            "overall":round(max(0.0,min(1.0,overall)),3),
            "walls":round(wall_score,3),"rooms":round(room_score,3),
            "text":round(text_score,3),"dimensions":round(dimension_score,3),
            "needsCalibration":scale is None,"warnings":warnings,
        },
        "source":{"fileName":filename,"mimeType":mime_type,"page":1},
    }
