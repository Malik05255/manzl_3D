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


it("marks manually moved topology as reviewed mixed provenance",()=>{
  const plan={
    schemaVersion:1 as const,id:"p",widthPx:1000,heightPx:700,metersPerPixel:.01,calibrationConfidence:1,
    walls:[
      {id:"shared",a:{x:500,y:100},b:{x:500,y:500},thicknessPx:10,confidence:.9,reviewed:false,provenance:"opencv" as const},
      {id:"top",a:{x:100,y:100},b:{x:500,y:100},thicknessPx:10,confidence:.9,reviewed:false,provenance:"opencv" as const},
    ],
    rooms:[
      {id:"room",name:"غرفة",polygon:[{x:100,y:100},{x:500,y:100},{x:500,y:500},{x:100,y:500}],confidence:.9,areaM2:16,reviewed:false,provenance:"opencv" as const},
    ],
    doors:[
      {id:"door",kind:"door" as const,wallId:"shared",a:{x:500,y:200},b:{x:500,y:290},confidence:.9,reviewed:false,provenance:"opencv" as const},
    ],
    windows:[],labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
  const original=plan.walls[0];
  const next=moveWallAndTopology(plan,original,{...original,a:{...original.a,x:550},b:{...original.b,x:550}});
  const moved=next.walls.find(item=>item.id==="shared")!;
  expect(moved.reviewed).toBe(true);
  expect(moved.provenance).toBe("mixed");
  expect(next.rooms[0].provenance).toBe("mixed");
  expect(next.doors[0].provenance).toBe("mixed");
});


it("moves a slanted wall as a rigid segment and keeps connected topology attached",()=>{
  const source:FloorPlanModel={
    schemaVersion:1,id:"diag",widthPx:500,heightPx:400,metersPerPixel:.01,calibrationConfidence:1,
    walls:[
      {id:"diag",a:{x:100,y:100},b:{x:250,y:250},thicknessPx:8,confidence:.9,provenance:"opencv"},
      {id:"connected",a:{x:250,y:250},b:{x:350,y:250},thicknessPx:8,confidence:.9,provenance:"opencv"},
    ],
    rooms:[{id:"r",name:"R",polygon:[{x:100,y:100},{x:250,y:250},{x:350,y:100}],confidence:.9,areaM2:1.875,provenance:"opencv"}],
    doors:[{id:"door",kind:"door",wallId:"diag",a:{x:160,y:160},b:{x:200,y:200},confidence:.9,provenance:"opencv"}],
    windows:[],labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
  const original=source.walls[0];
  const next=moveWallAndTopology(source,original,{...original,a:{x:120,y:80},b:{x:270,y:230}});
  const moved=next.walls.find(item=>item.id==="diag")!;
  expect(moved.b.x-moved.a.x).toBeCloseTo(150,6);
  expect(moved.b.y-moved.a.y).toBeCloseTo(150,6);
  expect(next.walls.find(item=>item.id==="connected")!.a).toEqual({x:270,y:230});
  expect(next.doors[0].a).toEqual({x:180,y:140});
  expect(next.rooms[0].polygon[0]).toEqual({x:120,y:80});
  expect(next.rooms[0].polygon[1]).toEqual({x:270,y:230});
});
