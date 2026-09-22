from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2

from .debug_render import render_extraction_overlay
from .document import decode_document_with_page
from .local_analysis import analyze_document_bytes_local


AEC_OBJECT_CLASSES=[
    "Single Swing Door","Double Swing Door","Window","Sink",
    "Toilet","Bathtub","Shower","Cooktops",
]


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


def _window_bbox(window:dict,sx:float,sy:float,padding_px:float)->list[float]:
    """Use vector glazing depth when available instead of generic wall padding."""
    try:
        depth=float(window.get("windowDepthPx") or 0.0)
    except (TypeError,ValueError):
        depth=0.0
    if str(window.get("provenance",""))!="pdf-vector" or depth<=1.0:
        return _opening_bbox(window,sx,sy,padding_px)

    ax=float(window["a"]["x"]); ay=float(window["a"]["y"])
    bx=float(window["b"]["x"]); by=float(window["b"]["y"])
    dx=bx-ax; dy=by-ay
    length=math.hypot(dx,dy)
    if length<=1e-9:
        return _opening_bbox(window,sx,sy,padding_px)

    ux=dx/length; uy=dy/length
    nx=-uy; ny=ux
    # Native PDF vectors already describe the glazing span closely. Preserve
    # that span and add only a tiny longitudinal tolerance for scorer/raster
    # quantization rather than reusing median wall thickness.
    longitudinal_pad=max(1.0,min(4.0,padding_px*.12))
    half=max(2.0,depth/2.0,padding_px*.48)
    half=min(half,padding_px*.72)
    points=[
        (ax-ux*longitudinal_pad+nx*half,ay-uy*longitudinal_pad+ny*half),
        (bx+ux*longitudinal_pad+nx*half,by+uy*longitudinal_pad+ny*half),
        (bx+ux*longitudinal_pad-nx*half,by+uy*longitudinal_pad-ny*half),
        (ax-ux*longitudinal_pad-nx*half,ay-uy*longitudinal_pad-ny*half),
    ]
    return [
        min(point[0] for point in points)*sx,
        min(point[1] for point in points)*sy,
        max(point[0] for point in points)*sx,
        max(point[1] for point in points)*sy,
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
        # The official released AEC object taxonomy scores swing doors but not
        # Sliding Door annotations. Do not turn an explicit sliding correction
        # into a false Single Swing Door prediction.
        if subtype=="sliding":
            continue
        object_class="Double Swing Door" if subtype=="double_swing" else "Single Swing Door"
        objects.append({
            "class":object_class,
            "bbox":_door_bbox(door,sx,sy,padding),
        })
    for window in plan.get("windows",[]):
        objects.append({
            "class":"Window",
            "bbox":_window_bbox(window,sx,sy,padding),
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
    # The released AEC benchmark counts stairs/elevators as Area rather than
    # object classes. Symbol detections can therefore recover these spaces when
    # room segmentation misses their enclosures.
    for symbol in plan.get("symbols",[]):
        if symbol.get("kind") not in {"stairs","elevator"}:
            continue
        x1=float(symbol["a"]["x"])*sx
        y1=float(symbol["a"]["y"])*sy
        x2=float(symbol["b"]["x"])*sx
        y2=float(symbol["b"]["y"])*sy
        if x2>x1 and y2>y1:
            areas.append([
                [x1,y1],[x2,y1],[x2,y2],[x1,y2],
            ])

    # Canonical plans intentionally retain low-confidence vector/raster
    # candidates for human review. The benchmark prediction represents the
    # automatic accepted result, so quarantined candidates must not count as
    # final walls.
    walls=[
        polygon
        for wall in plan.get("walls",[])
        if (
            wall.get("confidence") is None
            or float(wall.get("confidence",1.0))>=.70
        )
        and len(polygon:=_wall_polygon(wall,sx,sy))>=3
    ]
    return {"sheet":sheet,"objects":objects,"areas":areas,"walls":walls}


def run_dataset(dataset_dir:Path,output_dir:Path,limit:int|None=None,offset:int=0)->list[Path]:
    manifest=json.loads((dataset_dir/"manifest.json").read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True,exist_ok=True)
    canonical_dir=output_dir/"_canonical"
    debug_dir=output_dir/"_debug"
    timing_dir=output_dir/"_timings"
    canonical_dir.mkdir(parents=True,exist_ok=True)
    debug_dir.mkdir(parents=True,exist_ok=True)
    timing_dir.mkdir(parents=True,exist_ok=True)
    written=[]
    sheets=manifest.get("sheets",[])
    start=max(0,int(offset))
    sheets=sheets[start:]
    if limit is not None:
        sheets=sheets[:max(0,limit)]

    for item in sheets:
        sheet=str(item["sheet"])
        pdf_path=dataset_dir/str(item["pdf"])
        started=time.perf_counter()
        data=pdf_path.read_bytes()
        read_done=time.perf_counter()
        plan=analyze_document_bytes_local(
            data,"application/pdf",project_id=sheet,filename=pdf_path.name,
        )
        analysis_done=time.perf_counter()
        canonical_target=canonical_dir/f"{sheet}.json"
        canonical_target.write_text(
            json.dumps(plan,ensure_ascii=False,indent=2),
            encoding="utf-8",
        )
        source_image,_=decode_document_with_page(
            data,
            "application/pdf",
            int(plan.get("source",{}).get("page",1)),
        )
        overlay=render_extraction_overlay(source_image,plan)
        cv2.imwrite(str(debug_dir/f"{sheet}.png"),overlay)
        render_done=time.perf_counter()

        prediction=plan_to_aec_prediction(
            plan,sheet=sheet,width=int(item["width"]),height=int(item["height"]),
        )
        target=output_dir/f"{sheet}.json"
        target.write_text(json.dumps(prediction,ensure_ascii=False),encoding="utf-8")
        finished=time.perf_counter()
        timing={
            "sheet":sheet,
            "sourceBytes":len(data),
            "sourceWidth":int(plan.get("widthPx",0) or 0),
            "sourceHeight":int(plan.get("heightPx",0) or 0),
            "readSeconds":round(read_done-started,4),
            "analysisSeconds":round(analysis_done-read_done,4),
            "diagnosticRenderSeconds":round(render_done-analysis_done,4),
            "predictionExportSeconds":round(finished-render_done,4),
            "totalSeconds":round(finished-started,4),
            "counts":{
                "walls":len(plan.get("walls",[])),
                "rooms":len(plan.get("rooms",[])),
                "doors":len(plan.get("doors",[])),
                "windows":len(plan.get("windows",[])),
                "symbols":len(plan.get("symbols",[])),
                "dimensions":len(plan.get("dimensions",[])),
            },
            "engines":list(plan.get("analysis",{}).get("engines",[])),
        }
        (timing_dir/f"{sheet}.json").write_text(
            json.dumps(timing,ensure_ascii=False,indent=2),encoding="utf-8",
        )
        print(
            f"{sheet}: analysis={timing['analysisSeconds']:.2f}s "
            f"render={timing['diagnosticRenderSeconds']:.2f}s "
            f"total={timing['totalSeconds']:.2f}s"
        )
        written.append(target)
    return written



def parse_official_score_output(output:str)->dict:
    """Parse aggregate and per-class summary lines emitted by official score.py."""
    result={}
    mapping={
        "OBJECT MICRO":"objectMicro",
        "wall pixel":"wallPixel",
        "area pixel":"areaPixel",
        "area instance":"areaInstance",
    }
    classes={}
    for raw_line in output.splitlines():
        line=raw_line.strip()
        if not line or line.startswith("-"):
            continue

        matched_class=next(
            (name for name in AEC_OBJECT_CLASSES if line.startswith(name)),
            None,
        )
        if matched_class is not None:
            numeric=[
                float(value)
                for value in re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?",line[len(matched_class):])
            ]
            if len(numeric)>=6:
                classes[matched_class]={
                    "tp":int(numeric[-6]),
                    "fp":int(numeric[-5]),
                    "fn":int(numeric[-4]),
                    "precision":round(numeric[-3],4),
                    "recall":round(numeric[-2],4),
                    "f1":round(numeric[-1],4),
                }
            continue

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
    if not required.issubset(result):
        missing=sorted(required-set(result))
        raise ValueError("AEC_SCORE_PARSE:"+",".join(missing))
    result["macroF1"]=round(sum(result[key]["f1"] for key in required)/len(required),4)
    result["classes"]=classes
    return result


def _write_gt_subset(dataset_dir:Path,target_dir:Path,sheet_names:list[str])->Path:
    source=dataset_dir/"annotations_15_scoring_ready.xml"
    tree=ET.parse(source)
    root=tree.getroot()
    selected=set(sheet_names)
    for image in list(root.findall("image")):
        name=Path(str(image.get("name") or "")).stem
        if name not in selected:
            root.remove(image)
    target_dir.mkdir(parents=True,exist_ok=True)
    target=target_dir/"annotations_15_scoring_ready.xml"
    tree.write(target,encoding="utf-8",xml_declaration=True)
    return target


def _score_command(scorer:Path,prediction_dir:Path,dataset_dir:Path)->tuple[int,str,dict|None]:
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


def run_official_scorer(
    scorer:Path,
    prediction_dir:Path,
    dataset_dir:Path,
    *,
    sheet_names:list[str]|None=None,
    include_per_sheet:bool=True,
)->tuple[int,str,dict|None]:
    selected=sheet_names or sorted(path.stem for path in prediction_dir.glob("*.json"))
    with tempfile.TemporaryDirectory(prefix="manzil-aec-gt-") as temp:
        score_gt=dataset_dir
        if selected:
            _write_gt_subset(dataset_dir,Path(temp),selected)
            score_gt=Path(temp)
        code,output,report=_score_command(scorer,prediction_dir,score_gt)
        if code!=0 or report is None:
            return code,output,report

        report["sheets"]={}
        if include_per_sheet:
            for sheet in selected:
                per_sheet_dir=Path(temp)/f"sheet-{sheet}"
                _write_gt_subset(dataset_dir,per_sheet_dir,[sheet])
                sheet_code,_,sheet_report=_score_command(
                    scorer,prediction_dir,per_sheet_dir,
                )
                if sheet_code==0 and sheet_report is not None:
                    sheet_report.pop("sheets",None)
                    report["sheets"][sheet]=sheet_report
        report["selectedSheets"]=selected
        return code,output,report


def main()->int:
    parser=argparse.ArgumentParser(
        description="Run Manzil H against a licensed local copy of AEC-Geometric-Bench-15."
    )
    parser.add_argument("--dataset",required=True,help="Path to AEC benchmark dataset directory")
    parser.add_argument("--output",default="benchmark-output/aec15")
    parser.add_argument("--limit",type=int,default=None)
    parser.add_argument("--offset",type=int,default=0,help="Zero-based manifest offset for sharded runs")
    parser.add_argument("--scorer",default=None,help="Optional path to the benchmark's official score.py")
    parser.add_argument("--report-json",default=None,help="Optional path for machine-readable official score summary")
    args=parser.parse_args()

    dataset=Path(args.dataset)
    output=Path(args.output)
    required=[dataset/"manifest.json",dataset/"annotations_15_scoring_ready.xml"]
    missing=[str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing benchmark files: "+", ".join(missing))

    written=run_dataset(dataset,output,args.limit,args.offset)
    print(f"Wrote {len(written)} prediction file(s) to {output}")

    if args.scorer:
        code,score_output,report=run_official_scorer(
            Path(args.scorer),
            output,
            dataset,
            sheet_names=[path.stem for path in written],
            include_per_sheet=True,
        )
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
