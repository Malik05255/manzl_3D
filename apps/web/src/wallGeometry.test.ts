import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { createManualWall,extendWallEndpoint,joinCollinearWalls,removeUnboundWall,splitWallAtPoint,trimWallEndpoint,wallRemovalReason } from "./wallGeometry";

function plan():FloorPlanModel{
  return {
    schemaVersion:1,
    id:"p",
    widthPx:1000,
    heightPx:700,
    metersPerPixel:.01,
    calibrationConfidence:1,
    walls:[
      {id:"bound",a:{x:100,y:100},b:{x:500,y:100},thicknessPx:12,confidence:.9,role:"interior"},
      {id:"free",a:{x:700,y:100},b:{x:900,y:100},thicknessPx:18,confidence:.8,role:"unknown"},
    ],
    rooms:[
      {
        id:"room",
        name:"غرفة",
        polygon:[{x:100,y:100},{x:500,y:100},{x:500,y:500},{x:100,y:500}],
        confidence:.9,
        boundaryWallIds:["bound"],
      },
    ],
    doors:[],
    windows:[],
    labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
}

describe("manual wall geometry",()=>{
  it("creates reviewed manual wall using inferred thickness",()=>{
    const next=createManualWall(plan(),{x:200,y:600},{x:700,y:600})!;
    const wall=next.walls.at(-1)!;
    expect(wall.id).toBe("wall-manual-1");
    expect(wall.reviewed).toBe(true);
    expect(wall.provenance).toBe("manual");
    expect(wall.locked).toBe(false);
    expect(wall.role).toBe("unknown");
    expect(wall.thicknessPx).toBe(15);
  });

  it("rejects a wall shorter than the supported minimum",()=>{
    expect(createManualWall(plan(),{x:10,y:10},{x:15,y:10})).toBeNull();
  });

  it("allows deleting only walls that are not protected or referenced",()=>{
    const source=plan();
    expect(wallRemovalReason(source,"bound")).toContain("حدود غرفة");
    expect(wallRemovalReason(source,"free")).toBeNull();
    const next=removeUnboundWall(source,"free")!;
    expect(next.walls.some(wall=>wall.id==="free")).toBe(false);
    expect(next.walls.some(wall=>wall.id==="bound")).toBe(true);
  });

  it("blocks deleting a wall that hosts an opening",()=>{
    const source=plan();
    source.doors.push({id:"door",kind:"door",wallId:"free",a:{x:750,y:100},b:{x:840,y:100},confidence:1});
    expect(wallRemovalReason(source,"free")).toContain("باب");
    expect(removeUnboundWall(source,"free")).toBeNull();
  });
});


it("detaches dimension evidence when deleting an unbound wall",()=>{
  const source=plan();
  source.dimensions=[{
    id:"dimension-1",text:"4.20 m",center:{x:300,y:80},valueM:4.2,
    unit:"m",orientation:"horizontal",referenceWallId:"free",
    confidence:.9,provenance:"ocr",
  }];
  const next=removeUnboundWall(source,"free")!;
  expect(next.walls.some(item=>item.id==="free")).toBe(false);
  expect(next.dimensions?.[0].referenceWallId).toBeNull();
  expect(next.dimensions?.[0].orientation).toBe("unknown");
});


describe("CAD wall operations",()=>{
  it("splits a room boundary wall and rewrites topology references",()=>{
    const source=plan();
    source.doors=[{id:"door",kind:"door",wallId:"bound",a:{x:180,y:100},b:{x:240,y:100},confidence:1}];
    source.dimensions=[{id:"d",text:"2.00 m",center:{x:400,y:80},valueM:2,unit:"m",orientation:"horizontal",referenceWallId:"bound",confidence:.9}];
    const next=splitWallAtPoint(source,"bound",{x:300,y:105})!;
    expect(next.walls.some(wall=>wall.id==="bound")).toBe(false);
    const splitWalls=next.walls.filter(wall=>wall.id.startsWith("wall-split-"));
    expect(splitWalls).toHaveLength(2);
    expect(next.rooms[0].boundaryWallIds).toEqual(splitWalls.map(wall=>wall.id));
    expect(next.doors[0].wallId).toBe(splitWalls[0].id);
    expect(next.dimensions?.[0].referenceWallId).toBe(splitWalls[1].id);
  });

  it("joins connected collinear walls and rewrites hosted references",()=>{
    const source=plan();
    source.rooms=[];
    source.walls=[
      {id:"a",a:{x:100,y:200},b:{x:300,y:200},thicknessPx:10,confidence:.9,role:"interior"},
      {id:"b",a:{x:300,y:200},b:{x:550,y:200},thicknessPx:14,confidence:.8,role:"interior"},
    ];
    source.windows=[{id:"window",kind:"window",wallId:"b",a:{x:360,y:200},b:{x:430,y:200},confidence:1}];
    const next=joinCollinearWalls(source,"a","b")!;
    expect(next.walls).toHaveLength(1);
    expect(next.walls[0].a.x).toBe(100);
    expect(next.walls[0].b.x).toBe(550);
    expect(next.windows[0].wallId).toBe("a");
  });

  it("rejects joining walls that are not collinear",()=>{
    const source=plan();
    source.rooms=[];
    source.walls=[
      {id:"a",a:{x:100,y:200},b:{x:300,y:200},thicknessPx:10,confidence:.9},
      {id:"b",a:{x:300,y:200},b:{x:300,y:450},thicknessPx:10,confidence:.9},
    ];
    expect(joinCollinearWalls(source,"a","b")).toBeNull();
  });

  it("extends and trims a free diagonal wall without forcing orthogonal geometry",()=>{
    const source=plan();
    source.rooms=[];
    source.walls=[{id:"diag",a:{x:100,y:100},b:{x:200,y:200},thicknessPx:10,confidence:.9}];
    const extended=extendWallEndpoint(source,"diag","b",Math.sqrt(5000))!;
    expect(extended.walls[0].b.x).toBeCloseTo(250,5);
    expect(extended.walls[0].b.y).toBeCloseTo(250,5);
    const trimmed=trimWallEndpoint(extended,"diag","b",Math.sqrt(5000))!;
    expect(trimmed.walls[0].b.x).toBeCloseTo(200,5);
    expect(trimmed.walls[0].b.y).toBeCloseTo(200,5);
  });

  it("does not trim a room boundary wall outside topology-aware editing",()=>{
    const source=plan();
    expect(trimWallEndpoint(source,"bound","b",20)).toBeNull();
  });
});
