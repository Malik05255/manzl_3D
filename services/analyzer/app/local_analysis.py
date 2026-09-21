from __future__ import annotations

import hashlib
from datetime import datetime,timezone

from .document import (
    decode_document_with_page,
    extract_pdf_text_lines,
    extract_pdf_vector_lines,
    pdf_page_count,
    preprocess,
)
from .dimensions import extract_dimension_evidence
from .ocr import _merge_labels,classify_text,extract_ocr_labels
from .openings import detect_doors,detect_windows,normalize_opening_hosts
from .pipeline import assemble_plan
from .rooms import detect_rooms
from .scale import estimate_scale_with_diagnostics
from .topology import classify_wall_roles,link_room_boundaries
from .walls import add_vector_wall_candidates,detect_walls,enrich_walls_with_vector,rasterize_wall_mask


def analyze_document_bytes_local(
    data:bytes,
    mime_type:str,
    *,
    project_id:str="benchmark",
    filename:str="source",
    source_page:int|None=None,
)->dict:
    """Run the production geometry path locally without cloud OCR or callbacks.

    This is intended for repeatable dataset benchmarking. It still uses native
    PDF text/vector evidence when available, so PDF benchmarks exercise more
    than the raster-only fallback path.
    """
    page_count=pdf_page_count(data) if mime_type=="application/pdf" else 1
    image,page=decode_document_with_page(data,mime_type,source_page)
    h,w=image.shape[:2]
    _,ink=preprocess(image)

    try:
        labels=extract_ocr_labels(image)
        used_local_ocr=True
    except Exception:
        labels=[]
        used_local_ocr=False
    vector_lines=[]
    engines=["opencv","canonical-wall-barrier"]
    if used_local_ocr:
        engines.append("tesseract")

    if mime_type=="application/pdf":
        native_lines=extract_pdf_text_lines(data,page)
        native_labels=[
            {
                "id":f"pdf-text-{index}",
                "text":item["text"],
                "center":item["center"],
                "confidence":0.995,
                "kind":classify_text(item["text"]),
                "reviewed":False,
                "provenance":"pdf-text",
            }
            for index,item in enumerate(native_lines,start=1)
        ]
        if native_labels:
            distance=max(12.0,min(image.shape[:2])*0.012)
            labels=_merge_labels(labels,native_labels,distance)
            engines.append("pdf-text")
        vector_lines=extract_pdf_vector_lines(data,page)
        if vector_lines:
            engines.append("pdf-vector")

    walls,wall_mask=detect_walls(ink)
    if vector_lines:
        walls=enrich_walls_with_vector(walls,vector_lines)
        walls=add_vector_wall_candidates(walls,vector_lines,h,w)

    dimensions=extract_dimension_evidence(
        labels,walls,w,h,ink=ink,vector_lines=vector_lines,
    )
    scale,scale_confidence,scale_warnings=estimate_scale_with_diagnostics(dimensions,w,h)
    doors=detect_doors(image,walls,scale)
    windows=detect_windows(image,walls,scale)
    walls,doors,windows=normalize_opening_hosts(walls,doors,windows)
    barrier=rasterize_wall_mask(walls,h,w,wall_mask)
    rooms=detect_rooms(barrier,labels,scale)
    link_room_boundaries(rooms,walls)
    classify_wall_roles(walls,rooms)

    analysis={
        "pipelineVersion":"benchmark-local",
        "analyzedAt":datetime.now(timezone.utc).isoformat(),
        "sourceSha256":hashlib.sha256(data).hexdigest(),
        "engines":list(dict.fromkeys(engines)),
    }
    return assemble_plan(
        image,project_id,filename,mime_type,labels,walls,rooms,scale,scale_confidence,
        source_page=page,source_page_count=page_count,doors=doors,windows=windows,
        dimensions=dimensions,scale_warnings=scale_warnings,analysis=analysis,
    )
