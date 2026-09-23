from __future__ import annotations

import asyncio
import hashlib
import os

import cv2
from datetime import datetime,timezone

from .document import (
    decode_document_with_page,
    extract_pdf_text_lines,
    extract_pdf_vector_lines,
    pdf_page_count,
    preprocess,
)
from .dimensions import extract_dimension_evidence
from .ocr import _merge_labels,classify_text,extract_ocr_dimension_labels,extract_ocr_labels,native_pdf_text_is_sufficient
from .openings import detect_doors,detect_windows,fuse_ai_opening_detections,normalize_opening_hosts
from .pipeline import assemble_plan
from .rooms import build_room_barrier,detect_rooms
from .scale import estimate_scale_with_diagnostics
from .symbols import extract_configured_onnx_detections,extract_symbol_detections,normalize_configured_symbols
from .structural import extract_structural_wall_mask,filter_walls_by_structural_support,structural_mask_metrics
from .topology import classify_wall_roles,filter_nonarchitectural_enclosures,link_room_boundaries,recalibrate_extracted_room_confidence
from .walls import add_vector_wall_candidates,detect_walls,enrich_walls_with_vector,fuse_region_wall_candidates,quarantine_dimension_aligned_walls,rasterize_wall_mask


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
    reconstruction_v3=os.getenv("ANALYZER_RECONSTRUCTION_V3","1").strip().lower() not in {"0","false","off","no"}
    structural_mask=extract_structural_wall_mask(image,ink) if reconstruction_v3 else None
    structural_metrics=structural_mask_metrics(structural_mask) if structural_mask is not None else {}

    vector_lines=[]
    native_labels=[]
    engines=["opencv","canonical-wall-barrier"]
    if reconstruction_v3:
        engines.extend(["structural-wall-mask-v2","structural-region-vectorizer-v3","clean-vector-reconstruction-v2","room-barrier-v3"])

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
        vector_lines=extract_pdf_vector_lines(data,page)
        if native_labels:
            engines.append("pdf-text")
        if vector_lines:
            engines.append("pdf-vector")

    fastpath_enabled=os.getenv("PDF_NATIVE_TEXT_FASTPATH","1").strip().lower() not in {"0","false","off","no"}
    use_native_fastpath=(
        mime_type=="application/pdf"
        and fastpath_enabled
        and native_pdf_text_is_sufficient(native_labels)
    )
    try:
        labels=(
            extract_ocr_dimension_labels(image)
            if use_native_fastpath
            else extract_ocr_labels(image)
        )
        used_local_ocr=True
    except Exception:
        labels=[]
        used_local_ocr=False
    if used_local_ocr:
        engines.append("tesseract-dimensions" if use_native_fastpath else "tesseract")

    if native_labels:
        distance=max(12.0,min(image.shape[:2])*0.012)
        labels=_merge_labels(labels,native_labels,distance)

    symbols=[]
    ai_detections=[]
    onnx_model_configured=bool(
        os.getenv("SYMBOL_ONNX_MODEL","").strip()
        or os.getenv("SYMBOL_SECONDARY_ONNX_MODEL","").strip()
    )
    symbol_provider_configured=bool(
        onnx_model_configured
        or os.getenv("SYMBOL_DETECTOR_URL","").strip()
    )
    if onnx_model_configured:
        try:
            ai_detections=extract_configured_onnx_detections(image)
            symbols=normalize_configured_symbols(ai_detections,w,h)
        except Exception:
            ai_detections=[]
            symbols=[]
    elif symbol_provider_configured:
        try:
            symbols=asyncio.run(extract_symbol_detections(image))
        except Exception:
            symbols=[]
    if symbols:
        engines.append("symbol-detector")
    if ai_detections:
        engines.append("onnx-architectural-detector")

    # Detect on the original ink so diagonal/irregular walls survive. V3 then
    # filters raster candidates against the conservative structural mask instead
    # of throwing away non-axis evidence before detection.
    walls,wall_mask=detect_walls(ink)
    if structural_mask is not None and cv2.countNonZero(structural_mask)>0:
        walls=fuse_region_wall_candidates(walls,structural_mask)
    if vector_lines:
        walls=enrich_walls_with_vector(walls,vector_lines)
        walls=add_vector_wall_candidates(walls,vector_lines,h,w,labels=labels)

    dimensions=extract_dimension_evidence(
        labels,walls,w,h,ink=ink,vector_lines=vector_lines,
    )
    quarantined_wall_ids=quarantine_dimension_aligned_walls(
        walls,labels,h,w,vector_lines=vector_lines,dimensions=dimensions,
    )
    rejected_structural_walls=[]
    if structural_mask is not None and cv2.countNonZero(structural_mask)>0:
        accepted_walls,rejected_structural_walls=filter_walls_by_structural_support(
            walls,structural_mask,minimum_support=.34,
        )
        minimum_viable=max(3,int(round(len(walls)*.15))) if walls else 0
        if len(accepted_walls)>=minimum_viable:
            walls=accepted_walls
            quarantined_wall_ids={
                wall_id for wall_id in quarantined_wall_ids
                if any(str(item.get("id",""))==wall_id for item in walls)
            }
    topology_walls=[
        wall for wall in walls
        if str(wall.get("id","")) not in quarantined_wall_ids
        and not (
            str(wall.get("provenance",""))=="pdf-vector"
            and float(wall.get("confidence",0.0))<.70
        )
    ]
    scale,scale_confidence,scale_warnings=estimate_scale_with_diagnostics(dimensions,w,h)
    doors=detect_doors(image,topology_walls,scale)
    windows=detect_windows(
        image,topology_walls,scale,
        vector_lines=vector_lines if vector_lines else None,
    )
    if ai_detections:
        doors,windows=fuse_ai_opening_detections(
            topology_walls,doors,windows,ai_detections,
            min_confidence=max(.15,min(.99,float(os.getenv("OPENING_ONNX_MIN_CONFIDENCE",".35") or ".35"))),
        )
    walls,doors,windows=normalize_opening_hosts(walls,doors,windows)
    topology_walls=[
        wall for wall in walls
        if str(wall.get("id","")) not in quarantined_wall_ids
        and not (
            str(wall.get("provenance",""))=="pdf-vector"
            and float(wall.get("confidence",0.0))<.70
        )
    ]
    barrier=rasterize_wall_mask(
        walls,h,w,
        base_mask=structural_mask if reconstruction_v3 and structural_mask is not None else None,
        min_pdf_vector_confidence=.70,
        excluded_wall_ids=quarantined_wall_ids,
    )
    segmentation_barrier=build_room_barrier(barrier) if reconstruction_v3 else barrier
    rooms=detect_rooms(segmentation_barrier,labels,scale)
    link_room_boundaries(rooms,topology_walls)
    rooms=filter_nonarchitectural_enclosures(rooms,topology_walls,w,h)
    recalibrate_extracted_room_confidence(rooms,topology_walls,w,h)
    classify_wall_roles(walls,rooms)

    analysis={
        "pipelineVersion":"benchmark-local",
        "analyzedAt":datetime.now(timezone.utc).isoformat(),
        "sourceSha256":hashlib.sha256(data).hexdigest(),
        "engines":list(dict.fromkeys(engines)),
    }
    if reconstruction_v3:
        analysis["engines"].append(
            f"structural-components:{int(structural_metrics.get('structuralComponents',0))}"
        )
        if rejected_structural_walls:
            analysis["engines"].append(
                f"rejected-raster-strokes:{len(rejected_structural_walls)}"
            )
    if ai_detections:
        detector_counts={}
        for detection in ai_detections:
            name=str(detection.get("class","unknown"))
            detector_counts[name]=detector_counts.get(name,0)+1
        analysis["detectorClassCounts"]=detector_counts
    return assemble_plan(
        image,project_id,filename,mime_type,labels,walls,rooms,scale,scale_confidence,
        source_page=page,source_page_count=page_count,doors=doors,windows=windows,
        dimensions=dimensions,symbols=symbols,scale_warnings=scale_warnings,analysis=analysis,
    )
