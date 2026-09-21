from __future__ import annotations
import math
import cv2
import numpy as np

def _dedupe(lines:list[tuple[int,int,int,int]],tol:int=8)->list[tuple[int,int,int,int]]:
    out=[]
    for line in sorted(lines,key=lambda p:math.hypot(p[2]-p[0],p[3]-p[1]),reverse=True):
        x1,y1,x2,y2=line; horizontal=abs(y2-y1)<=abs(x2-x1); duplicate=False
        for a,b,c,d in out:
            other=abs(d-b)<=abs(c-a)
            if horizontal!=other: continue
            if horizontal:
                same=abs(((y1+y2)/2)-((b+d)/2))<tol
                overlap=max(min(x1,x2),min(a,c))<=min(max(x1,x2),max(a,c))+tol
            else:
                same=abs(((x1+x2)/2)-((a+c)/2))<tol
                overlap=max(min(y1,y2),min(b,d))<=min(max(y1,y2),max(b,d))+tol
            if same and overlap: duplicate=True; break
        if not duplicate: out.append(line)
    return out

def detect_walls(ink:np.ndarray)->tuple[list[dict],np.ndarray]:
    h,w=ink.shape[:2]
    hk=max(18,w//45); vk=max(18,h//45)
    horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(hk,1)))
    vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,vk)))
    mask=cv2.bitwise_or(horizontal,vertical)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    raw=cv2.HoughLinesP(mask,1,np.pi/180,threshold=max(40,min(h,w)//18),minLineLength=max(35,min(h,w)//18),maxLineGap=12)
    lines=[]
    if raw is not None:
        for item in raw[:,0]:
            x1,y1,x2,y2=map(int,item); dx,dy=abs(x2-x1),abs(y2-y1)
            if dx>=dy*4:
                y=int(round((y1+y2)/2)); lines.append((min(x1,x2),y,max(x1,x2),y))
            elif dy>=dx*4:
                x=int(round((x1+x2)/2)); lines.append((x,min(y1,y2),x,max(y1,y2)))
    walls=[{"id":f"wall-{i+1}","a":{"x":float(x1),"y":float(y1)},"b":{"x":float(x2),"y":float(y2)},"thicknessPx":4.0,"confidence":0.78} for i,(x1,y1,x2,y2) in enumerate(_dedupe(lines))]
    return walls,mask
