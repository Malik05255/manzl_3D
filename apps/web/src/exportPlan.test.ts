import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { planToSvg,safeFileName } from "./exportPlan";

function samplePlan():FloorPlanModel{
  return {
    schemaVersion:1,
    id:"p1",
    widthPx:600,
    heightPx:400,
    metersPerPixel:0.01,
    walls:[{id:"w1",a:{x:50,y:50},b:{x:550,y:50},thicknessPx:10,confidence:.9}],
    rooms:[{id:"r1",name:"غرفة <رئيسية>",polygon:[{x:50,y:50},{x:350,y:50},{x:350,y:250},{x:50,y:250}],confidence:.9,areaM2:6}],
    doors:[{id:"d1",kind:"door",wallId:"w1",a:{x:120,y:50},b:{x:210,y:50},confidence:.9}],
    windows:[],
    labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"plan.png",mimeType:"image/png",page:1},
  };
}

describe("plan export",()=>{
  it("escapes room names and preserves vector geometry",()=>{
    const svg=planToSvg(samplePlan());
    expect(svg).toContain("غرفة &lt;رئيسية&gt;");
    expect(svg).toContain('stroke-width="10"');
    expect(svg).toContain("3.00 × 2.00 م");
    expect(svg).not.toContain("غرفة <رئيسية>");
  });

  it("sanitizes project names for downloads",()=>{
    expect(safeFileName(' منزل / H : اختبار ')).toBe("منزل - H - اختبار");
    expect(safeFileName("   ")).toBe("manzil-h-plan");
  });
});
