from __future__ import annotations
import os
import re
from collections import defaultdict
import cv2
import numpy as np
import pytesseract
from pytesseract import Output

ROOM_WORDS=("غرفة","نوم","صالة","صاله","مجلس","مطبخ","حمام","دورة","ممر","مدخل","مستودع","غسيل","معيشة","living","bedroom","kitchen","bath","hall","majlis","corridor")

def normalize_digits(text:str)->str:
    table=str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹","01234567890123456789")
    return text.translate(table).replace("٫",".").replace(",",".")

def classify_text(text:str)->str:
    low=normalize_digits(text).lower().strip()
    if any(word in low for word in ROOM_WORDS): return "room_name"
    if re.search(r"(m\s*[²2]|م\s*[²2]|متر\s*مربع)",low): return "note"
    if re.search(r"\d+(?:\.\d+)?\s*(?:m|م|متر)\b",low) or re.search(r"\d+(?:\.\d+)?\s*[x×*]\s*\d+(?:\.\d+)?",low): return "dimension"
    if re.search(r"\d+(?:\.\d+)?",low): return "unknown"
    return "note" if len(low)>2 else "unknown"

def extract_ocr_labels(image:np.ndarray)->list[dict]:
    lang=os.getenv("OCR_LANG","ara+eng")
    rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB) if image.ndim==3 else cv2.cvtColor(image,cv2.COLOR_GRAY2RGB)
    data=pytesseract.image_to_data(rgb,lang=lang,config="--psm 11",output_type=Output.DICT)
    lines=defaultdict(list)
    for i,text in enumerate(data["text"]):
        text=(text or "").strip()
        try: conf=float(data["conf"][i])
        except (ValueError,TypeError): conf=-1
        if not text or conf<25: continue
        key=(int(data["block_num"][i]),int(data["par_num"][i]),int(data["line_num"][i]))
        lines[key].append({"text":text,"conf":conf,"x":int(data["left"][i]),"y":int(data["top"][i]),"w":int(data["width"][i]),"h":int(data["height"][i])})
    labels=[]
    for idx,words in enumerate(lines.values(),start=1):
        words.sort(key=lambda w:w["x"])
        text=" ".join(w["text"] for w in words).strip()
        if not text: continue
        x1=min(w["x"] for w in words); y1=min(w["y"] for w in words)
        x2=max(w["x"]+w["w"] for w in words); y2=max(w["y"]+w["h"] for w in words)
        confidence=max(0.0,min(1.0,sum(w["conf"] for w in words)/len(words)/100.0))
        labels.append({"id":f"label-{idx}","text":text,"center":{"x":(x1+x2)/2.0,"y":(y1+y2)/2.0},"confidence":confidence,"kind":classify_text(text)})
    return labels
