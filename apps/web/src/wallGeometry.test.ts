import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { createManualWall,removeUnboundWall,wallRemovalReason } from "./wallGeometry";

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
