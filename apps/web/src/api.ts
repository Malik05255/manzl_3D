import type { ApplyProposalRequest, EditProposalResponse, FloorPlanModel, ProjectView, RevisionView, SaveRevisionRequest, ValidationReport } from "@manzil/contracts";

const API_BASE=(import.meta.env.VITE_API_BASE_URL as string|undefined)?.replace(/\/$/,"")??"http://localhost:8787";
const tokenKey=(projectId:string)=>`manzil:project-token:${projectId}`;
const lastProjectKey="manzil:last-project";

function projectIdFromPath(path:string){
  return path.match(/^\/v1\/projects\/([^/]+)/)?.[1]??null;
}

function projectToken(projectId:string){
  try{return localStorage.getItem(tokenKey(projectId));}catch{return null;}
}

function rememberProjectToken(projectId:string,token:string){
  try{localStorage.setItem(tokenKey(projectId),token);}catch{}
}

function rememberLastProjectId(projectId:string){
  try{localStorage.setItem(lastProjectKey,projectId);}catch{}
}

export function getLastProjectId(){
  try{return localStorage.getItem(lastProjectKey);}catch{return null;}
}

export function forgetLastProject(){
  try{localStorage.removeItem(lastProjectKey);}catch{}
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

export function inferSourceMime(file:{name:string;type?:string}){
  const declared=(file.type??"").toLowerCase();
  if(["application/pdf","image/png","image/jpeg","image/webp"].includes(declared))return declared;
  const name=file.name.toLowerCase();
  if(name.endsWith(".pdf"))return "application/pdf";
  if(name.endsWith(".png"))return "image/png";
  if(name.endsWith(".jpg")||name.endsWith(".jpeg"))return "image/jpeg";
  if(name.endsWith(".webp"))return "image/webp";
  return null;
}

export function uploadSource(projectId:string,file:File,onProgress:(value:number)=>void):Promise<void>{
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open("PUT",`${API_BASE}/v1/projects/${projectId}/source?filename=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("content-type",inferSourceMime(file)??"application/octet-stream");
    const token=projectToken(projectId);
    if(token)xhr.setRequestHeader("authorization",`Bearer ${token}`);
    xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100));};
    xhr.onerror=()=>reject(new Error("تعذر رفع الملف إلى السحابة"));
    xhr.onload=()=>{
      if(xhr.status>=200&&xhr.status<300){rememberLastProjectId(projectId);resolve();}
      else reject(new Error(xhr.responseText||"فشل رفع الملف"));
    };
    xhr.send(file);
  });
}

export async function getProject(id:string){
  const project=await request<ProjectView>(`/v1/projects/${id}`);
  rememberLastProjectId(id);
  return project;
}
export async function getProjectPreview(id:string):Promise<string|null>{
  const token=projectToken(id);
  const response=await fetch(`${API_BASE}/v1/projects/${id}/preview`,{
    headers:token?{authorization:`Bearer ${token}`}:undefined
  });
  if(response.status===404)return null;
  if(!response.ok)throw new Error("تعذر تحميل المخطط الأصلي");
  return URL.createObjectURL(await response.blob());
}
export const askEngineer=(id:string,command:string)=>request<EditProposalResponse>(`/v1/projects/${id}/ai/proposals`,{method:"POST",body:JSON.stringify({command})});
export const resizeRoomPrecisely=(id:string,roomId:string,widthM:number,heightM:number)=>request<EditProposalResponse>(`/v1/projects/${id}/geometry/resize-proposals`,{method:"POST",body:JSON.stringify({roomId,widthM,heightM})});
export const validateProject=(id:string,plan:FloorPlanModel)=>request<ValidationReport>(`/v1/projects/${id}/validate`,{method:"POST",body:JSON.stringify({plan})});
export const applyProposal=(id:string,payload:ApplyProposalRequest)=>request<ProjectView>(`/v1/projects/${id}/ai/apply`,{method:"POST",body:JSON.stringify(payload)});
export const saveDraft=(id:string,plan:FloorPlanModel,expectedRevision:number)=>request<ProjectView>(`/v1/projects/${id}/draft`,{method:"PUT",body:JSON.stringify({plan,expectedRevision})});
export function saveRevision(id:string,plan:FloorPlanModel,summary:string,expectedRevision:number){
  const payload:SaveRevisionRequest={plan,summary,expectedRevision};
  return request<ProjectView>(`/v1/projects/${id}/revisions`,{method:"POST",body:JSON.stringify(payload)});
}

export const listRevisions=(id:string)=>request<{items:RevisionView[]}>(`/v1/projects/${id}/revisions`);
export const restoreRevision=(id:string,revision:number)=>request<ProjectView>(`/v1/projects/${id}/revisions/${revision}/restore`,{method:"POST"});


export async function importProjectBackup(name:string,plan:FloorPlanModel){
  const project=await createProject(name);
  const imported:FloorPlanModel={...plan,id:project.id};
  const ready=await saveRevision(project.id,imported,"استيراد نسخة مشروع",project.revision);
  rememberLastProjectId(project.id);
  return ready;
}
