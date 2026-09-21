import type { FloorPlanModel,Point } from "@manzil/contracts";

function escapeXml(value:string){
  return value.replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[char]??char));
}

function polygonArea(points:Point[]){
  let sum=0;
  for(let index=0;index<points.length;index++){
    const a=points[index];
    const b=points[(index+1)%points.length];
    sum+=a.x*b.y-b.x*a.y;
  }
  return Math.abs(sum)/2;
}

function roomMetrics(room:FloorPlanModel["rooms"][number],metersPerPixel?:number|null){
  const xs=room.polygon.map(point=>point.x);
  const ys=room.polygon.map(point=>point.y);
  const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
  const widthPx=Math.max(0,right-left),heightPx=Math.max(0,bottom-top);
  return {
    cx:(left+right)/2,
    cy:(top+bottom)/2,
    widthPx,
    heightPx,
    widthM:metersPerPixel?widthPx*metersPerPixel:null,
    heightM:metersPerPixel?heightPx*metersPerPixel:null,
    areaM2:metersPerPixel?polygonArea(room.polygon)*metersPerPixel*metersPerPixel:(room.areaM2??null),
  };
}

export function safeFileName(value:string){
  const cleaned=value.trim().replace(/[\\/:*?"<>|]+/g,"-").replace(/\s+/g," ").slice(0,90);
  return cleaned||"manzil-h-plan";
}

export function planToSvg(plan:FloorPlanModel){
  const width=Math.max(1,plan.widthPx);
  const height=Math.max(1,plan.heightPx);
  const parts=[
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<rect width="${width}" height="${height}" fill="#ffffff"/>`,
  ];

  for(const room of plan.rooms){
    const points=room.polygon.map(point=>`${point.x},${point.y}`).join(" ");
    parts.push(`<polygon points="${points}" fill="#f8fbff" stroke="#dbeafe" stroke-width="1"/>`);
  }

  for(const wall of plan.walls){
    parts.push(`<line x1="${wall.a.x}" y1="${wall.a.y}" x2="${wall.b.x}" y2="${wall.b.y}" stroke="#0f172a" stroke-width="${Math.max(3,wall.thicknessPx)}" stroke-linecap="round"/>`);
  }
  for(const door of plan.doors){
    parts.push(`<line x1="${door.a.x}" y1="${door.a.y}" x2="${door.b.x}" y2="${door.b.y}" stroke="#0284c7" stroke-width="4"/>`);
  }
  for(const window of plan.windows){
    parts.push(`<line x1="${window.a.x}" y1="${window.a.y}" x2="${window.b.x}" y2="${window.b.y}" stroke="#38bdf8" stroke-width="3"/>`);
  }

  for(const dimension of plan.dimensions??[]){
    if(!dimension.reviewed||!dimension.spanA||!dimension.spanB||!dimension.valueM)continue;
    const mx=(dimension.spanA.x+dimension.spanB.x)/2;
    const my=(dimension.spanA.y+dimension.spanB.y)/2;
    const label=`${dimension.valueM.toFixed(2)} م`;
    parts.push(`<line x1="${dimension.spanA.x}" y1="${dimension.spanA.y}" x2="${dimension.spanB.x}" y2="${dimension.spanB.y}" stroke="#6d28d9" stroke-width="2"/>`);
    parts.push(`<circle cx="${dimension.spanA.x}" cy="${dimension.spanA.y}" r="3" fill="#ffffff" stroke="#6d28d9" stroke-width="2"/>`);
    parts.push(`<circle cx="${dimension.spanB.x}" cy="${dimension.spanB.y}" r="3" fill="#ffffff" stroke="#6d28d9" stroke-width="2"/>`);
    parts.push(`<text x="${mx}" y="${my-7}" text-anchor="middle" fill="#6d28d9" font-size="11" font-weight="700" style="font-family:Arial,Tahoma,sans-serif;unicode-bidi:plaintext">${label}</text>`);
  }

  for(const room of plan.rooms){
    if(!room.polygon.length)continue;
    const metrics=roomMetrics(room,plan.metersPerPixel);
    const showMetrics=Boolean(plan.metersPerPixel)&&metrics.widthPx>=70&&metrics.heightPx>=55;
    const title=escapeXml(room.name||"غرفة");
    parts.push(`<text x="${metrics.cx}" y="${metrics.cy}" text-anchor="middle" dominant-baseline="middle" fill="#334155" font-size="16" font-weight="700" style="font-family:Arial,Tahoma,sans-serif;direction:rtl;unicode-bidi:plaintext">`);
    parts.push(`<tspan x="${metrics.cx}" dy="${showMetrics?-10:0}">${title}</tspan>`);
    if(showMetrics&&metrics.widthM!==null&&metrics.heightM!==null){
      parts.push(`<tspan x="${metrics.cx}" dy="18" fill="#2563eb" font-size="12">${metrics.widthM.toFixed(2)} × ${metrics.heightM.toFixed(2)} م</tspan>`);
      if(metrics.areaM2!==null)parts.push(`<tspan x="${metrics.cx}" dy="16" fill="#64748b" font-size="10">${metrics.areaM2.toFixed(1)} م²</tspan>`);
    }
    parts.push("</text>");
  }

  parts.push("</svg>");
  return parts.join("");
}

function downloadBlob(filename:string,blob:Blob){
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement("a");
  anchor.href=url;
  anchor.download=filename;
  anchor.style.display="none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),1500);
}

export function exportPlanJson(plan:FloorPlanModel,projectName:string){
  const body=JSON.stringify(plan,null,2);
  downloadBlob(`${safeFileName(projectName)}.manzil.json`,new Blob([body],{type:"application/json;charset=utf-8"}));
}

export function exportPlanSvg(plan:FloorPlanModel,projectName:string){
  const svg=planToSvg(plan);
  downloadBlob(`${safeFileName(projectName)}.svg`,new Blob([svg],{type:"image/svg+xml;charset=utf-8"}));
}

export async function exportPlanPng(plan:FloorPlanModel,projectName:string){
  const svg=planToSvg(plan);
  const blob=new Blob([svg],{type:"image/svg+xml;charset=utf-8"});
  const url=URL.createObjectURL(blob);
  try{
    const image=new Image();
    image.decoding="async";
    image.src=url;
    await new Promise<void>((resolve,reject)=>{
      image.onload=()=>resolve();
      image.onerror=()=>reject(new Error("PNG_RENDER_FAILED"));
    });

    const longest=Math.max(plan.widthPx,plan.heightPx,1);
    const scale=Math.max(1,Math.min(2,4096/longest));
    const width=Math.max(1,Math.round(plan.widthPx*scale));
    const height=Math.max(1,Math.round(plan.heightPx*scale));
    const canvas=document.createElement("canvas");
    canvas.width=width;
    canvas.height=height;
    const context=canvas.getContext("2d");
    if(!context)throw new Error("CANVAS_UNAVAILABLE");
    context.fillStyle="#ffffff";
    context.fillRect(0,0,width,height);
    context.drawImage(image,0,0,width,height);
    const png=await new Promise<Blob>((resolve,reject)=>{
      canvas.toBlob(result=>result?resolve(result):reject(new Error("PNG_ENCODE_FAILED")),"image/png",1);
    });
    downloadBlob(`${safeFileName(projectName)}.png`,png);
  }finally{
    URL.revokeObjectURL(url);
  }
}
