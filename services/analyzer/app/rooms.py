from __future__ import annotations
import cv2
import numpy as np


def _estimate_wall_thickness(mask:np.ndarray)->float:
    binary=(mask>0).astype(np.uint8)*255
    if cv2.countNonZero(binary)==0:
        return 4.0
    distance=cv2.distanceTransform(binary,cv2.DIST_L2,5)
    values=distance[distance>0]
    if values.size==0:
        return 4.0
    # Upper-middle percentile tracks the wall core without being dominated by
    # thin antialiased edges or rare oversized blobs.
    half=float(np.percentile(values,90))
    return max(2.0,min(48.0,half*2.0))


def build_room_barrier(wall_mask:np.ndarray)->np.ndarray:
    """Seal ordinary door-sized gaps only for room segmentation.

    The editable wall model must preserve openings. Room extraction is a
    different problem: two rooms connected by an open doorway are still two
    rooms. Earlier pipelines used the same open wall mask for both tasks, so
    connected-components merged spaces through doors and produced the large,
    incorrect polygons seen in production.

    This function builds a segmentation-only barrier by closing horizontal and
    vertical wall runs over a gap derived from measured wall thickness. The
    original mask is retained, so diagonal/curved structural evidence is not
    discarded. Large open-plan connections remain open.
    """
    if wall_mask.ndim!=2:
        raise ValueError("ROOM_BARRIER_SHAPE")
    h,w=wall_mask.shape[:2]
    if h<8 or w<8:
        return wall_mask.copy()

    binary=np.where(wall_mask>0,255,0).astype(np.uint8)
    thickness=_estimate_wall_thickness(binary)
    short=float(max(1,min(h,w)))

    # Typical residential door openings are several wall-thicknesses wide.
    # Cap by page scale so atria/open-plan connections are not bridged.
    bridge=int(round(max(17.0,min(short*.16,thickness*9.5))))
    bridge=max(9,bridge|1)

    run=int(round(max(18.0,min(short*.12,thickness*4.0))))
    run=max(7,run|1)

    horizontal=cv2.morphologyEx(
        binary,cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,(run,1)),
    )
    vertical=cv2.morphologyEx(
        binary,cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,(1,run)),
    )

    horizontal=cv2.morphologyEx(
        horizontal,cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT,(bridge,1)),
    )
    vertical=cv2.morphologyEx(
        vertical,cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT,(1,bridge)),
    )

    barrier=cv2.bitwise_or(binary,horizontal)
    barrier=cv2.bitwise_or(barrier,vertical)

    join=max(3,min(11,int(round(thickness*.45))|1))
    barrier=cv2.morphologyEx(
        barrier,cv2.MORPH_CLOSE,
        np.ones((join,join),np.uint8),
    )
    return barrier


def _component_polygon(component_mask:np.ndarray,offset_x:int,offset_y:int)->tuple[list[dict],float]:
    contours,_=cv2.findContours(component_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return [],0.0
    contour=max(contours,key=cv2.contourArea)
    area=float(cv2.contourArea(contour))
    if area<=0:
        return [],0.0

    x,y,w,h=cv2.boundingRect(contour)
    rectangularity=area/max(1.0,float(w*h))
    if rectangularity>=0.90:
        return [
            {"x":float(offset_x+x),"y":float(offset_y+y)},
            {"x":float(offset_x+x+w),"y":float(offset_y+y)},
            {"x":float(offset_x+x+w),"y":float(offset_y+y+h)},
            {"x":float(offset_x+x),"y":float(offset_y+y+h)},
        ],area

    perimeter=cv2.arcLength(contour,True)
    epsilon=max(1.5,0.012*perimeter)
    approx=cv2.approxPolyDP(contour,epsilon,True)
    if len(approx)>20:
        approx=cv2.approxPolyDP(contour,max(2.0,0.022*perimeter),True)

    points=[
        {"x":float(offset_x+point[0][0]),"y":float(offset_y+point[0][1])}
        for point in approx
    ]
    if len(points)<4:
        return [
            {"x":float(offset_x+x),"y":float(offset_y+y)},
            {"x":float(offset_x+x+w),"y":float(offset_y+y)},
            {"x":float(offset_x+x+w),"y":float(offset_y+y+h)},
            {"x":float(offset_x+x),"y":float(offset_y+y+h)},
        ],area
    return points,area


def _contains(polygon:list[dict],x:float,y:float)->bool:
    contour=np.array(
        [[point["x"],point["y"]] for point in polygon],
        dtype=np.float32,
    ).reshape((-1,1,2))
    return cv2.pointPolygonTest(contour,(float(x),float(y)),False)>=0


def detect_rooms(wall_mask:np.ndarray,labels:list[dict],meters_per_pixel:float|None,min_area_ratio:float=0.0012,max_area_ratio:float=0.72)->list[dict]:
    h,w=wall_mask.shape[:2]
    close_size=max(7,min(25,min(h,w)//80))
    barrier=cv2.morphologyEx(
        wall_mask,
        cv2.MORPH_CLOSE,
        np.ones((close_size,close_size),np.uint8),
    )
    barrier=cv2.dilate(barrier,np.ones((5,5),np.uint8),iterations=1)
    free=cv2.bitwise_not(barrier)

    count,component_map,stats,_=cv2.connectedComponentsWithStats(free,8)
    rooms=[]
    min_area=h*w*max(0.0005,min(0.10,min_area_ratio))
    max_area=h*w*max(min_area_ratio,min(0.98,max_area_ratio))
    room_labels=[label for label in labels if label["kind"]=="room_name"]
    min_dimension=max(12,min(35,int(round(min(h,w)*0.035))))

    for component in range(1,count):
        x,y,rw,rh,area=stats[component]
        if area<min_area or area>max_area or rw<min_dimension or rh<min_dimension:
            continue
        if x<=2 or y<=2 or x+rw>=w-2 or y+rh>=h-2:
            continue

        fill_ratio=float(area)/max(1,rw*rh)
        if fill_ratio<0.32:
            continue

        crop=(component_map[y:y+rh,x:x+rw]==component).astype(np.uint8)*255
        polygon,contour_area=_component_polygon(crop,x,y)
        if len(polygon)<4 or contour_area<min_area:
            continue

        name=""
        label_conf=0.0
        label_provenance=None
        for label in room_labels:
            cx,cy=label["center"]["x"],label["center"]["y"]
            if _contains(polygon,cx,cy) and label["confidence"]>label_conf:
                name=label["text"]
                label_conf=label["confidence"]
                label_provenance=label.get("provenance")

        area_m2=contour_area*(meters_per_pixel**2) if meters_per_pixel else None
        complexity_penalty=max(0,len(polygon)-8)*0.01
        confidence=min(
            0.94,
            0.50+min(fill_ratio,1.0)*0.34+(0.08 if name else 0)-complexity_penalty,
        )
        rooms.append({
            "id":f"room-{len(rooms)+1}",
            "name":name or f"غرفة {len(rooms)+1}",
            "polygon":polygon,
            "confidence":max(0.45,confidence),
            "areaM2":round(area_m2,2) if area_m2 else None,
            "reviewed":False,
            "provenance":"mixed" if name and label_provenance else "opencv",
        })

    return rooms
