from __future__ import annotations
import asyncio
import hashlib
import os
from datetime import datetime,timezone
import cv2
import httpx
from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel,HttpUrl
from .cloud_ocr import extract_cloud_ocr_labels
from .commands import find_target_room,parse_target_size
from .document import decode_document_with_page,extract_pdf_text_lines,extract_pdf_vector_lines,pdf_page_count,preprocess
from .dimensions import extract_dimension_evidence
from .edits import build_proposals,build_resize_proposals
from .models import CanonicalizeRequest,EditRequest,FloorPlan,ProposalResponse,ResizeRequest,ValidationReport,ValidationRequest
from .ocr import _merge_labels,classify_text,extract_ocr_dimension_labels,extract_ocr_labels,native_pdf_text_is_sufficient
from .openings import detect_doors,detect_windows,fuse_ai_opening_detections,normalize_opening_hosts
from .pipeline import assemble_plan
from .rooms import detect_rooms
from .scale import estimate_scale_with_diagnostics
from .symbols import extract_local_onnx_detections,extract_symbol_detections,normalize_configured_symbols
from .structural import extract_structural_wall_mask,filter_walls_by_structural_support,structural_mask_metrics
from .topology import canonicalize_plan,classify_wall_roles,filter_nonarchitectural_enclosures,link_room_boundaries,recalibrate_extracted_room_confidence
from .semantic import normalize_edit_semantics
from .walls import add_vector_wall_candidates,detect_walls,enrich_walls_with_vector,quarantine_dimension_aligned_walls,rasterize_wall_mask
from .validation import validate_plan

app=FastAPI(title="Manzil H Analyzer",version="0.1.0")
PIPELINE_VERSION=os.getenv("ANALYZER_PIPELINE_VERSION",app.version)

class AnalyzeRequest(BaseModel):
    project_id:str
    source_url:HttpUrl
    filename:str
    mime_type:str
    callback_url:HttpUrl|None=None
    preview_url:HttpUrl|None=None
    source_page:int|None=None

def authorize(token:str|None):
    expected=os.getenv("INTERNAL_TOKEN","")
    if expected and token!=expected:
        raise HTTPException(status_code=401,detail="unauthorized")

async def progress(url:HttpUrl|None,project_id:str,phase:str,value:int,message:str):
    if not url: return
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            await client.post(str(url),headers={"x-manzil-internal":os.getenv("INTERNAL_TOKEN","")},json={
                "project_id":project_id,"status":"analyzing","phase":phase,"progress":value,"message":message
            })
    except Exception:
        pass

async def upload_preview(url:HttpUrl|None,image):
    if not url: return
    ok,encoded=cv2.imencode(".webp",image,[cv2.IMWRITE_WEBP_QUALITY,88])
    if not ok: return
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response=await client.put(
                str(url),
                headers={
                    "x-manzil-internal":os.getenv("INTERNAL_TOKEN",""),
                    "content-type":"image/webp",
                },
                content=encoded.tobytes(),
            )
            response.raise_for_status()
    except Exception:
        pass

@app.get("/health")
async def health():
    return {"ok":True}

@app.post("/v1/analyze",response_model=FloorPlan)
async def analyze(req:AnalyzeRequest,x_manzil_internal:str|None=Header(default=None)):
    authorize(x_manzil_internal)
    await progress(req.callback_url,req.project_id,"preprocess",18,"تنزيل المخطط وتهيئته")
    async with httpx.AsyncClient(timeout=120,follow_redirects=True) as client:
        response=await client.get(str(req.source_url),headers={"x-manzil-internal":os.getenv("INTERNAL_TOKEN","")})
        response.raise_for_status()
        data=response.content
    if len(data)>50*1024*1024:
        raise HTTPException(status_code=413,detail="file too large")

    source_page_count=pdf_page_count(data) if req.mime_type=="application/pdf" else 1
    if req.source_page is not None:
        await progress(req.callback_url,req.project_id,"preprocess",23,f"تحليل الصفحة {req.source_page} من الملف")
    else:
        await progress(req.callback_url,req.project_id,"preprocess",23,"اختيار صفحة المخطط الأنسب")
    image,source_page=decode_document_with_page(data,req.mime_type,req.source_page)
    h,w=image.shape[:2]
    await upload_preview(req.preview_url,image)
    _,ink=preprocess(image)
    reconstruction_v2=os.getenv("ANALYZER_RECONSTRUCTION_V2","1").strip().lower() not in {"0","false","off","no"}
    structural_mask=extract_structural_wall_mask(image,ink) if reconstruction_v2 else None
    structural_metrics=structural_mask_metrics(structural_mask) if structural_mask is not None else {}

    native_labels=[]
    used_pdf_text=False
    used_pdf_vector=False
    if req.mime_type=="application/pdf":
        try:
            native_lines=extract_pdf_text_lines(data,source_page)
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
            used_pdf_text=bool(native_labels)
        except Exception:
            native_labels=[]

    fastpath_enabled=os.getenv("PDF_NATIVE_TEXT_FASTPATH","1").strip().lower() not in {"0","false","off","no"}
    use_native_fastpath=(
        req.mime_type=="application/pdf"
        and fastpath_enabled
        and native_pdf_text_is_sufficient(native_labels)
    )

    await progress(req.callback_url,req.project_id,"ocr",35,"قراءة النصوص والأبعاد")
    async def _safe_local_ocr():
        try:
            worker=extract_ocr_dimension_labels if use_native_fastpath else extract_ocr_labels
            return await asyncio.to_thread(worker,image)
        except Exception:
            return []
    async def _safe_cloud_ocr():
        try:
            return await extract_cloud_ocr_labels(image)
        except Exception:
            return []
    async def _safe_symbols():
        if os.getenv("SYMBOL_ONNX_MODEL","").strip():
            try:
                detections=await asyncio.to_thread(extract_local_onnx_detections,image)
                symbols=normalize_configured_symbols(detections,w,h)
                return symbols,detections
            except Exception:
                return [],[]
        try:
            return await extract_symbol_detections(image),[]
        except Exception:
            return [],[]
    local_labels,cloud_labels,symbol_bundle=await asyncio.gather(
        _safe_local_ocr(),
        _safe_cloud_ocr(),
        _safe_symbols(),
    )
    symbols,ai_detections=symbol_bundle
    used_cloud_ocr=bool(cloud_labels)
    if cloud_labels:
        distance=max(12.0,min(image.shape[:2])*0.012)
        labels=_merge_labels(local_labels,cloud_labels,distance)
    else:
        labels=local_labels
    if native_labels:
        distance=max(12.0,min(image.shape[:2])*0.012)
        labels=_merge_labels(labels,native_labels,distance)

    await progress(req.callback_url,req.project_id,"geometry",58,"استخراج الجدران والهندسة")
    wall_input=(
        structural_mask
        if reconstruction_v2 and structural_mask is not None and cv2.countNonZero(structural_mask)>0
        else ink
    )
    walls,wall_mask=detect_walls(wall_input)
    vector_lines=[]
    if req.mime_type=="application/pdf":
        try:
            vector_lines=extract_pdf_vector_lines(data,source_page)
            if vector_lines:
                used_pdf_vector=True
            walls=enrich_walls_with_vector(walls,vector_lines)
            walls=add_vector_wall_candidates(walls,vector_lines,h,w,labels=labels)
        except Exception:
            vector_lines=[]
    dimensions=extract_dimension_evidence(labels,walls,w,h,ink=ink,vector_lines=vector_lines)
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
        image,
        topology_walls,
        scale,
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
    room_barrier_mask=rasterize_wall_mask(
        walls,h,w,
        base_mask=structural_mask if reconstruction_v2 and structural_mask is not None else None,
        min_pdf_vector_confidence=.70,
        excluded_wall_ids=quarantined_wall_ids,
    )

    await progress(req.callback_url,req.project_id,"rooms",78,"فهم الغرف والعلاقات")
    rooms=detect_rooms(room_barrier_mask,labels,scale)
    link_room_boundaries(rooms,topology_walls)
    rooms=filter_nonarchitectural_enclosures(rooms,topology_walls,w,h)
    recalibrate_extracted_room_confidence(rooms,topology_walls,w,h)
    classify_wall_roles(walls,rooms)

    await progress(req.callback_url,req.project_id,"validation",93,"التحقق من جودة النتيجة")
    engines=["opencv","canonical-wall-barrier"]
    if reconstruction_v2:
        engines.extend(["structural-wall-mask-v2","clean-vector-reconstruction-v2"])
    if local_labels: engines.append("tesseract-dimensions" if use_native_fastpath else "tesseract")
    if used_cloud_ocr: engines.append("google-vision")
    if used_pdf_text: engines.append("pdf-text")
    if used_pdf_vector: engines.append("pdf-vector")
    if symbols: engines.append("symbol-detector")
    if ai_detections: engines.append("onnx-architectural-detector")
    analysis={
        "pipelineVersion":PIPELINE_VERSION,
        "analyzedAt":datetime.now(timezone.utc).isoformat(),
        "sourceSha256":hashlib.sha256(data).hexdigest(),
        "engines":list(dict.fromkeys(engines)),
    }
    if reconstruction_v2:
        analysis["engines"].append(
            f"structural-components:{int(structural_metrics.get('structuralComponents',0))}"
        )
        if rejected_structural_walls:
            analysis["engines"].append(
                f"rejected-raster-strokes:{len(rejected_structural_walls)}"
            )
    result=assemble_plan(
        image,req.project_id,req.filename,req.mime_type,labels,walls,rooms,scale,scale_confidence,
        source_page=source_page,source_page_count=source_page_count,doors=doors,windows=windows,
        dimensions=dimensions,symbols=symbols,scale_warnings=scale_warnings,analysis=analysis,
    )
    return FloorPlan.model_validate(result)

@app.post("/v1/edit/proposals",response_model=ProposalResponse)
async def proposals(req:EditRequest,x_manzil_internal:str|None=Header(default=None)):
    authorize(x_manzil_internal)
    normalized,clarification=await normalize_edit_semantics(req)
    if clarification:
        return ProposalResponse(command=req.command,proposals=[],needsClarification=clarification)
    normalized_request=req.model_copy(update={"command":normalized})
    result=build_proposals(normalized_request)
    result.command=req.command
    return result


@app.post("/v1/edit/resize-proposals",response_model=ProposalResponse)
async def resize_proposals(req:ResizeRequest,x_manzil_internal:str|None=Header(default=None)):
    authorize(x_manzil_internal)
    target=next((room for room in req.plan.rooms if room.id==req.room_id),None)
    if target is None:
        return ProposalResponse(command="تعديل دقيق",proposals=[],needsClarification="الغرفة المحددة لم تعد موجودة في المخطط.")
    command=f"عدل {target.name} إلى {req.width_m:g}×{req.height_m:g}"
    return build_resize_proposals(req.plan,target,req.width_m,req.height_m,command)


@app.post("/v1/validate",response_model=ValidationReport)
async def validate(req:ValidationRequest,x_manzil_internal:str|None=Header(default=None)):
    authorize(x_manzil_internal)
    return validate_plan(req.plan)


@app.post("/v1/canonicalize",response_model=FloorPlan)
async def canonicalize(req:CanonicalizeRequest,x_manzil_internal:str|None=Header(default=None)):
    authorize(x_manzil_internal)
    return canonicalize_plan(req.plan)
