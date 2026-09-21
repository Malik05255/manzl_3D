from __future__ import annotations
from .models import FloorPlan,Impact,Room

def _normalize_name(value:str)->str:
    return (value.lower().replace("أ","ا").replace("إ","ا").replace("آ","ا")
        .replace("ة","ه").replace("ى","ي").replace("ـ",""))

def minimum_clear_span_m(room:Room)->float:
    name=_normalize_name(room.name)
    if any(word in name for word in ("ممر","corridor","hallway")):
        return 0.90
    if any(word in name for word in ("حمام","دوره مياه","دورة مياه","bath","wc")):
        return 1.20
    if any(word in name for word in ("مطبخ","kitchen")):
        return 1.80
    if any(word in name for word in ("درج","stair","مصعد","elevator")):
        return 1.20
    if any(word in name for word in ("غرفه نوم","نوم","bedroom","صاله","معيشه","مجلس","living","majlis")):
        return 2.40
    return 1.20

def bbox(room:Room)->tuple[float,float,float,float]:
    xs=[p.x for p in room.polygon]; ys=[p.y for p in room.polygon]
    return min(xs),min(ys),max(xs),max(ys)

def is_rectangular_room(room:Room,tol:float=3.0)->bool:
    if len(room.polygon)!=4:
        return False
    x1,y1,x2,y2=bbox(room)
    expected=((x1,y1),(x2,y1),(x2,y2),(x1,y2))
    remaining=[(point.x,point.y) for point in room.polygon]
    for ex,ey in expected:
        match=next((i for i,(x,y) in enumerate(remaining) if abs(x-ex)<=tol and abs(y-ey)<=tol),None)
        if match is None:
            return False
        remaining.pop(match)
    return True

def set_rect(room:Room,box:tuple[float,float,float,float],mpp:float)->None:
    x1,y1,x2,y2=box
    pts=((x1,y1),(x2,y1),(x2,y2),(x1,y2))
    for point,(x,y) in zip(room.polygon,pts):
        point.x=x; point.y=y
    room.areaM2=round(max(0,x2-x1)*max(0,y2-y1)*(mpp**2),2)

def overlap(a1:float,a2:float,b1:float,b2:float)->float:
    return max(0.0,min(a2,b2)-max(a1,b1))

def adjacent(plan:FloorPlan,target:Room,side:str,tol:float)->list[Room]:
    tx1,ty1,tx2,ty2=bbox(target)
    found=[]
    for room in plan.rooms:
        if room.id==target.id: continue
        x1,y1,x2,y2=bbox(room)
        if side=="right":
            touching=abs(x1-tx2)<=tol; shared=overlap(ty1,ty2,y1,y2); base=min(ty2-ty1,y2-y1)
        elif side=="left":
            touching=abs(x2-tx1)<=tol; shared=overlap(ty1,ty2,y1,y2); base=min(ty2-ty1,y2-y1)
        elif side=="bottom":
            touching=abs(y1-ty2)<=tol; shared=overlap(tx1,tx2,x1,x2); base=min(tx2-tx1,x2-x1)
        else:
            touching=abs(y2-ty1)<=tol; shared=overlap(tx1,tx2,x1,x2); base=min(tx2-tx1,x2-x1)
        if touching and base>0 and shared/base>=0.35: found.append(room)
    return found

def move_boundary(plan:FloorPlan,side:str,old:float,new:float,span:tuple[float,float],tol:float)->int:
    changed=[]
    for wall in plan.walls:
        if side in ("left","right"):
            aligned=abs(wall.a.x-wall.b.x)<=tol
            shared=overlap(min(wall.a.y,wall.b.y),max(wall.a.y,wall.b.y),span[0],span[1])
            if aligned and abs((wall.a.x+wall.b.x)/2-old)<=tol and shared>0:
                wall.a.x=new; wall.b.x=new; changed.append(wall.id)
        else:
            aligned=abs(wall.a.y-wall.b.y)<=tol
            shared=overlap(min(wall.a.x,wall.b.x),max(wall.a.x,wall.b.x),span[0],span[1])
            if aligned and abs((wall.a.y+wall.b.y)/2-old)<=tol and shared>0:
                wall.a.y=new; wall.b.y=new; changed.append(wall.id)
    delta=new-old; moved=0
    for opening in [*plan.doors,*plan.windows]:
        if opening.wallId not in changed: continue
        if side in ("left","right"):
            opening.a.x+=delta; opening.b.x+=delta
        else:
            opening.a.y+=delta; opening.b.y+=delta
        moved+=1
    return moved

def apply_side(plan:FloorPlan,target:Room,side:str,delta_px:float,mpp:float)->tuple[bool,list[Impact],list[str]]:
    if abs(delta_px)<1:
        return True,[],[]

    tol=max(6.0,0.18/mpp)
    neighbors=adjacent(plan,target,side,tol)
    if not neighbors:
        return False,[],[]

    tx1,ty1,tx2,ty2=bbox(target)
    base_min_px=0.9/mpp

    if side=="right":
        new=tx2+delta_px
        if any(bbox(room)[2]-new<max(base_min_px,minimum_clear_span_m(room)/mpp) for room in neighbors):
            return False,[],[]
        set_rect(target,(tx1,ty1,new,ty2),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(new,ny1,nx2,ny2),mpp)
        moved=move_boundary(plan,side,tx2,new,(ty1,ty2),tol)
    elif side=="left":
        new=tx1-delta_px
        if any(new-bbox(room)[0]<max(base_min_px,minimum_clear_span_m(room)/mpp) for room in neighbors):
            return False,[],[]
        set_rect(target,(new,ty1,tx2,ty2),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(nx1,ny1,new,ny2),mpp)
        moved=move_boundary(plan,side,tx1,new,(ty1,ty2),tol)
    elif side=="bottom":
        new=ty2+delta_px
        if any(bbox(room)[3]-new<max(base_min_px,minimum_clear_span_m(room)/mpp) for room in neighbors):
            return False,[],[]
        set_rect(target,(tx1,ty1,tx2,new),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(nx1,new,nx2,ny2),mpp)
        moved=move_boundary(plan,side,ty2,new,(tx1,tx2),tol)
    else:
        new=ty1-delta_px
        if any(new-bbox(room)[1]<max(base_min_px,minimum_clear_span_m(room)/mpp) for room in neighbors):
            return False,[],[]
        set_rect(target,(tx1,new,tx2,ty2),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(nx1,ny1,nx2,new),mpp)
        moved=move_boundary(plan,side,ty1,new,(tx1,tx2),tol)

    amount=abs(delta_px*mpp)
    verb="تصغير" if delta_px>0 else "تكبير"
    impacts=[Impact(kind="wall_move",text=f"تحريك الجدار المشترك {amount:.2f} م")]
    for neighbor in neighbors:
        impacts.append(Impact(
            kind="room_resize",
            text=f"{verb} {neighbor.name} بمقدار {amount:.2f} م",
            severity="warning" if delta_px>0 else "info",
        ))
    if moved:
        impacts.append(Impact(
            kind="door_move",
            text=f"تحريك {moved} عنصر مرتبط بالجدار تلقائيًا",
            severity="warning",
        ))
    return True,impacts,[room.name for room in neighbors]


def absorb_neighbor(plan:FloorPlan,target:Room,neighbor:Room,side:str,delta_px:float,mpp:float)->tuple[bool,list[Impact]]:
    if abs(delta_px)<1 or not is_rectangular_room(target) or not is_rectangular_room(neighbor):
        return False,[]

    tol=max(6.0,0.15/mpp)
    tx1,ty1,tx2,ty2=bbox(target)
    nx1,ny1,nx2,ny2=bbox(neighbor)
    shared_wall_ids=set()

    if side=="right":
        if abs(nx1-tx2)>tol or abs(ny1-ty1)>tol or abs(ny2-ty2)>tol:
            return False,[]
        desired=tx2+delta_px
        if abs(desired-nx2)>tol:
            return False,[]
        shared_axis=tx2
        span=(ty1,ty2)
        new_box=(tx1,ty1,nx2,ty2)
    elif side=="left":
        if abs(nx2-tx1)>tol or abs(ny1-ty1)>tol or abs(ny2-ty2)>tol:
            return False,[]
        desired=tx1-delta_px
        if abs(desired-nx1)>tol:
            return False,[]
        shared_axis=tx1
        span=(ty1,ty2)
        new_box=(nx1,ty1,tx2,ty2)
    elif side=="bottom":
        if abs(ny1-ty2)>tol or abs(nx1-tx1)>tol or abs(nx2-tx2)>tol:
            return False,[]
        desired=ty2+delta_px
        if abs(desired-ny2)>tol:
            return False,[]
        shared_axis=ty2
        span=(tx1,tx2)
        new_box=(tx1,ty1,tx2,ny2)
    elif side=="top":
        if abs(ny2-ty1)>tol or abs(nx1-tx1)>tol or abs(nx2-tx2)>tol:
            return False,[]
        desired=ty1-delta_px
        if abs(desired-ny1)>tol:
            return False,[]
        shared_axis=ty1
        span=(tx1,tx2)
        new_box=(tx1,ny1,tx2,ty2)
    else:
        return False,[]

    for wall in plan.walls:
        if side in ("left","right"):
            aligned=abs(wall.a.x-wall.b.x)<=tol
            axis=(wall.a.x+wall.b.x)/2
            shared=overlap(min(wall.a.y,wall.b.y),max(wall.a.y,wall.b.y),span[0],span[1])
        else:
            aligned=abs(wall.a.y-wall.b.y)<=tol
            axis=(wall.a.y+wall.b.y)/2
            shared=overlap(min(wall.a.x,wall.b.x),max(wall.a.x,wall.b.x),span[0],span[1])
        if aligned and abs(axis-shared_axis)<=tol and shared>0:
            shared_wall_ids.add(wall.id)

    set_rect(target,new_box,mpp)
    plan.rooms=[room for room in plan.rooms if room.id!=neighbor.id]
    plan.walls=[wall for wall in plan.walls if wall.id not in shared_wall_ids]
    removed_openings=[
        opening for opening in [*plan.doors,*plan.windows]
        if opening.wallId in shared_wall_ids
    ]
    plan.doors=[opening for opening in plan.doors if opening.wallId not in shared_wall_ids]
    plan.windows=[opening for opening in plan.windows if opening.wallId not in shared_wall_ids]

    impacts=[
        Impact(kind="room_remove",text=f"إزالة {neighbor.name} وضم مساحته إلى {target.name}",severity="critical"),
        Impact(kind="wall_move",text="إزالة الجدار المشترك بين الفراغين",severity="warning"),
    ]
    if removed_openings:
        impacts.append(Impact(
            kind="door_move",
            text=f"إزالة {len(removed_openings)} فتحة مرتبطة بالجدار الملغى",
            severity="warning",
        ))
    return True,impacts


def merge_neighbor(plan:FloorPlan,target:Room,source:Room,mpp:float)->tuple[bool,list[Impact]]:
    if not is_rectangular_room(target) or not is_rectangular_room(source):
        return False,[]
    tx1,ty1,tx2,ty2=bbox(target)
    sx1,sy1,sx2,sy2=bbox(source)
    tol=max(6.0,0.15/mpp)

    candidates=[]
    if abs(sx1-tx2)<=tol and abs(sy1-ty1)<=tol and abs(sy2-ty2)<=tol:
        candidates.append(("right",sx2-tx2))
    if abs(sx2-tx1)<=tol and abs(sy1-ty1)<=tol and abs(sy2-ty2)<=tol:
        candidates.append(("left",tx1-sx1))
    if abs(sy1-ty2)<=tol and abs(sx1-tx1)<=tol and abs(sx2-tx2)<=tol:
        candidates.append(("bottom",sy2-ty2))
    if abs(sy2-ty1)<=tol and abs(sx1-tx1)<=tol and abs(sx2-tx2)<=tol:
        candidates.append(("top",ty1-sy1))

    for side,delta in candidates:
        if delta<=0:
            continue
        ok,impacts=absorb_neighbor(plan,target,source,side,delta,mpp)
        if ok:
            return True,impacts
    return False,[]
