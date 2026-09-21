import { floorPlanValidationError } from "@manzil/contracts";
import type { ApplyProposalRequest,EditProposalResponse,FloorPlanModel,SaveRevisionRequest,ValidationReport } from "@manzil/contracts";
import { createProjectAccess,hasProjectAccess } from "./access";
import { clearDraft,getProjectRow,persistDraft,persistPlan,projectView } from "./db";
import { cleanName,json } from "./http";
import type { Env,ProjectRow } from "./types";

async function analyzerProposals(env:Env,id:string,command:string,plan:FloorPlanModel,targetRoomId?:string|null,targetWallId?:string|null,targetOpeningId?:string|null):Promise<EditProposalResponse>{
  const upstream=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/edit/proposals`,{
    method:"POST",
    headers:{"content-type":"application/json","x-manzil-internal":env.INTERNAL_TOKEN},
    body:JSON.stringify({project_id:id,command,plan,target_room_id:targetRoomId??null,target_wall_id:targetWallId??null,target_opening_id:targetOpeningId??null})
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

function criticalFindingKey(item:ValidationReport["findings"][number]){
  const rooms=[...item.roomIds].sort().join(",");
  const walls=[...(item.wallIds??[])].sort().join(",");
  const openings=[...(item.openingIds??[])].sort().join(",");
  return `${item.code}:rooms=${rooms}:walls=${walls}:openings=${openings}`;
}

async function validateTransition(env:Env,id:string,before:FloorPlanModel|null,after:FloorPlanModel){
  const afterReport=await analyzerValidation(env,id,after);
  const afterCritical=afterReport.findings.filter(item=>item.severity==="critical");
  if(!afterCritical.length)return {report:afterReport,introduced:[] as ValidationReport["findings"]};

  let beforeKeys=new Set<string>();
  if(before){
    const beforeReport=await analyzerValidation(env,id,before);
    beforeKeys=new Set(beforeReport.findings.filter(item=>item.severity==="critical").map(criticalFindingKey));
  }
  const introduced=afterCritical.filter(item=>!beforeKeys.has(criticalFindingKey(item)));
  return {report:afterReport,introduced};
}

async function committedPlan(env:Env,row:ProjectRow):Promise<FloorPlanModel|null>{
  if(!row.plan_key)return null;
  const object=await env.ASSETS.get(row.plan_key);
  return object?object.json<FloorPlanModel>():null;
}

async function protectedRow(request:Request,env:Env,id:string):Promise<ProjectRow|Response>{
  const row=await getProjectRow(env,id);
  if(!row) return json({error:"المشروع غير موجود"},404);
  if(!(await hasProjectAccess(request,row))) return json({error:"ليس لديك صلاحية الوصول إلى هذا المشروع"},401);
  return row;
}

async function currentPlan(env:Env,row:ProjectRow):Promise<FloorPlanModel|null>{
  const key=row.draft_key||row.plan_key;
  if(!key) return null;
  const object=await env.ASSETS.get(key);
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
    if(secured.revision>0) return json({error:"هذا المشروع يحتوي على نسخة محفوظة. أنشئ مشروعًا جديدًا لرفع مخطط مختلف."},409);

    const mime=request.headers.get("content-type")?.split(";")[0]??"";
    const allowed=new Set(["application/pdf","image/png","image/jpeg","image/webp"]);
    if(!allowed.has(mime)) return json({error:"النوع المدعوم PDF أو PNG أو JPG أو WEBP فقط"},415);

    const declaredLength=Number(request.headers.get("content-length")??0);
    const maxSize=50*1024*1024;
    if(declaredLength>maxSize) return json({error:"الحد الأقصى للملف 50MB"},413);
    if(!request.body) return json({error:"الملف فارغ"},400);

    const fileName=cleanName(url.searchParams.get("filename")??"source");
    const key=`projects/${id}/source/${crypto.randomUUID()}-${fileName}`;
    const stored=await env.ASSETS.put(key,request.body,{httpMetadata:{contentType:mime}});
    if(stored.size>maxSize){
      await env.ASSETS.delete(key);
      return json({error:"الحد الأقصى للملف 50MB"},413);
    }

    const previousSourceKey=secured.source_key;
    const previousPreviewKey=secured.preview_key;
    const now=new Date().toISOString();
    const sourceUpdate=await env.DB.prepare("UPDATE projects SET source_key=?, preview_key=NULL, status='queued', phase='upload', progress=10, message=?, error=NULL, updated_at=? WHERE id=? AND revision=? AND (source_key IS NULL OR source_key=?)")
      .bind(key,"اكتمل الرفع، بانتظار محرك التحليل",now,id,secured.revision,previousSourceKey).run();
    if((sourceUpdate.meta.changes??0)<1){
      await env.ASSETS.delete(key).catch(()=>undefined);
      return json({error:"تغير المشروع أثناء رفع المصدر. أعد المحاولة."},409);
    }
    if(previousSourceKey&&previousSourceKey!==key) await env.ASSETS.delete(previousSourceKey).catch(()=>undefined);
    if(previousPreviewKey) await env.ASSETS.delete(previousPreviewKey).catch(()=>undefined);
    await env.ANALYZE_QUEUE.send({projectId:id,sourceKey:key,fileName,mimeType:mime,expectedRevision:secured.revision});
    return json({ok:true},202);
  }

  const retryAnalysis=path.match(/^\/v1\/projects\/([^/]+)\/retry-analysis$/);
  if(retryAnalysis&&request.method==="POST"){
    const id=retryAnalysis[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    if(!secured.source_key) return json({error:"لا يوجد ملف مصدر لإعادة التحليل"},409);
    if(["queued","analyzing"].includes(secured.status)) return json({error:"التحليل جارٍ بالفعل"},409);

    const body: {sourcePage?:number|null}=await request.json<{sourcePage?:number|null}>().catch(()=>({}));
    const requestedPage=body.sourcePage==null?null:Number(body.sourcePage);
    if(requestedPage!==null&&(!Number.isInteger(requestedPage)||requestedPage<1||requestedPage>10000)){
      return json({error:"رقم صفحة PDF غير صالح"},400);
    }

    const source=await env.ASSETS.head(secured.source_key);
    if(!source) return json({error:"تعذر العثور على ملف المصدر"},404);
    const mimeType=source.httpMetadata?.contentType??"";
    if(!["application/pdf","image/png","image/jpeg","image/webp"].includes(mimeType)) return json({error:"نوع الملف المصدر غير مدعوم"},415);
    if(requestedPage!==null&&mimeType!=="application/pdf") return json({error:"اختيار الصفحة متاح لملفات PDF فقط"},400);

    if(requestedPage!==null){
      const existing=await currentPlan(env,secured);
      const pageCount=existing?.source.pageCount;
      if(pageCount&&requestedPage>pageCount) return json({error:`الملف يحتوي على ${pageCount} صفحة فقط`},400);
      if(existing?.source.page===requestedPage&&secured.status==="ready") return json({error:"هذه الصفحة هي الصفحة الحالية بالفعل"},409);
    }

    const fileName=secured.source_key.split("/").at(-1)??"source";
    const now=new Date().toISOString();
    const message=requestedPage===null?"تمت إعادة جدولة التحليل السحابي":`تمت جدولة تحليل الصفحة ${requestedPage}`;
    const scheduled=await env.DB.prepare("UPDATE projects SET status='queued', phase='upload', progress=10, message=?, error=NULL, updated_at=? WHERE id=? AND source_key=? AND revision=? AND status NOT IN ('queued','analyzing')")
      .bind(message,now,id,secured.source_key,secured.revision).run();
    if((scheduled.meta.changes??0)<1) return json({error:"تغير المشروع أو بدأ تحليل آخر قبل جدولة الطلب. حدّث المشروع وحاول مرة أخرى."},409);
    await env.ANALYZE_QUEUE.send({
      projectId:id,sourceKey:secured.source_key,fileName,mimeType,
      sourcePage:requestedPage??undefined,expectedRevision:secured.revision
    });
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,false),202);
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
    const body=await request.json<{plan?:unknown;expectedRevision?:number}>();
    const planError=floorPlanValidationError(body.plan,id);
    if(planError) return json({error:"صيغة المسودة غير صالحة"},400);
    const plan=body.plan as FloorPlanModel;
    const expectedRevision=body.expectedRevision;
    if(typeof expectedRevision!=="number"||!Number.isInteger(expectedRevision)||expectedRevision<0) return json({error:"رقم النسخة المرجعية للمسودة غير صالح"},400);
    try{await persistDraft(env,id,plan,expectedRevision);}
    catch(error){
      if(error instanceof Error&&error.message==="STALE_DRAFT") return json({error:"المسودة متقادمة بعد حفظ نسخة أحدث"},409);
      throw error;
    }
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,false));
  }
  if(draftMatch&&request.method==="DELETE"){
    const id=draftMatch[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const expectedRevision=Number(url.searchParams.get("expectedRevision"));
    if(!Number.isInteger(expectedRevision)||expectedRevision<0) return json({error:"رقم النسخة المرجعية للمسودة غير صالح"},400);
    try{await clearDraft(env,id,expectedRevision);}
    catch(error){
      if(error instanceof Error&&error.message==="STALE_DRAFT") return json({error:"تغير المشروع قبل حذف المسودة. أعد تحميله."},409);
      throw error;
    }
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
    const planError=floorPlanValidationError(body.plan,id);
    if(planError) return json({error:"صيغة المخطط غير صالحة"},400);
    if(!Number.isInteger(body.expectedRevision)||body.expectedRevision<0) return json({error:"رقم النسخة المرجعية غير صالح"},400);
    try{
      const baseline=await committedPlan(env,secured);
      const checked=await validateTransition(env,id,baseline,body.plan);
      if(checked.introduced.length){
        return json({
          error:"لن يتم حفظ التعديل لأنه أضاف تعارضًا هندسيًا جديدًا. راجع العناصر المحددة ثم حاول مرة أخرى.",
          validation:checked.report,
          introduced:checked.introduced,
        },422);
      }
    }catch(error){
      return json({error:error instanceof Error?error.message:"تعذر التحقق الهندسي قبل الحفظ"},502);
    }
    try{await persistPlan(env,id,body.plan,cleanName(body.summary||"تعديل يدوي"),body.expectedRevision);}
    catch(error){
      if(error instanceof Error&&error.message==="STALE_REVISION") return json({error:"تم حفظ نسخة أحدث من مشروعك. حدّث المشروع قبل الحفظ مرة أخرى."},409);
      throw error;
    }
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
    try{await persistPlan(env,id,plan,`استعادة النسخة ${revisionNumber}`,secured.revision);}
    catch(error){if(error instanceof Error&&error.message==="STALE_REVISION") return json({error:"تغير المشروع أثناء الاستعادة. أعد تحميله وحاول مرة أخرى."},409);throw error;}
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  const validateMatch=path.match(/^\/v1\/projects\/([^/]+)\/validate$/);
  if(validateMatch&&request.method==="POST"){
    const id=validateMatch[1];
    const secured=await protectedRow(request,env,id);
    if(secured instanceof Response) return secured;
    const body:{plan?:unknown}=await request.json<{plan?:unknown}>().catch(()=>({}));
    const stored=await currentPlan(env,secured);
    const candidate=body.plan??stored;
    if(!candidate) return json({error:"المخطط غير جاهز للفحص"},409);
    const planError=floorPlanValidationError(candidate,id);
    if(planError) return json({error:"صيغة المخطط غير صالحة للفحص"},400);
    const plan=candidate as FloorPlanModel;
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
    const body=await request.json<{command?:string;targetRoomId?:string|null;targetWallId?:string|null;targetOpeningId?:string|null}>();
    const command=(body.command??"").trim();
    const targetRoomId=(body.targetRoomId??"").trim()||null;
    const targetWallId=(body.targetWallId??"").trim()||null;
    const targetOpeningId=(body.targetOpeningId??"").trim()||null;
    if(!command) return json({error:"اكتب التعديل المطلوب"},400);
    if(targetRoomId&&!plan.rooms.some(room=>room.id===targetRoomId)) return json({error:"الغرفة المحددة لم تعد موجودة"},409);
    if(targetWallId&&!plan.walls.some(wall=>wall.id===targetWallId)) return json({error:"الجدار المحدد لم يعد موجودًا"},409);
    if(targetOpeningId&&![...plan.doors,...plan.windows].some(opening=>opening.id===targetOpeningId)) return json({error:"الفتحة المحددة لم تعد موجودة"},409);
    try{return json(await analyzerProposals(env,id,command,plan,targetRoomId,targetWallId,targetOpeningId));}
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

    const targetRoomId=(body.targetRoomId??"").trim()||null;
    const targetWallId=(body.targetWallId??"").trim()||null;
    const targetOpeningId=(body.targetOpeningId??"").trim()||null;
    if(targetRoomId&&!plan.rooms.some(room=>room.id===targetRoomId)) return json({error:"الغرفة المحددة لم تعد موجودة"},409);
    if(targetWallId&&!plan.walls.some(wall=>wall.id===targetWallId)) return json({error:"الجدار المحدد لم يعد موجودًا"},409);
    if(targetOpeningId&&![...plan.doors,...plan.windows].some(opening=>opening.id===targetOpeningId)) return json({error:"الفتحة المحددة لم تعد موجودة"},409);

    let fresh:EditProposalResponse;
    try{fresh=await analyzerProposals(env,id,command,plan,targetRoomId,targetWallId,targetOpeningId);}
    catch(error){return json({error:error instanceof Error?error.message:"تعذر التحقق من التعديل"},502);}

    const selected=fresh.proposals.find(proposal=>proposal.id===selectedId);
    if(!selected) return json({error:"المخطط تغير أو أن خيار التعديل لم يعد صالحًا. أعد المعاينة."},409);
    if(floorPlanValidationError(selected.previewPlan,id)) return json({error:"نتيجة H Engineer غير صالحة"},502);
    try{
      const checked=await validateTransition(env,id,plan,selected.previewPlan);
      if(checked.introduced.length){
        return json({
          error:"تم إيقاف الاقتراح لأنه يضيف تعارضًا هندسيًا جديدًا.",
          validation:checked.report,
          introduced:checked.introduced,
        },422);
      }
    }catch(error){
      return json({error:error instanceof Error?error.message:"تعذر التحقق الهندسي من الاقتراح"},502);
    }

    try{await persistPlan(env,id,selected.previewPlan,`H Engineer: ${cleanName(command)}`,secured.revision);}
    catch(error){if(error instanceof Error&&error.message==="STALE_REVISION") return json({error:"تغير المشروع أثناء تحليل H Engineer. أعد المعاينة على النسخة الأحدث."},409);throw error;}
    const row=await getProjectRow(env,id);
    return json(await projectView(env,row!,true));
  }

  return json({error:"not found"},404);
}
