import type { FloorPlanModel,Opening,PlanLabel,Point,Room,Wall } from "@manzil/contracts";

function object(value:unknown):value is Record<string,unknown>{
  return typeof value==="object"&&value!==null&&!Array.isArray(value);
}
function finite(value:unknown):value is number{
  return typeof value==="number"&&Number.isFinite(value);
}
function confidence(value:unknown){
  return finite(value)&&value>=0&&value<=1;
}
function point(value:unknown):value is Point{
  return object(value)&&finite(value.x)&&finite(value.y);
}
function wall(value:unknown):value is Wall{
  return object(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&point(value.a)&&point(value.b)
    &&finite(value.thicknessPx)&&value.thicknessPx>0&&value.thicknessPx<=200
    &&confidence(value.confidence);
}
function room(value:unknown):value is Room{
  return object(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&typeof value.name==="string"&&value.name.length<=160
    &&Array.isArray(value.polygon)&&value.polygon.length>=3&&value.polygon.length<=500
    &&value.polygon.every(point)
    &&confidence(value.confidence)
    &&(value.areaM2===undefined||value.areaM2===null||(finite(value.areaM2)&&value.areaM2>=0&&value.areaM2<=100000));
}
function opening(value:unknown):value is Opening{
  return object(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&(value.kind==="door"||value.kind==="window")
    &&(value.wallId===undefined||value.wallId===null||typeof value.wallId==="string")
    &&point(value.a)&&point(value.b)
    &&confidence(value.confidence);
}
function label(value:unknown):value is PlanLabel{
  return object(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&typeof value.text==="string"&&value.text.length<=500
    &&point(value.center)
    &&confidence(value.confidence)
    &&["room_name","dimension","note","unknown"].includes(String(value.kind));
}

export function parsePlanBackup(text:string):FloorPlanModel{
  if(text.length>12*1024*1024)throw new Error("BACKUP_TOO_LARGE");
  let value:unknown;
  try{value=JSON.parse(text);}catch{throw new Error("BACKUP_INVALID_JSON");}
  if(!object(value)||value.schemaVersion!==1)throw new Error("BACKUP_SCHEMA");
  if(typeof value.id!=="string"||!value.id)throw new Error("BACKUP_ID");
  if(!finite(value.widthPx)||!finite(value.heightPx)||value.widthPx<=0||value.heightPx<=0||value.widthPx>30000||value.heightPx>30000)throw new Error("BACKUP_SIZE");
  if(value.metersPerPixel!==undefined&&value.metersPerPixel!==null&&(!finite(value.metersPerPixel)||value.metersPerPixel<=0||value.metersPerPixel>10))throw new Error("BACKUP_SCALE");
  if(value.calibrationConfidence!==undefined&&value.calibrationConfidence!==null&&!confidence(value.calibrationConfidence))throw new Error("BACKUP_CALIBRATION");

  if(!Array.isArray(value.walls)||value.walls.length>10000||!value.walls.every(wall))throw new Error("BACKUP_WALLS");
  if(!Array.isArray(value.rooms)||value.rooms.length>5000||!value.rooms.every(room))throw new Error("BACKUP_ROOMS");
  if(!Array.isArray(value.doors)||value.doors.length>5000||!value.doors.every(opening))throw new Error("BACKUP_DOORS");
  if(!Array.isArray(value.windows)||value.windows.length>5000||!value.windows.every(opening))throw new Error("BACKUP_WINDOWS");
  if(!Array.isArray(value.labels)||value.labels.length>10000||!value.labels.every(label))throw new Error("BACKUP_LABELS");

  if(!object(value.quality))throw new Error("BACKUP_QUALITY");
  const quality=value.quality;
  if(!confidence(quality.overall)||!confidence(quality.walls)||!confidence(quality.rooms)||!confidence(quality.text)||!confidence(quality.dimensions)||typeof quality.needsCalibration!=="boolean"||!Array.isArray(quality.warnings)||!quality.warnings.every(item=>typeof item==="string"&&item.length<=500))throw new Error("BACKUP_QUALITY");

  if(!object(value.source)||typeof value.source.fileName!=="string"||typeof value.source.mimeType!=="string"||!finite(value.source.page)||!Number.isInteger(value.source.page)||value.source.page<1)throw new Error("BACKUP_SOURCE");

  const ids=[
    ...value.walls.map(item=>(item as Wall).id),
    ...value.rooms.map(item=>(item as Room).id),
    ...value.doors.map(item=>(item as Opening).id),
    ...value.windows.map(item=>(item as Opening).id),
  ];
  if(new Set(ids).size!==ids.length)throw new Error("BACKUP_DUPLICATE_IDS");

  return value as unknown as FloorPlanModel;
}

export function clonePlanForProject(plan:FloorPlanModel,projectId:string):FloorPlanModel{
  return {
    ...plan,
    id:projectId,
    walls:plan.walls.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    rooms:plan.rooms.map(item=>({...item,polygon:item.polygon.map(point=>({...point}))})),
    doors:plan.doors.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    windows:plan.windows.map(item=>({...item,a:{...item.a},b:{...item.b}})),
    labels:plan.labels.map(item=>({...item,center:{...item.center}})),
    quality:{...plan.quality,warnings:[...plan.quality.warnings]},
    source:{...plan.source},
  };
}
