import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { addOpeningToWall,changeOpeningKind,openingMetrics,positionOpening,removeOpening,resizeOpening } from "./openingGeometry";

function plan():FloorPlanModel{
  return {
    schemaVersion:1,id:"p",widthPx:1000,heightPx:500,metersPerPixel:.01,calibrationConfidence:1,
    walls:[{id:"w",a:{x:100,y:100},b:{x:900,y:100},thicknessPx:10,confidence:.9}],
    rooms:[],
    doors:[{id:"d",kind:"door",wallId:"w",a:{x:200,y:100},b:{x:290,y:100},confidence:.9}],
    windows:[],labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.9,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"x.png",mimeType:"image/png",page:1},
  };
}

describe("opening geometry",()=>{
  it("resizes an opening on its wall without detaching it",()=>{
    const next=resizeOpening(plan(),"d",1.2)!;
    const metrics=openingMetrics(next,"d")!;
    expect(metrics.widthM).toBeCloseTo(1.2,3);
    expect(metrics.opening.a.y).toBe(100);
    expect(metrics.opening.b.y).toBe(100);
  });

  it("moves an opening along the wall and clamps it inside the wall",()=>{
    const next=positionOpening(plan(),"d",98)!;
    const metrics=openingMetrics(next,"d")!;
    expect(metrics.opening.b.x).toBeLessThan(900);
    expect(metrics.opening.a.x).toBeGreaterThan(100);
  });

  it("adds a window into free wall space without overlapping the existing door",()=>{
    const next=addOpeningToWall(plan(),"w","window")!;
    expect(next.windows).toHaveLength(1);
    const window=next.windows[0];
    expect(window.wallId).toBe("w");
    expect(window.a.x).toBeGreaterThanOrEqual(300);
  });

  it("can correct opening type and remove it",()=>{
    const changed=changeOpeningKind(plan(),"d","window")!;
    expect(changed.doors).toHaveLength(0);
    expect(changed.windows[0].kind).toBe("window");
    const removed=removeOpening(changed,"d");
    expect(removed.windows).toHaveLength(0);
  });
});
