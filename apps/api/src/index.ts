import { getProjectRow,setProgress } from "./db";
import { json,withCors } from "./http";
import { consumeAnalysis } from "./queue";
import { route } from "./routes";
import type { AnalyzeMessage,Env } from "./types";

function internalAuthorized(request:Request,env:Env){
  return Boolean(env.INTERNAL_TOKEN)&&request.headers.get("x-manzil-internal")===env.INTERNAL_TOKEN;
}

function callbackMatchesAnalysis(url:URL,row:{source_key:string|null;revision:number}){
  const sourceKey=url.searchParams.get("sourceKey");
  const revisionRaw=url.searchParams.get("revision");
  if(sourceKey&&sourceKey!==row.source_key)return false;
  if(revisionRaw!==null){
    const revision=Number(revisionRaw);
    if(!Number.isInteger(revision)||revision!==row.revision)return false;
  }
  return true;
}

async function app(request:Request,env:Env){
  const url=new URL(request.url);

  if(url.pathname==="/internal/progress"&&request.method==="POST"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const body=await request.json<{project_id:string;status?:string;phase:string;progress:number;message?:string;error?:string}>();
    const row=await getProjectRow(env,body.project_id);
    if(!row) return json({error:"project not found"},404);
    if(!callbackMatchesAnalysis(url,row)) return json({error:"stale analysis callback"},409);
    await setProgress(env,body.project_id,body.status??"analyzing",body.phase,body.progress,body.message,body.error);
    return json({ok:true});
  }

  const preview=url.pathname.match(/^\/internal\/preview\/([^/]+)$/);
  if(preview&&request.method==="PUT"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const projectId=decodeURIComponent(preview[1]);
    const row=await getProjectRow(env,projectId);
    if(!row) return json({error:"project not found"},404);
    if(!callbackMatchesAnalysis(url,row)) return json({error:"stale analysis callback"},409);
    if(!request.body) return json({error:"preview body required"},400);
    const contentType=request.headers.get("content-type")?.split(";")[0]??"image/webp";
    if(!["image/webp","image/png","image/jpeg"].includes(contentType)) return json({error:"unsupported preview type"},415);
    const key=`projects/${projectId}/preview.webp`;
    const object=await env.ASSETS.put(key,request.body,{httpMetadata:{contentType}});
    if(object.size>30*1024*1024){
      await env.ASSETS.delete(key);
      return json({error:"preview too large"},413);
    }
    await env.DB.prepare("UPDATE projects SET preview_key=?, updated_at=? WHERE id=?")
      .bind(key,new Date().toISOString(),projectId).run();
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
