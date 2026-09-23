import type { FloorPlanModel } from "@manzil/contracts";
import { floorPlanValidationError } from "@manzil/contracts";

export function parsePlanBackup(text:string):FloorPlanModel{
  if(text.length>12*1024*1024)throw new Error("BACKUP_TOO_LARGE");
  let value:unknown;
  try{value=JSON.parse(text);}catch{throw new Error("BACKUP_INVALID_JSON");}
  const error=floorPlanValidationError(value);
  if(error)throw new Error(error.replace(/^PLAN_/,"BACKUP_"));
  return value as FloorPlanModel;
}

export function clonePlanForProject(plan:FloorPlanModel,projectId:string):FloorPlanModel{
  return {
    ...plan,
    id:projectId,
    walls:plan.walls.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    rooms:plan.rooms.map(item=>({...item,polygon:item.polygon.map(point=>({...point})),boundaryWallIds:item.boundaryWallIds?[...item.boundaryWallIds]:item.boundaryWallIds})),
    doors:plan.doors.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    windows:plan.windows.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    labels:plan.labels.map(item=>({...item,center:{...item.center}})),
    dimensions:plan.dimensions?.map(item=>({
      ...item,
      center:{...item.center},
      spanA:item.spanA?{...item.spanA}:item.spanA,
      spanB:item.spanB?{...item.spanB}:item.spanB,
    })),
    symbols:plan.symbols?.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    quality:{...plan.quality,warnings:[...plan.quality.warnings]},
    source:{...plan.source},
    analysis:plan.analysis?{...plan.analysis,engines:[...plan.analysis.engines]}:plan.analysis,
  };
}
