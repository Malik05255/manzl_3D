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
    def __init__(self,classes:int=5,base:int=12):
        super().__init__()
        def block(a,b):
            return nn.Sequential(
                nn.Conv2d(a,b,3,padding=1,bias=False),nn.BatchNorm2d(b),nn.ReLU(inplace=True),
                nn.Conv2d(b,b,3,padding=1,bias=False),nn.BatchNorm2d(b),nn.ReLU(inplace=True),
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


def _draw_plan(seed:int,size:int)->tuple[np.ndarray,np.ndarray]:
    rng=random.Random(seed)
    image=np.full((size,size,3),255,dtype=np.uint8)
    mask=np.zeros((size,size),dtype=np.uint8)

    margin=rng.randint(size//12,size//8)
    x0=y0=margin
    x1=y1=size-margin
    wall_t=rng.randint(max(5,size//40),max(8,size//25))

    # Random 2x2 / 3x2 / 2x3 grid creates multiple room instances while
    # remaining deterministic enough for a small CPU-trained model.
    cols=rng.choice([2,2,3]); rows=rng.choice([2,2,3])
    xs=[x0]+[int(round(x0+(x1-x0)*i/cols)) for i in range(1,cols)]+[x1]
    ys=[y0]+[int(round(y0+(y1-y0)*i/rows)) for i in range(1,rows)]+[y1]

    # Room class first.
    mask[y0:y1+1,x0:x1+1]=1

    wall_color=rng.choice([(40,90,210),(15,15,15),(85,85,85),(180,95,35)])
    def wall_line(a,b):
        cv2.line(image,a,b,wall_color,wall_t,cv2.LINE_8)
        cv2.line(mask,a,b,2,wall_t,cv2.LINE_8)

    wall_line((x0,y0),(x1,y0)); wall_line((x1,y0),(x1,y1))
    wall_line((x1,y1),(x0,y1)); wall_line((x0,y1),(x0,y0))

    # Internal partitions with one learned door per run.
    for x in xs[1:-1]:
        door_y=rng.randint(y0+wall_t*3,y1-wall_t*3)
        gap=rng.randint(max(14,size//18),max(20,size//12))
        wall_line((x,y0),(x,max(y0,door_y-gap//2)))
        wall_line((x,min(y1,door_y+gap//2)),(x,y1))
        cv2.rectangle(mask,(x-wall_t//2,door_y-gap//2),(x+wall_t//2,door_y+gap//2),3,-1)
        cv2.line(image,(x,door_y-gap//2),(x+gap//2,door_y), (80,80,80),2)
    for y in ys[1:-1]:
        door_x=rng.randint(x0+wall_t*3,x1-wall_t*3)
        gap=rng.randint(max(14,size//18),max(20,size//12))
        wall_line((x0,y),(max(x0,door_x-gap//2),y))
        wall_line((min(x1,door_x+gap//2),y),(x1,y))
        cv2.rectangle(mask,(door_x-gap//2,y-wall_t//2),(door_x+gap//2,y+wall_t//2),3,-1)
        cv2.line(image,(door_x-gap//2,y),(door_x, y-gap//2),(80,80,80),2)

    # Exterior windows.
    for _ in range(rng.randint(2,5)):
        if rng.random()<.5:
            y=rng.choice([y0,y1])
            cx=rng.randint(x0+size//12,x1-size//12)
            span=rng.randint(size//18,size//11)
            cv2.rectangle(mask,(cx-span//2,y-wall_t//2),(cx+span//2,y+wall_t//2),4,-1)
            cv2.line(image,(cx-span//2,y),(cx+span//2,y),(20,180,220),max(2,wall_t//3))
        else:
            x=rng.choice([x0,x1])
            cy=rng.randint(y0+size//12,y1-size//12)
            span=rng.randint(size//18,size//11)
            cv2.rectangle(mask,(x-wall_t//2,cy-span//2),(x+wall_t//2,cy+span//2),4,-1)
            cv2.line(image,(x,cy-span//2),(x,cy+span//2),(20,180,220),max(2,wall_t//3))

    # Distractor dimension lines and labels that must not become walls.
    green=(40,150,60); red=(40,40,190)
    cv2.line(image,(x0,y0//2),(x1,y0//2),green,1)
    for x in xs:
        cv2.line(image,(x,y0//2-5),(x,y0//2+5),green,1)
    for r in range(rows):
        for c in range(cols):
            cx=(xs[c]+xs[c+1])//2; cy=(ys[r]+ys[r+1])//2
            cv2.putText(image,rng.choice(["ROOM","HALL","BED","KIT"]),(cx-22,cy),
                        cv2.FONT_HERSHEY_SIMPLEX,.38,red,1,cv2.LINE_AA)

    # Mild scan/color variation.
    gain=rng.uniform(.88,1.08); bias=rng.randint(-8,8)
    image=np.clip(image.astype(np.float32)*gain+bias,0,255).astype(np.uint8)
    if rng.random()<.35:
        image=cv2.GaussianBlur(image,(3,3),rng.uniform(.2,.8))
    return image,mask


class SyntheticPlans(Dataset):
    def __init__(self,count:int,size:int,seed:int):
        self.count=count; self.size=size; self.seed=seed
    def __len__(self): return self.count
    def __getitem__(self,index):
        image,mask=_draw_plan(self.seed+index,self.size)
        x=torch.from_numpy(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).permute(2,0,1).float()/255.0
        y=torch.from_numpy(mask.astype(np.int64))
        return x,y


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
    ap.add_argument("--epochs",type=int,default=5)
    ap.add_argument("--train-count",type=int,default=900)
    ap.add_argument("--val-count",type=int,default=180)
    ap.add_argument("--size",type=int,default=256)
    args=ap.parse_args()

    random.seed(240923); np.random.seed(240923); torch.manual_seed(240923)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train=DataLoader(SyntheticPlans(args.train_count,args.size,1000),batch_size=12,shuffle=True,num_workers=0)
    val=DataLoader(SyntheticPlans(args.val_count,args.size,900000),batch_size=12,shuffle=False,num_workers=0)

    model=TinyUNet().to(device)
    weights=torch.tensor([.35,1.0,2.4,4.0,4.0],device=device)
    loss_fn=nn.CrossEntropyLoss(weight=weights)
    opt=torch.optim.AdamW(model.parameters(),lr=2e-3,weight_decay=1e-4)

    best=None; best_score=-1.0
    for epoch in range(1,args.epochs+1):
        model.train(); running=0.0
        for x,y in train:
            x=x.to(device); y=y.to(device)
            loss=loss_fn(model(x),y)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
            running+=float(loss.item())
        metrics=evaluate(model,val,device)
        score=(metrics["wall"]+metrics["door"]+metrics["window"]+metrics["room"])/4
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
        dynamic_axes={"image":{0:"batch",2:"height",3:"width"},"logits":{0:"batch",2:"height",3:"width"}},
    )
    final=evaluate(model,val,torch.device("cpu"))
    meta={"classes":CLASSES,"inputSize":384,"syntheticValidationIoU":final,"training":"Manzil-owned procedural floorplan generator","version":"vision-segmentation-v1"}
    (output/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print(json.dumps(meta,indent=2))


if __name__=="__main__":
    main()
