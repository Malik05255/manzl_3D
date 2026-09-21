from __future__ import annotations
import cv2
import numpy as np

def detect_rooms(wall_mask:np.ndarray,labels:list[dict],meters_per_pixel:float|None)->list[dict]:
    h,w=wall_mask.shape[:2]
    close_size=max(7,min(25,min(h,w)//80))
    barrier=cv2.morphologyEx(wall_mask,cv2.MORPH_CLOSE,np.ones((close_size,close_size),np.uint8))
    barrier=cv2.dilate(barrier,np.ones((5,5),np.uint8),iterations=1)
    free=cv2.bitwise_not(barrier)
    count,_,stats,_=cv2.connectedComponentsWithStats(free,8)
    rooms=[]
    min_area=h*w*0.004; max_area=h*w*0.40
    room_labels=[label for label in labels if label["kind"]=="room_name"]
    for component in range(1,count):
        x,y,rw,rh,area=stats[component]
        if area<min_area or area>max_area or rw<35 or rh<35: continue
        if x<=2 or y<=2 or x+rw>=w-2 or y+rh>=h-2: continue
        fill_ratio=float(area)/max(1,rw*rh)
        if fill_ratio<0.42: continue
        name=""; label_conf=0.0
        for label in room_labels:
            cx,cy=label["center"]["x"],label["center"]["y"]
            if x<=cx<=x+rw and y<=cy<=y+rh and label["confidence"]>label_conf:
                name=label["text"]; label_conf=label["confidence"]
        polygon=[{"x":float(x),"y":float(y)},{"x":float(x+rw),"y":float(y)},{"x":float(x+rw),"y":float(y+rh)},{"x":float(x),"y":float(y+rh)}]
        area_m2=rw*rh*(meters_per_pixel**2) if meters_per_pixel else None
        rooms.append({"id":f"room-{len(rooms)+1}","name":name or f"غرفة {len(rooms)+1}","polygon":polygon,"confidence":min(0.92,0.48+fill_ratio*0.42+(0.08 if name else 0)),"areaM2":round(area_m2,2) if area_m2 else None})
    return rooms
