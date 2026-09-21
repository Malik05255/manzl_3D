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
  return {...plan,walls:plan.walls.filter(wall=>wall.id!==wallId)};
}
