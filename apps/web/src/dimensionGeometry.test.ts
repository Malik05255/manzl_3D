import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { calibratePlanFromDimension,correctDimensionValue } from "./dimensionGeometry";

function plan():FloorPlanModel{
  return {
    schemaVersion:1,
    id:"p",
    widthPx:1000,
    heightPx:700,
    metersPerPixel:.01,
    calibrationConfidence:.6,
    walls:[{
      id:"top",
      a:{x:100,y:100},
      b:{x:500,y:100},
      thicknessPx:10,
      confidence:.9,
      provenance:"opencv",
    }],
    rooms:[{
      id:"room",
      name:"غرفة",
      polygon:[{x:100,y:100},{x:500,y:100},{x:500,y:500},{x:100,y:500}],
      confidence:.9,
      areaM2:16,
    }],
    doors:[],
    windows:[],
    labels:[{
      id:"label-1",
      text:"5.00 m",
      center:{x:300,y:80},
      confidence:.88,
      kind:"dimension",
      provenance:"ocr",
    }],
    dimensions:[{
      id:"dimension-1",
      sourceLabelId:"label-1",
      text:"5.00 m",
      center:{x:300,y:80},
      valueM:5,
      unit:"m",
      orientation:"horizontal",
      referenceWallId:"top",
      confidence:.88,
      reviewed:false,
      provenance:"ocr",
    }],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.75,needsCalibration:true,warnings:["مقياس الرسم يحتاج مراجعة"]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
}

describe("dimension geometry",()=>{
  it("corrects a source dimension without rewriting its evidence text",()=>{
    const source=plan();
    const next=correctDimensionValue(source,"dimension-1",4.2)!;
    expect(next.dimensions?.[0].valueM).toBe(4.2);
    expect(next.dimensions?.[0].text).toBe("5.00 m");
    expect(next.dimensions?.[0].reviewed).toBe(true);
    expect(next.dimensions?.[0].provenance).toBe("mixed");
    expect(source.dimensions?.[0].valueM).toBe(5);
  });

  it("calibrates the whole plan from a reviewed linked dimension without moving geometry",()=>{
    const source=plan();
    source.dimensions![0].reviewed=true;
    const beforeWall=JSON.stringify(source.walls[0]);
    const next=calibratePlanFromDimension(source,"dimension-1")!;
    expect(next.metersPerPixel).toBeCloseTo(.0125,6);
    expect(next.calibrationConfidence).toBe(1);
    expect(next.rooms[0].areaM2).toBe(25);
    expect(next.dimensions?.[0].reviewed).toBe(true);
    expect(next.quality.needsCalibration).toBe(false);
    expect(JSON.stringify(next.walls[0])).toBe(beforeWall);
  });

  it("refuses calibration before human review",()=>{\n    const source=plan();\n    expect(calibratePlanFromDimension(source,"dimension-1")).toBeNull();\n  });\n\n  it("refuses calibration when the dimension is not linked to a wall",()=>{
    const source=plan();
    source.dimensions![0].reviewed=true;
    source.dimensions![0].referenceWallId=null;
    expect(calibratePlanFromDimension(source,"dimension-1")).toBeNull();
  });
});
