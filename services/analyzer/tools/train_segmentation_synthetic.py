from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader,Dataset

CLASSES=("background","room","wall","door","window")


class TinyUNet(nn.Module):
    def __init__(self,classes:int=5,base:int=16):
        super().__init__()
        def block(a,b):
            return nn.Sequential(
                nn.Conv2d(a,b,3,padding=1,bias=False),nn.BatchNorm2d(b),nn.SiLU(inplace=True),
                nn.Conv2d(b,b,3,padding=1,bias=False),nn.BatchNorm2d(b),nn.SiLU(inplace=True),
            )
        self.e1=block(3,base); self.e2=block(base,base*2); self.e3=block(base*2,base*4)
        self.pool=nn.MaxPool2d(2)
        self.mid=block(base*4,base*8)
        self.u3=nn.ConvTranspose2d(base*8,base*4,2,2); self.d3=block(base*8,base*4)
        self.u2=nn.ConvTranspose2d(base*4,base*2,2,2); self.d2=block(base*4,base*2)
        self.u1=nn.ConvTranspose2d(base*2,base,2,2); self.d1=block(base*2,base)
        self.head=nn.Conv2d(base,classes,1)

    def forward(self,x):
        e1=self.e1(x); e2=self.e2(self.pool(e1)); e3=self.e3(self.pool(e2))
        m=self.mid(self.pool(e3))
        d3=self.d3(torch.cat([self.u3(m),e3],1))
        d2=self.d2(torch.cat([self.u2(d3),e2],1))
        d1=self.d1(torch.cat([self.u1(d2),e1],1))
        return self.head(d1)


def _clip_point(p,size):
    return (max(0,min(size-1,int(round(p[0])))),max(0,min(size-1,int(round(p[1])))))


def _wall_style(rng):
    return rng.choice(["solid-black","solid-gray","solid-blue","double-black","double-blue"])


def _draw_wall_visual(image,a,b,thickness,style,color):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    vec=b-a; length=float(np.linalg.norm(vec))
    if length<1:
        return
    if style.startswith("solid"):
        cv2.line(image,tuple(a.astype(int)),tuple(b.astype(int)),color,max(2,int(thickness)),cv2.LINE_AA)
        return
    unit=vec/length
    normal=np.array([-unit[1],unit[0]])
    half=max(2.0,float(thickness)*.42)
    for sign in (-1,1):
        off=normal*half*sign
        p1=tuple(np.round(a+off).astype(int)); p2=tuple(np.round(b+off).astype(int))
        cv2.line(image,p1,p2,color,max(1,int(round(thickness*.16))),cv2.LINE_AA)


def _draw_door_visual(image,a,b,thickness,color,double=False,sliding=False):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    vec=b-a; length=float(np.linalg.norm(vec))
    if length<5:
        return
    unit=vec/length
    normal=np.array([-unit[1],unit[0]])
    bg=(255,255,255)
    cv2.line(image,tuple(a.astype(int)),tuple(b.astype(int)),bg,max(4,int(thickness*1.5)),cv2.LINE_AA)
    if sliding:
        off=normal*max(2,thickness*.35)
        cv2.line(image,tuple(np.round(a+off).astype(int)),tuple(np.round(b+off).astype(int)),color,1,cv2.LINE_AA)
        cv2.line(image,tuple(np.round(a-off).astype(int)),tuple(np.round(b-off).astype(int)),color,1,cv2.LINE_AA)
        return
    hinge=a
    leaf=b
    if double:
        mid=(a+b)/2
        for h,l,sgn in ((a,mid,1),(b,mid,-1)):
            radius=float(np.linalg.norm(l-h))
            target=h+normal*radius*sgn
            cv2.line(image,tuple(h.astype(int)),tuple(np.round(target).astype(int)),color,1,cv2.LINE_AA)
            pts=np.array([h,l,target],dtype=np.int32)
            cv2.polylines(image,[pts],False,color,1,cv2.LINE_AA)
    else:
        radius=length
        target=hinge+normal*radius
        cv2.line(image,tuple(hinge.astype(int)),tuple(np.round(target).astype(int)),color,1,cv2.LINE_AA)
        center=tuple(hinge.astype(int))
        angle=math.degrees(math.atan2(vec[1],vec[0]))
        cv2.ellipse(image,center,(int(radius),int(radius)),0,angle,angle+90,color,1,cv2.LINE_AA)


def _draw_window_visual(image,a,b,thickness,color):
    a=np.asarray(a,dtype=float); b=np.asarray(b,dtype=float)
    vec=b-a; length=float(np.linalg.norm(vec))
    if length<5:
        return
    unit=vec/length; normal=np.array([-unit[1],unit[0]])
    cv2.line(image,tuple(a.astype(int)),tuple(b.astype(int)),(255,255,255),max(4,int(thickness*1.6)),cv2.LINE_AA)
    for off in (-max(1.5,thickness*.28),0,max(1.5,thickness*.28)):
        p1=tuple(np.round(a+normal*off).astype(int)); p2=tuple(np.round(b+normal*off).astype(int))
        cv2.line(image,p1,p2,color,1,cv2.LINE_AA)


def _partition_segments(rng,x0,y0,x1,y1,rows,cols,wall_t):
    segments=[]
    doors=[]
    for i in range(1,cols):
        x=int(round(x0+(x1-x0)*i/cols+rng.uniform(-.035,.035)*(x1-x0)))
        gap=max(18,int((y1-y0)*rng.uniform(.055,.095)))
        cy=rng.randint(y0+gap*2,y1-gap*2)
        segments.append(((x,y0),(x,cy-gap//2)))
        segments.append(((x,cy+gap//2),(x,y1)))
        doors.append(((x,cy-gap//2),(x,cy+gap//2)))
    for i in range(1,rows):
        y=int(round(y0+(y1-y0)*i/rows+rng.uniform(-.035,.035)*(y1-y0)))
        gap=max(18,int((x1-x0)*rng.uniform(.055,.095)))
        cx=rng.randint(x0+gap*2,x1-gap*2)
        segments.append(((x0,y),(cx-gap//2,y)))
        segments.append(((cx+gap//2,y),(x1,y)))
        doors.append(((cx-gap//2,y),(cx+gap//2,y)))
    # Add short secondary partitions, sometimes diagonal, to mimic service cores.
    if rng.random()<.65:
        for _ in range(rng.randint(1,3)):
            cx=rng.randint(x0+40,x1-40); cy=rng.randint(y0+40,y1-40)
            length=rng.randint(max(35,(x1-x0)//12),max(55,(x1-x0)//5))
            if rng.random()<.75:
                if rng.random()<.5:
                    segments.append(((cx-length//2,cy),(cx+length//2,cy)))
                else:
                    segments.append(((cx,cy-length//2),(cx,cy+length//2)))
            else:
                ang=rng.choice([-35,-25,25,35])*math.pi/180
                dx=math.cos(ang)*length/2; dy=math.sin(ang)*length/2
                segments.append(((int(cx-dx),int(cy-dy)),(int(cx+dx),int(cy+dy))))
    return segments,doors


def _draw_dimensions_and_text(image,rng,x0,y0,x1,y1,size):
    dim_color=rng.choice([(50,150,70),(70,130,70),(100,100,100)])
    text_color=rng.choice([(35,35,180),(60,60,60),(120,60,40)])
    top=max(8,y0-rng.randint(18,42))
    cv2.line(image,(x0,top),(x1,top),dim_color,rng.choice([1,1,2]),cv2.LINE_AA)
    for x in np.linspace(x0,x1,rng.randint(3,7)).astype(int):
        cv2.line(image,(x,top-5),(x,top+5),dim_color,1,cv2.LINE_AA)
    left=max(8,x0-rng.randint(18,40))
    cv2.line(image,(left,y0),(left,y1),dim_color,1,cv2.LINE_AA)
    for y in np.linspace(y0,y1,rng.randint(3,7)).astype(int):
        cv2.line(image,(left-5,y),(left+5,y),dim_color,1,cv2.LINE_AA)

    words=["ROOM","HALL","BED","KITCHEN","BATH","MAJLIS","3.20","4.00","12.5 m2"]
    for _ in range(rng.randint(8,24)):
        x=rng.randint(max(5,x0),min(size-80,x1))
        y=rng.randint(max(20,y0),min(size-5,y1))
        cv2.putText(image,rng.choice(words),(x,y),cv2.FONT_HERSHEY_SIMPLEX,
                    rng.uniform(.25,.48),text_color,rng.choice([1,1,1,2]),cv2.LINE_AA)


def _draw_furniture(image,rng,x0,y0,x1,y1):
    color=rng.choice([(80,80,80),(120,120,120),(40,40,40)])
    for _ in range(rng.randint(5,18)):
        cx=rng.randint(x0+20,x1-20); cy=rng.randint(y0+20,y1-20)
        w=rng.randint(12,55); h=rng.randint(10,45)
        shape=rng.choice(["rect","bed","circle","table","stairs"])
        if shape=="circle":
            cv2.circle(image,(cx,cy),rng.randint(5,16),color,1,cv2.LINE_AA)
        elif shape=="stairs":
            for k in range(rng.randint(4,8)):
                yy=cy-h//2+k*max(2,h//7)
                cv2.line(image,(cx-w//2,yy),(cx+w//2,yy),color,1,cv2.LINE_AA)
        else:
            cv2.rectangle(image,(cx-w//2,cy-h//2),(cx+w//2,cy+h//2),color,1,cv2.LINE_AA)
            if shape=="bed":
                cv2.line(image,(cx-w//2,cy-h//4),(cx+w//2,cy-h//4),color,1,cv2.LINE_AA)
            if shape=="table":
                cv2.circle(image,(cx,cy),max(3,min(w,h)//4),color,1,cv2.LINE_AA)


def _augment(image,mask,rng):
    h,w=image.shape[:2]
    # Small scan rotation and scale.
    angle=rng.uniform(-2.2,2.2) if rng.random()<.55 else 0.0
    scale=rng.uniform(.96,1.04)
    m=cv2.getRotationMatrix2D((w/2,h/2),angle,scale)
    image=cv2.warpAffine(image,m,(w,h),flags=cv2.INTER_LINEAR,borderValue=(255,255,255))
    mask=cv2.warpAffine(mask,m,(w,h),flags=cv2.INTER_NEAREST,borderValue=0)

    if rng.random()<.45:
        sigma=rng.uniform(.25,1.0)
        image=cv2.GaussianBlur(image,(3,3),sigma)
    if rng.random()<.65:
        noise=np.random.default_rng(rng.randint(0,2**31-1)).normal(0,rng.uniform(1.0,7.0),image.shape)
        image=np.clip(image.astype(np.float32)+noise,0,255).astype(np.uint8)
    if rng.random()<.55:
        quality=rng.randint(55,92)
        ok,enc=cv2.imencode(".jpg",image,[int(cv2.IMWRITE_JPEG_QUALITY),quality])
        if ok:
            image=cv2.imdecode(enc,cv2.IMREAD_COLOR)
    if rng.random()<.25:
        # Uneven scan illumination.
        gx=np.linspace(rng.uniform(.88,1.02),rng.uniform(.98,1.10),w,dtype=np.float32)
        image=np.clip(image.astype(np.float32)*gx[None,:,None],0,255).astype(np.uint8)
    return image,mask


def _draw_plan(seed:int,size:int)->tuple[np.ndarray,np.ndarray]:
    rng=random.Random(seed)
    image=np.full((size,size,3),rng.choice([255,255,252,248]),dtype=np.uint8)
    mask=np.zeros((size,size),dtype=np.uint8)

    margin=rng.randint(size//13,size//8)
    x0=y0=margin
    x1=y1=size-margin
    wall_t=rng.randint(max(5,size//42),max(10,size//24))
    rows=rng.choice([2,2,3,3,4]); cols=rng.choice([2,2,3,3,4])
    style=_wall_style(rng)
    color={
        "solid-black":(15,15,15),"solid-gray":(75,75,75),"solid-blue":(215,105,45),
        "double-black":(20,20,20),"double-blue":(205,105,55),
    }[style]

    # The footprint is deliberately plain in topology but highly varied in
    # rendering. This avoids licensing external plans while creating a large
    # supervised style domain for walls/openings.
    mask[y0:y1+1,x0:x1+1]=1

    outer=[((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]
    partitions,doors=_partition_segments(rng,x0,y0,x1,y1,rows,cols,wall_t)

    for a,b in outer+partitions:
        cv2.line(mask,a,b,2,wall_t,cv2.LINE_8)
        _draw_wall_visual(image,a,b,wall_t,style,color)

    # Doors: carve mask and visual from partition wall bands.
    for a,b in doors:
        double=rng.random()<.14
        sliding=(not double) and rng.random()<.10
        cv2.line(mask,a,b,3,max(wall_t+2,int(wall_t*1.25)),cv2.LINE_8)
        _draw_door_visual(image,a,b,wall_t,color,double=double,sliding=sliding)

    # Windows on the exterior shell.
    for _ in range(rng.randint(3,9)):
        side=rng.randrange(4)
        if side in (0,2):
            y=y0 if side==0 else y1
            span=rng.randint(max(16,size//22),max(24,size//11))
            cx=rng.randint(x0+span,x1-span)
            a=(cx-span//2,y); b=(cx+span//2,y)
        else:
            x=x1 if side==1 else x0
            span=rng.randint(max(16,size//22),max(24,size//11))
            cy=rng.randint(y0+span,y1-span)
            a=(x,cy-span//2); b=(x,cy+span//2)
        cv2.line(mask,a,b,4,max(wall_t+2,int(wall_t*1.22)),cv2.LINE_8)
        _draw_window_visual(image,a,b,wall_t,color)

    _draw_dimensions_and_text(image,rng,x0,y0,x1,y1,size)
    _draw_furniture(image,rng,x0,y0,x1,y1)

    # Add hatching/cabinet lines as hard negatives.
    for _ in range(rng.randint(1,5)):
        ax=rng.randint(x0+10,x1-35); ay=rng.randint(y0+10,y1-35)
        bw=rng.randint(20,70); bh=rng.randint(15,60)
        cv2.rectangle(image,(ax,ay),(min(x1,ax+bw),min(y1,ay+bh)),(105,105,105),1,cv2.LINE_AA)
        if rng.random()<.5:
            for t in range(0,bw+bh,8):
                p1=(ax+max(0,t-bh),ay+min(t,bh))
                p2=(ax+min(t,bw),ay+max(0,t-bw))
                cv2.line(image,p1,p2,(150,150,150),1,cv2.LINE_AA)

    return _augment(image,mask,rng)


class SyntheticPlans(Dataset):
    def __init__(self,count:int,size:int,seed:int):
        self.count=count; self.size=size; self.seed=seed
    def __len__(self): return self.count
    def __getitem__(self,index):
        image,mask=_draw_plan(self.seed+index,self.size)
        x=torch.from_numpy(cv2.cvtColor(image,cv2.COLOR_BGR2RGB).copy()).permute(2,0,1).float()/255.0
        y=torch.from_numpy(mask.astype(np.int64))
        return x,y


def _dice_loss(logits,target):
    probs=torch.softmax(logits,dim=1)
    onehot=torch.nn.functional.one_hot(target,num_classes=5).permute(0,3,1,2).float()
    # Focus Dice on semantic structure, not background.
    p=probs[:,1:]; t=onehot[:,1:]
    inter=(p*t).sum(dim=(0,2,3))
    denom=p.sum(dim=(0,2,3))+t.sum(dim=(0,2,3))
    dice=(2*inter+1.0)/(denom+1.0)
    weights=torch.tensor([.75,1.4,1.8,1.8],device=logits.device)
    return ((1-dice)*weights).sum()/weights.sum()


@torch.no_grad()
def evaluate(model,loader,device):
    model.eval()
    tp=torch.zeros(5,dtype=torch.float64); fp=torch.zeros(5,dtype=torch.float64); fn=torch.zeros(5,dtype=torch.float64)
    for x,y in loader:
        x=x.to(device); y=y.to(device)
        pred=model(x).argmax(1)
        for cls in range(5):
            p=pred==cls; t=y==cls
            tp[cls]+=(p&t).sum().cpu()
            fp[cls]+=(p&~t).sum().cpu()
            fn[cls]+=(~p&t).sum().cpu()
    iou=(tp/(tp+fp+fn).clamp(min=1)).tolist()
    return {name:round(float(value),4) for name,value in zip(CLASSES,iou)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default="segmentation-model")
    ap.add_argument("--epochs",type=int,default=4)
    ap.add_argument("--train-count",type=int,default=1400)
    ap.add_argument("--val-count",type=int,default=220)
    ap.add_argument("--size",type=int,default=256)
    args=ap.parse_args()

    random.seed(240923); np.random.seed(240923); torch.manual_seed(240923)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train=DataLoader(SyntheticPlans(args.train_count,args.size,1000),batch_size=10,shuffle=True,num_workers=0)
    val=DataLoader(SyntheticPlans(args.val_count,args.size,900000),batch_size=10,shuffle=False,num_workers=0)

    model=TinyUNet().to(device)
    class_weights=torch.tensor([.25,.85,2.3,4.2,4.2],device=device)
    ce=nn.CrossEntropyLoss(weight=class_weights)
    opt=torch.optim.AdamW(model.parameters(),lr=1.6e-3,weight_decay=2e-4)

    best=None; best_score=-1.0
    for epoch in range(1,args.epochs+1):
        model.train(); running=0.0
        for x,y in train:
            x=x.to(device); y=y.to(device)
            logits=model(x)
            loss=ce(logits,y)+.55*_dice_loss(logits,y)
            opt.zero_grad(set_to_none=True); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),3.0)
            opt.step()
            running+=float(loss.item())
        metrics=evaluate(model,val,device)
        score=(metrics["wall"]*1.4+metrics["room"]+metrics["door"]+metrics["window"])/4.4
        print(json.dumps({"epoch":epoch,"loss":running/max(1,len(train)),"iou":metrics,"score":score}))
        if score>best_score:
            best_score=score
            best={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}

    model.load_state_dict(best); model=model.cpu().eval()
    output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    example=torch.zeros(1,3,384,384,dtype=torch.float32)
    onnx_path=output/"manzil-segmentation-v1.onnx"
    torch.onnx.export(
        model,example,onnx_path,
        input_names=["image"],output_names=["logits"],
        opset_version=17,
        dynamo=False,
    )
    final=evaluate(model,val,torch.device("cpu"))
    meta={
        "classes":CLASSES,
        "inputSize":384,
        "syntheticValidationIoU":final,
        "training":"Manzil-owned procedural architectural renderer with domain randomization",
        "version":"vision-segmentation-v1.1",
        "note":"AEC-15 remains evaluation-only and is never used for training",
    }
    (output/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print(json.dumps(meta,indent=2))


if __name__=="__main__":
    main()
