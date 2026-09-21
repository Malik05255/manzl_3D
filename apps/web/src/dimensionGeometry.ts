import type { ElementProvenance,FloorPlanModel } from "@manzil/contracts";

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

export function calibratePlanFromDimension(plan:FloorPlanModel,dimensionId:string):FloorPlanModel|null{
  const dimension=(plan.dimensions??[]).find(item=>item.id===dimensionId);
  if(!dimension?.reviewed||!dimension.valueM||!dimension.referenceWallId)return null;
  const wall=plan.walls.find(item=>item.id===dimension.referenceWallId);
  if(!wall)return null;

  const pixels=Math.hypot(wall.b.x-wall.a.x,wall.b.y-wall.a.y);
  if(pixels<5)return null;
  const metersPerPixel=dimension.valueM/pixels;
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
    dimensions:(plan.dimensions??[]).map(item=>item.id===dimensionId?{
      ...item,
      reviewed:true,
      provenance:manualProvenance(item.provenance),
    }:item),
    quality:{
      ...plan.quality,
      needsCalibration:false,
      dimensions:Math.max(plan.quality.dimensions,.95),
      warnings:plan.quality.warnings.filter(item=>!item.includes("مقياس")&&!item.includes("معاير")),
    },
  };
}
