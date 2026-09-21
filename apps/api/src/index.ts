import { getProjectRow,setAnalysisProgress } from "./db";
import { json,withCors } from "./http";
import { consumeAnalysis } from "./queue";
import { route } from "./routes";
import type { AnalyzeMessage,Env } from "./types";

function internalAuthorized(request:Request,env:Env){
  return Boolean(env.INTERNAL_TOKEN)&&request.headers.get("x-manzil-internal")===env.INTERNAL_TOKEN;
}

function analysisIdentity(url:URL){
  const sourceKey=url.searchParams.get("sourceKey");
  const revisionRaw=url.searchParams.get("revision");
  const revision=Number(revisionRaw);
  if(!sourceKey||revisionRaw===null||!Number.isInteger(revision)||revision<0)return null;
  return {sourceKey,revision};
}

async function app(request:Request,env:Env){
  const url=new URL(request.url);

  if(url.pathname==="/internal/progress"&&request.method==="POST"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const identity=analysisIdentity(url);
    if(!identity) return json({error:"analysis identity required"},400);
    const body=await request.json<{project_id:string;status?:string;phase:string;progress:number;message?:string;error?:string}>();
    const updated=await setAnalysisProgress(
      env,body.project_id,identity.sourceKey,identity.revision,
      body.status??"analyzing",body.phase,body.progress,body.message,body.error
    );
    if(!updated) return json({error:"stale analysis callback"},409);
    return json({ok:true});
  }

  const preview=url.pathname.match(/^\/internal\/preview\/([^/]+)$/);
  if(preview&&request.method==="PUT"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const identity=analysisIdentity(url);
    if(!identity) return json({error:"analysis identity required"},400);
    const projectId=decodeURIComponent(preview[1]);
    const current=await getProjectRow(env,projectId);
    if(!current) return json({error:"project not found"},404);
    if(current.source_key!==identity.sourceKey||current.revision!==identity.revision) return json({error:"stale analysis callback"},409);
    const previousPreviewKey=current.preview_key;
    if(!request.body) return json({error:"preview body required"},400);
    const contentType=request.headers.get("content-type")?.split(";")[0]??"image/webp";
    if(!["image/webp","image/png","image/jpeg"].includes(contentType)) return json({error:"unsupported preview type"},415);
    const key=`projects/${projectId}/previews/r${identity.revision}-${crypto.randomUUID()}.webp`;
    const object=await env.ASSETS.put(key,request.body,{httpMetadata:{contentType}});
    if(object.size>30*1024*1024){
      await env.ASSETS.delete(key);
      return json({error:"preview too large"},413);
    }
    const result=await env.DB.prepare("UPDATE projects SET preview_key=?, updated_at=? WHERE id=? AND source_key=? AND revision=?")
      .bind(key,new Date().toISOString(),projectId,identity.sourceKey,identity.revision).run();
    if((result.meta.changes??0)<1){
      await env.ASSETS.delete(key).catch(()=>undefined);
      return json({error:"stale analysis callback"},409);
    }
    if(previousPreviewKey&&previousPreviewKey!==key) await env.ASSETS.delete(previousPreviewKey).catch(()=>undefined);
    return json({ok:true,size:object.size});
  }

  const source=url.pathname.match(/^\/internal\/source\/([^/]+)$/);
  if(source&&request.method==="GET"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const row=await getProjectRow(env,decodeURIComponent(source[1]));
    if(!row?.source_key) return json({error:"source not found"},404);
    const requestedKey=url.searchParams.get("key");
    if(requestedKey&&requestedKey!==row.source_key) return json({error:"stale source"},409);
    const object=await env.ASSETS.get(requestedKey||row.source_key);
    if(!object) return json({error:"source not found"},404);
    const headers=new Headers();
    object.writeHttpMetadata(headers);
    headers.set("cache-control","private, no-store");
    headers.set("content-length",String(object.size));
    return new Response(object.body,{headers});
  }

  return route(request,env);
}

export default {
  async fetch(request:Request,env:Env){
    try{return withCors(env,request,await app(request,env));}
    catch(error){
      const detail=error instanceof Error?error.message:"unexpected error";
      return withCors(env,request,json({error:detail},500));
    }
  },
  queue:consumeAnalysis
} satisfies ExportedHandler<Env,AnalyzeMessage>;
