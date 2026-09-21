from __future__ import annotations
import os
import cv2
import httpx
from fastapi import FastAPI,Header,HTTPException
from pydantic import BaseModel,HttpUrl
from .commands import find_target_room,parse_target_size
from .document import decode_document_with_page,preprocess
from .edits import build_proposals
from .models import EditRequest,FloorPlan,ProposalResponse
from .ocr import extract_ocr_labels
from .openings import detect_doors
from .pipeline import assemble_plan
from .rooms import detect_rooms
from .scale import estimate_scale
from .semantic import normalize_edit_semantics
from .walls import detect_walls

app=FastAPI(title="Manzil H Analyzer",version="0.1.0")

class AnalyzeRequest(BaseModel):
    project_id:str
    source_url:HttpUrl
    filename:str
    mime_type:str
    callback_url:HttpUrl|None=None
    preview_url:HttpUrl|None=None

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

    await progress(req.callback_url,req.project_id,"preprocess",23,"اختيار صفحة المخطط الأنسب")
    image,source_page=decode_document_with_page(data,req.mime_type)
    h,w=image.shape[:2]
    await upload_preview(req.preview_url,image)
    _,ink=preprocess(image)

    await progress(req.callback_url,req.project_id,"ocr",35,"قراءة النصوص والأبعاد")
    labels=extract_ocr_labels(image)

    await progress(req.callback_url,req.project_id,"geometry",58,"استخراج الجدران والهندسة")
    walls,wall_mask=detect_walls(ink)
    scale,scale_confidence=estimate_scale(labels,walls,w,h)
    doors=detect_doors(image,walls,scale)

    await progress(req.callback_url,req.project_id,"rooms",78,"فهم الغرف والعلاقات")
    rooms=detect_rooms(wall_mask,labels,scale)

    await progress(req.callback_url,req.project_id,"validation",93,"التحقق من جودة النتيجة")
    result=assemble_plan(image,req.project_id,req.filename,req.mime_type,labels,walls,rooms,scale,scale_confidence,source_page=source_page,doors=doors)
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
