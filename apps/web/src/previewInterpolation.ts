import type { FloorPlanModel,Opening,Point,Room,Wall } from "@manzil/contracts";

function lerp(a:number,b:number,t:number){return a+(b-a)*t;}
function point(a:Point,b:Point,t:number):Point{return{x:lerp(a.x,b.x,t),y:lerp(a.y,b.y,t)};}

function interpolateWall(from:Wall,to:Wall,t:number):Wall{
  return {...to,a:point(from.a,to.a,t),b:point(from.b,to.b,t),thicknessPx:lerp(from.thicknessPx,to.thicknessPx,t)};
}
function interpolateOpening(from:Opening,to:Opening,t:number):Opening{
  return {...to,a:point(from.a,to.a,t),b:point(from.b,to.b,t)};
}
function interpolateRoom(from:Room,to:Room,t:number):Room{
  if(from.polygon.length!==to.polygon.length)return t<.5?from:to;
  const areaFrom=from.areaM2??null,areaTo=to.areaM2??null;
  return {
    ...to,
    polygon:to.polygon.map((p,index)=>point(from.polygon[index],p,t)),
    areaM2:areaFrom!==null&&areaTo!==null?lerp(areaFrom,areaTo,t):areaTo,
  };
}
function byId<T extends {id:string}>(items:T[]){return new Map(items.map(item=>[item.id,item]));}

export function interpolatePlan(from:FloorPlanModel,to:FloorPlanModel,t:number):FloorPlanModel{
  const progress=Math.max(0,Math.min(1,t));
  if(progress<=0)return from;
  if(progress>=1)return to;

  const fromWalls=byId(from.walls);
  const fromRooms=byId(from.rooms);
  const fromDoors=byId(from.doors);
  const fromWindows=byId(from.windows);

  return {
    ...to,
    metersPerPixel:to.metersPerPixel??from.metersPerPixel,
    walls:to.walls.map(item=>{
      const previous=fromWalls.get(item.id);
      return previous?interpolateWall(previous,item,progress):item;
    }),
    rooms:to.rooms.map(item=>{
      const previous=fromRooms.get(item.id);
      return previous?interpolateRoom(previous,item,progress):item;
    }),
    doors:to.doors.map(item=>{
      const previous=fromDoors.get(item.id);
      return previous?interpolateOpening(previous,item,progress):item;
    }),
    windows:to.windows.map(item=>{
      const previous=fromWindows.get(item.id);
      return previous?interpolateOpening(previous,item,progress):item;
    }),
  };
}

export function easePreview(t:number){
  const value=Math.max(0,Math.min(1,t));
  return 1-Math.pow(1-value,3);
}
