from __future__ import annotations
import numpy as np
from .document import preprocess
from .dimensions import extract_dimension_evidence
from .ocr import extract_ocr_labels
from .openings import detect_doors,detect_windows,normalize_opening_hosts
from .rooms import detect_rooms
from .scale import estimate_scale_with_diagnostics
from .topology import classify_wall_roles,link_room_boundaries,recalibrate_extracted_room_confidence,room_boundary_coverage
from .walls import detect_walls,quarantine_dimension_aligned_walls,rasterize_wall_mask

def assemble_plan(image:np.ndarray,project_id:str,filename:str,mime_type:str,labels:list[dict],walls:list[dict],rooms:list[dict],scale:float|None,scale_confidence:float|None,source_page:int=1,source_page_count:int|None=None,doors:list[dict]|None=None,windows:list[dict]|None=None,dimensions:list[dict]|None=None,symbols:list[dict]|None=None,scale_warnings:list[str]|None=None,analysis:dict|None=None)->dict:
    h,w=image.shape[:2]

    wall_confidence=(
        sum(float(item.get("confidence",0.0)) for item in walls)/len(walls)
        if walls else 0.0
    )
    wall_count_support=min(1.0,len(walls)/8.0)
    wall_score=(
        min(0.96,0.12+0.70*wall_confidence+0.14*wall_count_support)
        if walls else 0.12
    )

    room_confidence=(
        sum(float(item.get("confidence",0.0)) for item in rooms)/len(rooms)
        if rooms else 0.0
    )
    room_coverage=(
        sum(room_boundary_coverage(room,walls) for room in rooms)/len(rooms)
        if rooms and walls else 0.0
    )
    room_count_support=min(1.0,len(rooms)/4.0)
    room_score=(
        min(
            0.94,
            0.10
            +0.42*room_confidence
            +0.34*room_coverage
            +0.08*room_count_support,
        )
        if rooms else 0.12
    )

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
    elif room_coverage<0.70:
        warnings.append("تغطية حدود بعض الغرف بالجدران منخفضة؛ راجع الجدران أو أكمل الأجزاء الناقصة.")
    if walls and wall_confidence<0.72:
        warnings.append("متوسط ثقة الجدران منخفض؛ راجع الخطوط المكتشفة قبل التعديل الهندسي.")
    quarantined_vectors=[
        wall for wall in walls
        if str(wall.get("provenance",""))=="pdf-vector"
        and float(wall.get("confidence",0.0))<.70
    ]
    if quarantined_vectors:
        warnings.append(
            f"تم حفظ {len(quarantined_vectors)} خط PDF منخفض الثقة للمراجعة دون استخدامه تلقائيًا في إغلاق الغرف."
        )
    warnings.append("العناصر منخفضة الثقة لا تُثبت تلقائيًا؛ يجب تأكيد الأبواب والنوافذ بصريًا.")

    return {
        "schemaVersion":1,"id":project_id,"widthPx":w,"heightPx":h,
        "metersPerPixel":scale,"calibrationConfidence":scale_confidence,
        "walls":walls,"rooms":rooms,"doors":doors or [],"windows":windows or [],"labels":labels,"dimensions":dimension_objects,"symbols":symbols or [],
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
    walls,_wall_mask=detect_walls(ink)
    quarantined_wall_ids=quarantine_dimension_aligned_walls(walls,labels,h,w)
    topology_walls=[
        wall for wall in walls
        if str(wall.get("id","")) not in quarantined_wall_ids
    ]
    dimensions=extract_dimension_evidence(labels,walls,w,h,ink=ink)
    scale,scale_confidence,scale_warnings=estimate_scale_with_diagnostics(dimensions,w,h)
    doors=detect_doors(image,topology_walls,scale)
    windows=detect_windows(image,topology_walls,scale)
    walls,doors,windows=normalize_opening_hosts(walls,doors,windows)
    topology_walls=[
        wall for wall in walls
        if str(wall.get("id","")) not in quarantined_wall_ids
    ]
    room_barrier_mask=rasterize_wall_mask(walls,h,w,excluded_wall_ids=quarantined_wall_ids)
    rooms=detect_rooms(room_barrier_mask,labels,scale)
    link_room_boundaries(rooms,topology_walls)
    recalibrate_extracted_room_confidence(rooms,topology_walls,w,h)
    classify_wall_roles(walls,rooms)
    return assemble_plan(image,project_id,filename,mime_type,labels,walls,rooms,scale,scale_confidence,doors=doors,windows=windows,dimensions=dimensions,symbols=[],scale_warnings=scale_warnings)
