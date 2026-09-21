import type { FloorPlanModel,Point,Wall } from "@manzil/contracts";

function distance(a:Point,b:Point){
  return Math.hypot(b.x-a.x,b.y-a.y);
}

function median(values:number[]){
  if(!values.length)return null;
  const sorted=[...values].sort((a,b)=>a-b);
  const middle=Math.floor(sorted.length/2);
  return sorted.length%2?sorted[middle]:(sorted[middle-1]+sorted[middle])/2;
}

export function createManualWall(plan:FloorPlanModel,a:Point,b:Point):FloorPlanModel|null{
  const start={
    x:Math.max(0,Math.min(plan.widthPx,a.x)),
    y:Math.max(0,Math.min(plan.heightPx,a.y)),
  };
  const end={
    x:Math.max(0,Math.min(plan.widthPx,b.x)),
    y:Math.max(0,Math.min(plan.heightPx,b.y)),
  };
  const minimumPx=plan.metersPerPixel?Math.max(4,.15/plan.metersPerPixel):8;
  if(distance(start,end)<minimumPx)return null;

  const existing=new Set(plan.walls.map(wall=>wall.id));
  let index=1;
  while(existing.has(`wall-manual-${index}`))index+=1;

  const inferred=median(plan.walls.map(wall=>wall.thicknessPx).filter(value=>Number.isFinite(value)&&value>0));
  const metricDefault=plan.metersPerPixel&&plan.metersPerPixel>0 ? .15/plan.metersPerPixel : null;
  const thicknessPx=Math.max(2,Math.min(200,inferred??metricDefault??8));

  const wall:Wall={
    id:`wall-manual-${index}`,
    a:start,
    b:end,
    thicknessPx:Number(thicknessPx.toFixed(2)),
    confidence:1,
    role:"unknown",
    locked:false,
    reviewed:true,
    provenance:"manual",
  };
  return {...plan,walls:[...plan.walls,wall]};
}

export function wallRemovalReason(plan:FloorPlanModel,wallId:string):string|null{
  const wall=plan.walls.find(item=>item.id===wallId);
  if(!wall)return "الجدار غير موجود.";
  if(wall.locked||wall.role==="structural")return "الجدار محمي؛ فك الحماية أولًا.";
  if([...plan.doors,...plan.windows].some(opening=>opening.wallId===wallId))return "الجدار يحمل بابًا أو نافذة. احذف أو انقل الفتحة أولًا.";
  if(plan.rooms.some(room=>room.boundaryWallIds?.includes(wallId)))return "الجدار مرتبط بحدود غرفة. استخدم دمج/إعادة توزيع الغرف بدل حذفه مباشرة.";
  return null;
}

export function removeUnboundWall(plan:FloorPlanModel,wallId:string):FloorPlanModel|null{
  if(wallRemovalReason(plan,wallId))return null;
  return {
    ...plan,
    walls:plan.walls.filter(wall=>wall.id!==wallId),
    dimensions:plan.dimensions?.map(item=>item.referenceWallId===wallId?{...item,referenceWallId:null,orientation:"unknown"}:item),
  };
}


function generatedSplitIds(plan:FloorPlanModel){
  const ids=new Set(plan.walls.map(wall=>wall.id));
  let index=1;
  while(ids.has(`wall-split-${index}-a`)||ids.has(`wall-split-${index}-b`))index+=1;
  return [`wall-split-${index}-a`,`wall-split-${index}-b`] as const;
}

function projectParameter(point:Point,a:Point,b:Point){
  const vx=b.x-a.x,vy=b.y-a.y;
  const lengthSq=vx*vx+vy*vy;
  if(lengthSq<=1e-9)return 0;
  return ((point.x-a.x)*vx+(point.y-a.y)*vy)/lengthSq;
}

function mixedProvenance(wall:Wall):Wall["provenance"]{
  return wall.provenance?"mixed":"manual";
}

function protectedWall(wall:Wall){
  return Boolean(wall.locked)||wall.role==="structural";
}

export function splitWallAtPoint(plan:FloorPlanModel,wallId:string,point:Point):FloorPlanModel|null{
  const wall=plan.walls.find(item=>item.id===wallId);
  if(!wall||protectedWall(wall))return null;
  const vx=wall.b.x-wall.a.x,vy=wall.b.y-wall.a.y;
  const length=Math.hypot(vx,vy);
  if(length<=1e-9)return null;
  const minimumPx=plan.metersPerPixel?Math.max(4,.15/plan.metersPerPixel):8;
  const rawT=projectParameter(point,wall.a,wall.b);
  const t=Math.max(0,Math.min(1,rawT));
  if(t*length<minimumPx||(1-t)*length<minimumPx)return null;
  const split={x:wall.a.x+vx*t,y:wall.a.y+vy*t};
  const [firstId,secondId]=generatedSplitIds(plan);
  const metadata={reviewed:true,provenance:mixedProvenance(wall)};
  const first:Wall={...wall,...metadata,id:firstId,b:split};
  const second:Wall={...wall,...metadata,id:secondId,a:split};

  const hostForPoint=(candidate:Point)=>projectParameter(candidate,wall.a,wall.b)<=t?firstId:secondId;
  const doors=plan.doors.map(opening=>opening.wallId===wallId?{
    ...opening,
    wallId:hostForPoint({x:(opening.a.x+opening.b.x)/2,y:(opening.a.y+opening.b.y)/2}),
    reviewed:true,
    provenance:opening.provenance?"mixed":"manual",
  }:opening);
  const windows=plan.windows.map(opening=>opening.wallId===wallId?{
    ...opening,
    wallId:hostForPoint({x:(opening.a.x+opening.b.x)/2,y:(opening.a.y+opening.b.y)/2}),
    reviewed:true,
    provenance:opening.provenance?"mixed":"manual",
  }:opening);
  const rooms=plan.rooms.map(room=>room.boundaryWallIds?.includes(wallId)?{
    ...room,
    boundaryWallIds:room.boundaryWallIds.flatMap(id=>id===wallId?[firstId,secondId]:[id]),
    provenance:room.provenance?"mixed":"manual",
  }:room);
  const dimensions=plan.dimensions?.map(item=>{
    if(item.referenceWallId!==wallId)return item;
    const anchor=item.spanA&&item.spanB
      ?{x:(item.spanA.x+item.spanB.x)/2,y:(item.spanA.y+item.spanB.y)/2}
      :item.center;
    return {...item,referenceWallId:hostForPoint(anchor),provenance:item.provenance?"mixed":"manual"};
  });
  const walls=plan.walls.flatMap(item=>item.id===wallId?[first,second]:[item]);
  return {...plan,walls,rooms,doors,windows,dimensions};
}

function pointLineDistance(point:Point,a:Point,b:Point){
  const vx=b.x-a.x,vy=b.y-a.y;
  const length=Math.hypot(vx,vy);
  if(length<=1e-9)return distance(point,a);
  return Math.abs(vy*point.x-vx*point.y+b.x*a.y-b.y*a.x)/length;
}

export function joinCollinearWalls(plan:FloorPlanModel,firstId:string,secondId:string):FloorPlanModel|null{
  if(firstId===secondId)return null;
  const first=plan.walls.find(item=>item.id===firstId);
  const second=plan.walls.find(item=>item.id===secondId);
  if(!first||!second||protectedWall(first)||protectedWall(second))return null;
  const v1={x:first.b.x-first.a.x,y:first.b.y-first.a.y};
  const v2={x:second.b.x-second.a.x,y:second.b.y-second.a.y};
  const l1=Math.hypot(v1.x,v1.y),l2=Math.hypot(v2.x,v2.y);
  if(l1<1e-6||l2<1e-6)return null;
  const sine=Math.abs(v1.x*v2.y-v1.y*v2.x)/(l1*l2);
  if(sine>Math.sin(Math.PI/60))return null;
  const tolerance=Math.max(8,(first.thicknessPx+second.thicknessPx)*.75);
  if(Math.min(pointLineDistance(second.a,first.a,first.b),pointLineDistance(second.b,first.a,first.b))>tolerance)return null;

  const endpoints=[
    {point:first.a,owner:firstId},{point:first.b,owner:firstId},
    {point:second.a,owner:secondId},{point:second.b,owner:secondId},
  ];
  let nearest=Infinity;
  for(const a of endpoints.filter(item=>item.owner===firstId)){
    for(const b of endpoints.filter(item=>item.owner===secondId)){
      nearest=Math.min(nearest,distance(a.point,b.point));
    }
  }
  if(nearest>tolerance*1.5)return null;

  let farthest=[endpoints[0].point,endpoints[1].point] as [Point,Point];
  let farthestDistance=0;
  for(let i=0;i<endpoints.length;i++){
    for(let j=i+1;j<endpoints.length;j++){
      const current=distance(endpoints[i].point,endpoints[j].point);
      if(current>farthestDistance){farthestDistance=current;farthest=[endpoints[i].point,endpoints[j].point];}
    }
  }
  const joined:Wall={
    ...first,
    a:{...farthest[0]},
    b:{...farthest[1]},
    thicknessPx:Number(((first.thicknessPx*l1+second.thicknessPx*l2)/(l1+l2)).toFixed(2)),
    confidence:Math.min(first.confidence,second.confidence),
    role:first.role===second.role?first.role:"unknown",
    reviewed:true,
    provenance:first.provenance||second.provenance?"mixed":"manual",
  };
  const walls=plan.walls.filter(item=>item.id!==secondId).map(item=>item.id===firstId?joined:item);
  const rewriteIds=(ids:string[]|undefined)=>ids?Array.from(new Set(ids.map(id=>id===secondId?firstId:id))):ids;
  return {
    ...plan,
    walls,
    rooms:plan.rooms.map(room=>({...room,boundaryWallIds:rewriteIds(room.boundaryWallIds)})),
    doors:plan.doors.map(opening=>opening.wallId===secondId?{...opening,wallId:firstId,provenance:opening.provenance?"mixed":"manual"}:opening),
    windows:plan.windows.map(opening=>opening.wallId===secondId?{...opening,wallId:firstId,provenance:opening.provenance?"mixed":"manual"}:opening),
    dimensions:plan.dimensions?.map(item=>item.referenceWallId===secondId?{...item,referenceWallId:firstId,provenance:item.provenance?"mixed":"manual"}:item),
  };
}

function endpointEditBlocked(plan:FloorPlanModel,wall:Wall){
  if(protectedWall(wall))return true;
  return plan.rooms.some(room=>room.boundaryWallIds?.includes(wall.id));
}

function pointInsidePlan(plan:FloorPlanModel,point:Point){
  return point.x>=0&&point.y>=0&&point.x<=plan.widthPx&&point.y<=plan.heightPx;
}

function openingFitsWall(plan:FloorPlanModel,wall:Wall){
  const tolerance=Math.max(6,wall.thicknessPx*1.5);
  return [...plan.doors,...plan.windows].filter(item=>item.wallId===wall.id).every(opening=>
    [opening.a,opening.b].every(point=>{
      const t=projectParameter(point,wall.a,wall.b);
      return t>=-0.01&&t<=1.01&&pointLineDistance(point,wall.a,wall.b)<=tolerance;
    })
  );
}

function resizeWallEndpoint(plan:FloorPlanModel,wallId:string,endpoint:"a"|"b",distancePx:number,mode:"extend"|"trim"):FloorPlanModel|null{
  if(!Number.isFinite(distancePx)||distancePx<=0)return null;
  const wall=plan.walls.find(item=>item.id===wallId);
  if(!wall||endpointEditBlocked(plan,wall))return null;
  const vx=wall.b.x-wall.a.x,vy=wall.b.y-wall.a.y;
  const length=Math.hypot(vx,vy);
  const minimumPx=plan.metersPerPixel?Math.max(4,.15/plan.metersPerPixel):8;
  if(length<=minimumPx)return null;
  if(mode==="trim"&&length-distancePx<minimumPx)return null;
  const ux=vx/length,uy=vy/length;
  const direction=mode==="extend"?1:-1;
  let a={...wall.a},b={...wall.b};
  if(endpoint==="a"){
    a={x:wall.a.x-ux*distancePx*direction,y:wall.a.y-uy*distancePx*direction};
  }else{
    b={x:wall.b.x+ux*distancePx*direction,y:wall.b.y+uy*distancePx*direction};
  }
  if(!pointInsidePlan(plan,a)||!pointInsidePlan(plan,b))return null;
  const next:Wall={...wall,a,b,reviewed:true,provenance:mixedProvenance(wall)};
  if(!openingFitsWall(plan,next))return null;
  return {...plan,walls:plan.walls.map(item=>item.id===wallId?next:item)};
}

export function extendWallEndpoint(plan:FloorPlanModel,wallId:string,endpoint:"a"|"b",distancePx:number){
  return resizeWallEndpoint(plan,wallId,endpoint,distancePx,"extend");
}

export function trimWallEndpoint(plan:FloorPlanModel,wallId:string,endpoint:"a"|"b",distancePx:number){
  return resizeWallEndpoint(plan,wallId,endpoint,distancePx,"trim");
}
