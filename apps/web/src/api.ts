import type { ApplyProposalRequest, EditProposalResponse, FloorPlanModel, ProjectView, RevisionView, SaveRevisionRequest, ValidationReport } from "@manzil/contracts";

const API_BASE=(import.meta.env.VITE_API_BASE_URL as string|undefined)?.replace(/\/$/,"")??"http://localhost:8787";
const tokenKey=(projectId:string)=>`manzil:project-token:${projectId}`;
export class ApiError extends Error{
  constructor(message:string,public readonly status:number,public readonly data?:unknown){super(message);this.name="ApiError";}
}

const lastProjectKey="manzil:last-project";
const knownProjectsKey="manzil:known-projects";

export interface KnownProject{ id:string; name:string; updatedAt:string; }

function readKnownProjects():KnownProject[]{
  try{
    const value=JSON.parse(localStorage.getItem(knownProjectsKey)??"[]") as unknown;
    if(!Array.isArray(value))return [];
    return value.filter((item):item is KnownProject=>Boolean(item&&typeof item==="object"&&typeof (item as KnownProject).id==="string"&&typeof (item as KnownProject).name==="string"&&typeof (item as KnownProject).updatedAt==="string")).slice(0,20);
  }catch{return [];}
}
function rememberKnownProject(project:Pick<ProjectView,"id"|"name"|"updatedAt">){
  try{
    const next=[{id:project.id,name:project.name,updatedAt:project.updatedAt},...readKnownProjects().filter(item=>item.id!==project.id)]
      .sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt)).slice(0,20);
    localStorage.setItem(knownProjectsKey,JSON.stringify(next));
  }catch{}
}
export function getKnownProjects(){return readKnownProjects();}
export function forgetKnownProject(projectId:string){
  try{localStorage.removeItem(tokenKey(projectId));localStorage.setItem(knownProjectsKey,JSON.stringify(readKnownProjects().filter(item=>item.id!==projectId)));}catch{}
}


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
    let data:unknown=undefined;
    try{
      data=await response.json();
      if(data&&typeof data==="object"&&"error" in data&&typeof (data as {error?:unknown}).error==="string")message=(data as {error:string}).error;
    }catch{}
    throw new ApiError(message,response.status,data);
  }
  return response.json() as Promise<T>;
}

export async function createProject(name:string){
  const project=await request<ProjectView>("/v1/projects",{method:"POST",body:JSON.stringify({name})});
  if(project.accessToken) rememberProjectToken(project.id,project.accessToken);
  rememberLastProjectId(project.id);
  rememberKnownProject(project);
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

export const retryAnalysis=(id:string)=>request<ProjectView>(`/v1/projects/${id}/retry-analysis`,{method:"POST"});

export async function getProject(id:string){
  const project=await request<ProjectView>(`/v1/projects/${id}`);
  rememberLastProjectId(id);
  rememberKnownProject(project);
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
export const askEngineer=(id:string,command:string,targetRoomId?:string|null)=>request<EditProposalResponse>(`/v1/projects/${id}/ai/proposals`,{method:"POST",body:JSON.stringify({command,targetRoomId:targetRoomId??null})});
export const resizeRoomPrecisely=(id:string,roomId:string,widthM:number,heightM:number)=>request<EditProposalResponse>(`/v1/projects/${id}/geometry/resize-proposals`,{method:"POST",body:JSON.stringify({roomId,widthM,heightM})});
export const validateProject=(id:string,plan:FloorPlanModel)=>request<ValidationReport>(`/v1/projects/${id}/validate`,{method:"POST",body:JSON.stringify({plan})});
export async function applyProposal(id:string,payload:ApplyProposalRequest){const project=await request<ProjectView>(`/v1/projects/${id}/ai/apply`,{method:"POST",body:JSON.stringify(payload)});rememberKnownProject(project);return project;}
export const saveDraft=(id:string,plan:FloorPlanModel,expectedRevision:number)=>request<ProjectView>(`/v1/projects/${id}/draft`,{method:"PUT",body:JSON.stringify({plan,expectedRevision})});
export const clearProjectDraft=(id:string,expectedRevision:number)=>request<ProjectView>(`/v1/projects/${id}/draft?expectedRevision=${expectedRevision}`,{method:"DELETE"});
export async function saveRevision(id:string,plan:FloorPlanModel,summary:string,expectedRevision:number){
  const payload:SaveRevisionRequest={plan,summary,expectedRevision};
  const project=await request<ProjectView>(`/v1/projects/${id}/revisions`,{method:"POST",body:JSON.stringify(payload)});
  rememberKnownProject(project);
  rememberLastProjectId(id);
  return project;
}

export const listRevisions=(id:string)=>request<{items:RevisionView[]}>(`/v1/projects/${id}/revisions`);
export async function restoreRevision(id:string,revision:number){const project=await request<ProjectView>(`/v1/projects/${id}/revisions/${revision}/restore`,{method:"POST"});rememberKnownProject(project);return project;}


export async function importProjectBackup(name:string,plan:FloorPlanModel){
  const project=await createProject(name);
  const imported:FloorPlanModel={...plan,id:project.id};
  const ready=await saveRevision(project.id,imported,"استيراد نسخة مشروع",project.revision);
  rememberKnownProject(ready);
  rememberLastProjectId(project.id);
  return ready;
}
