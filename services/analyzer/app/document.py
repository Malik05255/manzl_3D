from __future__ import annotations
import cv2
import fitz
import numpy as np

def decode_document(data:bytes,mime_type:str)->np.ndarray:
    if mime_type=="application/pdf":
        document=fitz.open(stream=data,filetype="pdf")
        if document.page_count<1:
            raise ValueError("PDF_EMPTY")
        page=document.load_page(0)
        pix=page.get_pixmap(matrix=fitz.Matrix(2.4,2.4),alpha=False)
        image=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        return cv2.cvtColor(image,cv2.COLOR_RGB2BGR)
    raw=np.frombuffer(data,dtype=np.uint8)
    image=cv2.imdecode(raw,cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("IMAGE_DECODE_FAILED")
    return image

def preprocess(image:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    gray=cv2.bilateralFilter(gray,7,35,35)
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,11)
    return gray,ink
