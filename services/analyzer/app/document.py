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


def _order_quad(points:np.ndarray)->np.ndarray:
    pts=np.asarray(points,dtype=np.float32).reshape(4,2)
    sums=pts.sum(axis=1)
    diffs=np.diff(pts,axis=1).reshape(-1)
    return np.array([
        pts[np.argmin(sums)],
        pts[np.argmin(diffs)],
        pts[np.argmax(sums)],
        pts[np.argmax(diffs)],
    ],dtype=np.float32)


def _detect_document_quad(image:np.ndarray)->np.ndarray|None:
    h,w=image.shape[:2]
    longest=max(h,w)
    scale=min(1.0,1400.0/max(1,longest))
    preview=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA) if scale<1 else image.copy()
    gray=cv2.cvtColor(preview,cv2.COLOR_BGR2GRAY)
    gray=cv2.GaussianBlur(gray,(5,5),0)
    edges=cv2.Canny(gray,45,135)
    edges=cv2.dilate(edges,np.ones((3,3),np.uint8),iterations=1)
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    page_area=float(preview.shape[0]*preview.shape[1])

    best=None
    best_area=0.0
    for contour in sorted(contours,key=cv2.contourArea,reverse=True)[:30]:
        perimeter=cv2.arcLength(contour,True)
        approx=cv2.approxPolyDP(contour,0.018*perimeter,True)
        if len(approx)!=4 or not cv2.isContourConvex(approx):
            continue
        area=float(cv2.contourArea(approx))
        if area<page_area*0.38:
            continue
        x,y,rw,rh=cv2.boundingRect(approx)
        if rw<preview.shape[1]*0.45 or rh<preview.shape[0]*0.45:
            continue
        if area>best_area:
            best_area=area
            best=approx.reshape(4,2).astype(np.float32)

    if best is None:
        return None
    return _order_quad(best/scale)


def _warp_quad(image:np.ndarray,quad:np.ndarray)->np.ndarray:
    ordered=_order_quad(quad)
    tl,tr,br,bl=ordered
    width_top=np.linalg.norm(tr-tl)
    width_bottom=np.linalg.norm(br-bl)
    height_left=np.linalg.norm(bl-tl)
    height_right=np.linalg.norm(br-tr)
    width=int(round(max(width_top,width_bottom)))
    height=int(round(max(height_left,height_right)))
    if width<120 or height<120:
        return image

    destination=np.array([
        [0,0],
        [width-1,0],
        [width-1,height-1],
        [0,height-1],
    ],dtype=np.float32)
    matrix=cv2.getPerspectiveTransform(ordered,destination)
    return cv2.warpPerspective(
        image,matrix,(width,height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255,255,255),
    )


def _deskew_angle(image:np.ndarray)->float:
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,60,170)
    h,w=gray.shape[:2]
    raw=cv2.HoughLinesP(
        edges,1,np.pi/180,
        threshold=max(50,min(h,w)//12),
        minLineLength=max(60,min(h,w)//7),
        maxLineGap=max(8,min(h,w)//120),
    )
    if raw is None:
        return 0.0
    angles=[]
    weights=[]
    for x1,y1,x2,y2 in raw[:,0]:
        dx=float(x2-x1); dy=float(y2-y1)
        length=float((dx*dx+dy*dy)**0.5)
        if length<40:
            continue
        angle=float(np.degrees(np.arctan2(dy,dx)))
        while angle>45:
            angle-=90
        while angle<-45:
            angle+=90
        if abs(angle)<=10:
            angles.append(angle)
            weights.append(length)
    if not angles:
        return 0.0
    order=np.argsort(angles)
    angles_arr=np.array(angles)[order]
    weights_arr=np.array(weights)[order]
    cutoff=weights_arr.sum()/2
    index=int(np.searchsorted(np.cumsum(weights_arr),cutoff))
    return float(angles_arr[min(index,len(angles_arr)-1)])


def _rotate_keep_bounds(image:np.ndarray,angle:float)->np.ndarray:
    if abs(angle)<0.35:
        return image
    h,w=image.shape[:2]
    center=(w/2.0,h/2.0)
    matrix=cv2.getRotationMatrix2D(center,-angle,1.0)
    cos=abs(matrix[0,0]); sin=abs(matrix[0,1])
    new_w=int(round(h*sin+w*cos))
    new_h=int(round(h*cos+w*sin))
    matrix[0,2]+=new_w/2-center[0]
    matrix[1,2]+=new_h/2-center[1]
    return cv2.warpAffine(
        image,matrix,(new_w,new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255,255,255),
    )


def normalize_resolution(image:np.ndarray)->np.ndarray:
    h,w=image.shape[:2]
    short=max(1,min(h,w))
    long=max(h,w)

    if long>5200:
        scale=5200.0/long
    elif short<1050 and long<4200:
        scale=min(2.2,1200.0/short)
    else:
        return image

    new_w=max(1,int(round(w*scale)))
    new_h=max(1,int(round(h*scale)))
    interpolation=cv2.INTER_CUBIC if scale>1 else cv2.INTER_AREA
    return cv2.resize(image,(new_w,new_h),interpolation=interpolation)


def normalize_raster_document(image:np.ndarray)->np.ndarray:
    quad=_detect_document_quad(image)
    normalized=_warp_quad(image,quad) if quad is not None else image
    angle=_deskew_angle(normalized)
    if abs(angle)<=8:
        normalized=_rotate_keep_bounds(normalized,angle)
    return normalize_resolution(normalized)


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
    return normalize_raster_document(image),1


def decode_document(data:bytes,mime_type:str)->np.ndarray:
    image,_=decode_document_with_page(data,mime_type)
    return image


def preprocess(image:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    gray=cv2.createCLAHE(clipLimit=1.8,tileGridSize=(8,8)).apply(gray)
    gray=cv2.bilateralFilter(gray,7,35,35)
    ink=cv2.adaptiveThreshold(
        gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,11
    )
    return gray,ink
