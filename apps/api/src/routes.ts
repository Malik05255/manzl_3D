import type { ApplyProposalRequest, EditProposalResponse, FloorPlanModel, SaveRevisionRequest } from "@manzil/contracts";
import { getProjectRow, persistPlan, projectView } from "./db";
import { cleanName, json } from "./http";
import type { Env } from "./types";

export async function route(request:Request,env:Env):Promise<Response>{
  const url=new URL(request.url);
  const path=url.pathname;

  if(request.method==="OPTIONS") return new Response(null,{status:204});
  if(path==="/health") return json({ok:true});
  if(path==="/v1/version") return json({version:env.APP_VERSION??"0.1.0"});

  if(path==="/v1/projects"&&request.method==="POST"){
    const body=await request.json<{name?:string}>().catch(()=>({}));
    const id=crypto.randomUUID();
    const now=new Date().toISOString();
    const name=cleanName(body.name??"مخطط جديد");
    await env.DB.prepare("INSERT INTO projects(id,name,status,phase,progress,created_at,updated_at) VALUES(?,?,?,?,?,?,?)")
      .bind(id,name,"created","created",0,now,now).run();
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,false),201);
  }

  const source=path.match(/^\/v1\/projects\/([^/]+)\/source$/);
  if(source&&request.method==="PUT"){
    const id=source[1];
    const row=await getProjectRow(env,id);
    if(!row) return json({error:"المشروع غير موجود"},404);
    const mime=request.headers.get("content-type")?.split(";")[0]??"";
    const allowed=new Set(["application/pdf","image/png","image/jpeg","image/webp"]);
    if(!allowed.has(mime)) return json({error:"النوع المدعوم PDF أو PNG أو JPG أو WEBP فقط"},415);
    const length=Number(request.headers.get("content-length")??0);
    if(length>50*1024*1024) return json({error:"الحد الأقصى للملف 50MB"},413);
    if(!request.body) return json({error:"الملف فارغ"},400);

    const fileName=cleanName(url.searchParams.get("filename")??"source");
    const key=`projects/${id}/source/${fileName}`;
    await env.ASSETS.put(key,request.body,{httpMetadata:{contentType:mime}});
    const now=new Date().toISOString();
    await env.DB.prepare("UPDATE projects SET source_key=?, status='queued', phase='upload', progress=10, message=?, updated_at=? WHERE id=?")
      .bind(key,"اكتمل الرفع، بانتظار محرك التحليل",now,id).run();
    await env.ANALYZE_QUEUE.send({projectId:id,sourceKey:key,fileName,mimeType:mime});
    return json({ok:true},202);
  }

  const projectMatch=path.match(/^\/v1\/projects\/([^/]+)$/);
  if(projectMatch&&request.method==="GET"){
    const row=await getProjectRow(env,projectMatch[1]);
    if(!row) return json({error:"المشروع غير موجود"},404);
    return json(await projectView(env,row,true));
  }

  const revision=path.match(/^\/v1\/projects\/([^/]+)\/revisions$/);
  if(revision&&request.method==="POST"){
    const id=revision[1];
    const body=await request.json<SaveRevisionRequest>();
    if(!body.plan||body.plan.schemaVersion!==1||body.plan.id!==id) return json({error:"صيغة المخطط غير صالحة"},400);
    await persistPlan(env,id,body.plan,cleanName(body.summary||"تعديل يدوي"));
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  const proposals=path.match(/^\/v1\/projects\/([^/]+)\/ai\/proposals$/);
  if(proposals&&request.method==="POST"){
    const id=proposals[1];
    const row=await getProjectRow(env,id);
    if(!row?.plan_key) return json({error:"المخطط غير جاهز للتحرير"},409);
    const body=await request.json<{command?:string}>();
    const command=(body.command??"").trim();
    if(!command) return json({error:"اكتب التعديل المطلوب"},400);
    const object=await env.ASSETS.get(row.plan_key);
    if(!object) return json({error:"تعذر تحميل نموذج المخطط"},500);
    const plan=await object.json<FloorPlanModel>();
    const upstream=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/edit/proposals`,{
      method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify({project_id:id,command,plan})
    });
    if(!upstream.ok) return json({error:"تعذر على H Engineer تحليل التعديل"},502);
    return json(await upstream.json<EditProposalResponse>());
  }

  const apply=path.match(/^\/v1\/projects\/([^/]+)\/ai\/apply$/);
  if(apply&&request.method==="POST"){
    const id=apply[1];
    const body=await request.json<ApplyProposalRequest>();
    const plan=body.proposal?.previewPlan;
    if(!plan||plan.schemaVersion!==1||plan.id!==id) return json({error:"المعاينة غير صالحة"},400);
    await persistPlan(env,id,plan,`H Engineer: ${cleanName(body.command||body.proposal.title)}`);
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  return json({error:"not found"},404);
}
