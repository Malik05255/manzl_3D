import type { ApplyProposalRequest,EditProposalResponse,FloorPlanModel,SaveRevisionRequest,ValidationReport } from "@manzil/contracts";
import { createProjectAccess,hasProjectAccess } from "./access";
import { getProjectRow,persistDraft,persistPlan,projectView } from "./db";
import { cleanName,json } from "./http";
import type { Env,ProjectRow } from "./types";

async function analyzerProposals(env:Env,id:string,command:string,plan:FloorPlanModel):Promise<EditProposalResponse>{
  const upstream=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/edit/proposals`,{
    method:"POST",
    headers:{"content-type":"application/json","x-manzil-internal":env.INTERNAL_TOKEN},
    body:JSON.stringify({project_id:id,command,plan})
  });
  if(!upstream.ok){
    const detail=await upstream.text().catch(()=>"");
    throw new Error(detail||"تعذر على H Engineer تحليل التعديل");
  }
  return upstream.json<EditProposalResponse>();
}

async function analyzerResizeProposals(env:Env,id:string,roomId:string,widthM:number,heightM:number,plan:FloorPlanModel):Promise<EditProposalResponse>{
  const upstream=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/edit/resize-proposals`,{
    method:"POST",
    headers:{"content-type":"application/json","x-manzil-internal":env.INTERNAL_TOKEN},
    body:JSON.stringify({project_id:id,room_id:roomId,width_m:widthM,height_m:heightM,plan})
  });
  if(!upstream.ok){
    const detail=await upstream.text().catch(()=>"");
    throw new Error(detail||"تعذر إنشاء المعاينة الهندسية");
  }
  return upstream.json<EditProposalResponse>();
}

async function analyzerValidation(env:Env,id:string,plan:FloorPlanModel):Promise<ValidationReport>{
  const upstream=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/validate`,{
    method:"POST",
    headers:{"content-type":"application/json","x-manzil-internal":env.INTERNAL_TOKEN},
    body:JSON.stringify({project_id:id,plan})
  });
  if(!upstream.ok){
    const detail=await upstream.text().catch(()=>"");
    throw new Error(detail||"تعذر فحص المخطط");
  }
  return upstream.json<ValidationReport>();
}

async function protectedRow(request:Request,env:Env,id:string):Promise<ProjectRow|Response>{
  const row=await getProjectRow(env,id);
  if(!row) return json({error:"المشروع غير موجود"},404);
  if(!(await hasProjectAccess(request,row))) return json({error:"ليس لديك صلاحية الوصول إلى هذا المشروع"},401);
  return row;
}

async function currentPlan(env:Env,row:ProjectRow):Promise<FloorPlanModel|null>{
  if(!row.plan_key) return null;
  const object=await env.ASSETS.get(row.plan_key);
  return object?object.json<FloorPlanModel>():null;
}

export async function route(request:Request,env:Env):Promise<Response>{
  const url=new URL(request.url);
  const path=url.pathname;

  if(request.method==="OPTIONS") return new Response(null,{status:204});
  if(path==="/health") return json({ok:true});
  if(path==="/v1/version") return json({version:env.APP_VERSION??"0.1.0"});

  if(path==="/v1/projects"&&request.method==="POST"){
    const body:{name?:string}=await request.json<{name?:string}>().catch(()=>({}));
    const id=crypto.randomUUID();
    const now=new Date().toISOString();
    const name=cleanName(body.name??"مخطط جديد");
    const access=await createProjectAccess();
    await env.DB.prepare("INSERT INTO projects(id,name,status,phase,progress,access_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)")
      .bind(id,name,"created","created",0,access.hash,now,now).run();
    const row=await getProjectRow(env,id);
    const view=await projectView(env,row!,false);
    return json({...view,accessToken:access.token},201);
  }

  const source=path.match(/^\/v1\/projects\/([^/]+)\/source$/);
  if(source&&request.method==="PUT"){
    const id=source[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;

    const mime=request.headers.get("content-type")?.split(";")[0]??"";
    const allowed=new Set(["application/pdf","image/png","image/jpeg","image/webp"]);
    if(!allowed.has(mime)) return json({error:"النوع المدعوم PDF أو PNG أو JPG أو WEBP فقط"},415);

    const declaredLength=Number(request.headers.get("content-length")??0);
    const maxSize=50*1024*1024;
    if(declaredLength>maxSize) return json({error:"الحد الأقصى للملف 50MB"},413);
    if(!request.body) return json({error:"الملف فارغ"},400);

    const fileName=cleanName(url.searchParams.get("filename")??"source");
    const key=`projects/${id}/source/${fileName}`;
    const stored=await env.ASSETS.put(key,request.body,{httpMetadata:{contentType:mime}});
    if(stored.size>maxSize){
      await env.ASSETS.delete(key);
      return json({error:"الحد الأقصى للملف 50MB"},413);
    }

    const now=new Date().toISOString();
    await env.DB.prepare("UPDATE projects SET source_key=?, status='queued', phase='upload', progress=10, message=?, error=NULL, updated_at=? WHERE id=?")
      .bind(key,"اكتمل الرفع، بانتظار محرك التحليل",now,id).run();
    await env.ANALYZE_QUEUE.send({projectId:id,sourceKey:key,fileName,mimeType:mime});
    return json({ok:true},202);
  }

  const projectMatch=path.match(/^\/v1\/projects\/([^/]+)$/);
  if(projectMatch&&request.method==="GET"){
    const secured=await protectedRow(request,env,projectMatch[1]);
    if(secured instanceof Response) return secured;
    return json(await projectView(env,secured,true));
  }

  const previewMatch=path.match(/^\/v1\/projects\/([^/]+)\/preview$/);
  if(previewMatch&&request.method==="GET"){
    const secured=await protectedRow(request,env,previewMatch[1]);
    if(secured instanceof Response) return secured;
    if(!secured.preview_key) return json({error:"المعاينة غير متوفرة"},404);
    const object=await env.ASSETS.get(secured.preview_key);
    if(!object) return json({error:"المعاينة غير متوفرة"},404);
    const headers=new Headers();
    object.writeHttpMetadata(headers);
    headers.set("cache-control","private, max-age=300");
    headers.set("content-length",String(object.size));
    return new Response(object.body,{headers});
  }

  const draftMatch=path.match(/^\/v1\/projects\/([^/]+)\/draft$/);
  if(draftMatch&&request.method==="PUT"){
    const id=draftMatch[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const body=await request.json<{plan?:FloorPlanModel}>();
    if(!body.plan||body.plan.id!==id||body.plan.schemaVersion!==1) return json({error:"صيغة المسودة غير صالحة"},400);
    await persistDraft(env,id,body.plan);
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,false));
  }

  const revision=path.match(/^\/v1\/projects\/([^/]+)\/revisions$/);
  if(revision&&request.method==="GET"){
    const id=revision[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const result=await env.DB.prepare("SELECT revision, summary, created_at FROM revisions WHERE project_id=? ORDER BY revision DESC LIMIT 50")
      .bind(id).all<{revision:number;summary:string;created_at:string}>();
    return json({items:(result.results??[]).map(item=>({
      revision:item.revision,
      summary:item.summary,
      createdAt:item.created_at
    }))});
  }
  if(revision&&request.method==="POST"){
    const id=revision[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const body=await request.json<SaveRevisionRequest>();
    if(!body.plan||body.plan.schemaVersion!==1||body.plan.id!==id) return json({error:"صيغة المخطط غير صالحة"},400);
    await persistPlan(env,id,body.plan,cleanName(body.summary||"تعديل يدوي"));
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  const restoreRevision=path.match(/^\/v1\/projects\/([^/]+)\/revisions\/(\d+)\/restore$/);
  if(restoreRevision&&request.method==="POST"){
    const id=restoreRevision[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const revisionNumber=Number(restoreRevision[2]);
    if(!Number.isInteger(revisionNumber)||revisionNumber<1) return json({error:"رقم النسخة غير صالح"},400);
    const item=await env.DB.prepare("SELECT plan_key FROM revisions WHERE project_id=? AND revision=?")
      .bind(id,revisionNumber).first<{plan_key:string}>();
    if(!item?.plan_key) return json({error:"النسخة غير موجودة"},404);
    const object=await env.ASSETS.get(item.plan_key);
    if(!object) return json({error:"تعذر تحميل النسخة"},500);
    const plan=await object.json<FloorPlanModel>();
    if(plan.id!==id||plan.schemaVersion!==1) return json({error:"النسخة المخزنة غير صالحة"},500);
    await persistPlan(env,id,plan,`استعادة النسخة ${revisionNumber}`);
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  const validateMatch=path.match(/^\/v1\/projects\/([^/]+)\/validate$/);
  if(validateMatch&&request.method==="POST"){
    const id=validateMatch[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const body:{plan?:FloorPlanModel}=await request.json<{plan?:FloorPlanModel}>().catch(()=>({}));
    const stored=await currentPlan(env,secured);
    const plan=body.plan??stored;
    if(!plan) return json({error:"المخطط غير جاهز للفحص"},409);
    if(plan.id!==id||plan.schemaVersion!==1) return json({error:"صيغة المخطط غير صالحة للفحص"},400);
    try{return json(await analyzerValidation(env,id,plan));}
    catch(error){return json({error:error instanceof Error?error.message:"تعذر فحص المخطط"},502);}
  }

  const preciseResize=path.match(/^\/v1\/projects\/([^/]+)\/geometry\/resize-proposals$/);
  if(preciseResize&&request.method==="POST"){
    const id=preciseResize[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const plan=await currentPlan(env,secured);
    if(!plan) return json({error:"المخطط غير جاهز للتحرير"},409);
    const body=await request.json<{roomId?:string;widthM?:number;heightM?:number}>();
    const roomId=(body.roomId??"").trim();
    const widthM=Number(body.widthM);
    const heightM=Number(body.heightM);
    if(!roomId||!Number.isFinite(widthM)||!Number.isFinite(heightM)||widthM<=0||heightM<=0){
      return json({error:"بيانات المقاس غير مكتملة"},400);
    }
    if(!plan.rooms.some(room=>room.id===roomId)) return json({error:"الغرفة المحددة غير موجودة"},404);
    try{return json(await analyzerResizeProposals(env,id,roomId,widthM,heightM,plan));}
    catch(error){return json({error:error instanceof Error?error.message:"تعذر إنشاء المعاينة الهندسية"},502);}
  }

  const proposals=path.match(/^\/v1\/projects\/([^/]+)\/ai\/proposals$/);
  if(proposals&&request.method==="POST"){
    const id=proposals[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const plan=await currentPlan(env,secured);
    if(!plan) return json({error:"المخطط غير جاهز للتحرير"},409);
    const body=await request.json<{command?:string}>();
    const command=(body.command??"").trim();
    if(!command) return json({error:"اكتب التعديل المطلوب"},400);
    try{return json(await analyzerProposals(env,id,command,plan));}
    catch(error){return json({error:error instanceof Error?error.message:"تعذر تحليل الطلب"},502);}
  }

  const apply=path.match(/^\/v1\/projects\/([^/]+)\/ai\/apply$/);
  if(apply&&request.method==="POST"){
    const id=apply[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const body=await request.json<ApplyProposalRequest>();
    const command=(body.command??"").trim();
    const selectedId=body.proposal?.id;
    if(!command||!selectedId) return json({error:"طلب التعديل غير مكتمل"},400);

    const plan=await currentPlan(env,secured);
    if(!plan) return json({error:"المخطط غير جاهز للتحرير"},409);

    let fresh:EditProposalResponse;
    try{fresh=await analyzerProposals(env,id,command,plan);}
    catch(error){return json({error:error instanceof Error?error.message:"تعذر التحقق من التعديل"},502);}

    const selected=fresh.proposals.find(proposal=>proposal.id===selectedId);
    if(!selected) return json({error:"المخطط تغير أو أن خيار التعديل لم يعد صالحًا. أعد المعاينة."},409);
    if(selected.previewPlan.id!==id||selected.previewPlan.schemaVersion!==1) return json({error:"نتيجة H Engineer غير صالحة"},502);

    await persistPlan(env,id,selected.previewPlan,`H Engineer: ${cleanName(command)}`);
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  return json({error:"not found"},404);
}
