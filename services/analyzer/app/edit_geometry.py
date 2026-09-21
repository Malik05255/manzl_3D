from __future__ import annotations
from .models import FloorPlan,Impact,Room

def bbox(room:Room)->tuple[float,float,float,float]:
    xs=[p.x for p in room.polygon]; ys=[p.y for p in room.polygon]
    return min(xs),min(ys),max(xs),max(ys)

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
    min_px=0.9/mpp

    if side=="right":
        new=tx2+delta_px
        if any(bbox(room)[2]-new<min_px for room in neighbors):
            return False,[],[]
        set_rect(target,(tx1,ty1,new,ty2),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(new,ny1,nx2,ny2),mpp)
        moved=move_boundary(plan,side,tx2,new,(ty1,ty2),tol)
    elif side=="left":
        new=tx1-delta_px
        if any(new-bbox(room)[0]<min_px for room in neighbors):
            return False,[],[]
        set_rect(target,(new,ty1,tx2,ty2),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(nx1,ny1,new,ny2),mpp)
        moved=move_boundary(plan,side,tx1,new,(ty1,ty2),tol)
    elif side=="bottom":
        new=ty2+delta_px
        if any(bbox(room)[3]-new<min_px for room in neighbors):
            return False,[],[]
        set_rect(target,(tx1,ty1,tx2,new),mpp)
        for room in neighbors:
            nx1,ny1,nx2,ny2=bbox(room)
            set_rect(room,(nx1,new,nx2,ny2),mpp)
        moved=move_boundary(plan,side,ty2,new,(tx1,tx2),tol)
    else:
        new=ty1-delta_px
        if any(new-bbox(room)[1]<min_px for room in neighbors):
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
