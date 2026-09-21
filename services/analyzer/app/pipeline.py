from __future__ import annotations
import numpy as np
from .document import preprocess
from .dimensions import extract_dimension_evidence
from .ocr import extract_ocr_labels
from .openings import detect_doors,detect_windows,normalize_opening_hosts
from .rooms import detect_rooms
from .scale import estimate_scale_with_diagnostics
from .walls import detect_walls,rasterize_wall_mask

def assemble_plan(image:np.ndarray,project_id:str,filename:str,mime_type:str,labels:list[dict],walls:list[dict],rooms:list[dict],scale:float|None,scale_confidence:float|None,source_page:int=1,source_page_count:int|None=None,doors:list[dict]|None=None,windows:list[dict]|None=None,dimensions:list[dict]|None=None,scale_warnings:list[str]|None=None,analysis:dict|None=None)->dict:
    h,w=image.shape[:2]
    wall_score=min(0.96,0.35+len(walls)/35)
    room_score=min(0.94,0.35+len(rooms)/16)
    text_score=sum(x["confidence"] for x in labels)/len(labels) if labels else 0.20
    dimension_labels=[x for x in labels if x["kind"]=="dimension"]
    dimension_objects=dimensions or []
    dimension_score=min(0.95,(scale_confidence or 0.25)+(0.08 if len(dimension_labels)>1 else 0)+(0.03 if any(item.get("valueM") for item in dimension_objects) else 0))
    overall=0.34*wall_score+0.28*room_score+0.20*text_score+0.18*dimension_score

    warnings=list(scale_warnings or [])
    if scale is None:
        warnings.append("لم يتم تثبيت مقياس الرسم تلقائيًا بثقة كافية.")
    if not rooms:
        warnings.append("لم تُكتشف غرف مغلقة بثقة كافية؛ يلزم تأكيد بصري.")
    warnings.append("العناصر منخفضة الثقة لا تُثبت تلقائيًا؛ يجب تأكيد الأبواب والنوافذ بصريًا.")

    return {
        "schemaVersion":1,"id":project_id,"widthPx":w,"heightPx":h,
        "metersPerPixel":scale,"calibrationConfidence":scale_confidence,
        "walls":walls,"rooms":rooms,"doors":doors or [],"windows":windows or [],"labels":labels,"dimensions":dimension_objects,
        "quality":{
            "overall":round(max(0.0,min(1.0,overall)),3),
            "walls":round(wall_score,3),"rooms":round(room_score,3),
            "text":round(text_score,3),"dimensions":round(dimension_score,3),
            "needsCalibration":scale is None,"warnings":warnings,
        },
        "source":{"fileName":filename,"mimeType":mime_type,"page":source_page,"pageCount":source_page_count},
        "analysis":analysis,
    }

def analyze_image(image:np.ndarray,project_id:str,filename:str,mime_type:str)->dict:
    h,w=image.shape[:2]
    _,ink=preprocess(image)
    labels=extract_ocr_labels(image)
    walls,wall_mask=detect_walls(ink)
    dimensions=extract_dimension_evidence(labels,walls,w,h)
    scale,scale_confidence,scale_warnings=estimate_scale_with_diagnostics(labels,walls,w,h)
    doors=detect_doors(image,walls,scale)
    windows=detect_windows(image,walls,scale)
    walls,doors,windows=normalize_opening_hosts(walls,doors,windows)
    room_barrier_mask=rasterize_wall_mask(walls,h,w,wall_mask)
    rooms=detect_rooms(room_barrier_mask,labels,scale)
    return assemble_plan(image,project_id,filename,mime_type,labels,walls,rooms,scale,scale_confidence,doors=doors,windows=windows,dimensions=dimensions,scale_warnings=scale_warnings)
