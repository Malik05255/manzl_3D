import type { FloorPlanModel, ProjectFloorView, ProjectView } from "@manzil/contracts";
import type { Env, FloorRow, ProjectRow } from "./types";

export async function getProjectRow(env:Env,id:string):Promise<ProjectRow|null>{
  return env.DB.prepare("SELECT * FROM projects WHERE id = ?").bind(id).first<ProjectRow>();
}

export function floorIdForPage(projectId:string,sourcePage:number){
  return `${projectId}:page:${sourcePage}`;
}

export async function getProjectFloors(env:Env,id:string):Promise<ProjectFloorView[]>{
  const result=await env.DB.prepare("SELECT * FROM project_floors WHERE project_id=? ORDER BY source_page ASC")
    .bind(id).all<FloorRow>();
  return (result.results??[]).map(item=>({
    id:item.id,
    sourcePage:item.source_page,
    name:item.name,
    latestRevision:item.latest_revision,
    previewAvailable:Boolean(item.preview_key),
    elevationM:item.elevation_m,
    heightM:item.height_m,
    updatedAt:item.updated_at,
  }));
}

export async function projectView(env:Env,row:ProjectRow,includePlan=true):Promise<ProjectView>{
  let plan:FloorPlanModel|null=null;
  const activePlanKey=row.draft_key||row.plan_key;
  if(includePlan&&activePlanKey){
    const object=await env.ASSETS.get(activePlanKey);
    if(object) plan=await object.json<FloorPlanModel>();
  }
  const floors=await getProjectFloors(env,row.id);
  return {
    id:row.id,name:row.name,status:row.status as ProjectView["status"],phase:row.phase as ProjectView["phase"],
    progress:row.progress,revision:row.revision,hasDraft:Boolean(row.draft_key),activeFloorId:row.active_floor_id,
    floors,message:row.message,error:row.error,createdAt:row.created_at,updatedAt:row.updated_at,plan
  };
}

export async function setProgress(env:Env,id:string,status:string,phase:string,progress:number,message?:string|null,error?:string|null){
  const now=new Date().toISOString();
  await env.DB.prepare("UPDATE projects SET status=?, phase=?, progress=?, message=?, error=?, updated_at=? WHERE id=?")
    .bind(status,phase,Math.max(0,Math.min(100,Math.round(progress))),message??null,error??null,now,id).run();
}

export async function setAnalysisProgress(env:Env,id:string,sourceKey:string,expectedRevision:number,status:string,phase:string,progress:number,message?:string|null,error?:string|null){
  const now=new Date().toISOString();
  const result=await env.DB.prepare("UPDATE projects SET status=?, phase=?, progress=?, message=?, error=?, updated_at=? WHERE id=? AND source_key=? AND revision=?")
    .bind(status,phase,Math.max(0,Math.min(100,Math.round(progress))),message??null,error??null,now,id,sourceKey,expectedRevision).run();
  return (result.meta.changes??0)>0;
}

export async function persistPlan(env:Env,id:string,plan:FloorPlanModel,summary:string,expectedRevision?:number,expectedSourceKey?:string,previewKeyOverride?:string|null){
  const row=await getProjectRow(env,id);
  if(!row) throw new Error("PROJECT_NOT_FOUND");
  if(expectedRevision!==undefined&&row.revision!==expectedRevision) throw new Error("STALE_REVISION");
  if(expectedSourceKey!==undefined&&row.source_key!==expectedSourceKey) throw new Error("STALE_SOURCE");

  const baseRevision=row.revision;
  const revision=baseRevision+1;
  const revisionId=crypto.randomUUID();
  const floorId=floorIdForPage(id,plan.source.page);
  const effectivePreviewKey=previewKeyOverride===undefined?row.preview_key:previewKeyOverride;
  const key=`projects/${id}/revisions/${String(revision).padStart(5,"0")}-${revisionId}.json`;
  await env.ASSETS.put(key,JSON.stringify(plan),{httpMetadata:{contentType:"application/json"}});
  const now=new Date().toISOString();
  const sourceGuard=expectedSourceKey!==undefined?" AND source_key=?":"";
  const projectGuardArgs=expectedSourceKey!==undefined?[id,baseRevision,expectedSourceKey]:[id,baseRevision];

  try{
    const results=await env.DB.batch([
      env.DB.prepare(`INSERT INTO revisions(id,project_id,revision,summary,plan_key,source_page,preview_key,floor_id,created_at)
        SELECT ?,?,?,?,?,?,?,?,?
        WHERE EXISTS (SELECT 1 FROM projects WHERE id=? AND revision=?${sourceGuard})`)
        .bind(revisionId,id,revision,summary,key,plan.source.page,effectivePreviewKey,floorId,now,...projectGuardArgs),
      env.DB.prepare(`UPDATE projects SET plan_key=?, preview_key=?, active_floor_id=?, draft_key=NULL, revision=?, status='ready', phase='ready', progress=100, message=?, error=NULL, updated_at=? WHERE id=? AND revision=?${sourceGuard}`)
        .bind(key,effectivePreviewKey,floorId,revision,"المشروع جاهز للتعديل",now,...projectGuardArgs),
      env.DB.prepare(`INSERT INTO project_floors(id,project_id,source_page,name,plan_key,preview_key,latest_revision,created_at,updated_at)
        SELECT ?,?,?,?,?,?,?,?,?
        WHERE EXISTS (SELECT 1 FROM projects WHERE id=? AND revision=? AND active_floor_id=? AND plan_key=?)
        ON CONFLICT(project_id,source_page) DO UPDATE SET
          plan_key=excluded.plan_key,
          preview_key=excluded.preview_key,
          latest_revision=excluded.latest_revision,
          updated_at=excluded.updated_at`)
        .bind(floorId,id,plan.source.page,`الصفحة ${plan.source.page}`,key,effectivePreviewKey,revision,now,now,id,revision,floorId,key),
    ]);
    if((results[0]?.meta.changes??0)<1||(results[1]?.meta.changes??0)<1||(results[2]?.meta.changes??0)<1){
      throw new Error(expectedSourceKey!==undefined?"STALE_SOURCE_OR_REVISION":"STALE_REVISION");
    }
  }catch(error){
    await env.ASSETS.delete(key).catch(()=>undefined);
    const current=await getProjectRow(env,id);
    if(expectedSourceKey!==undefined&&current?.source_key!==expectedSourceKey) throw new Error("STALE_SOURCE");
    if(current&&current.revision!==baseRevision) throw new Error("STALE_REVISION");
    throw error;
  }
  if(row.draft_key) await env.ASSETS.delete(row.draft_key).catch(()=>undefined);
}

export async function persistDraft(env:Env,id:string,plan:FloorPlanModel,expectedRevision:number){
  const row=await getProjectRow(env,id);
  if(!row) throw new Error("PROJECT_NOT_FOUND");
  if(row.revision!==expectedRevision) throw new Error("STALE_DRAFT");
  if(["queued","analyzing"].includes(row.status)) throw new Error("ANALYSIS_IN_PROGRESS");
  const expectedFloorId=floorIdForPage(id,plan.source.page);
  if(row.active_floor_id&&row.active_floor_id!==expectedFloorId) throw new Error("STALE_FLOOR");

  const key=`projects/${id}/draft/current-r${expectedRevision}.json`;
  await env.ASSETS.put(key,JSON.stringify(plan),{httpMetadata:{contentType:"application/json"}});
  const now=new Date().toISOString();
  const result=await env.DB.prepare("UPDATE projects SET draft_key=?, status='ready', phase='ready', progress=100, message=?, error=NULL, updated_at=? WHERE id=? AND revision=? AND status NOT IN ('queued','analyzing')")
    .bind(key,"تم حفظ المسودة سحابيًا",now,id,expectedRevision).run();
  if((result.meta.changes??0)<1){
    await env.ASSETS.delete(key).catch(()=>undefined);
    const current=await getProjectRow(env,id);
    if(current&&["queued","analyzing"].includes(current.status)) throw new Error("ANALYSIS_IN_PROGRESS");
    throw new Error("STALE_DRAFT");
  }
}

export async function clearDraft(env:Env,id:string,expectedRevision:number){
  const row=await getProjectRow(env,id);
  if(!row) throw new Error("PROJECT_NOT_FOUND");
  if(row.revision!==expectedRevision) throw new Error("STALE_DRAFT");
  if(!row.draft_key) return;

  const key=row.draft_key;
  const now=new Date().toISOString();
  const result=await env.DB.prepare("UPDATE projects SET draft_key=NULL, message=?, updated_at=? WHERE id=? AND revision=?")
    .bind("المشروع جاهز للتعديل",now,id,expectedRevision).run();
  if((result.meta.changes??0)<1) throw new Error("STALE_DRAFT");
  await env.ASSETS.delete(key).catch(()=>undefined);
}
