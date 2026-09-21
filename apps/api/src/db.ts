import type { FloorPlanModel, ProjectView } from "@manzil/contracts";
import type { Env, ProjectRow } from "./types";

export async function getProjectRow(env:Env,id:string):Promise<ProjectRow|null>{
  return env.DB.prepare("SELECT * FROM projects WHERE id = ?").bind(id).first<ProjectRow>();
}

export async function projectView(env:Env,row:ProjectRow,includePlan=true):Promise<ProjectView>{
  let plan:FloorPlanModel|null=null;
  const activePlanKey=row.draft_key||row.plan_key;
  if(includePlan&&activePlanKey){
    const object=await env.ASSETS.get(activePlanKey);
    if(object) plan=await object.json<FloorPlanModel>();
  }
  return {
    id:row.id,name:row.name,status:row.status as ProjectView["status"],phase:row.phase as ProjectView["phase"],
    progress:row.progress,revision:row.revision,hasDraft:Boolean(row.draft_key),message:row.message,error:row.error,createdAt:row.created_at,updatedAt:row.updated_at,plan
  };
}

export async function setProgress(env:Env,id:string,status:string,phase:string,progress:number,message?:string|null,error?:string|null){
  const now=new Date().toISOString();
  await env.DB.prepare("UPDATE projects SET status=?, phase=?, progress=?, message=?, error=?, updated_at=? WHERE id=?")
    .bind(status,phase,Math.max(0,Math.min(100,Math.round(progress))),message??null,error??null,now,id).run();
}

export async function persistPlan(env:Env,id:string,plan:FloorPlanModel,summary:string,expectedRevision?:number){
  const row=await getProjectRow(env,id);
  if(!row) throw new Error("PROJECT_NOT_FOUND");
  if(expectedRevision!==undefined&&row.revision!==expectedRevision) throw new Error("STALE_REVISION");

  const baseRevision=row.revision;
  const revision=baseRevision+1;
  const revisionId=crypto.randomUUID();
  const key=`projects/${id}/revisions/${String(revision).padStart(5,"0")}-${revisionId}.json`;
  await env.ASSETS.put(key,JSON.stringify(plan),{httpMetadata:{contentType:"application/json"}});
  const now=new Date().toISOString();

  try{
    const results=await env.DB.batch([
      env.DB.prepare("UPDATE projects SET plan_key=?, draft_key=NULL, revision=?, status='ready', phase='ready', progress=100, message=?, error=NULL, updated_at=? WHERE id=? AND revision=?")
        .bind(key,revision,"المشروع جاهز للتعديل",now,id,baseRevision),
      env.DB.prepare("INSERT INTO revisions(id,project_id,revision,summary,plan_key,created_at) VALUES(?,?,?,?,?,?)")
        .bind(revisionId,id,revision,summary,key,now),
    ]);
    if((results[0]?.meta.changes??0)<1) throw new Error("STALE_REVISION");
  }catch(error){
    const current=await getProjectRow(env,id);
    if(current&&current.revision!==baseRevision) throw new Error("STALE_REVISION");
    throw error;
  }
  if(row.draft_key) await env.ASSETS.delete(row.draft_key).catch(()=>undefined);
}


export async function persistDraft(env:Env,id:string,plan:FloorPlanModel,expectedRevision:number){
  const row=await getProjectRow(env,id);
  if(!row) throw new Error("PROJECT_NOT_FOUND");
  if(row.revision!==expectedRevision) throw new Error("STALE_DRAFT");

  const key=`projects/${id}/draft/current-r${expectedRevision}.json`;
  await env.ASSETS.put(key,JSON.stringify(plan),{httpMetadata:{contentType:"application/json"}});
  const now=new Date().toISOString();
  const result=await env.DB.prepare("UPDATE projects SET draft_key=?, status='ready', phase='ready', progress=100, message=?, error=NULL, updated_at=? WHERE id=? AND revision=?")
    .bind(key,"تم حفظ المسودة سحابيًا",now,id,expectedRevision).run();
  if((result.meta.changes??0)<1) throw new Error("STALE_DRAFT");
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
