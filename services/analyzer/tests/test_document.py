import fitz
import numpy as np
import cv2

from app.document import _plan_likeness_score,decode_document_with_page


def test_plan_likeness_prefers_orthogonal_geometry():
    blank=np.full((500,500,3),255,dtype=np.uint8)
    cv2.putText(blank,"TITLE",(160,250),cv2.FONT_HERSHEY_SIMPLEX,1.0,(0,0,0),2)

    plan=np.full((500,500,3),255,dtype=np.uint8)
    for x in (60,180,320,440):
        cv2.line(plan,(x,60),(x,440),(0,0,0),5)
    for y in (60,190,310,440):
        cv2.line(plan,(60,y),(440,y),(0,0,0),5)

    assert _plan_likeness_score(plan)>_plan_likeness_score(blank)


def test_pdf_selects_floorplan_like_page():
    document=fitz.open()
    first=document.new_page(width=420,height=420)
    first.insert_text((120,210),"PROJECT NOTES",fontsize=18)

    second=document.new_page(width=420,height=420)
    shape=second.new_shape()
    for x in (50,160,280,370):
        shape.draw_line((x,50),(x,370))
    for y in (50,160,270,370):
        shape.draw_line((50,y),(370,y))
    shape.finish(width=4,color=(0,0,0))
    shape.commit()

    data=document.tobytes()
    document.close()

    image,page=decode_document_with_page(data,"application/pdf")
    assert page==2
    assert image.shape[0]>0 and image.shape[1]>0
