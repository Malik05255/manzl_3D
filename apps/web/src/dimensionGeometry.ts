import type { ElementProvenance,FloorPlanModel,Point } from "@manzil/contracts";

function manualProvenance(value?:ElementProvenance):ElementProvenance{
  return value?"mixed":"manual";
}

function polygonArea(points:{x:number;y:number}[]){
  let total=0;
  for(let i=0;i<points.length;i++){
    const a=points[i],b=points[(i+1)%points.length];
    total+=a.x*b.y-b.x*a.y;
  }
  return Math.abs(total)/2;
}

function pointSegmentDistance(px:number,py:number,ax:number,ay:number,bx:number,by:number){
  const vx=bx-ax,vy=by-ay;
  const lengthSq=vx*vx+vy*vy;
  if(lengthSq<=1e-9)return Math.hypot(px-ax,py-ay);
  const t=Math.max(0,Math.min(1,((px-ax)*vx+(py-ay)*vy)/lengthSq));
  const cx=ax+t*vx,cy=ay+t*vy;
  return Math.hypot(px-cx,py-cy);
}

export interface DimensionWallCandidate{
  wallId:string;
  distancePx:number;
  lengthPx:number;
}

export function dimensionWallCandidates(plan:FloorPlanModel,dimensionId:string,limit=12):DimensionWallCandidate[]{
  const dimension=(plan.dimensions??[]).find(item=>item.id===dimensionId);
  if(!dimension||limit<=0)return [];
  return plan.walls.map(wall=>({
    wallId:wall.id,
    distancePx:pointSegmentDistance(dimension.center.x,dimension.center.y,wall.a.x,wall.a.y,wall.b.x,wall.b.y),
    lengthPx:Math.hypot(wall.b.x-wall.a.x,wall.b.y-wall.a.y),
  })).filter(item=>item.lengthPx>=5)
    .sort((a,b)=>a.distancePx-b.distancePx||b.lengthPx-a.lengthPx)
    .slice(0,limit);
}

export function linkDimensionToWall(plan:FloorPlanModel,dimensionId:string,wallId:string|null):FloorPlanModel|null{
  const dimension=(plan.dimensions??[]).find(item=>item.id===dimensionId);
  if(!dimension)return null;
  const wall=wallId?plan.walls.find(item=>item.id===wallId):null;
  if(wallId&&!wall)return null;
  const orientation=wall
    ?Math.abs(wall.b.x-wall.a.x)>=Math.abs(wall.b.y-wall.a.y)?"horizontal":"vertical"
    :"unknown";
  return {
    ...plan,
    dimensions:(plan.dimensions??[]).map(item=>item.id===dimensionId?{
      ...item,
      referenceWallId:wall?.id??null,
      orientation,
      reviewed:true,
      provenance:manualProvenance(item.provenance),
    }:item),
  };
}

export function correctDimensionValue(plan:FloorPlanModel,dimensionId:string,valueM:number):FloorPlanModel|null{
  if(!Number.isFinite(valueM)||valueM<=0||valueM>1000)return null;
  const current=(plan.dimensions??[]).find(item=>item.id===dimensionId);
  if(!current)return null;
  return {
    ...plan,
    dimensions:(plan.dimensions??[]).map(item=>item.id===dimensionId?{
      ...item,
      valueM,
      reviewed:true,
      provenance:manualProvenance(item.provenance),
    }:item),
  };
}

export function calibratePlanFromSpan(plan:FloorPlanModel,valueM:number,a:Point,b:Point):FloorPlanModel|null{
  if(!Number.isFinite(valueM)||valueM<=0||valueM>1000)return null;
  const pixels=Math.hypot(b.x-a.x,b.y-a.y);
  if(!Number.isFinite(pixels)||pixels<5)return null;
  const metersPerPixel=valueM/pixels;
  if(!Number.isFinite(metersPerPixel)||metersPerPixel<=0||metersPerPixel>10)return null;

  const rooms=plan.rooms.map(room=>({
    ...room,
    areaM2:Number((polygonArea(room.polygon)*metersPerPixel*metersPerPixel).toFixed(2)),
  }));

  return {
    ...plan,
    metersPerPixel,
    calibrationConfidence:1,
    rooms,
    quality:{
      ...plan.quality,
      needsCalibration:false,
      dimensions:Math.max(plan.quality.dimensions,.95),
      warnings:plan.quality.warnings.filter(item=>!item.includes("مقياس")&&!item.includes("معاير")),
    },
  };
}

export function calibratePlanFromDimensionSpan(plan:FloorPlanModel,dimensionId:string,a:Point,b:Point):FloorPlanModel|null{
  const dimension=(plan.dimensions??[]).find(item=>item.id===dimensionId);
  if(!dimension?.reviewed||!dimension.valueM)return null;
  const calibrated=calibratePlanFromSpan(plan,dimension.valueM,a,b);
  if(!calibrated)return null;
  const orientation=Math.abs(b.x-a.x)>=Math.abs(b.y-a.y)?"horizontal":"vertical";
  return {
    ...calibrated,
    dimensions:(calibrated.dimensions??[]).map(item=>item.id===dimensionId?{
      ...item,
      spanA:{...a},
      spanB:{...b},
      orientation,
      reviewed:true,
      provenance:manualProvenance(item.provenance),
    }:item),
  };
}
