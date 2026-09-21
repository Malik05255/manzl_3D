import type { ApplyProposalRequest, EditProposalResponse, FloorPlanModel, ProjectView, SaveRevisionRequest } from "@manzil/contracts";

const API_BASE=(import.meta.env.VITE_API_BASE_URL as string|undefined)?.replace(/\/$/,"")??"http://localhost:8787";
const tokenKey=(projectId:string)=>`manzil:project-token:${projectId}`;

function projectIdFromPath(path:string){
  return path.match(/^\/v1\/projects\/([^/]+)/)?.[1]??null;
}

function projectToken(projectId:string){
  try{return localStorage.getItem(tokenKey(projectId));}catch{return null;}
}

function rememberProjectToken(projectId:string,token:string){
  try{localStorage.setItem(tokenKey(projectId),token);}catch{}
}

async function request<T>(path:string,init?:RequestInit):Promise<T>{
  const projectId=projectIdFromPath(path);
  const token=projectId?projectToken(projectId):null;
  const response=await fetch(`${API_BASE}${path}`,{
    ...init,
    headers:{
      "content-type":"application/json",
      ...(token?{authorization:`Bearer ${token}`}:{}),
      ...(init?.headers??{})
    }
  });
  if(!response.ok){
    let message=`HTTP ${response.status}`;
    try{const body=await response.json() as {error?:string};if(body.error)message=body.error;}catch{}
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function createProject(name:string){
  const project=await request<ProjectView>("/v1/projects",{method:"POST",body:JSON.stringify({name})});
  if(project.accessToken) rememberProjectToken(project.id,project.accessToken);
  return project;
}

export function uploadSource(projectId:string,file:File,onProgress:(value:number)=>void):Promise<void>{
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open("PUT",`${API_BASE}/v1/projects/${projectId}/source?filename=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("content-type",file.type||"application/octet-stream");
    const token=projectToken(projectId);
    if(token)xhr.setRequestHeader("authorization",`Bearer ${token}`);
    xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100));};
    xhr.onerror=()=>reject(new Error("تعذر رفع الملف إلى السحابة"));
    xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve():reject(new Error(xhr.responseText||"فشل رفع الملف"));
    xhr.send(file);
  });
}

export const getProject=(id:string)=>request<ProjectView>(`/v1/projects/${id}`);
export const askEngineer=(id:string,command:string)=>request<EditProposalResponse>(`/v1/projects/${id}/ai/proposals`,{method:"POST",body:JSON.stringify({command})});
export const applyProposal=(id:string,payload:ApplyProposalRequest)=>request<ProjectView>(`/v1/projects/${id}/ai/apply`,{method:"POST",body:JSON.stringify(payload)});
export function saveRevision(id:string,plan:FloorPlanModel,summary:string){
  const payload:SaveRevisionRequest={plan,summary};
  return request<ProjectView>(`/v1/projects/${id}/revisions`,{method:"POST",body:JSON.stringify(payload)});
}
