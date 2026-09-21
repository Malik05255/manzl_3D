from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

from .commands import find_target_room,normalize_arabic,parse_merge_rooms,resolve_target_size
from .edit_geometry import bbox
from .models import EditRequest


@dataclass(frozen=True)
class Provider:
    name:str
    base_url:str
    model:str
    key_env:str|None=None
    timeout_s:float=12.0


def _load_providers()->list[Provider]:
    raw=os.getenv("H_ENGINEER_PROVIDERS_JSON","").strip()
    if not raw:
        return []
    try:
        items=json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items,list):
        return []

    providers=[]
    for index,item in enumerate(items):
        if not isinstance(item,dict):
            continue
        base_url=str(item.get("base_url","")).strip().rstrip("/")
        model=str(item.get("model","")).strip()
        if not base_url or not model:
            continue
        key_env=str(item.get("key_env","")).strip() or None
        try:
            timeout_s=float(item.get("timeout_s",12))
        except (TypeError,ValueError):
            timeout_s=12.0
        providers.append(Provider(
            name=str(item.get("name") or f"provider-{index+1}"),
            base_url=base_url,
            model=model,
            key_env=key_env,
            timeout_s=max(4.0,min(timeout_s,30.0)),
        ))
    return providers


def _room_context(request:EditRequest)->list[dict]:
    scale=request.plan.metersPerPixel
    result=[]
    for room in request.plan.rooms[:40]:
        x1,y1,x2,y2=bbox(room)
        width=(x2-x1)*scale if scale else None
        height=(y2-y1)*scale if scale else None
        result.append({
            "name":room.name,
            "width_m":round(width,3) if width else None,
            "height_m":round(height,3) if height else None,
            "area_m2":room.areaM2,
        })
    return result


def _deterministic_understands(request:EditRequest)->bool:
    if parse_merge_rooms(request.command,request.plan.rooms) is not None:
        return True
    target=find_target_room(request.command,request.plan.rooms)
    if target is None or not request.plan.metersPerPixel:
        return False
    x1,y1,x2,y2=bbox(target)
    current_width=(x2-x1)*request.plan.metersPerPixel
    current_height=(y2-y1)*request.plan.metersPerPixel
    return resolve_target_size(request.command,current_width,current_height) is not None


def _extract_json(text:str)->dict|None:
    text=text.strip()
    text=re.sub(r"^\s*json\s*","",text,flags=re.I)
    try:
        value=json.loads(text)
        return value if isinstance(value,dict) else None
    except json.JSONDecodeError:
        pass

    start=text.find("{")
    end=text.rfind("}")
    if start<0 or end<=start:
        return None
    try:
        value=json.loads(text[start:end+1])
        return value if isinstance(value,dict) else None
    except json.JSONDecodeError:
        return None


def _canonical_from_payload(payload:dict,request:EditRequest)->tuple[str|None,str|None]:
    clarification=str(payload.get("needs_clarification") or "").strip()
    if clarification:
        return None,clarification[:240]

    action=str(payload.get("action") or "")
    if action=="merge_room":
        source_name=str(payload.get("source_room") or "").strip()
        target_name=str(payload.get("target_room") or "").strip()
        source=next((room for room in request.plan.rooms if normalize_arabic(room.name)==normalize_arabic(source_name)),None)
        target=next((room for room in request.plan.rooms if normalize_arabic(room.name)==normalize_arabic(target_name)),None)
        if source is None or target is None or source.id==target.id:
            return None,None
        return f"ادمج {source.name} مع {target.name}",None

    if action!="resize_room":
        return None,None

    target_name=str(payload.get("target_room") or "").strip()
    if not target_name:
        return None,None

    exact=next(
        (room for room in request.plan.rooms if normalize_arabic(room.name)==normalize_arabic(target_name)),
        None,
    )
    target=exact or find_target_room(target_name,request.plan.rooms)
    if target is None:
        return None,None

    try:
        width=float(payload.get("width_m"))
        height=float(payload.get("height_m"))
    except (TypeError,ValueError):
        return None,None
    if not (0.8<=width<=50 and 0.8<=height<=50):
        return None,None

    return f"عدل {target.name} إلى {width:g}×{height:g}",None


async def _ask_provider(provider:Provider,request:EditRequest)->tuple[str|None,str|None]:
    api_key=os.getenv(provider.key_env,"").strip() if provider.key_env else ""
    headers={"content-type":"application/json"}
    if api_key:
        headers["authorization"]=f"Bearer {api_key}"

    context={
        "user_command":request.command,
        "rooms":_room_context(request),
        "rules":[
            "Do not invent a room that is not listed.",
            "Only interpret the requested change; do not redesign the house.",
            "Use merge_room only when the user explicitly asks to remove or merge one listed room into another.",
            "Convert relative resize changes into final width_m and height_m using current dimensions.",
            "If ambiguous, set needs_clarification instead of guessing.",
        ],
        "output_schema":{
            "action":"resize_room or merge_room",
            "source_room":"exact room name when action is merge_room",
            "target_room":"exact room name",
            "width_m":"number when action is resize_room",
            "height_m":"number when action is resize_room",
            "needs_clarification":"empty string or short Arabic question",
        },
    }
    body={
        "model":provider.model,
        "temperature":0,
        "max_tokens":220,
        "messages":[
            {
                "role":"system",
                "content":"You interpret Arabic floor-plan edit requests. Return JSON only. A deterministic geometry engine validates every result.",
            },
            {
                "role":"user",
                "content":json.dumps(context,ensure_ascii=False,separators=(",",":")),
            },
        ],
    }

    async with httpx.AsyncClient(timeout=provider.timeout_s,follow_redirects=True) as client:
        response=await client.post(f"{provider.base_url}/chat/completions",headers=headers,json=body)
        if response.status_code in (401,403,404,408,409,429) or response.status_code>=500:
            return None,None
        response.raise_for_status()
        data=response.json()

    try:
        content=data["choices"][0]["message"]["content"]
    except (KeyError,IndexError,TypeError):
        return None,None
    if not isinstance(content,str):
        return None,None
    payload=_extract_json(content)
    if not payload:
        return None,None
    return _canonical_from_payload(payload,request)


async def normalize_edit_semantics(request:EditRequest)->tuple[str,str|None]:
    if _deterministic_understands(request):
        return request.command,None

    for provider in _load_providers():
        try:
            normalized,clarification=await _ask_provider(provider,request)
        except (httpx.HTTPError,ValueError,TypeError,json.JSONDecodeError):
            continue
        if clarification:
            return request.command,clarification
        if normalized:
            return normalized,None

    return request.command,None
