from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from app.document import decode_document_with_page, extract_pdf_vector_lines


def angle_delta(a: float, b: float) -> float:
    value=abs((a-b)%180.0)
    return min(value,180.0-value)


def segment_bbox(line:dict)->tuple[float,float,float,float]:
    ax=float(line["a"]["x"]); ay=float(line["a"]["y"])
    bx=float(line["b"]["x"]); by=float(line["b"]["y"])
    return min(ax,bx),min(ay,by),max(ax,bx),max(ay,by)


def intersects(a,b)->bool:
    return not (a[2]<b[0] or b[2]<a[0] or a[3]<b[1] or b[3]<a[1])


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--dataset",required=True)
    parser.add_argument("--sheet",default="sheet_05")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()

    dataset=Path(args.dataset)
    manifest=json.loads((dataset/"manifest.json").read_text(encoding="utf-8"))
    meta=next(item for item in manifest if item["sheet"]==args.sheet)
    pdf=(dataset/meta["pdf"]).read_bytes()

    image,page=decode_document_with_page(pdf,"application/pdf",1)
    h,w=image.shape[:2]
    vectors=extract_pdf_vector_lines(pdf,page)

    root=ET.parse(dataset/"annotations_15_scoring_ready.xml").getroot()
    node=next(
        img for img in root.findall("image")
        if Path(img.get("name","")).stem==args.sheet
    )
    gt_w=float(node.get("width")); gt_h=float(node.get("height"))
    sx=w/gt_w; sy=h/gt_h

    probes=[]
    for child in node:
        label=child.get("label")
        if child.tag!="box" or label not in {
            "Window","Single Swing Door","Double Swing Door",
            "Sink","Toilet","Bathtub","Cooktops",
        }:
            continue
        gt=[
            float(child.get("xtl")),float(child.get("ytl")),
            float(child.get("xbr")),float(child.get("ybr")),
        ]
        box=[gt[0]*sx,gt[1]*sy,gt[2]*sx,gt[3]*sy]
        bw=box[2]-box[0]; bh=box[3]-box[1]
        long=max(bw,bh); short=max(1.0,min(bw,bh))
        host_angle=0.0 if bw>=bh else 90.0
        pad=max(12.0,short*.8)
        expanded=[box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad]

        nearby=[]
        for line in vectors:
            sb=segment_bbox(line)
            if not intersects(sb,expanded):
                continue
            ax=float(line["a"]["x"]); ay=float(line["a"]["y"])
            bx=float(line["b"]["x"]); by=float(line["b"]["y"])
            dx=bx-ax; dy=by-ay
            length=math.hypot(dx,dy)
            angle=(math.degrees(math.atan2(dy,dx))+180.0)%180.0
            nearby.append({
                "a":[round(ax,2),round(ay,2)],
                "b":[round(bx,2),round(by,2)],
                "length":round(length,2),
                "angle":round(angle,2),
                "widthPx":float(line.get("widthPx",1.0)),
                "parallel":angle_delta(angle,host_angle)<=8.0,
                "perpendicular":angle_delta(angle,(host_angle+90.0)%180.0)<=8.0,
                "longRatio":round(length/max(long,1.0),3),
            })

        parallel=[x for x in nearby if x["parallel"]]
        perpendicular=[x for x in nearby if x["perpendicular"]]
        probes.append({
            "label":label,
            "gtBBox":gt,
            "renderBBox":[round(v,2) for v in box],
            "orientation":"horizontal" if host_angle==0 else "vertical",
            "longPx":round(long,2),
            "shortPx":round(short,2),
            "nearbyCount":len(nearby),
            "parallelCount":len(parallel),
            "perpendicularCount":len(perpendicular),
            "parallelLengths":[x["length"] for x in parallel],
            "parallelWidths":[x["widthPx"] for x in parallel],
            "segments":sorted(nearby,key=lambda x:x["length"])[:80],
        })

    output={
        "sheet":args.sheet,
        "renderWidth":w,
        "renderHeight":h,
        "gtWidth":gt_w,
        "gtHeight":gt_h,
        "scaleX":sx,
        "scaleY":sy,
        "vectorCount":len(vectors),
        "probes":probes,
    }
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "sheet":args.sheet,
        "render":[w,h],
        "vectorCount":len(vectors),
        "summary":[
            {
                "label":p["label"],
                "orientation":p["orientation"],
                "nearby":p["nearbyCount"],
                "parallel":p["parallelCount"],
                "perpendicular":p["perpendicularCount"],
                "parallelLengths":p["parallelLengths"][:10],
            }
            for p in probes
        ],
    },ensure_ascii=False))


if __name__=="__main__":
    main()
