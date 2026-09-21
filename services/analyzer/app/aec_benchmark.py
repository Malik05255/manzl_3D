from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from .local_analysis import analyze_document_bytes_local


def _scale_point(point:dict,sx:float,sy:float)->list[float]:
    return [float(point["x"])*sx,float(point["y"])*sy]


def _wall_polygon(wall:dict,sx:float,sy:float)->list[list[float]]:
    ax=float(wall["a"]["x"])
    ay=float(wall["a"]["y"])
    bx=float(wall["b"]["x"])
    by=float(wall["b"]["y"])
    dx=bx-ax
    dy=by-ay
    length=math.hypot(dx,dy)
    if length<=1e-9:
        return []
    nx=-dy/length
    ny=dx/length
    half=max(1.0,float(wall.get("thicknessPx",4.0))/2)
    points=[
        {"x":ax+nx*half,"y":ay+ny*half},
        {"x":bx+nx*half,"y":by+ny*half},
        {"x":bx-nx*half,"y":by-ny*half},
        {"x":ax-nx*half,"y":ay-ny*half},
    ]
    return [_scale_point(point,sx,sy) for point in points]


def _opening_bbox(opening:dict,sx:float,sy:float,padding_px:float)->list[float]:
    xs=[float(opening["a"]["x"]),float(opening["b"]["x"])]
    ys=[float(opening["a"]["y"]),float(opening["b"]["y"])]
    return [
        (min(xs)-padding_px)*sx,
        (min(ys)-padding_px)*sy,
        (max(xs)+padding_px)*sx,
        (max(ys)+padding_px)*sy,
    ]


def _door_bbox(door:dict,sx:float,sy:float,padding_px:float)->list[float]:
    fallback=_opening_bbox(door,sx,sy,padding_px)
    side=str(door.get("doorSwingSide") or "unknown")
    try:
        depth=float(door.get("doorSwingDepthPx") or 0.0)
    except (TypeError,ValueError):
        return fallback
    if side not in {"positive","negative"} or depth<=1:
        return fallback

    ax=float(door["a"]["x"]); ay=float(door["a"]["y"])
    bx=float(door["b"]["x"]); by=float(door["b"]["y"])
    dx=bx-ax; dy=by-ay
    length=math.hypot(dx,dy)
    if length<=1e-9:
        return fallback
    nx=-dy/length; ny=dx/length
    sign=1.0 if side=="positive" else -1.0
    # Clamp noisy Hough depth to a plausible door-symbol envelope.
    depth=max(length*.25,min(depth,length*1.25))
    points=[
        (ax,ay),(bx,by),
        (ax+nx*depth*sign,ay+ny*depth*sign),
        (bx+nx*depth*sign,by+ny*depth*sign),
    ]
    pad=max(2.0,padding_px*.45)
    x1=min(point[0] for point in points)-pad
    y1=min(point[1] for point in points)-pad
    x2=max(point[0] for point in points)+pad
    y2=max(point[1] for point in points)+pad
    return [x1*sx,y1*sy,x2*sx,y2*sy]


def plan_to_aec_prediction(plan:dict,*,sheet:str,width:int,height:int)->dict:
    """Convert FloorPlanModel output into AEC-Geometric-Bench prediction JSON."""
    source_w=max(1.0,float(plan["widthPx"]))
    source_h=max(1.0,float(plan["heightPx"]))
    sx=float(width)/source_w
    sy=float(height)/source_h
    median_thickness=4.0
    if plan.get("walls"):
        ordered=sorted(max(1.0,float(item.get("thicknessPx",4.0))) for item in plan["walls"])
        median_thickness=ordered[len(ordered)//2]
    padding=max(3.0,median_thickness*1.25)

    objects=[]
    for door in plan.get("doors",[]):
        subtype=door.get("doorSubtype")
        object_class="Double Swing Door" if subtype=="double_swing" else "Single Swing Door"
        objects.append({
            "class":object_class,
            "bbox":_door_bbox(door,sx,sy,padding),
        })
    for window in plan.get("windows",[]):
        objects.append({
            "class":"Window",
            "bbox":_opening_bbox(window,sx,sy,padding),
        })

    symbol_classes={
        "sink":"Sink",
        "toilet":"Toilet",
        "bathtub":"Bathtub",
        "shower":"Shower",
        "cooktop":"Cooktops",
    }
    for symbol in plan.get("symbols",[]):
        object_class=symbol_classes.get(symbol.get("kind"))
        if not object_class:
            continue
        objects.append({
            "class":object_class,
            "bbox":[
                float(symbol["a"]["x"])*sx,
                float(symbol["a"]["y"])*sy,
                float(symbol["b"]["x"])*sx,
                float(symbol["b"]["y"])*sy,
            ],
        })

    areas=[
        [_scale_point(point,sx,sy) for point in room.get("polygon",[])]
        for room in plan.get("rooms",[])
        if len(room.get("polygon",[]))>=3
    ]
    walls=[
        polygon
        for wall in plan.get("walls",[])
        if len(polygon:=_wall_polygon(wall,sx,sy))>=3
    ]
    return {"sheet":sheet,"objects":objects,"areas":areas,"walls":walls}


def run_dataset(dataset_dir:Path,output_dir:Path,limit:int|None=None)->list[Path]:
    manifest=json.loads((dataset_dir/"manifest.json").read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True,exist_ok=True)
    written=[]
    sheets=manifest.get("sheets",[])
    if limit is not None:
        sheets=sheets[:max(0,limit)]

    for item in sheets:
        sheet=str(item["sheet"])
        pdf_path=dataset_dir/str(item["pdf"])
        data=pdf_path.read_bytes()
        plan=analyze_document_bytes_local(
            data,"application/pdf",project_id=sheet,filename=pdf_path.name,
        )
        prediction=plan_to_aec_prediction(
            plan,sheet=sheet,width=int(item["width"]),height=int(item["height"]),
        )
        target=output_dir/f"{sheet}.json"
        target.write_text(json.dumps(prediction,ensure_ascii=False),encoding="utf-8")
        written.append(target)
    return written



def parse_official_score_output(output:str)->dict:
    """Parse the stable summary lines emitted by AEC-Geometric-Bench score.py."""
    result={}
    mapping={
        "OBJECT MICRO":"objectMicro",
        "wall pixel":"wallPixel",
        "area pixel":"areaPixel",
        "area instance":"areaInstance",
    }
    for raw_line in output.splitlines():
        line=raw_line.strip()
        for prefix,key in mapping.items():
            if not line.startswith(prefix):
                continue
            numeric=[
                float(value)
                for value in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?",line[len(prefix):])
            ]
            if len(numeric)<3:
                continue
            precision,recall,f1=numeric[-3:]
            item={
                "precision":round(precision,4),
                "recall":round(recall,4),
                "f1":round(f1,4),
            }
            if key=="objectMicro" and len(numeric)>=6:
                item.update({
                    "tp":int(numeric[-6]),
                    "fp":int(numeric[-5]),
                    "fn":int(numeric[-4]),
                })
            result[key]=item
            break
    required={"objectMicro","wallPixel","areaPixel","areaInstance"}
    if set(result)!=required:
        missing=sorted(required-set(result))
        raise ValueError("AEC_SCORE_PARSE:"+",".join(missing))
    result["macroF1"]=round(sum(result[key]["f1"] for key in required)/len(required),4)
    return result


def run_official_scorer(
    scorer:Path,
    prediction_dir:Path,
    dataset_dir:Path,
)->tuple[int,str,dict|None]:
    command=[
        sys.executable,str(scorer),
        "--pred",str(prediction_dir),
        "--gt",str(dataset_dir),
        "--name","Manzil H",
    ]
    completed=subprocess.run(command,check=False,text=True,capture_output=True)
    output=(completed.stdout or "")+(("\n"+completed.stderr) if completed.stderr else "")
    report=None
    if completed.returncode==0:
        report=parse_official_score_output(output)
    return completed.returncode,output,report


def main()->int:
    parser=argparse.ArgumentParser(
        description="Run Manzil H against a licensed local copy of AEC-Geometric-Bench-15."
    )
    parser.add_argument("--dataset",required=True,help="Path to AEC benchmark dataset directory")
    parser.add_argument("--output",default="benchmark-output/aec15")
    parser.add_argument("--limit",type=int,default=None)
    parser.add_argument("--scorer",default=None,help="Optional path to the benchmark's official score.py")
    parser.add_argument("--report-json",default=None,help="Optional path for machine-readable official score summary")
    args=parser.parse_args()

    dataset=Path(args.dataset)
    output=Path(args.output)
    required=[dataset/"manifest.json",dataset/"annotations_15_scoring_ready.xml"]
    missing=[str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing benchmark files: "+", ".join(missing))

    written=run_dataset(dataset,output,args.limit)
    print(f"Wrote {len(written)} prediction file(s) to {output}")

    if args.scorer:
        code,score_output,report=run_official_scorer(Path(args.scorer),output,dataset)
        print(score_output,end="" if score_output.endswith("\n") else "\n")
        if args.report_json and report is not None:
            target=Path(args.report_json)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        return code
    if args.report_json:
        raise SystemExit("--report-json requires --scorer")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
