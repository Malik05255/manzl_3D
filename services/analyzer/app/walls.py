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

def _estimate_thickness(ink:np.ndarray,line:tuple[int,int,int,int])->float:
    x1,y1,x2,y2=line
    h,w=ink.shape[:2]
    horizontal=abs(y2-y1)<=abs(x2-x1)
    max_radius=max(6,min(36,min(h,w)//45))

    if horizontal:
        axis=int(round((y1+y2)/2))
        start=max(0,min(x1,x2)); end=min(w,max(x1,x2)+1)
        if end-start<6:
            return 4.0
        trim=max(1,int((end-start)*0.12))
        start=min(end-1,start+trim); end=max(start+1,end-trim)
        top=max(0,axis-max_radius); bottom=min(h,axis+max_radius+1)
        strip=ink[top:bottom,start:end]
        if strip.size==0:
            return 4.0
        density=np.mean(strip>0,axis=1)
        active=np.where(density>=0.10)[0]
        center=axis-top
    else:
        axis=int(round((x1+x2)/2))
        start=max(0,min(y1,y2)); end=min(h,max(y1,y2)+1)
        if end-start<6:
            return 4.0
        trim=max(1,int((end-start)*0.12))
        start=min(end-1,start+trim); end=max(start+1,end-trim)
        left=max(0,axis-max_radius); right=min(w,axis+max_radius+1)
        strip=ink[start:end,left:right]
        if strip.size==0:
            return 4.0
        density=np.mean(strip>0,axis=0)
        active=np.where(density>=0.10)[0]
        center=axis-left

    if active.size==0:
        return 4.0

    # Only use evidence reasonably close to the detected wall axis so nearby
    # dimension lines/text do not inflate wall thickness.
    active=active[np.abs(active-center)<=max_radius]
    if active.size==0:
        return 4.0
    thickness=float(active.max()-active.min()+1)
    return max(2.0,min(32.0,thickness))


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
    deduped=_dedupe(lines)
    walls=[{"id":f"wall-{i+1}","a":{"x":float(x1),"y":float(y1)},"b":{"x":float(x2),"y":float(y2)},"thicknessPx":round(_estimate_thickness(ink,(x1,y1,x2,y2)),2),"confidence":0.80} for i,(x1,y1,x2,y2) in enumerate(deduped)]
    return walls,mask


def enrich_walls_with_vector(walls:list[dict],vector_lines:list[dict])->list[dict]:
    if not walls or not vector_lines:
        return walls

    def orientation(line:dict)->str:
        dx=abs(line["b"]["x"]-line["a"]["x"])
        dy=abs(line["b"]["y"]-line["a"]["y"])
        return "h" if dx>=dy else "v"

    def ordered(line:dict,axis:str):
        if axis=="h":
            return (
                min(line["a"]["x"],line["b"]["x"]),
                max(line["a"]["x"],line["b"]["x"]),
                (line["a"]["y"]+line["b"]["y"])/2,
            )
        return (
            min(line["a"]["y"],line["b"]["y"]),
            max(line["a"]["y"],line["b"]["y"]),
            (line["a"]["x"]+line["b"]["x"])/2,
        )

    result=[]
    for wall in walls:
        axis=orientation(wall)
        start,end,wall_axis=ordered(wall,axis)
        wall_length=max(1.0,end-start)
        best=0.0
        for vector in vector_lines:
            if orientation(vector)!=axis:
                continue
            v_start,v_end,v_axis=ordered(vector,axis)
            axis_tol=max(4.0,float(wall.get("thicknessPx",4.0))*1.8)
            axis_distance=abs(v_axis-wall_axis)
            if axis_distance>axis_tol:
                continue
            shared=max(0.0,min(end,v_end)-max(start,v_start))
            overlap_ratio=shared/max(1.0,min(wall_length,v_end-v_start))
            if overlap_ratio<0.45:
                continue
            score=overlap_ratio*(1.0-axis_distance/max(axis_tol,1.0))
            best=max(best,score)

        if best>0:
            confidence=max(float(wall.get("confidence",0.0)),min(0.97,0.88+0.09*best))
            result.append({**wall,"confidence":round(confidence,3)})
        else:
            result.append(wall)
    return result
