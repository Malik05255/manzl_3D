import { readFile } from "node:fs/promises";

const api=(process.env.MANZIL_API_URL??"").replace(/\/$/,"");
const sourceFile=process.env.MANZIL_E2E_SOURCE??"";
if(!api)throw new Error("MANZIL_API_URL is required");
if(!sourceFile)throw new Error("MANZIL_E2E_SOURCE is required");

async function jsonRequest(path,{method="GET",token,body,headers={}}={}){
  const response=await fetch(api+path,{
    method,
    headers:{
      ...(body!==undefined?{"content-type":"application/json"}:{}),
      ...(token?{authorization:`Bearer ${token}`}:{}),
      ...headers,
    },
    body:body===undefined?undefined:JSON.stringify(body),
  });
  const text=await response.text();
  let payload=null;
  try{payload=text?JSON.parse(text):null;}catch{payload=text;}
  if(!response.ok){
    throw new Error(`${method} ${path} -> ${response.status}: ${typeof payload==="string"?payload:JSON.stringify(payload)}`);
  }
  return payload;
}

const created=await jsonRequest("/v1/projects",{
  method:"POST",
  body:{name:`E2E ${new Date().toISOString()}`},
});
const projectId=created.id;
const token=created.accessToken;
if(!projectId||!token)throw new Error("Project creation did not return id/accessToken");

const bytes=await readFile(sourceFile);
const upload=await fetch(
  `${api}/v1/projects/${projectId}/source?filename=e2e-floorplan.pdf`,
  {
    method:"PUT",
    headers:{
      authorization:`Bearer ${token}`,
      "content-type":"application/pdf",
      "content-length":String(bytes.byteLength),
    },
    body:bytes,
  },
);
if(!upload.ok)throw new Error(`upload failed: ${upload.status} ${await upload.text()}`);

let project=null;
const deadline=Date.now()+Number(process.env.MANZIL_E2E_TIMEOUT_MS??180000);
while(Date.now()<deadline){
  project=await jsonRequest(`/v1/projects/${projectId}`,{token});
  if(project.status==="ready"&&project.plan)break;
  if(project.status==="error")throw new Error(`analysis failed: ${project.error??project.message??"unknown"}`);
  await new Promise(resolve=>setTimeout(resolve,2000));
}
if(!project?.plan||project.status!=="ready")throw new Error("analysis did not reach ready before timeout");
if((project.plan.walls?.length??0)<4)throw new Error("analysis returned fewer than four walls");

const revisionAfterAnalysis=project.revision;
const command="إعادة بناء الغرف من الجدران";
const preview=await jsonRequest(`/v1/projects/${projectId}/ai/proposals`,{
  method:"POST",
  token,
  body:{command,expectedRevision:project.revision},
});
if(!preview.proposals?.length)throw new Error(`H Engineer returned no preview: ${preview.needsClarification??"unknown"}`);

const selected=preview.proposals[0];
const applied=await jsonRequest(`/v1/projects/${projectId}/ai/apply`,{
  method:"POST",
  token,
  body:{
    command,
    proposal:selected,
    expectedRevision:project.revision,
    targetRoomId:null,
    targetWallId:null,
    targetOpeningId:null,
  },
});
if(applied.revision<=revisionAfterAnalysis)throw new Error("applying preview did not create a new revision");

const revisions=await jsonRequest(`/v1/projects/${projectId}/revisions`,{token});
if(!revisions.items?.some(item=>item.revision===revisionAfterAnalysis)){
  throw new Error("analysis revision is missing from revision history");
}

const restored=await jsonRequest(
  `/v1/projects/${projectId}/revisions/${revisionAfterAnalysis}/restore`,
  {method:"POST",token},
);
if(restored.revision<=applied.revision)throw new Error("restore did not create a new revision");
if(!restored.plan)throw new Error("restore did not return a plan");

console.log(JSON.stringify({
  ok:true,
  projectId,
  analysisRevision:revisionAfterAnalysis,
  appliedRevision:applied.revision,
  restoredRevision:restored.revision,
  walls:restored.plan.walls?.length??0,
  rooms:restored.plan.rooms?.length??0,
},null,2));
