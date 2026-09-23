import { floorPlanValidationError } from "@manzil/contracts";
import type { FloorPlanModel } from "@manzil/contracts";
import { getProjectRow,persistPlan,setAnalysisProgress } from "./db";
import type { AnalyzeMessage,Env } from "./types";

export async function consumeAnalysis(batch:MessageBatch<AnalyzeMessage>,env:Env){
  for(const message of batch.messages){
    const job=message.body;
    try{
      const before=await getProjectRow(env,job.projectId);
      if(!before||before.source_key!==job.sourceKey||(before.revision!==job.expectedRevision)){
        message.ack();
        continue;
      }
      const started=await setAnalysisProgress(env,job.projectId,job.sourceKey,job.expectedRevision,"analyzing","preprocess",14,"بدأ محرك التحليل السحابي");
      if(!started){message.ack();continue;}
      const apiBase=env.API_PUBLIC_URL.replace(/\/$/,"");
      const analysisQuery=new URLSearchParams({sourceKey:job.sourceKey});
      analysisQuery.set("revision",String(job.expectedRevision));
      const callbackQuery=analysisQuery.toString();
      const response=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/analyze`,{
        method:"POST",
        headers:{"content-type":"application/json","x-manzil-internal":env.INTERNAL_TOKEN},
        body:JSON.stringify({
          project_id:job.projectId,
          source_url:`${apiBase}/internal/source/${encodeURIComponent(job.projectId)}?key=${encodeURIComponent(job.sourceKey)}`,
          filename:job.fileName,
          mime_type:job.mimeType,
          callback_url:`${apiBase}/internal/progress?${callbackQuery}`,
          preview_url:`${apiBase}/internal/preview/${encodeURIComponent(job.projectId)}?${callbackQuery}`,
          source_page:job.sourcePage??null
        })
      });
      if(!response.ok) throw new Error((await response.text().catch(()=>""))||`ANALYZER_${response.status}`);
      const rawPlan=await response.json<unknown>();
      const planError=floorPlanValidationError(rawPlan,job.projectId);
      if(planError) throw new Error(`ANALYZER_INVALID_PLAN:${planError}`);
      const plan=rawPlan as FloorPlanModel;
      const latest=await getProjectRow(env,job.projectId);
      if(!latest||latest.source_key!==job.sourceKey||(latest.revision!==job.expectedRevision)){
        message.ack();
        continue;
      }
      await persistPlan(env,job.projectId,plan,job.sourcePage?`تحليل الصفحة ${job.sourcePage}`:"التحليل السحابي الأولي",job.expectedRevision,job.sourceKey);
      message.ack();
    }catch(error){
      const detail=error instanceof Error?error.message:"UNKNOWN_ANALYSIS_ERROR";
      const current=await getProjectRow(env,job.projectId);
      const stale=!current||current.source_key!==job.sourceKey||(current.revision!==job.expectedRevision);
      if(stale||detail==="STALE_REVISION"||detail==="STALE_SOURCE"||detail==="STALE_SOURCE_OR_REVISION"){
        message.ack();
        continue;
      }
      if(message.attempts<3){
        const marked=await setAnalysisProgress(env,job.projectId,job.sourceKey,job.expectedRevision,"queued","preprocess",12,"إعادة محاولة التحليل السحابي");
        if(marked)message.retry({delaySeconds:Math.min(120,20*message.attempts)});else message.ack();
      }else{
        await setAnalysisProgress(env,job.projectId,job.sourceKey,job.expectedRevision,"error","error",100,"تعذر إكمال التحليل",detail);
        message.ack();
      }
    }
  }
}
