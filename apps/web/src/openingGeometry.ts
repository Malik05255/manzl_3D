import type { ElementProvenance,FloorPlanModel,Opening,Point,Wall } from "@manzil/contracts";

function manualProvenance(value?:ElementProvenance):ElementProvenance{
  return value?"mixed":"manual";
}

function markManual(opening:Opening):Opening{
  return {...opening,reviewed:true,provenance:manualProvenance(opening.provenance)};
}

function wallVector(wall:Wall){
  const vx=wall.b.x-wall.a.x;
  const vy=wall.b.y-wall.a.y;
  const length=Math.hypot(vx,vy);
  if(length<1)return null;
  return {vx,vy,length,ux:vx/length,uy:vy/length};
}

function pointAt(wall:Wall,distance:number):Point{
  const vector=wallVector(wall);
  if(!vector)return {...wall.a};
  return {x:wall.a.x+vector.ux*distance,y:wall.a.y+vector.uy*distance};
}

function projectDistance(wall:Wall,point:Point){
  const vector=wallVector(wall);
  if(!vector)return 0;
  return (point.x-wall.a.x)*vector.ux+(point.y-wall.a.y)*vector.uy;
}

export function findOpening(plan:FloorPlanModel,id:string):Opening|null{
  return plan.doors.find(item=>item.id===id)??plan.windows.find(item=>item.id===id)??null;
}

function replaceOpening(plan:FloorPlanModel,next:Opening):FloorPlanModel{
  const doors=plan.doors.filter(item=>item.id!==next.id);
  const windows=plan.windows.filter(item=>item.id!==next.id);
  if(next.kind==="door")doors.push(next);
  else windows.push(next);
  return {...plan,doors,windows};
}

export function removeOpening(plan:FloorPlanModel,id:string):FloorPlanModel{
  return {...plan,doors:plan.doors.filter(item=>item.id!==id),windows:plan.windows.filter(item=>item.id!==id)};
}

export function changeOpeningKind(plan:FloorPlanModel,id:string,kind:Opening["kind"]):FloorPlanModel|null{
  const opening=findOpening(plan,id);
  if(!opening)return null;
  return replaceOpening(plan,markManual({...opening,kind}));
}

function normalizedOpening(plan:FloorPlanModel,opening:Opening,widthPx:number,centerDistance:number):Opening|null{
  if(!opening.wallId)return null;
  const wall=plan.walls.find(item=>item.id===opening.wallId);
  if(!wall)return null;
  const vector=wallVector(wall);
  if(!vector)return null;
  const margin=Math.max(4,wall.thicknessPx*1.25);
  const usable=Math.max(0,vector.length-margin*2);
  const safeWidth=Math.min(Math.max(6,widthPx),usable);
  if(safeWidth<6)return null;
  const half=safeWidth/2;
  const center=Math.max(margin+half,Math.min(vector.length-margin-half,centerDistance));
  return markManual({...opening,a:pointAt(wall,center-half),b:pointAt(wall,center+half)});
}

export function openingMetrics(plan:FloorPlanModel,id:string){
  const opening=findOpening(plan,id);
  if(!opening||!opening.wallId)return null;
  const wall=plan.walls.find(item=>item.id===opening.wallId);
  if(!wall)return null;
  const vector=wallVector(wall);
  if(!vector)return null;
  const a=projectDistance(wall,opening.a);
  const b=projectDistance(wall,opening.b);
  const center=(a+b)/2;
  const widthPx=Math.abs(b-a);
  return {
    opening,
    wall,
    widthPx,
    widthM:plan.metersPerPixel?widthPx*plan.metersPerPixel:null,
    positionPct:Math.max(0,Math.min(100,center/vector.length*100)),
  };
}

export function resizeOpening(plan:FloorPlanModel,id:string,widthM:number):FloorPlanModel|null{
  if(!plan.metersPerPixel||!Number.isFinite(widthM)||widthM<=0)return null;
  const metrics=openingMetrics(plan,id);
  if(!metrics)return null;
  const target=normalizedOpening(plan,metrics.opening,widthM/plan.metersPerPixel,metrics.positionPct/100*wallVector(metrics.wall)!.length);
  return target?replaceOpening(plan,target):null;
}

export function positionOpening(plan:FloorPlanModel,id:string,positionPct:number):FloorPlanModel|null{
  const metrics=openingMetrics(plan,id);
  if(!metrics)return null;
  const vector=wallVector(metrics.wall)!;
  const target=normalizedOpening(plan,metrics.opening,metrics.widthPx,Math.max(0,Math.min(100,positionPct))/100*vector.length);
  return target?replaceOpening(plan,target):null;
}

function openingInterval(wall:Wall,opening:Opening){
  const a=projectDistance(wall,opening.a);
  const b=projectDistance(wall,opening.b);
  return [Math.min(a,b),Math.max(a,b)] as const;
}

function nextOpeningId(plan:FloorPlanModel,kind:Opening["kind"]){
  const existing=new Set([...plan.doors,...plan.windows].map(item=>item.id));
  let index=1;
  while(existing.has(`${kind}-manual-${index}`))index++;
  return `${kind}-manual-${index}`;
}

export function addOpeningToWall(plan:FloorPlanModel,wallId:string,kind:Opening["kind"]):FloorPlanModel|null{
  const wall=plan.walls.find(item=>item.id===wallId);
  if(!wall)return null;
  const vector=wallVector(wall);
  if(!vector)return null;
  const margin=Math.max(5,wall.thicknessPx*1.5);
  const preferredM=kind==="door"?.9:1.2;
  let widthPx=plan.metersPerPixel?preferredM/plan.metersPerPixel:Math.max(18,vector.length*.14);
  widthPx=Math.min(widthPx,vector.length*.55);
  if(widthPx<8)return null;

  const occupied=[...plan.doors,...plan.windows]
    .filter(item=>item.wallId===wallId)
    .map(item=>openingInterval(wall,item))
    .sort((a,b)=>a[0]-b[0]);

  const free:Array<[number,number]>=[];
  let cursor=margin;
  for(const [start,end] of occupied){
    const protectedStart=Math.max(margin,start-margin);
    const protectedEnd=Math.min(vector.length-margin,end+margin);
    if(protectedStart>cursor)free.push([cursor,protectedStart]);
    cursor=Math.max(cursor,protectedEnd);
  }
  if(cursor<vector.length-margin)free.push([cursor,vector.length-margin]);

  const slot=free
    .filter(([start,end])=>end-start>=widthPx)
    .sort((a,b)=>(b[1]-b[0])-(a[1]-a[0]))[0];
  if(!slot)return null;

  const center=(slot[0]+slot[1])/2;
  const opening:Opening={
    id:nextOpeningId(plan,kind),
    kind,
    wallId,
    a:pointAt(wall,center-widthPx/2),
    b:pointAt(wall,center+widthPx/2),
    confidence:1,
    reviewed:true,
    provenance:"manual",
  };
  return replaceOpening(plan,opening);
}
