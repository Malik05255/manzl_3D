import { floorPlanValidationError } from "@manzil/contracts";
import type { FloorPlanModel } from "@manzil/contracts";
import { persistPlan,setProgress } from "./db";
import type { AnalyzeMessage,Env } from "./types";

export async function consumeAnalysis(batch:MessageBatch<AnalyzeMessage>,env:Env){
  for(const message of batch.messages){
    const job=message.body;
    try{
      await setProgress(env,job.projectId,"analyzing","preprocess",14,"بدأ محرك التحليل السحابي");
      const apiBase=env.API_PUBLIC_URL.replace(/\/$/,"");
      const response=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/analyze`,{
        method:"POST",
        headers:{"content-type":"application/json","x-manzil-internal":env.INTERNAL_TOKEN},
        body:JSON.stringify({
          project_id:job.projectId,
          source_url:`${apiBase}/internal/source/${encodeURIComponent(job.projectId)}`,
          filename:job.fileName,
          mime_type:job.mimeType,
          callback_url:`${apiBase}/internal/progress`,
          preview_url:`${apiBase}/internal/preview/${encodeURIComponent(job.projectId)}`,
          source_page:job.sourcePage??null
        })
      });
      if(!response.ok) throw new Error((await response.text().catch(()=>""))||`ANALYZER_${response.status}`);
      const rawPlan=await response.json<unknown>();
      const planError=floorPlanValidationError(rawPlan,job.projectId);
      if(planError) throw new Error(`ANALYZER_INVALID_PLAN:${planError}`);
      const plan=rawPlan as FloorPlanModel;
      await persistPlan(env,job.projectId,plan,"التحليل السحابي الأولي");
      message.ack();
    }catch(error){
      const detail=error instanceof Error?error.message:"UNKNOWN_ANALYSIS_ERROR";
      if(message.attempts<3){
        await setProgress(env,job.projectId,"queued","preprocess",12,"إعادة محاولة التحليل السحابي");
        message.retry({delaySeconds:Math.min(120,20*message.attempts)});
      }else{
        await setProgress(env,job.projectId,"error","error",100,"تعذر إكمال التحليل",detail);
        message.ack();
      }
    }
  }
}
