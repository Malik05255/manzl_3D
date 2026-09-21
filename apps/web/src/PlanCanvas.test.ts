import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { moveWallAndTopology,snapAxis } from "./PlanCanvas";

function plan():FloorPlanModel{
  return {
    schemaVersion:1,id:"p1",widthPx:500,heightPx:300,metersPerPixel:.01,calibrationConfidence:1,
    walls:[
      {id:"left",a:{x:0,y:0},b:{x:0,y:300},thicknessPx:8,confidence:.9},
      {id:"shared",a:{x:200,y:0},b:{x:200,y:300},thicknessPx:8,confidence:.9},
      {id:"right",a:{x:500,y:0},b:{x:500,y:300},thicknessPx:8,confidence:.9},
      {id:"top-left",a:{x:0,y:0},b:{x:200,y:0},thicknessPx:8,confidence:.9},
      {id:"top-right",a:{x:200,y:0},b:{x:500,y:0},thicknessPx:8,confidence:.9},
    ],
    rooms:[
      {id:"a",name:"A",polygon:[{x:0,y:0},{x:200,y:0},{x:200,y:300},{x:0,y:300}],confidence:.9,areaM2:6},
      {id:"b",name:"B",polygon:[{x:200,y:0},{x:500,y:0},{x:500,y:300},{x:200,y:300}],confidence:.9,areaM2:9},
    ],
    doors:[{id:"door",kind:"door",wallId:"shared",a:{x:200,y:100},b:{x:200,y:190},confidence:.9}],
    windows:[],labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
}

describe("manual wall topology",()=>{
  it("moves the shared wall, both room boundaries and attached openings from the drag base plan",()=>{
    const base=plan();
    const original=base.walls.find(wall=>wall.id==="shared")!;
    const moved=moveWallAndTopology(base,original,{...original,a:{x:220,y:0},b:{x:220,y:300}});
    expect(moved.walls.find(wall=>wall.id==="shared")!.a.x).toBe(220);
    expect(moved.rooms[0].polygon.some(point=>point.x===220)).toBe(true);
    expect(moved.rooms[1].polygon.some(point=>point.x===220)).toBe(true);
    expect(moved.doors[0].a.x).toBe(220);
    expect(moved.walls.find(wall=>wall.id==="top-left")!.b.x).toBe(220);
    expect(moved.walls.find(wall=>wall.id==="top-right")!.a.x).toBe(220);
    expect(moved.rooms[0].areaM2).toBe(6.6);
    expect(moved.rooms[1].areaM2).toBe(8.4);
  });

  it("computes later drag frames from the original plan instead of accumulating deltas",()=>{
    const base=plan();
    const original=base.walls.find(wall=>wall.id==="shared")!;
    const frame1=moveWallAndTopology(base,original,{...original,a:{x:215,y:0},b:{x:215,y:300}});
    const frame2=moveWallAndTopology(base,original,{...original,a:{x:230,y:0},b:{x:230,y:300}});
    expect(frame1.walls.find(wall=>wall.id==="shared")!.a.x).toBe(215);
    expect(frame2.walls.find(wall=>wall.id==="shared")!.a.x).toBe(230);
  });
});


describe("manual wall snapping",()=>{
  it("snaps to 5cm increments when the plan scale is known",()=>{
    expect(snapAxis(123,.01,.05)).toBe(125);
    expect(snapAxis(122,.01,.05)).toBe(120);
  });

  it("leaves coordinates unchanged before calibration",()=>{
    expect(snapAxis(123,null,.05)).toBe(123);
  });
});
