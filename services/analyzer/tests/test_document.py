import fitz
import numpy as np
import cv2

from app.document import PDF_RENDER_SCALE,_order_quad,_plan_likeness_score,_warp_quad,decode_document_with_page,extract_pdf_text_lines,extract_pdf_vector_lines,normalize_resolution,pdf_page_count


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


def test_orders_and_warps_document_quad():
    image=np.full((320,420,3),220,dtype=np.uint8)
    quad=np.array([[70,45],[360,70],[330,275],[45,250]],dtype=np.float32)
    cv2.fillConvexPoly(image,quad.astype(np.int32),(255,255,255))
    cv2.polylines(image,[quad.astype(np.int32)],True,(0,0,0),5)
    ordered=_order_quad(quad[[2,0,3,1]])
    assert ordered.shape==(4,2)
    warped=_warp_quad(image,quad)
    assert warped.shape[0]>180
    assert warped.shape[1]>250


def test_low_resolution_plan_is_upscaled():
    image=np.full((500,800,3),255,dtype=np.uint8)
    resized=normalize_resolution(image)
    assert min(resized.shape[:2])>=1100
    assert max(resized.shape[:2])<2000


def test_very_large_plan_is_capped():
    image=np.full((5400,1200,3),255,dtype=np.uint8)
    resized=normalize_resolution(image)
    assert max(resized.shape[:2])<=5200


def test_pdf_native_text_is_extracted_in_render_coordinates():
    document=fitz.open()
    page=document.new_page(width=400,height=300)
    page.insert_text((100,120),"BEDROOM 5.00 m",fontsize=16)
    data=document.tobytes()
    document.close()

    lines=extract_pdf_text_lines(data,1)
    match=next(item for item in lines if "BEDROOM" in item["text"])
    assert match["center"]["x"]>100*PDF_RENDER_SCALE
    assert match["center"]["y"]>90*PDF_RENDER_SCALE


def test_pdf_native_vector_lines_are_scaled_to_render_coordinates():
    document=fitz.open()
    page=document.new_page(width=400,height=300)
    shape=page.new_shape()
    shape.draw_line((50,80),(350,80))
    shape.draw_line((200,40),(200,260))
    shape.finish(width=5,color=(0,0,0))
    shape.commit()
    data=document.tobytes()
    document.close()

    lines=extract_pdf_vector_lines(data,1)
    horizontal=next(item for item in lines if abs(item["a"]["y"]-item["b"]["y"])<1 and item["b"]["x"]-item["a"]["x"]>500)
    vertical=next(item for item in lines if abs(item["a"]["x"]-item["b"]["x"])<1 and item["b"]["y"]-item["a"]["y"]>350)
    assert horizontal["a"]["x"]==50*PDF_RENDER_SCALE
    assert vertical["a"]["x"]==200*PDF_RENDER_SCALE
    assert horizontal["widthPx"]>=5*PDF_RENDER_SCALE


def test_pdf_can_render_explicit_selected_page():
    document=fitz.open()
    first=document.new_page(width=300,height=300)
    first.insert_text((80,150),"PAGE ONE",fontsize=18)
    second=document.new_page(width=300,height=300)
    second.insert_text((80,150),"PAGE TWO",fontsize=18)
    data=document.tobytes()
    document.close()

    image,page=decode_document_with_page(data,"application/pdf",preferred_page=1)
    assert page==1
    assert image.shape[0]>0
    assert pdf_page_count(data)==2


def test_pdf_rejects_out_of_range_selected_page():
    document=fitz.open()
    document.new_page(width=300,height=300)
    data=document.tobytes()
    document.close()

    import pytest
    with pytest.raises(ValueError,match="PDF_PAGE_OUT_OF_RANGE"):
        decode_document_with_page(data,"application/pdf",preferred_page=2)
