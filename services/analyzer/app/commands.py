from __future__ import annotations
import re
from .ocr import normalize_digits

GENERIC_ROOM_WORDS={"غرفه","الغرفه","room","منطقه","مساحه"}

def normalize_arabic(text:str)->str:
    text=normalize_digits(text).lower()
    text=re.sub(r"[\u064b-\u065f\u0670]","",text)
    return (text.replace("أ","ا").replace("إ","ا").replace("آ","ا")
        .replace("ة","ه").replace("ى","ي").replace("ـ","").strip())

def _valid_dimension(value:float)->bool:
    return 0.8<=value<=50

def parse_target_size(command:str)->tuple[float,float]|None:
    text=normalize_arabic(command)
    match=re.search(
        r"(\d+(?:\.\d+)?)\s*(?:م|متر)?\s*(?:x|×|\*|في)\s*(\d+(?:\.\d+)?)\s*(?:م|متر)?",
        text,
    )
    if not match:
        return None
    width=float(match.group(1)); height=float(match.group(2))
    if not (_valid_dimension(width) and _valid_dimension(height)):
        return None
    return width,height

def _named_value(text:str,words:tuple[str,...])->float|None:
    alternatives="|".join(re.escape(word) for word in words)
    match=re.search(
        rf"(?:{alternatives}).{0,45}?(\d+(?:\.\d+)?)\s*(?:متر|م)?(?=\s|$|[،,.])",
        text,
    )
    if not match:
        return None
    value=float(match.group(1))
    return value if _valid_dimension(value) else None

def _relative_delta(text:str,dimension_words:tuple[str,...])->float|None:
    dimensions="|".join(re.escape(word) for word in dimension_words)
    increase=r"(?:زد|زود|كبر|وسع|زيد)"
    decrease=r"(?:قلل|نقص|صغر)"
    unit=r"(سنتيمتر|متر|سم|م)"
    end=r"(?=\s|$|[،,.])"

    for sign,actions in ((1.0,increase),(-1.0,decrease)):
        context=rf"{actions}.{{0,35}}?(?:{dimensions}).{{0,35}}?"
        explicit=re.search(context+rf"(\d+(?:\.\d+)?)\s*{unit}{end}",text)
        if explicit:
            value=float(explicit.group(1))
            if explicit.group(2) in ("سم","سنتيمتر"):
                value/=100
            return sign*value if 0<value<=20 else None

        default_one=re.search(context+rf"{unit}{end}",text)
        if default_one:
            value=0.01 if default_one.group(1) in ("سم","سنتيمتر") else 1.0
            return sign*value

    return None

def resolve_target_size(command:str,current_width:float,current_height:float)->tuple[float,float]|None:
    absolute=parse_target_size(command)
    if absolute:
        return absolute

    text=normalize_arabic(command)
    width=_named_value(text,("العرض","عرض"))
    height=_named_value(text,("الطول","طول","العمق","عمق"))
    if width is not None or height is not None:
        result=(width if width is not None else current_width,height if height is not None else current_height)
        return result if _valid_dimension(result[0]) and _valid_dimension(result[1]) else None

    width_delta=_relative_delta(text,("العرض","عرض"))
    height_delta=_relative_delta(text,("الطول","طول","العمق","عمق"))
    if width_delta is None and height_delta is None:
        return None

    target_width=current_width+(width_delta or 0)
    target_height=current_height+(height_delta or 0)
    if not (_valid_dimension(target_width) and _valid_dimension(target_height)):
        return None
    return target_width,target_height

def room_match(command:str,room_name:str)->float:
    cmd=normalize_arabic(command)
    name=normalize_arabic(room_name)
    if name and name in cmd:
        return 1.0

    name_tokens={
        token for token in re.split(r"\s+",name)
        if len(token)>2 and not token.isdigit() and token not in GENERIC_ROOM_WORDS
    }
    cmd_tokens={
        token for token in re.split(r"\s+",cmd)
        if len(token)>2 and not token.isdigit() and token not in GENERIC_ROOM_WORDS
    }
    if not name_tokens:
        return 0.0
    return len(name_tokens & cmd_tokens)/len(name_tokens)

def find_target_room(command:str,rooms:list)->object|None:
    scored=[(room_match(command,room.name),room) for room in rooms]
    scored=[item for item in scored if item[0]>0]
    if not scored:
        return None
    scored.sort(key=lambda item:item[0],reverse=True)
    if len(scored)>1 and abs(scored[0][0]-scored[1][0])<0.05:
        return None
    return scored[0][1]
