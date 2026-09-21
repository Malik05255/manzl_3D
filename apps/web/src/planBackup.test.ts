import { describe,expect,it } from "vitest";
import type { FloorPlanModel } from "@manzil/contracts";
import { clonePlanForProject,parsePlanBackup } from "./planBackup";

function plan():FloorPlanModel{
  return {
    schemaVersion:1,id:"old",widthPx:800,heightPx:600,metersPerPixel:.01,calibrationConfidence:.9,
    walls:[{id:"wall-1",a:{x:0,y:0},b:{x:800,y:0},thicknessPx:8,confidence:.9}],
    rooms:[{id:"room-1",name:"غرفة",polygon:[{x:0,y:0},{x:400,y:0},{x:400,y:300},{x:0,y:300}],confidence:.9,areaM2:12}],
    doors:[],windows:[],labels:[],
    quality:{overall:.9,walls:.9,rooms:.9,text:.8,dimensions:.9,needsCalibration:false,warnings:[]},
    source:{fileName:"plan.png",mimeType:"image/png",page:1},
  };
}

describe("plan backup",()=>{
  it("round trips a valid canonical plan",()=>{
    const parsed=parsePlanBackup(JSON.stringify(plan()));
    expect(parsed.id).toBe("old");
    expect(parsed.rooms[0].name).toBe("غرفة");
  });

  it("rejects malformed geometry",()=>{
    const broken={...plan(),walls:[{id:"wall-1",a:{x:"bad",y:0},b:{x:5,y:5},thicknessPx:4,confidence:.9}]};
    expect(()=>parsePlanBackup(JSON.stringify(broken))).toThrow("BACKUP_WALLS");
  });

  it("round trips canonical dimension evidence",()=>{
    const source={...plan(),labels:[{
      id:"label-1",text:"4.20 m",center:{x:200,y:30},confidence:.92,kind:"dimension" as const,provenance:"ocr" as const,
    }],dimensions:[{
      id:"dimension-1",sourceLabelId:"label-1",text:"4.20 m",center:{x:200,y:30},
      valueM:4.2,unit:"m" as const,orientation:"horizontal" as const,referenceWallId:"wall-1",
      confidence:.92,reviewed:false,provenance:"ocr" as const,
    }]};
    const parsed=parsePlanBackup(JSON.stringify(source));
    expect(parsed.dimensions?.[0].valueM).toBe(4.2);
    expect(parsed.dimensions?.[0].referenceWallId).toBe("wall-1");
  });

  it("rejects orphaned dimension source label references",()=>{
    const source={...plan(),dimensions:[{
      id:"dimension-1",sourceLabelId:"missing-label",text:"4.20 m",center:{x:200,y:30},
      valueM:4.2,unit:"m" as const,orientation:"horizontal" as const,referenceWallId:"wall-1",
      confidence:.92,
    }]};
    expect(()=>parsePlanBackup(JSON.stringify(source))).toThrow("BACKUP_DIMENSION_LABEL");
  });

  it("rejects orphaned dimension wall references",()=>{
    const source={...plan(),dimensions:[{
      id:"dimension-1",text:"4.20 m",center:{x:200,y:30},
      valueM:4.2,unit:"m" as const,orientation:"horizontal" as const,referenceWallId:"missing-wall",
      confidence:.92,
    }]};
    expect(()=>parsePlanBackup(JSON.stringify(source))).toThrow("BACKUP_DIMENSION_WALL");
  });

  it("clones a backup under the new cloud project id",()=>{
    const original=plan();
    const cloned=clonePlanForProject(original,"new-project");
    expect(cloned.id).toBe("new-project");
    expect(cloned.rooms).not.toBe(original.rooms);
    expect(cloned.rooms[0].polygon).not.toBe(original.rooms[0].polygon);
  });

  it("rejects orphaned opening references through the shared contract validator",()=>{
    const broken={...plan(),doors:[{id:"door-1",kind:"door" as const,wallId:"missing-wall",a:{x:10,y:10},b:{x:20,y:10},confidence:.9}]};
    expect(()=>parsePlanBackup(JSON.stringify(broken))).toThrow("BACKUP_OPENING_WALL");
  });
});


it("deep clones dimension symbol and analysis metadata for a new project",()=>{
  const original:FloorPlanModel={
    ...plan(),
    labels:[{id:"label-1",text:"4.20 m",center:{x:200,y:30},confidence:.9,kind:"dimension",provenance:"ocr"}],
    dimensions:[{
      id:"dim-1",sourceLabelId:"label-1",text:"4.20 m",center:{x:200,y:30},
      valueM:4.2,unit:"m",orientation:"horizontal",referenceWallId:"wall-1",
      spanA:{x:100,y:25},spanB:{x:520,y:25},confidence:.9,provenance:"ocr",
    }],
    symbols:[{
      id:"symbol-1",kind:"toilet",a:{x:500,y:300},b:{x:560,y:370},confidence:.9,provenance:"ai",
    }],
    analysis:{
      pipelineVersion:"test",analyzedAt:"2026-09-22T00:00:00Z",
      sourceSha256:"a".repeat(64),engines:["opencv","symbol-detector"],
    },
  };
  const cloned=clonePlanForProject(original,"new-project");

  expect(cloned.id).toBe("new-project");
  expect(cloned.dimensions).not.toBe(original.dimensions);
  expect(cloned.dimensions?.[0].center).not.toBe(original.dimensions?.[0].center);
  expect(cloned.dimensions?.[0].spanA).not.toBe(original.dimensions?.[0].spanA);
  expect(cloned.symbols).not.toBe(original.symbols);
  expect(cloned.symbols?.[0].a).not.toBe(original.symbols?.[0].a);
  expect(cloned.analysis).not.toBe(original.analysis);
  expect(cloned.analysis?.engines).not.toBe(original.analysis?.engines);

  cloned.symbols![0].a.x=999;
  cloned.dimensions![0].center.x=999;
  cloned.analysis!.engines.push("changed");
  expect(original.symbols![0].a.x).toBe(500);
  expect(original.dimensions![0].center.x).toBe(200);
  expect(original.analysis!.engines).toEqual(["opencv","symbol-detector"]);
});
