import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { easePreview,interpolatePlan } from "./previewInterpolation";

function plan():FloorPlanModel{
  return {
    schemaVersion:1,id:"p",widthPx:1000,heightPx:600,metersPerPixel:.01,calibrationConfidence:1,
    walls:[{id:"w",a:{x:100,y:100},b:{x:100,y:500},thicknessPx:10,confidence:1}],
    rooms:[{id:"r",name:"غرفة",polygon:[{x:100,y:100},{x:500,y:100},{x:500,y:500},{x:100,y:500}],confidence:1,areaM2:16}],
    doors:[{id:"d",kind:"door",wallId:"w",a:{x:100,y:200},b:{x:100,y:290},confidence:1}],
    windows:[],labels:[],
    quality:{overall:1,walls:1,rooms:1,text:1,dimensions:1,needsCalibration:false,warnings:[]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
}

describe("preview interpolation",()=>{
  it("moves matching geometry halfway without mutating endpoints",()=>{
    const from=plan();
    const to=structuredClone(from);
    to.walls[0].a.x=200;to.walls[0].b.x=200;
    to.rooms[0].polygon[0].x=200;to.rooms[0].polygon[3].x=200;
    to.rooms[0].areaM2=12;
    to.doors[0].a.x=200;to.doors[0].b.x=200;
    const mid=interpolatePlan(from,to,.5);
    expect(mid.walls[0].a.x).toBe(150);
    expect(mid.rooms[0].polygon[0].x).toBe(150);
    expect(mid.rooms[0].areaM2).toBe(14);
    expect(mid.doors[0].a.x).toBe(150);
    expect(from.walls[0].a.x).toBe(100);
    expect(to.walls[0].a.x).toBe(200);
  });

  it("clamps progress and eases toward the destination",()=>{
    const from=plan(),to=structuredClone(from);
    to.walls[0].a.x=300;
    expect(interpolatePlan(from,to,-1).walls[0].a.x).toBe(100);
    expect(interpolatePlan(from,to,2).walls[0].a.x).toBe(300);
    expect(easePreview(.5)).toBeGreaterThan(.5);
  });
});
