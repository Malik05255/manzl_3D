from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def build_fixture(path:Path):
    document=fitz.open()
    page=document.new_page(width=420,height=320)
    shape=page.new_shape()

    # Thick vector walls form two closed rooms; the production PDF-vector path
    # can recover them without depending on OCR.
    for a,b in [
        ((60,55),(360,55)),
        ((360,55),(360,265)),
        ((360,265),(60,265)),
        ((60,265),(60,55)),
        ((210,55),(210,265)),
    ]:
        shape.draw_line(a,b)
    shape.finish(width=8,color=(0,0,0))
    shape.commit()

    page.insert_text((105,150),"ROOM A",fontsize=12)
    page.insert_text((255,150),"ROOM B",fontsize=12)
    document.save(path)
    document.close()


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("output")
    args=parser.parse_args()
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    build_fixture(target)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
