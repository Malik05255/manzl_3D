from __future__ import annotations

import argparse
import json
import math
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
        objects.append({
            "class":"Single Swing Door",
            "bbox":_opening_bbox(door,sx,sy,padding),
        })
    for window in plan.get("windows",[]):
        objects.append({
            "class":"Window",
            "bbox":_opening_bbox(window,sx,sy,padding),
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


def main()->int:
    parser=argparse.ArgumentParser(
        description="Run Manzil H against a licensed local copy of AEC-Geometric-Bench-15."
    )
    parser.add_argument("--dataset",required=True,help="Path to AEC benchmark dataset directory")
    parser.add_argument("--output",default="benchmark-output/aec15")
    parser.add_argument("--limit",type=int,default=None)
    parser.add_argument("--scorer",default=None,help="Optional path to the benchmark's official score.py")
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
        command=[
            sys.executable,str(Path(args.scorer)),
            "--pred",str(output),
            "--gt",str(dataset),
            "--name","Manzil H",
        ]
        return subprocess.run(command,check=False).returncode
    return 0


if __name__=="__main__":
    raise SystemExit(main())
