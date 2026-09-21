from __future__ import annotations
import re
from .ocr import normalize_digits

def normalize_arabic(text:str)->str:
    text=normalize_digits(text).lower()
    return (text.replace("أ","ا").replace("إ","ا").replace("آ","ا")
        .replace("ة","ه").replace("ى","ي").replace("ـ","").strip())

def parse_target_size(command:str)->tuple[float,float]|None:
    text=normalize_arabic(command)
    match=re.search(r"(\d+(?:\.\d+)?)\s*(?:x|×|\*|في)\s*(\d+(?:\.\d+)?)",text)
    if not match: return None
    width=float(match.group(1)); height=float(match.group(2))
    if not (0.8<=width<=50 and 0.8<=height<=50): return None
    return width,height

def room_match(command:str,room_name:str)->float:
    cmd=normalize_arabic(command)
    name=normalize_arabic(room_name)
    if name and name in cmd: return 1.0
    name_tokens={t for t in re.split(r"\s+",name) if len(t)>2 and not t.isdigit()}
    cmd_tokens={t for t in re.split(r"\s+",cmd) if len(t)>2 and not t.isdigit()}
    if not name_tokens: return 0.0
    return len(name_tokens & cmd_tokens)/len(name_tokens)

def find_target_room(command:str,rooms:list)->object|None:
    scored=[(room_match(command,room.name),room) for room in rooms]
    scored=[item for item in scored if item[0]>0]
    if not scored: return None
    scored.sort(key=lambda item:item[0],reverse=True)
    return scored[0][1]
