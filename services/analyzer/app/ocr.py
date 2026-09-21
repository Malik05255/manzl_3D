from __future__ import annotations
import os
import re
from collections import defaultdict
import cv2
import numpy as np
import pytesseract
from pytesseract import Output

ROOM_WORDS=("غرفة","نوم","صالة","صاله","مجلس","مطبخ","حمام","دورة","ممر","مدخل","مستودع","غسيل","معيشة","living","bedroom","kitchen","bath","hall","majlis","corridor")

def _arabic_letter_count(value:str)->int:
    return sum(1 for ch in value if "\u0600"<=ch<="\u06ff")

def _latin_letter_count(value:str)->int:
    return sum(1 for ch in value if ("a"<=ch.lower()<="z"))

def order_line_words(words:list[dict])->list[dict]:
    combined=" ".join(str(word.get("text","")) for word in words)
    arabic=_arabic_letter_count(combined)
    latin=_latin_letter_count(combined)
    rtl=arabic>latin and arabic>0
    return sorted(words,key=lambda word:word["x"],reverse=rtl)

def normalize_digits(text:str)->str:
    table=str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹","01234567890123456789")
    return text.translate(table).replace("٫",".").replace(",",".")

def classify_text(text:str)->str:
    low=normalize_digits(text).lower().strip()
    if any(word in low for word in ROOM_WORDS): return "room_name"
    if re.search(r"(m\s*[²2]|م\s*[²2]|متر\s*مربع)",low): return "note"
    if re.search(r"\d+(?:\.\d+)?\s*(?:m|م|متر)\b",low) or re.search(r"\d+(?:\.\d+)?\s*[x×*]\s*\d+(?:\.\d+)?",low): return "dimension"
    if re.fullmatch(r"\s*\d+\.\d+\s*",low):
        try:
            value=float(low.strip())
            if 0.4<=value<=50:
                return "dimension"
        except ValueError:
            pass
    if re.search(r"\d+(?:\.\d+)?",low): return "unknown"
    return "note" if len(low)>2 else "unknown"

def _ocr_pass(image:np.ndarray,lang:str,config:str,min_conf:float,prefix:str)->list[dict]:
    data=pytesseract.image_to_data(image,lang=lang,config=config,output_type=Output.DICT)
    lines=defaultdict(list)
    for i,text in enumerate(data["text"]):
        text=(text or "").strip()
        try:
            conf=float(data["conf"][i])
        except (ValueError,TypeError):
            conf=-1
        if not text or conf<min_conf:
            continue
        key=(int(data["block_num"][i]),int(data["par_num"][i]),int(data["line_num"][i]))
        lines[key].append({
            "text":text,
            "conf":conf,
            "x":int(data["left"][i]),
            "y":int(data["top"][i]),
            "w":int(data["width"][i]),
            "h":int(data["height"][i]),
        })

    labels=[]
    for idx,words in enumerate(lines.values(),start=1):
        words=order_line_words(words)
        text=" ".join(word["text"] for word in words).strip()
        if not text:
            continue
        x1=min(word["x"] for word in words)
        y1=min(word["y"] for word in words)
        x2=max(word["x"]+word["w"] for word in words)
        y2=max(word["y"]+word["h"] for word in words)
        confidence=max(0.0,min(1.0,sum(word["conf"] for word in words)/len(words)/100.0))
        labels.append({
            "id":f"{prefix}-{idx}",
            "text":text,
            "center":{"x":(x1+x2)/2.0,"y":(y1+y2)/2.0},
            "confidence":confidence,
            "kind":classify_text(text),
        })
    return labels


def _label_distance(a:dict,b:dict)->float:
    dx=a["center"]["x"]-b["center"]["x"]
    dy=a["center"]["y"]-b["center"]["y"]
    return float((dx*dx+dy*dy)**0.5)


def _merge_labels(primary:list[dict],secondary:list[dict],distance_px:float)->list[dict]:
    result=[dict(label) for label in primary]
    for candidate in secondary:
        duplicate_index=None
        for index,existing in enumerate(result):
            if _label_distance(existing,candidate)>distance_px:
                continue
            existing_digits=re.sub(r"\D","",normalize_digits(existing["text"]))
            candidate_digits=re.sub(r"\D","",normalize_digits(candidate["text"]))
            same_numeric=bool(existing_digits and candidate_digits and existing_digits==candidate_digits)
            same_kind=existing["kind"]==candidate["kind"]=="dimension"
            if same_numeric or same_kind:
                duplicate_index=index
                break
        if duplicate_index is None:
            result.append(candidate)
        elif candidate["confidence"]>result[duplicate_index]["confidence"]:
            result[duplicate_index]=candidate

    for index,label in enumerate(result,start=1):
        label["id"]=f"label-{index}"
    return result


def extract_ocr_labels(image:np.ndarray)->list[dict]:
    lang=os.getenv("OCR_LANG","ara+eng")
    rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB) if image.ndim==3 else cv2.cvtColor(image,cv2.COLOR_GRAY2RGB)

    base=_ocr_pass(rgb,lang,"--psm 11",25,"base")

    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image.copy()
    gray=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(gray)
    numeric=cv2.adaptiveThreshold(
        gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,9
    )
    numeric_config=(
        "--psm 11 "
        "-c tessedit_char_whitelist=0123456789٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹.xX×*mMمتر² "
        "-c preserve_interword_spaces=1"
    )
    numeric_labels=_ocr_pass(numeric,lang,numeric_config,30,"dim")
    numeric_labels=[
        label for label in numeric_labels
        if re.search(r"[0-9٠-٩۰-۹]",label["text"])
        and label["kind"] in ("dimension","unknown","note")
    ]

    distance=max(12.0,min(image.shape[:2])*0.012)
    return _merge_labels(base,numeric_labels,distance)
