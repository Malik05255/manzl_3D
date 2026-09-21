import { setProgress } from "./db";
import { json,withCors } from "./http";
import { consumeAnalysis } from "./queue";
import { route } from "./routes";
import type { AnalyzeMessage,Env } from "./types";

async function app(request:Request,env:Env){
  const url=new URL(request.url);
  if(url.pathname==="/internal/progress"&&request.method==="POST"){
    if(request.headers.get("x-manzil-internal")!==env.INTERNAL_TOKEN) return json({error:"unauthorized"},401);
    const body=await request.json<{project_id:string;status?:string;phase:string;progress:number;message?:string;error?:string}>();
    await setProgress(env,body.project_id,body.status??"analyzing",body.phase,body.progress,body.message,body.error);
    return json({ok:true});
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
