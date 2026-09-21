from __future__ import annotations
import os
import cv2
import fitz
import numpy as np


def _pixmap_to_bgr(pix:fitz.Pixmap)->np.ndarray:
    image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
    if pix.n==4:
        return cv2.cvtColor(image,cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(image,cv2.COLOR_RGB2BGR)


def _render_page(page:fitz.Page,scale:float)->np.ndarray:
    pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
    return _pixmap_to_bgr(pix)


def _plan_likeness_score(image:np.ndarray)->float:
    if image.size==0:
        return -1.0

    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    _,ink=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    h,w=ink.shape[:2]
    if h<40 or w<40:
        return -1.0

    ink_ratio=float(cv2.countNonZero(ink))/float(h*w)
    if ink_ratio<0.002:
        return 0.0

    hk=max(12,w//24)
    vk=max(12,h//24)
    horizontal=cv2.morphologyEx(
        ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(hk,1))
    )
    vertical=cv2.morphologyEx(
        ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,vk))
    )
    orthogonal=cv2.bitwise_or(horizontal,vertical)
    line_ratio=float(cv2.countNonZero(orthogonal))/float(h*w)

    raw=cv2.HoughLinesP(
        orthogonal,
        1,
        np.pi/180,
        threshold=max(18,min(h,w)//28),
        minLineLength=max(24,min(h,w)//12),
        maxLineGap=max(5,min(h,w)//100),
    )
    long_lines=0
    if raw is not None:
        for x1,y1,x2,y2 in raw[:,0]:
            dx=abs(int(x2)-int(x1))
            dy=abs(int(y2)-int(y1))
            if dx>=dy*5 or dy>=dx*5:
                long_lines+=1

    # Plans usually contain many long orthogonal segments but do not fill the page with ink.
    density_bonus=min(line_ratio*240.0,18.0)
    line_bonus=min(long_lines,60)*0.55
    ink_bonus=min(ink_ratio,0.16)*20.0
    dense_penalty=max(0.0,ink_ratio-0.35)*45.0
    return line_bonus+density_bonus+ink_bonus-dense_penalty


def _candidate_page_indexes(page_count:int)->list[int]:
    configured=int(os.getenv("PDF_PAGE_SCAN_LIMIT","40") or "40")
    limit=max(1,min(configured,100))
    if page_count<=limit:
        return list(range(page_count))
    points=np.linspace(0,page_count-1,num=limit,dtype=int)
    return sorted(set(int(value) for value in points))


def decode_document_with_page(data:bytes,mime_type:str)->tuple[np.ndarray,int]:
    if mime_type=="application/pdf":
        document=fitz.open(stream=data,filetype="pdf")
        try:
            if document.page_count<1:
                raise ValueError("PDF_EMPTY")

            best_index=0
            best_score=float("-inf")
            for index in _candidate_page_indexes(document.page_count):
                preview=_render_page(document.load_page(index),0.72)
                score=_plan_likeness_score(preview)
                if score>best_score:
                    best_score=score
                    best_index=index

            image=_render_page(document.load_page(best_index),2.4)
            return image,best_index+1
        finally:
            document.close()

    raw=np.frombuffer(data,dtype=np.uint8)
    image=cv2.imdecode(raw,cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("IMAGE_DECODE_FAILED")
    return image,1


def decode_document(data:bytes,mime_type:str)->np.ndarray:
    image,_=decode_document_with_page(data,mime_type)
    return image


def preprocess(image:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    gray=cv2.bilateralFilter(gray,7,35,35)
    ink=cv2.adaptiveThreshold(
        gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,11
    )
    return gray,ink
