from __future__ import annotations

import base64
import os
from typing import Any

import cv2
import httpx
import numpy as np

from .ocr import classify_text


def _vertex_xy(vertex:dict[str,Any])->tuple[float,float]:
    return float(vertex.get("x",0) or 0),float(vertex.get("y",0) or 0)


def _paragraph_text(paragraph:dict[str,Any])->str:
    words=[]
    for word in paragraph.get("words",[]) or []:
        text="".join(str(symbol.get("text","")) for symbol in (word.get("symbols",[]) or [])).strip()
        if text:
            words.append(text)
    return " ".join(words).strip()


def _paragraph_confidence(paragraph:dict[str,Any])->float:
    value=paragraph.get("confidence")
    if isinstance(value,(int,float)):
        return max(0.0,min(1.0,float(value)))
    values=[
        float(word["confidence"])
        for word in (paragraph.get("words",[]) or [])
        if isinstance(word.get("confidence"),(int,float))
    ]
    return max(0.0,min(1.0,sum(values)/len(values))) if values else 0.86


def labels_from_google_vision_response(payload:dict[str,Any])->list[dict]:
    responses=payload.get("responses")
    if not isinstance(responses,list) or not responses:
        return []
    response=responses[0] if isinstance(responses[0],dict) else {}
    annotation=response.get("fullTextAnnotation")
    if not isinstance(annotation,dict):
        return []

    labels=[]
    for page in annotation.get("pages",[]) or []:
        if not isinstance(page,dict):
            continue
        for block in page.get("blocks",[]) or []:
            if not isinstance(block,dict):
                continue
            for paragraph in block.get("paragraphs",[]) or []:
                if not isinstance(paragraph,dict):
                    continue
                text=_paragraph_text(paragraph)
                if not text or len(text)>500:
                    continue
                bounding=paragraph.get("boundingBox") or paragraph.get("boundingPoly") or {}
                vertices=bounding.get("vertices",[]) if isinstance(bounding,dict) else []
                points=[_vertex_xy(vertex) for vertex in vertices if isinstance(vertex,dict)]
                if not points:
                    continue
                xs=[point[0] for point in points]
                ys=[point[1] for point in points]
                labels.append({
                    "id":f"cloud-ocr-{len(labels)+1}",
                    "text":text,
                    "center":{"x":(min(xs)+max(xs))/2.0,"y":(min(ys)+max(ys))/2.0},
                    "confidence":_paragraph_confidence(paragraph),
                    "kind":classify_text(text),
                    "reviewed":False,
                    "provenance":"cloud-ocr",
                })
    return labels


def _encode_for_google(image:np.ndarray)->str:
    working=image
    height,width=working.shape[:2]
    max_side=max(height,width)
    limit=5200
    if max_side>limit:
        ratio=limit/max_side
        working=cv2.resize(
            working,
            (max(1,int(round(width*ratio))),max(1,int(round(height*ratio)))),
            interpolation=cv2.INTER_AREA,
        )
    ok,encoded=cv2.imencode(".png",working,[cv2.IMWRITE_PNG_COMPRESSION,4])
    if not ok:
        raise ValueError("CLOUD_OCR_ENCODE_FAILED")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


async def extract_google_vision_labels(image:np.ndarray,api_key:str,timeout_s:float=35.0)->list[dict]:
    content=_encode_for_google(image)
    body={
        "requests":[{
            "image":{"content":content},
            "features":[{"type":"DOCUMENT_TEXT_DETECTION"}],
            "imageContext":{"languageHints":["ar","en"]},
        }]
    }
    url=f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response=await client.post(url,json=body)
        response.raise_for_status()
        payload=response.json()
    if isinstance(payload,dict):
        first=(payload.get("responses") or [{}])[0]
        if isinstance(first,dict) and first.get("error"):
            return []
        return labels_from_google_vision_response(payload)
    return []


async def extract_cloud_ocr_labels(image:np.ndarray)->list[dict]:
    provider=os.getenv("CLOUD_OCR_PROVIDER","").strip().lower().replace("_","-")
    if provider in ("","off","none","disabled"):
        return []
    if provider not in ("google","google-vision"):
        return []

    api_key=os.getenv("GOOGLE_VISION_API_KEY","").strip()
    if not api_key:
        return []

    try:
        timeout=float(os.getenv("CLOUD_OCR_TIMEOUT_SECONDS","35"))
    except ValueError:
        timeout=35.0
    timeout=max(8.0,min(timeout,90.0))
    return await extract_google_vision_labels(image,api_key,timeout)
