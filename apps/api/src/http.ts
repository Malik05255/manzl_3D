import type { Env } from "./types";

export const json=(data:unknown,status=200,headers:HeadersInit={})=>new Response(JSON.stringify(data),{
  status,
  headers:{"content-type":"application/json; charset=utf-8",...headers}
});

export function withCors(env:Env,request:Request,response:Response){
  const origin=request.headers.get("origin")??"";
  const allowed=!env.ALLOWED_ORIGIN||env.ALLOWED_ORIGIN==="*"||origin===env.ALLOWED_ORIGIN;
  const headers=new Headers(response.headers);
  if(allowed) headers.set("access-control-allow-origin",env.ALLOWED_ORIGIN==="*"?"*":(origin||env.ALLOWED_ORIGIN||"*"));
  headers.set("access-control-allow-methods","GET,POST,PUT,DELETE,OPTIONS");
  headers.set("access-control-allow-headers","content-type,authorization");
  headers.set("vary","Origin");
  return new Response(response.body,{status:response.status,statusText:response.statusText,headers});
}

export function cleanName(value:string){
  return value.replace(/[\\/\0]/g,"_").replace(/\s+/g," ").trim().slice(0,160)||"مخطط";
}
