from __future__ import annotations
import asyncio
import os
import httpx
from fastapi import FastAPI,File,Form,Header,HTTPException,UploadFile
from .document import decode_document
from .edits import build_proposals
from .models import EditRequest,FloorPlan,ProposalResponse
from .pipeline import analyze_image

app=FastAPI(title="Manzil H Analyzer",version="0.1.0")
MAX_BYTES=50*1024*1024

def verify_internal(value:str|None)->None:
    expected=os.getenv("INTERNAL_TOKEN","")
    if expected and value!=expected:
        raise HTTPException(status_code=401,detail="unauthorized")

async def report(url:str,token:str,project_id:str,phase:str,progress:int,message:str)->None:
    if not url: return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url,headers={"x-manzil-internal":token},json={"project_id":project_id,"status":"analyzing","phase":phase,"progress":progress,"message":message})
    except Exception:
        pass

@app.get("/health")
async def health():
    return {"ok":True}

@app.post("/v1/analyze",response_model=FloorPlan)
async def analyze(
    file:UploadFile=File(...),
    project_id:str=Form(...),
    filename:str=Form(...),
    mime_type:str=Form(...),
    callback_url:str=Form(""),
    callback_token:str=Form(""),
    x_manzil_internal:str|None=Header(default=None),
):
    verify_internal(x_manzil_internal)
    data=await file.read()
    if not data or len(data)>MAX_BYTES:
        raise HTTPException(status_code=413,detail="invalid file size")
    await report(callback_url,callback_token,project_id,"preprocess",20,"تهيئة الملف وتصحيح الصورة")
    image=await asyncio.to_thread(decode_document,data,mime_type)
    await report(callback_url,callback_token,project_id,"ocr",38,"قراءة النصوص والأبعاد")
    result=await asyncio.to_thread(analyze_image,image,project_id,filename,mime_type)
    await report(callback_url,callback_token,project_id,"validation",94,"التحقق من النموذج الهندسي")
    return FloorPlan.model_validate(result)

@app.post("/v1/edit/proposals",response_model=ProposalResponse)
async def proposals(req:EditRequest,x_manzil_internal:str|None=Header(default=None)):
    verify_internal(x_manzil_internal)
    if req.project_id!=req.plan.id:
        raise HTTPException(status_code=400,detail="project mismatch")
    return build_proposals(req)
