import { getProjectRow,setProgress } from "./db";
import { json,withCors } from "./http";
import { consumeAnalysis } from "./queue";
import { route } from "./routes";
import type { AnalyzeMessage,Env } from "./types";

function internalAuthorized(request:Request,env:Env){
  return Boolean(env.INTERNAL_TOKEN)&&request.headers.get("x-manzil-internal")===env.INTERNAL_TOKEN;
}

async function app(request:Request,env:Env){
  const url=new URL(request.url);

  if(url.pathname==="/internal/progress"&&request.method==="POST"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const body=await request.json<{project_id:string;status?:string;phase:string;progress:number;message?:string;error?:string}>();
    await setProgress(env,body.project_id,body.status??"analyzing",body.phase,body.progress,body.message,body.error);
    return json({ok:true});
  }

  const source=url.pathname.match(/^\/internal\/source\/([^/]+)$/);
  if(source&&request.method==="GET"){
    if(!internalAuthorized(request,env)) return json({error:"unauthorized"},401);
    const row=await getProjectRow(env,decodeURIComponent(source[1]));
    if(!row?.source_key) return json({error:"source not found"},404);
    const object=await env.ASSETS.get(row.source_key);
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
