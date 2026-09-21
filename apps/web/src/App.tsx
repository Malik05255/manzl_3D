import { useEffect,useMemo,useRef,useState } from "react";
import { ArrowLeft,BrainCircuit,Check,ChevronLeft,Cloud,FileImage,FileText,Hammer,Layers3,LoaderCircle,Save,Sparkles,Undo2,UploadCloud,WandSparkles } from "lucide-react";
import type { EditProposal,FloorPlanModel,Point,ProjectView } from "@manzil/contracts";
import { applyProposal,askEngineer,createProject,getProject,getProjectPreview,saveRevision,uploadSource } from "./api";
import { PlanCanvas } from "./PlanCanvas";
import { useAppUpdate } from "./useAppUpdate";

type Screen="home"|"choice"|"upload"|"processing"|"editor";
const phaseLabels:Record<string,string>={
  created:"تجهيز المشروع",upload:"رفع المخطط إلى السحابة",preprocess:"تهيئة الصورة وتصحيحها",
  ocr:"قراءة النصوص والأبعاد",geometry:"استخراج الجدران والهندسة",rooms:"فهم الغرف والعلاقات",
  validation:"مراجعة النتيجة والتحقق منها",ready:"اكتمل التحليل",error:"تعذر إكمال التحليل"
};

function Brand({compact=false}:{compact?:boolean}){return <div className={`brand ${compact?"brand-compact":""}`}><img src="/icon.svg" alt=""/><div><strong>منزل H</strong>{!compact&&<span>محرر المخططات الذكي</span>}</div></div>;}
function UpdateBanner({onInstall}:{onInstall:()=>void}){return <div className="update-banner"><span>يتوفر إصدار أحدث من منزل H.</span><button onClick={onInstall}>تثبيت التحديث</button></div>;}

function Home({onStart}:{onStart:()=>void}){return <main className="landing">
  <header className="landing-header"><Brand/></header>
  <section className="hero">
    <div className="hero-copy"><span className="eyebrow"><Cloud size={16}/> معالجة سحابية</span><h1>عدّل مخططك كما تفكر فيه.</h1><p>ارفع المخطط، راجعه بصريًا، ثم عدّله يدويًا أو اطلب من H Engineer اقتراح التغيير مع أثره قبل التنفيذ.</p><button className="primary giant" onClick={onStart}>ابنِ مشروعك <ChevronLeft size={20}/></button></div>
    <div className="hero-board" aria-hidden="true"><div className="mock-plan"><div className="mock-room room-a">غرفة نوم</div><div className="mock-room room-b">صالة</div><div className="mock-room room-c">مطبخ</div><div className="mock-ai"><WandSparkles size={18}/> كبّر غرفة النوم إلى 5×5</div></div></div>
  </section>
</main>;}

function Choice({onEdit,onBack}:{onEdit:()=>void;onBack:()=>void}){return <main className="center-page">
  <div className="top-inline"><button className="ghost" onClick={onBack}><ArrowLeft size={18}/> رجوع</button><Brand compact/></div>
  <section className="choice-card"><h2>ماذا تريد أن تفعل؟</h2><div className="choice-grid">
    <button className="choice disabled" disabled><Hammer size={28}/><strong>مشروع جديد</strong><span>سيضاف لاحقًا فوق نفس المحرك الهندسي.</span></button>
    <button className="choice active" onClick={onEdit}><Layers3 size={28}/><strong>تعديل مشروع</strong><span>ارفع مخطط PDF أو صورة وحوّله إلى مشروع قابل للتعديل.</span></button>
  </div></section>
</main>;}

function Upload({onStarted,onBack}:{onStarted:(p:ProjectView)=>void;onBack:()=>void}){
  const input=useRef<HTMLInputElement|null>(null);const[busy,setBusy]=useState(false);const[pct,setPct]=useState(0);const[error,setError]=useState<string|null>(null);
  const handle=async(file?:File)=>{if(!file)return;const allowed=["application/pdf","image/png","image/jpeg","image/webp"];if(!allowed.includes(file.type)){setError("الملف يجب أن يكون PDF أو صورة PNG/JPG/WEBP.");return;}setBusy(true);setError(null);try{const p=await createProject(file.name.replace(/\.[^.]+$/,""));await uploadSource(p.id,file,setPct);onStarted({...p,status:"queued",phase:"upload",progress:10});}catch(e){setError(e instanceof Error?e.message:"حدث خطأ غير متوقع");setBusy(false);}};
  return <main className="center-page"><div className="top-inline"><button className="ghost" onClick={onBack}><ArrowLeft size={18}/> رجوع</button><Brand compact/></div>
    <section className="upload-card"><span className="eyebrow"><Sparkles size={16}/> تعديل مخطط قائم</span><h2>ارفع المخطط</h2><p>PDF أو صورة واضحة. تبدأ المعالجة السحابية فور اكتمال الرفع.</p>
      <button className="drop-zone" onClick={()=>input.current?.click()} disabled={busy}>{busy?<LoaderCircle className="spin" size={44}/>:<UploadCloud size={44}/>}<strong>{busy?`جارٍ الرفع ${pct}%`:"اختر ملفًا من جهازك"}</strong><span>PDF · PNG · JPG · WEBP</span></button>
      <input ref={input} hidden type="file" accept=".pdf,image/png,image/jpeg,image/webp" onChange={e=>handle(e.target.files?.[0])}/>{error&&<div className="error-box">{error}</div>}
    </section>
  </main>;
}

function Processing({projectId,onReady}:{projectId:string;onReady:(p:ProjectView)=>void}){
  const[project,setProject]=useState<ProjectView|null>(null);
  useEffect(()=>{let alive=true;const poll=async()=>{try{const next=await getProject(projectId);if(!alive)return;setProject(next);if(next.status==="ready"&&next.plan){onReady(next);return;}}catch{}if(alive)window.setTimeout(poll,1200);};poll();return()=>{alive=false;};},[projectId,onReady]);
  const progress=Math.max(0,Math.min(100,project?.progress??10));
  return <main className="processing-page"><Brand/><section className="processing-card">
    <div className="progress-ring" style={{"--p":`${progress*3.6}deg`} as React.CSSProperties}><div><strong>{progress}%</strong><span>تحليل حقيقي</span></div></div>
    <h2>{phaseLabels[project?.phase??"upload"]}</h2><p>{project?.message??"نعالج المخطط ونبني نموذجًا هندسيًا قابلًا للتعديل."}</p>
    {project?.status==="error"&&<div className="error-box">{project.error??"تعذر تحليل المخطط."}</div>}
    <div className="stage-list">{["preprocess","ocr","geometry","rooms","validation"].map(p=><span key={p} className={project?.phase===p?"current":""}>{phaseLabels[p]}</span>)}</div>
  </section></main>;
}

function Editor({initialProject}:{initialProject:ProjectView}){
  const[project,setProject]=useState(initialProject);const[plan,setPlan]=useState<FloorPlanModel>(initialProject.plan!);const[savedPlan,setSavedPlan]=useState<FloorPlanModel>(initialProject.plan!);
  const[selectedWall,setSelectedWall]=useState<string|null>(null);const[command,setCommand]=useState("");const[thinking,setThinking]=useState(false);const[proposals,setProposals]=useState<EditProposal[]>([]);const[preview,setPreview]=useState<EditProposal|null>(null);const[saving,setSaving]=useState(false);const[notice,setNotice]=useState<string|null>(null);
  const[calibrating,setCalibrating]=useState(false);const[calibrationPoints,setCalibrationPoints]=useState<Point[]>([]);const[knownDistance,setKnownDistance]=useState("");
  const[sourcePreview,setSourcePreview]=useState<string|null>(null);const[sourceOpacity,setSourceOpacity]=useState(.42);
  const dirty=useMemo(()=>JSON.stringify(plan)!==JSON.stringify(savedPlan),[plan,savedPlan]);

  useEffect(()=>{
    let active=true;let objectUrl:string|null=null;
    getProjectPreview(project.id).then(url=>{objectUrl=url;if(active)setSourcePreview(url);else if(url)URL.revokeObjectURL(url);}).catch(()=>undefined);
    return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[project.id]);
  const ask=async()=>{if(!command.trim())return;setThinking(true);setNotice(null);setPreview(null);try{const r=await askEngineer(project.id,command.trim());setProposals(r.proposals);if(r.needsClarification)setNotice(r.needsClarification);}catch(e){setNotice(e instanceof Error?e.message:"تعذر تحليل الطلب");}finally{setThinking(false);}};
  const save=async()=>{setSaving(true);try{const u=await saveRevision(project.id,plan,"تعديل يدوي");setProject(u);setSavedPlan(plan);setNotice("تم حفظ التعديل في السحابة.");}catch(e){setNotice(e instanceof Error?e.message:"تعذر الحفظ");}finally{setSaving(false);}};
  const apply=async()=>{if(!preview)return;setSaving(true);try{const u=await applyProposal(project.id,{command,proposal:preview});if(u.plan){setPlan(u.plan);setSavedPlan(u.plan);}setProject(u);setPreview(null);setProposals([]);setCommand("");setNotice("تم اعتماد التعديل وحفظ نسخة جديدة.");}catch(e){setNotice(e instanceof Error?e.message:"تعذر تطبيق التعديل");}finally{setSaving(false);}};
  const applyCalibration=()=>{
    if(calibrationPoints.length!==2)return;
    const meters=Number(knownDistance.replace(",","."));
    const [a,b]=calibrationPoints;
    const pixels=Math.hypot(b.x-a.x,b.y-a.y);
    if(!Number.isFinite(meters)||meters<=0||pixels<5){setNotice("أدخل المسافة الحقيقية بين النقطتين بالمتر.");return;}
    const mpp=meters/pixels;
    const rooms=plan.rooms.map(room=>{
      let area=0;
      for(let i=0;i<room.polygon.length;i++){const p=room.polygon[i],q=room.polygon[(i+1)%room.polygon.length];area+=p.x*q.y-q.x*p.y;}
      return {...room,areaM2:Number((Math.abs(area)/2*mpp*mpp).toFixed(2))};
    });
    setPlan({...plan,metersPerPixel:mpp,calibrationConfidence:1,rooms,quality:{...plan.quality,needsCalibration:false,dimensions:Math.max(plan.quality.dimensions,.95),warnings:plan.quality.warnings.filter(w=>!w.includes("مقياس الرسم"))}});
    setCalibrating(false);setCalibrationPoints([]);setKnownDistance("");setNotice("تم تثبيت المقياس. احفظ المشروع لتثبيت المعايرة.");
  };

  return <main className="editor-page">
    <header className="editor-header"><Brand compact/><div className="project-name"><FileText size={17}/><strong>{project.name}</strong></div><div className="editor-actions"><button className="ghost" disabled={!dirty} onClick={()=>setPlan(savedPlan)}><Undo2 size={17}/> تراجع</button><button className="primary small" disabled={!dirty||saving} onClick={save}><Save size={17}/> حفظ</button></div></header>
    <div className="editor-workspace">
      <section className="plan-panel"><div className="panel-title"><div><strong>منطقة التعديل</strong><span>اسحب جدارًا لتحريكه أو استخدم H Engineer</span></div><div className="panel-status">{sourcePreview&&<label className="overlay-control"><span>الأصل</span><input type="range" min="0" max=".85" step=".05" value={sourceOpacity} onChange={e=>setSourceOpacity(Number(e.target.value))}/></label>}<div className="quality-pill">جودة التحليل {Math.round(plan.quality.overall*100)}%</div></div></div>
        <PlanCanvas plan={preview?.previewPlan??plan} readonly={Boolean(preview)} selectedWallId={selectedWall} onSelectWall={setSelectedWall} onPlanChange={setPlan}
          calibrationMode={calibrating} calibrationPoints={calibrationPoints}
          onCalibrationPoint={point=>setCalibrationPoints(points=>points.length<2?[...points,point]:points)}
          backgroundUrl={sourcePreview} backgroundOpacity={sourceOpacity} comparisonPlan={preview?plan:null}/>
        {plan.quality.needsCalibration&&!calibrating&&<div className="inline-warning calibration-warning"><span>تعذر تثبيت المقياس تلقائيًا. ثبته مرة واحدة لتفعيل أوامر الأمتار بدقة.</span><button className="ghost" onClick={()=>{setCalibrating(true);setCalibrationPoints([]);}}>معايرة الآن</button></div>}
        {calibrating&&<div className="calibration-bar"><div><strong>معايرة المقياس</strong><span>{calibrationPoints.length<2?`حدد نقطتين على بُعد معروف · ${calibrationPoints.length}/2`:"أدخل المسافة الحقيقية بين النقطتين"}</span></div>{calibrationPoints.length===2&&<input inputMode="decimal" value={knownDistance} onChange={e=>setKnownDistance(e.target.value)} placeholder="مثال: 4.20 م"/>}<button className="ghost" onClick={()=>{setCalibrating(false);setCalibrationPoints([]);setKnownDistance("");}}>إلغاء</button>{calibrationPoints.length===2&&<button className="primary small" onClick={applyCalibration}><Check size={16}/> تثبيت</button>}</div>}
      </section>
      <aside className="ai-panel"><div className="ai-title"><div className="ai-avatar"><BrainCircuit size={22}/></div><div><strong>H Engineer</strong><span>يفهم الأثر قبل التنفيذ</span></div></div>
        <div className="prompt-box"><textarea value={command} onChange={e=>setCommand(e.target.value)} placeholder="مثال: عدّل غرفة النوم إلى 5×5"/><button className="primary" disabled={thinking||!command.trim()} onClick={ask}>{thinking?<LoaderCircle className="spin" size={18}/>:<Sparkles size={18}/>} تحليل الطلب</button></div>
        {notice&&<div className="notice-box">{notice}</div>}
        {!preview&&proposals.length>0&&<div className="proposal-list"><span className="section-caption">الخيارات الممكنة</span>{proposals.map(p=><button key={p.id} className="proposal-card" onClick={()=>setPreview(p)}><div><strong>{p.title}</strong><span>{p.summary}</span></div><ChevronLeft size={18}/></button>)}</div>}
        {preview&&<div className="preview-card"><span className="section-caption">معاينة قبل التنفيذ</span><h3>{preview.title}</h3><p>{preview.summary}</p><div className="impact-list">{preview.impacts.map((i,n)=><div key={n} className={`impact ${i.severity}`}><Check size={16}/><span>{i.text}</span></div>)}{preview.warnings.map((w,n)=><div key={n} className="impact warning"><span>!</span><span>{w}</span></div>)}</div><div className="preview-actions"><button className="ghost" onClick={()=>setPreview(null)}>اختر حلًا آخر</button><button className="primary" disabled={saving} onClick={apply}><Check size={17}/> اعتماد التعديل</button></div></div>}
        <div className="engine-info"><span><Cloud size={15}/> سحابي</span><span><FileImage size={15}/> المخطط الأصلي محفوظ</span></div>
      </aside>
    </div>
  </main>;
}

export default function App(){
  const[screen,setScreen]=useState<Screen>("home");const[project,setProject]=useState<ProjectView|null>(null);const{updateReady,installUpdate}=useAppUpdate();
  return <>{updateReady&&<UpdateBanner onInstall={installUpdate}/>}
    {screen==="home"&&<Home onStart={()=>setScreen("choice")}/>}
    {screen==="choice"&&<Choice onEdit={()=>setScreen("upload")} onBack={()=>setScreen("home")}/>}
    {screen==="upload"&&<Upload onBack={()=>setScreen("choice")} onStarted={p=>{setProject(p);setScreen("processing");}}/>}
    {screen==="processing"&&project&&<Processing projectId={project.id} onReady={p=>{setProject(p);setScreen("editor");}}/>}
    {screen==="editor"&&project?.plan&&<Editor initialProject={project}/>}
  </>;
}
