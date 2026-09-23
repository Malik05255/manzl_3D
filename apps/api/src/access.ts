import type { ProjectRow } from "./types";

const encoder=new TextEncoder();

async function sha256Hex(value:string){
  const digest=await crypto.subtle.digest("SHA-256",encoder.encode(value));
  return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,"0")).join("");
}

function accessValue(request:Request){
  const value=request.headers.get("authorization")??"";
  const match=value.match(/^Bearer\s+(.+)$/i);
  return match?.[1]?.trim()||null;
}

export async function createProjectAccess(){
  const token=`${crypto.randomUUID()}.${crypto.randomUUID()}`;
  return {token,hash:await sha256Hex(token)};
}

export async function hasProjectAccess(request:Request,row:ProjectRow){
  if(!row.access_hash) return false;
  const token=accessValue(request);
  if(!token) return false;
  return (await sha256Hex(token))===row.access_hash;
}
