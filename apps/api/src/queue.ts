import type { FloorPlanModel } from "@manzil/contracts";
import { persistPlan, setProgress } from "./db";
import type { AnalyzeMessage, Env } from "./types";

export async function consumeAnalysis(batch:MessageBatch<AnalyzeMessage>,env:Env){
  for(const message of batch.messages){
    const job=message.body;
    try{
      await setProgress(env,job.projectId,"analyzing","preprocess",15,"بدأ محرك التحليل السحابي");
      const source=await env.ASSETS.get(job.sourceKey);
      if(!source) throw new Error("SOURCE_NOT_FOUND");

      const bytes=await source.arrayBuffer();
      const form=new FormData();
      form.set("file",new File([bytes],job.fileName,{type:job.mimeType}));
      form.set("project_id",job.projectId);
      form.set("filename",job.fileName);
      form.set("mime_type",job.mimeType);
      form.set("callback_url",`${env.API_PUBLIC_URL.replace(/\/$/,"")}/internal/progress`);
      form.set("callback_token",env.INTERNAL_TOKEN);

      const response=await fetch(`${env.ANALYZER_URL.replace(/\/$/,"")}/v1/analyze`,{method:"POST",body:form});
      if(!response.ok) throw new Error((await response.text().catch(()=>""))||`ANALYZER_${response.status}`);

      const plan=await response.json<FloorPlanModel>();
      if(plan.id!==job.projectId) throw new Error("ANALYZER_PROJECT_MISMATCH");
      await persistPlan(env,job.projectId,plan,"التحليل السحابي الأولي");
      message.ack();
    }catch(error){
      const detail=error instanceof Error?error.message:"UNKNOWN_ANALYSIS_ERROR";
      await setProgress(env,job.projectId,"error","error",100,"تعذر إكمال التحليل",detail);
      message.ack();
    }
  }
}
