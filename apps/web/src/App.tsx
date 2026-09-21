import { useEffect,useMemo,useRef,useState } from "react";
import { ArrowLeft,BrainCircuit,Check,ChevronLeft,Clock3,Cloud,DoorOpen,Download,FileImage,FileText,Hammer,Layers3,LoaderCircle,Redo2,Ruler,Save,ShieldCheck,Sparkles,Square,Trash2,Undo2,UploadCloud,WandSparkles,X } from "lucide-react";
import type { EditProposal,FloorPlanModel,Opening,Point,ProjectView,RevisionView,ValidationReport } from "@manzil/contracts";
import { ApiError,applyProposal,askEngineer,clearProjectDraft,createProject,forgetKnownProject,forgetLastProject,getKnownProjects,getLastProjectId,getProject,getProjectPreview,importProjectBackup,inferSourceMime,listRevisions,resizeRoomPrecisely,restoreRevision,saveDraft,saveRevision,uploadSource,validateProject } from "./api";
import type { KnownProject } from "./api";
import { PlanCanvas } from "./PlanCanvas";
import { exportPlanJson,exportPlanPng,exportPlanSvg } from "./exportPlan";
import { parsePlanBackup } from "./planBackup";
import { addOpeningToWall,changeOpeningKind,findOpening,openingMetrics,positionOpening,removeOpening,resizeOpening } from "./openingGeometry";
import { useAppUpdate } from "./useAppUpdate";

function validationFromApiError(error:unknown):ValidationReport|null{
  if(!(error instanceof ApiError)||!error.data||typeof error.data!=="object")return null;
  const value=(error.data as {validation?:unknown}).validation;
  if(!value||typeof value!=="object")return null;
  const report=value as Partial<ValidationReport>;
  return typeof report.score==="number"&&Array.isArray(report.findings)?report as ValidationReport:null;
}

type Screen="home"|"choice"|"upload"|"processing"|"editor";
const phaseLabels:Record<string,string>={
  created:"تجهيز المشروع",upload:"رفع المخطط إلى السحابة",preprocess:"تهيئة الصورة وتصحيحها",
  ocr:"قراءة النصوص والأبعاد",geometry:"استخراج الجدران والهندسة",rooms:"فهم الغرف والعلاقات",
  validation:"مراجعة النتيجة والتحقق منها",ready:"اكتمل التحليل",error:"تعذر إكمال التحليل"
};

function Brand({compact=false}:{compact?:boolean}){return <div className={`brand ${compact?"brand-compact":""}`}><img src="/icon.svg" alt=""/><div><strong>منزل H</strong>{!compact&&<span>محرر المخططات الذكي</span>}</div></div>;}
function UpdateBanner({onInstall}:{onInstall:()=>void}){return <div className="update-banner"><span>يتوفر إصدار أحدث من منزل H.</span><button onClick={onInstall}>تثبيت التحديث</button></div>;}

function Home({onStart,onResume,resumeAvailable,resumeBusy,projects,onOpenProject,openingProjectId,openError}:{onStart:()=>void;onResume:()=>void;resumeAvailable:boolean;resumeBusy:boolean;projects:KnownProject[];onOpenProject:(id:string)=>void;openingProjectId:string|null;openError:string|null}){return <main className="landing">
  <header className="landing-header"><Brand/></header>
  <section className="hero">
    <div className="hero-copy"><span className="eyebrow"><Cloud size={16}/> معالجة سحابية</span><h1>عدّل مخططك كما تفكر فيه.</h1><p>ارفع المخطط، راجعه بصريًا، ثم عدّله يدويًا أو اطلب من H Engineer اقتراح التغيير مع أثره قبل التنفيذ.</p><div className="hero-actions"><button className="primary giant" onClick={onStart}>ابنِ مشروعك <ChevronLeft size={20}/></button>{resumeAvailable&&<button className="ghost giant resume-button" disabled={resumeBusy} onClick={onResume}>{resumeBusy?<LoaderCircle className="spin" size={19}/>:<Layers3 size={19}/>} استكمال آخر مشروع</button>}</div></div>
    <div className="hero-board" aria-hidden="true"><div className="mock-plan"><div className="mock-room room-a">غرفة نوم</div><div className="mock-room room-b">صالة</div><div className="mock-room room-c">مطبخ</div><div className="mock-ai"><WandSparkles size={18}/> كبّر غرفة النوم إلى 5×5</div></div></div>
  </section>
  {(projects.length>0||openError)&&<section className="recent-projects">{openError&&<div className="error-box recent-error">{openError}</div>}<div className="recent-head"><div><strong>مشاريعك على هذا الجهاز</strong><span>تُحفظ صلاحية كل مشروع محليًا، بينما المخطط نفسه محفوظ سحابيًا.</span></div></div><div className="recent-grid">{projects.slice(0,6).map(item=><button className="recent-card" key={item.id} disabled={openingProjectId===item.id} onClick={()=>onOpenProject(item.id)}><div className="recent-icon">{openingProjectId===item.id?<LoaderCircle className="spin" size={20}/>:<Layers3 size={20}/>}</div><div><strong>{item.name}</strong><span>{new Date(item.updatedAt).toLocaleString("ar-SA")}</span></div><ChevronLeft size={18}/></button>)}</div></section>}
</main>;}

function Choice({onEdit,onBack}:{onEdit:()=>void;onBack:()=>void}){return <main className="center-page">
  <div className="top-inline"><button className="ghost" onClick={onBack}><ArrowLeft size={18}/> رجوع</button><Brand compact/></div>
  <section className="choice-card"><h2>ماذا تريد أن تفعل؟</h2><div className="choice-grid">
    <button className="choice disabled" disabled><Hammer size={28}/><strong>مشروع جديد</strong><span>سيضاف لاحقًا فوق نفس المحرك الهندسي.</span></button>
    <button className="choice active" onClick={onEdit}><Layers3 size={28}/><strong>تعديل مشروع</strong><span>ارفع مخطط PDF أو صورة وحوّله إلى مشروع قابل للتعديل.</span></button>
  </div></section>
</main>;}

function Upload({onStarted,onBack}:{onStarted:(p:ProjectView)=>void;onBack:()=>void}){
  const input=useRef<HTMLInputElement|null>(null);const[busy,setBusy]=useState(false);const[pct,setPct]=useState(0);const[error,setError]=useState<string|null>(null);const[mode,setMode]=useState<"upload"|"backup">("upload");
  const handle=async(file?:File)=>{
    if(!file)return;
    const backup=file.name.toLowerCase().endsWith(".json")||file.type==="application/json";
    const sourceMime=inferSourceMime(file);
    if(!backup&&!sourceMime){setError("الملف يجب أن يكون PDF أو PNG/JPG/WEBP أو نسخة مشروع JSON.");return;}
    setBusy(true);setPct(0);setMode(backup?"backup":"upload");setError(null);
    try{
      const name=file.name.replace(/\.(manzil\.)?json$/i,"").replace(/\.[^.]+$/,"")||"مخطط مستورد";
      if(backup){
        const parsed=parsePlanBackup(await file.text());
        const ready=await importProjectBackup(name,parsed);
        onStarted(ready);
        return;
      }
      const p=await createProject(name);
      await uploadSource(p.id,file,setPct);
      onStarted({...p,status:"queued",phase:"upload",progress:10});
    }catch(e){
      const code=e instanceof Error?e.message:"";
      const backupErrors=new Set(["BACKUP_TOO_LARGE","BACKUP_INVALID_JSON","BACKUP_SCHEMA","BACKUP_ID","BACKUP_SIZE","BACKUP_SCALE","BACKUP_CALIBRATION","BACKUP_WALLS","BACKUP_ROOMS","BACKUP_DOORS","BACKUP_WINDOWS","BACKUP_LABELS","BACKUP_QUALITY","BACKUP_SOURCE","BACKUP_DUPLICATE_IDS"]);
      setError(backupErrors.has(code)?"نسخة المشروع غير صالحة أو غير متوافقة مع منزل H.":e instanceof Error?e.message:"حدث خطأ غير متوقع");
      setBusy(false);
    }
  };
  return <main className="center-page"><div className="top-inline"><button className="ghost" onClick={onBack}><ArrowLeft size={18}/> رجوع</button><Brand compact/></div>
    <section className="upload-card"><span className="eyebrow"><Sparkles size={16}/> تعديل مخطط قائم</span><h2>ارفع المخطط</h2><p>ارفع PDF أو صورة للتحليل، أو استعد نسخة مشروع JSON سبق تصديرها من منزل H.</p>
      <button className="drop-zone" onClick={()=>input.current?.click()} disabled={busy}>{busy?<LoaderCircle className="spin" size={44}/>:<UploadCloud size={44}/>}<strong>{busy?(mode==="backup"?"جارٍ استعادة المشروع...":`جارٍ الرفع ${pct}%`):"اختر ملفًا من جهازك"}</strong><span>PDF · PNG · JPG · WEBP · JSON</span></button>
      <input ref={input} hidden type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.json,application/pdf,application/json,image/png,image/jpeg,image/webp" onChange={e=>handle(e.target.files?.[0])}/>{error&&<div className="error-box">{error}</div>}
    </section>
  </main>;
}

function Processing({projectId,onReady,onHome}:{projectId:string;onReady:(p:ProjectView)=>void;onHome:()=>void}){
  const[project,setProject]=useState<ProjectView|null>(null);
  useEffect(()=>{let alive=true;const poll=async()=>{try{const next=await getProject(projectId);if(!alive)return;setProject(next);if(next.status==="ready"&&next.plan){onReady(next);return;}if(next.status==="error")return;}catch{}if(alive)window.setTimeout(poll,1200);};poll();return()=>{alive=false;};},[projectId,onReady]);
  const progress=Math.max(0,Math.min(100,project?.progress??10));
  return <main className="processing-page"><Brand/><section className="processing-card">
    <div className="progress-ring" style={{"--p":`${progress*3.6}deg`} as React.CSSProperties}><div><strong>{progress}%</strong><span>تحليل حقيقي</span></div></div>
    <h2>{phaseLabels[project?.phase??"upload"]}</h2><p>{project?.message??"نعالج المخطط ونبني نموذجًا هندسيًا قابلًا للتعديل."}</p>
    {project?.status==="error"&&<div className="error-box processing-error"><span>{project.error??"تعذر تحليل المخطط."}</span><button className="ghost" onClick={onHome}>العودة للرئيسية</button></div>}
    <div className="stage-list">{["preprocess","ocr","geometry","rooms","validation"].map(p=><span key={p} className={project?.phase===p?"current":""}>{phaseLabels[p]}</span>)}</div>
  </section></main>;
}

function Editor({initialProject,onHome}:{initialProject:ProjectView;onHome:()=>void}){
  const[project,setProject]=useState(initialProject);const[plan,setPlan]=useState<FloorPlanModel>(initialProject.plan!);const[savedPlan,setSavedPlan]=useState<FloorPlanModel>(initialProject.plan!);const[undoStack,setUndoStack]=useState<FloorPlanModel[]>([]);const[redoStack,setRedoStack]=useState<FloorPlanModel[]>([]);
  const[selectedWall,setSelectedWall]=useState<string|null>(null);const[selectedRoom,setSelectedRoom]=useState<string|null>(null);const[selectedOpening,setSelectedOpening]=useState<string|null>(null);const[openingWidth,setOpeningWidth]=useState("");const[openingPosition,setOpeningPosition]=useState(50);const[exactName,setExactName]=useState("");const[exactWidth,setExactWidth]=useState("");const[exactHeight,setExactHeight]=useState("");const[command,setCommand]=useState("");const[thinking,setThinking]=useState(false);const[proposals,setProposals]=useState<EditProposal[]>([]);const[preview,setPreview]=useState<EditProposal|null>(null);const[saving,setSaving]=useState(false);const[notice,setNotice]=useState<string|null>(null);
  const[calibrating,setCalibrating]=useState(false);const[calibrationPoints,setCalibrationPoints]=useState<Point[]>([]);const[knownDistance,setKnownDistance]=useState("");
  const[sourcePreview,setSourcePreview]=useState<string|null>(null);const[sourceOpacity,setSourceOpacity]=useState(.42);
  const[historyOpen,setHistoryOpen]=useState(false);const[historyBusy,setHistoryBusy]=useState(false);const[revisions,setRevisions]=useState<RevisionView[]>([]);const[exportOpen,setExportOpen]=useState(false);const[exportBusy,setExportBusy]=useState(false);
  const[validationReport,setValidationReport]=useState<ValidationReport|null>(null);const[validationBusy,setValidationBusy]=useState(false);const[draftState,setDraftState]=useState<"idle"|"saving"|"saved"|"error">(initialProject.hasDraft?"saved":"idle");const[recoveredDraft,setRecoveredDraft]=useState(initialProject.hasDraft);
  const draftGeneration=useRef(0);const draftChain=useRef<Promise<void>>(Promise.resolve());
  const localDirty=useMemo(()=>JSON.stringify(plan)!==JSON.stringify(savedPlan),[plan,savedPlan]);
  const dirty=localDirty||recoveredDraft;
  const enqueueDraft=(snapshot:FloorPlanModel,revision:number,generation:number)=>{
    const run=async()=>{
      if(generation!==draftGeneration.current)return;
      setDraftState("saving");
      try{
        const synced=await saveDraft(project.id,snapshot,revision);
        if(generation===draftGeneration.current){
          setProject(current=>({...current,...synced,plan:current.plan,hasDraft:true}));
          setDraftState("saved");
        }
      }catch(error){
        if(generation===draftGeneration.current)setDraftState("error");
        throw error;
      }
    };
    const queued=draftChain.current.catch(()=>undefined).then(run);
    draftChain.current=queued.catch(()=>undefined);
    return queued;
  };
  const syncPlanForEngineer=async()=>{
    if(!localDirty)return;
    const generation=++draftGeneration.current;
    await draftChain.current.catch(()=>undefined);
    await enqueueDraft(plan,project.revision,generation);
  };
  const applyLocalPlan=(next:FloorPlanModel,recordHistory=true)=>{
    if(recordHistory){
      setUndoStack(stack=>[...stack.slice(-49),plan]);
      setRedoStack([]);
    }
    setPlan(next);
  };
  const commitTransientPlan=(basePlan:FloorPlanModel)=>{
    if(JSON.stringify(basePlan)===JSON.stringify(plan))return;
    setUndoStack(stack=>[...stack.slice(-49),basePlan]);
    setRedoStack([]);
  };
  const undoLocal=()=>{
    const previous=undoStack.at(-1);
    if(!previous)return;
    setUndoStack(stack=>stack.slice(0,-1));
    setRedoStack(stack=>[...stack.slice(-49),plan]);
    setPlan(previous);setSelectedWall(null);setSelectedRoom(null);setSelectedOpening(null);setPreview(null);setProposals([]);
  };
  const redoLocal=()=>{
    const next=redoStack.at(-1);
    if(!next)return;
    setRedoStack(stack=>stack.slice(0,-1));
    setUndoStack(stack=>[...stack.slice(-49),plan]);
    setPlan(next);setSelectedWall(null);setSelectedRoom(null);setSelectedOpening(null);setPreview(null);setProposals([]);
  };
  const selectRoom=(roomId:string|null)=>{
    setSelectedRoom(roomId);setSelectedWall(null);setSelectedOpening(null);setPreview(null);setProposals([]);
    const room=plan.rooms.find(item=>item.id===roomId);
    setExactName(room?.name??"");
    if(!room||!plan.metersPerPixel){setExactWidth("");setExactHeight("");return;}
    const xs=room.polygon.map(p=>p.x),ys=room.polygon.map(p=>p.y);
    setExactWidth(((Math.max(...xs)-Math.min(...xs))*plan.metersPerPixel).toFixed(2));
    setExactHeight(((Math.max(...ys)-Math.min(...ys))*plan.metersPerPixel).toFixed(2));
  };
  const selectOpening=(openingId:string|null)=>{
    setSelectedOpening(openingId);setSelectedRoom(null);setSelectedWall(null);setPreview(null);setProposals([]);
    if(!openingId){setOpeningWidth("");setOpeningPosition(50);return;}
    const metrics=openingMetrics(plan,openingId);
    setOpeningWidth(metrics?.widthM?.toFixed(2)??"");
    setOpeningPosition(Math.round(metrics?.positionPct??50));
  };
  const addOpening=(kind:Opening["kind"])=>{
    if(!selectedWall)return;
    const next=addOpeningToWall(plan,selectedWall,kind);
    if(!next){setNotice("لا توجد مساحة كافية على الجدار المحدد لإضافة فتحة جديدة.");return;}
    const beforeIds=new Set([...plan.doors,...plan.windows].map(item=>item.id));
    const created=[...next.doors,...next.windows].find(item=>!beforeIds.has(item.id));
    applyLocalPlan(next);setSelectedRoom(null);setSelectedWall(null);setNotice(kind==="door"?"تمت إضافة باب. اضبط عرضه وموقعه ثم احفظ.":"تمت إضافة نافذة. اضبط عرضها وموقعها ثم احفظ.");
    if(created)queueMicrotask(()=>selectOpening(created.id));
  };
  const updateOpeningWidth=()=>{
    if(!selectedOpening)return;
    const width=Number(openingWidth.replace(",","."));
    const next=resizeOpening(plan,selectedOpening,width);
    if(!next){setNotice("تعذر تطبيق العرض المطلوب على هذا الجدار.");return;}
    applyLocalPlan(next);
    const metrics=openingMetrics(next,selectedOpening);
    setOpeningWidth(metrics?.widthM?.toFixed(2)??openingWidth);
    setOpeningPosition(Math.round(metrics?.positionPct??openingPosition));
    setNotice("تم تحديث عرض الفتحة محليًا.");
  };
  const updateOpeningPosition=(position:number)=>{
    if(!selectedOpening)return;
    const next=positionOpening(plan,selectedOpening,position);
    if(!next)return;
    applyLocalPlan(next);setOpeningPosition(position);
  };
  const updateOpeningKind=(kind:Opening["kind"])=>{
    if(!selectedOpening)return;
    const next=changeOpeningKind(plan,selectedOpening,kind);
    if(!next)return;
    applyLocalPlan(next);setNotice(kind==="door"?"تم تصحيح الفتحة إلى باب.":"تم تصحيح الفتحة إلى نافذة.");
  };
  const deleteOpening=()=>{
    if(!selectedOpening)return;
    applyLocalPlan(removeOpening(plan,selectedOpening));setSelectedOpening(null);setOpeningWidth("");setNotice("تم حذف الفتحة محليًا. يمكنك التراجع قبل الحفظ.");
  };
  const renameSelectedRoom=()=>{
    const room=plan.rooms.find(item=>item.id===selectedRoom);
    const name=exactName.trim().replace(/\s+/g," ").slice(0,80);
    if(!room||!name||name===room.name)return;
    applyLocalPlan({...plan,rooms:plan.rooms.map(item=>item.id===room.id?{...item,name}:item)});
    setNotice("تم تحديث اسم الغرفة محليًا. احفظ المشروع لتثبيت التغيير.");
  };
  const precisePreview=async()=>{
    const room=plan.rooms.find(item=>item.id===selectedRoom);
    const width=Number(exactWidth.replace(",","."));
    const height=Number(exactHeight.replace(",","."));
    if(!room){setNotice("حدد غرفة من المخطط أولًا.");return;}
    if(!plan.metersPerPixel){setNotice("ثبّت مقياس المخطط أولًا.");return;}
    if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0){setNotice("أدخل العرض والطول بالمتر.");return;}
    const canonical=`عدل ${room.name} إلى ${width}×${height}`;
    setThinking(true);setNotice(null);setPreview(null);
    try{
      await syncPlanForEngineer();
      const result=await resizeRoomPrecisely(project.id,room.id,width,height);
      setCommand(canonical);setProposals(result.proposals);
      if(result.needsClarification)setNotice(result.needsClarification);
    }catch(e){setNotice(e instanceof Error?e.message:"تعذر إنشاء المعاينة الهندسية");}
    finally{setThinking(false);}
  };

  useEffect(()=>{
    let active=true;let objectUrl:string|null=null;
    getProjectPreview(project.id).then(url=>{objectUrl=url;if(active)setSourcePreview(url);else if(url)URL.revokeObjectURL(url);}).catch(()=>undefined);
    return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[project.id]);
  useEffect(()=>{
    if(!localDirty||preview)return;
    const generation=++draftGeneration.current;
    setDraftState("idle");
    const snapshot=plan;
    const revision=project.revision;
    const timer=window.setTimeout(()=>{
      void enqueueDraft(snapshot,revision,generation).catch(()=>undefined);
    },1400);
    return()=>window.clearTimeout(timer);
  },[plan,localDirty,preview,project.id,project.revision]);
  useEffect(()=>{
    if(localDirty||recoveredDraft||!project.hasDraft||preview)return;
    const generation=++draftGeneration.current;
    const timer=window.setTimeout(async()=>{
      await draftChain.current.catch(()=>undefined);
      if(generation!==draftGeneration.current)return;
      try{
        const synced=await clearProjectDraft(project.id,project.revision);
        if(generation===draftGeneration.current){
          setProject(current=>({...current,...synced,plan:current.plan,hasDraft:false}));
          setDraftState("idle");
        }
      }catch{if(generation===draftGeneration.current)setDraftState("error");}
    },350);
    return()=>window.clearTimeout(timer);
  },[localDirty,recoveredDraft,project.hasDraft,project.id,project.revision,preview]);
  useEffect(()=>{
    const handle=(event:KeyboardEvent)=>{
      const modifier=event.ctrlKey||event.metaKey;
      if(!modifier)return;
      const tag=(event.target as HTMLElement|null)?.tagName?.toLowerCase();
      if(tag==="input"||tag==="textarea"||tag==="select")return;
      if(event.key.toLowerCase()==="z"&&!event.shiftKey){event.preventDefault();undoLocal();}
      else if((event.key.toLowerCase()==="z"&&event.shiftKey)||event.key.toLowerCase()==="y"){event.preventDefault();redoLocal();}
    };
    window.addEventListener("keydown",handle);
    return()=>window.removeEventListener("keydown",handle);
  },[undoStack,redoStack,plan]);
  const ask=async()=>{if(!command.trim())return;setThinking(true);setNotice(null);setPreview(null);try{await syncPlanForEngineer();const r=await askEngineer(project.id,command.trim());setProposals(r.proposals);if(r.needsClarification)setNotice(r.needsClarification);}catch(e){setNotice(e instanceof Error?e.message:"تعذر تحليل الطلب");}finally{setThinking(false);}};
  const save=async()=>{setSaving(true);const generation=++draftGeneration.current;try{await draftChain.current.catch(()=>undefined);if(generation!==draftGeneration.current)return;const u=await saveRevision(project.id,plan,"تعديل يدوي",project.revision);setProject(u);setSavedPlan(plan);setRecoveredDraft(false);setDraftState("idle");setValidationReport(null);setNotice("تم حفظ التعديل في السحابة.");}catch(e){const report=validationFromApiError(e);if(report)setValidationReport(report);setNotice(e instanceof Error?e.message:"تعذر الحفظ");}finally{setSaving(false);}};
  const openHistory=async()=>{setHistoryOpen(true);setHistoryBusy(true);try{const r=await listRevisions(project.id);setRevisions(r.items);}catch(e){setNotice(e instanceof Error?e.message:"تعذر تحميل سجل النسخ");setHistoryOpen(false);}finally{setHistoryBusy(false);}};
  const runValidation=async()=>{setValidationBusy(true);setNotice(null);try{setValidationReport(await validateProject(project.id,plan));}catch(e){setNotice(e instanceof Error?e.message:"تعذر فحص المخطط");}finally{setValidationBusy(false);}};
  const runExport=async(format:"svg"|"png"|"json")=>{setExportBusy(true);setNotice(null);try{if(format==="svg")exportPlanSvg(plan,project.name);else if(format==="json")exportPlanJson(plan,project.name);else await exportPlanPng(plan,project.name);setExportOpen(false);}catch{setNotice("تعذر إنشاء ملف التصدير. جرّب صيغة أخرى.");}finally{setExportBusy(false);}};
  const restore=async(revision:number)=>{if(localDirty){setNotice("احفظ التغييرات الحالية أو تراجع عنها قبل استعادة نسخة سابقة.");return;}setSaving(true);++draftGeneration.current;try{await draftChain.current.catch(()=>undefined);const u=await restoreRevision(project.id,revision);if(u.plan){setPlan(u.plan);setSavedPlan(u.plan);setUndoStack([]);setRedoStack([]);}setProject(u);setRecoveredDraft(false);setHistoryOpen(false);setNotice(`تمت استعادة النسخة ${revision} كنسخة جديدة محفوظة.`);}catch(e){setNotice(e instanceof Error?e.message:"تعذر استعادة النسخة");}finally{setSaving(false);}};
  const apply=async()=>{if(!preview)return;setSaving(true);++draftGeneration.current;try{await draftChain.current.catch(()=>undefined);const u=await applyProposal(project.id,{command,proposal:preview});if(u.plan){setPlan(u.plan);setSavedPlan(u.plan);setUndoStack([]);setRedoStack([]);}setProject(u);setRecoveredDraft(false);setPreview(null);setProposals([]);setCommand("");setSelectedRoom(null);setSelectedOpening(null);setExactName("");setExactWidth("");setExactHeight("");setValidationReport(null);setNotice("تم اعتماد التعديل وحفظ نسخة جديدة.");}catch(e){const report=validationFromApiError(e);if(report)setValidationReport(report);setNotice(e instanceof Error?e.message:"تعذر تطبيق التعديل");}finally{setSaving(false);}};
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
    applyLocalPlan({...plan,metersPerPixel:mpp,calibrationConfidence:1,rooms,quality:{...plan.quality,needsCalibration:false,dimensions:Math.max(plan.quality.dimensions,.95),warnings:plan.quality.warnings.filter(w=>!w.includes("مقياس الرسم"))}});
    setCalibrating(false);setCalibrationPoints([]);setKnownDistance("");setNotice("تم تثبيت المقياس. احفظ المشروع لتثبيت المعايرة.");
  };
  const discardRecoveredDraft=async()=>{
    setSaving(true);++draftGeneration.current;setNotice(null);
    try{
      await draftChain.current.catch(()=>undefined);
      await clearProjectDraft(project.id,project.revision);
      const fresh=await getProject(project.id);
      if(!fresh.plan)throw new Error("لا توجد نسخة محفوظة يمكن الرجوع إليها.");
      setProject(fresh);setPlan(fresh.plan);setSavedPlan(fresh.plan);setRecoveredDraft(false);setUndoStack([]);setRedoStack([]);setDraftState("idle");setNotice("تم تجاهل المسودة التلقائية والعودة إلى آخر نسخة محفوظة.");
    }catch(e){setNotice(e instanceof Error?e.message:"تعذر تجاهل المسودة.");}
    finally{setSaving(false);}
  };

  return <main className="editor-page">
    {exportOpen&&<div className="history-backdrop" onClick={()=>!exportBusy&&setExportOpen(false)}><section className="history-modal export-modal" onClick={e=>e.stopPropagation()}><div className="history-head"><div><strong>تصدير المخطط</strong><span>التصدير يستخدم النموذج الحالي كما يظهر بعد تعديلاتك، حتى لو لم تحفظ Revision بعد.</span></div><button className="icon-button" disabled={exportBusy} onClick={()=>setExportOpen(false)} aria-label="إغلاق"><X size={17}/></button></div><div className="export-grid"><button className="export-option" disabled={exportBusy} onClick={()=>void runExport("svg")}><FileText size={26}/><strong>SVG متجهي</strong><span>الأفضل للطباعة والتعديل لاحقًا دون فقدان الدقة.</span></button><button className="export-option" disabled={exportBusy} onClick={()=>void runExport("png")}><FileImage size={26}/><strong>PNG عالي الدقة</strong><span>صورة جاهزة للمشاركة والمعاينة.</span></button><button className="export-option" disabled={exportBusy} onClick={()=>void runExport("json")}><Layers3 size={26}/><strong>نسخة مشروع JSON</strong><span>يحفظ النموذج الهندسي الكامل للنسخ الاحتياطي والتكامل.</span></button></div>{exportBusy&&<div className="history-loading"><LoaderCircle className="spin" size={22}/> تجهيز الملف...</div>}</section></div>}
    {historyOpen&&<div className="history-backdrop" onClick={()=>setHistoryOpen(false)}><section className="history-modal" onClick={e=>e.stopPropagation()}><div className="history-head"><div><strong>سجل النسخ</strong><span>الاستعادة لا تحذف أي نسخة؛ تُنشئ نسخة جديدة من الحالة المختارة.</span></div><button className="icon-button" onClick={()=>setHistoryOpen(false)} aria-label="إغلاق"><X size={17}/></button></div>{localDirty&&<div className="inline-warning">لديك تغييرات محلية غير محفوظة. احفظها أو تراجع عنها قبل الاستعادة.</div>}{recoveredDraft&&!localDirty&&<div className="notice-box">أنت تعرض مسودة تلقائية مستعادة. يمكنك استعادة أي نسخة محفوظة دون أن تضيع من سجل النسخ.</div>}<div className="history-list">{historyBusy?<div className="history-loading"><LoaderCircle className="spin" size={24}/> تحميل النسخ...</div>:revisions.length?revisions.map((item,index)=><div className="history-item" key={item.revision}><div><strong>نسخة {item.revision}{index===0?" · الأحدث":""}</strong><span>{item.summary}</span><small>{new Date(item.createdAt).toLocaleString("ar-SA")}</small></div><button className="ghost" disabled={localDirty||saving||(!recoveredDraft&&index===0)} onClick={()=>restore(item.revision)}>{index===0?(recoveredDraft?"استعادة آخر حفظ":localDirty?"آخر حفظ":"الحالية"):"استعادة"}</button></div>):<div className="history-empty">لا توجد نسخ محفوظة بعد.</div>}</div></section></div>}
    <header className="editor-header"><Brand compact/><div className="project-name"><FileText size={17}/><strong>{project.name}</strong></div><div className="editor-actions"><button className="ghost" onClick={openHistory}><Clock3 size={17}/> النسخ</button><button className="ghost" onClick={onHome}><ArrowLeft size={17}/> الرئيسية</button><button className="ghost" disabled={!undoStack.length} onClick={undoLocal}><Undo2 size={17}/> تراجع</button><button className="ghost" disabled={!redoStack.length} onClick={redoLocal}><Redo2 size={17}/> إعادة</button><button className="primary small" disabled={!dirty||saving} onClick={save}><Save size={17}/> حفظ</button></div></header>
    <div className="editor-workspace">
      <section className="plan-panel"><div className="panel-title"><div><strong>منطقة التعديل</strong><span>اسحب جدارًا لتحريكه أو استخدم H Engineer</span></div><div className="panel-status"><span className={`draft-pill ${draftState}`}>{draftState==="saving"?"حفظ...":draftState==="saved"?"مسودة سحابية":draftState==="error"?"تعذر الحفظ":"سحابي"}</span><button className="validate-chip export-chip" onClick={()=>setExportOpen(true)}><Download size={14}/> تصدير</button>{sourcePreview&&<label className="overlay-control"><span>الأصل</span><input type="range" min="0" max=".85" step=".05" value={sourceOpacity} onChange={e=>setSourceOpacity(Number(e.target.value))}/></label>}<button className="validate-chip" disabled={validationBusy} onClick={runValidation}>{validationBusy?<LoaderCircle className="spin" size={14}/>:<ShieldCheck size={14}/>} فحص</button><div className="quality-pill">جودة التحليل {Math.round(plan.quality.overall*100)}%</div></div></div>
        {recoveredDraft&&<div className="recovered-draft"><div><strong>تمت استعادة مسودة تلقائية</strong><span>هذه التغييرات محفوظة سحابيًا لكنها ليست Revision رسمية بعد.</span></div><div><button className="ghost" disabled={saving} onClick={()=>void discardRecoveredDraft()}>تجاهل المسودة</button><button className="primary small" disabled={saving} onClick={save}><Save size={15}/> حفظ كنسخة</button></div></div>}
        <PlanCanvas plan={preview?.previewPlan??plan} readonly={Boolean(preview)} selectedWallId={selectedWall} onSelectWall={id=>{setSelectedWall(id);if(id){setSelectedRoom(null);setSelectedOpening(null);}}} selectedRoomId={selectedRoom} onSelectRoom={selectRoom} selectedOpeningId={selectedOpening} onSelectOpening={selectOpening} onPlanChange={applyLocalPlan} onPlanCommit={commitTransientPlan}
          calibrationMode={calibrating} calibrationPoints={calibrationPoints}
          onCalibrationPoint={point=>setCalibrationPoints(points=>points.length<2?[...points,point]:points)}
          backgroundUrl={sourcePreview} backgroundOpacity={sourceOpacity} comparisonPlan={preview?plan:null} validationFindings={validationReport?.findings??[]}/>
        {plan.quality.needsCalibration&&!calibrating&&<div className="inline-warning calibration-warning"><span>تعذر تثبيت المقياس تلقائيًا. ثبته مرة واحدة لتفعيل أوامر الأمتار بدقة.</span><button className="ghost" onClick={()=>{setCalibrating(true);setCalibrationPoints([]);}}>معايرة الآن</button></div>}
        {calibrating&&<div className="calibration-bar"><div><strong>معايرة المقياس</strong><span>{calibrationPoints.length<2?`حدد نقطتين على بُعد معروف · ${calibrationPoints.length}/2`:"أدخل المسافة الحقيقية بين النقطتين"}</span></div>{calibrationPoints.length===2&&<input inputMode="decimal" value={knownDistance} onChange={e=>setKnownDistance(e.target.value)} placeholder="مثال: 4.20 م"/>}<button className="ghost" onClick={()=>{setCalibrating(false);setCalibrationPoints([]);setKnownDistance("");}}>إلغاء</button>{calibrationPoints.length===2&&<button className="primary small" onClick={applyCalibration}><Check size={16}/> تثبيت</button>}</div>}
      </section>
      <aside className="ai-panel"><div className="ai-title"><div className="ai-avatar"><BrainCircuit size={22}/></div><div><strong>H Engineer</strong><span>يفهم الأثر قبل التنفيذ</span></div></div>
        {validationReport&&<div className="validation-card"><div className="validation-summary"><div><strong>الفحص الهندسي الداخلي</strong><span>سلامة النموذج {Math.round(validationReport.score*100)}%</span></div><div className={`validation-score ${validationReport.findings.some(item=>item.severity==="critical")?"bad":validationReport.findings.length?"warn":"good"}`}>{Math.round(validationReport.score*100)}</div></div>{validationReport.findings.length?<div className="validation-findings">{validationReport.findings.slice(0,6).map((item,index)=><button type="button" key={`${item.code}-${index}`} className={`validation-finding ${item.severity} ${item.roomIds.length?"clickable":""}`} disabled={!item.roomIds.length} onClick={()=>item.roomIds[0]&&selectRoom(item.roomIds[0])}><span>{item.severity==="critical"?"!":"•"}</span><p>{item.text}</p></button>)}</div>:<div className="validation-clean"><Check size={16}/> لا توجد مشاكل هندسية واضحة في النموذج الحالي.</div>}<small>هذا فحص اتساق واستخدام داخلي، وليس اعتمادًا لكود البناء.</small></div>}
        {selectedWall&&<div className="opening-add-card"><div><strong>الجدار محدد</strong><span>أضف فتحة في أكبر مساحة خالية على الجدار.</span></div><div><button className="ghost" disabled={Boolean(preview)} onClick={()=>addOpening("door")}><DoorOpen size={16}/> إضافة باب</button><button className="ghost" disabled={Boolean(preview)} onClick={()=>addOpening("window")}><Square size={15}/> إضافة نافذة</button></div></div>}
        {selectedOpening&&findOpening(plan,selectedOpening)&&<div className="opening-editor"><div className="precise-title"><div><strong>تعديل الفتحة</strong><span>صحح النوع والعرض والموقع على الجدار</span></div>{findOpening(plan,selectedOpening)?.kind==="door"?<DoorOpen size={19}/>:<Square size={18}/>}</div><div className="opening-kind"><button className={findOpening(plan,selectedOpening)?.kind==="door"?"active":""} onClick={()=>updateOpeningKind("door")}>باب</button><button className={findOpening(plan,selectedOpening)?.kind==="window"?"active":""} onClick={()=>updateOpeningKind("window")}>نافذة</button></div><label className="opening-width"><span>العرض بالمتر</span><div><input inputMode="decimal" disabled={!plan.metersPerPixel} value={openingWidth} onChange={e=>setOpeningWidth(e.target.value)} placeholder={plan.metersPerPixel?"0.90":"ثبّت المقياس"}/><button className="ghost" disabled={!plan.metersPerPixel||!openingWidth} onClick={updateOpeningWidth}>تطبيق</button></div></label><label className="opening-position"><span>الموقع على الجدار · {openingPosition}%</span><input type="range" min="2" max="98" step="1" value={openingPosition} onChange={e=>updateOpeningPosition(Number(e.target.value))}/></label><button className="delete-opening" onClick={deleteOpening}><Trash2 size={15}/> حذف الفتحة</button></div>}
        <div className="precise-editor"><div className="precise-title"><div><strong>تعديل دقيق</strong><span>اختر الغرفة ثم أدخل المقاس بالمتر</span></div><Ruler size={19}/></div>
          <select value={selectedRoom??""} onChange={e=>selectRoom(e.target.value||null)}><option value="">اختر غرفة</option>{plan.rooms.map(room=><option key={room.id} value={room.id}>{room.name}</option>)}</select>
          {selectedRoom&&<div className="room-name-edit"><label><span>اسم الغرفة</span><input value={exactName} onChange={e=>setExactName(e.target.value)} maxLength={80}/></label><button className="ghost" disabled={!exactName.trim()||exactName.trim()===plan.rooms.find(room=>room.id===selectedRoom)?.name||Boolean(preview)} onClick={renameSelectedRoom}>تحديث</button></div>}
          <div className="dimension-grid"><label><span>العرض</span><input inputMode="decimal" value={exactWidth} onChange={e=>setExactWidth(e.target.value)} placeholder="5.00"/></label><label><span>الطول</span><input inputMode="decimal" value={exactHeight} onChange={e=>setExactHeight(e.target.value)} placeholder="4.00"/></label></div>
          <button className="ghost precise-preview" disabled={thinking||!selectedRoom||!exactWidth||!exactHeight||!plan.metersPerPixel} onClick={precisePreview}>{thinking?<LoaderCircle className="spin" size={17}/>:<Ruler size={17}/>} معاينة هندسية</button>
        </div>
        <div className="prompt-divider"><span>أو اكتب طلبك</span></div>
        <div className="prompt-box"><textarea value={command} onChange={e=>setCommand(e.target.value)} placeholder="مثال: عدّل غرفة النوم إلى 5×5"/><button className="primary" disabled={thinking||!command.trim()} onClick={ask}>{thinking?<LoaderCircle className="spin" size={18}/>:<Sparkles size={18}/>} تحليل الطلب</button></div>
        {notice&&<div className="notice-box">{notice}</div>}
        {!preview&&proposals.length>0&&<div className="proposal-list"><span className="section-caption">الخيارات الممكنة</span>{proposals.map(p=><button key={p.id} className="proposal-card" onClick={()=>setPreview(p)}><div><strong>{p.title}</strong><span>{p.summary}</span>{p.validationScore!==undefined&&<small>فحص هندسي {Math.round(p.validationScore*100)}%</small>}</div><ChevronLeft size={18}/></button>)}</div>}
        {preview&&<div className="preview-card"><span className="section-caption">معاينة قبل التنفيذ</span><h3>{preview.title}</h3><p>{preview.summary}</p><div className="impact-list">{preview.impacts.map((i,n)=><div key={n} className={`impact ${i.severity}`}><Check size={16}/><span>{i.text}</span></div>)}{preview.warnings.map((w,n)=><div key={n} className="impact warning"><span>!</span><span>{w}</span></div>)}</div><div className="preview-actions"><button className="ghost" onClick={()=>setPreview(null)}>اختر حلًا آخر</button><button className="primary" disabled={saving} onClick={apply}><Check size={17}/> اعتماد التعديل</button></div></div>}
        <div className="engine-info"><span><Cloud size={15}/> سحابي</span><span><FileImage size={15}/> المخطط الأصلي محفوظ</span></div>
      </aside>
    </div>
  </main>;
}

export default function App(){
  const[screen,setScreen]=useState<Screen>("home");const[project,setProject]=useState<ProjectView|null>(null);const[resumeAvailable,setResumeAvailable]=useState(()=>Boolean(getLastProjectId()));const[resumeBusy,setResumeBusy]=useState(false);const[knownProjects,setKnownProjects]=useState<KnownProject[]>(()=>getKnownProjects());const[openingProjectId,setOpeningProjectId]=useState<string|null>(null);const[projectOpenError,setProjectOpenError]=useState<string|null>(null);const{updateReady,installUpdate}=useAppUpdate();
  const openProject=async(id:string)=>{
    setOpeningProjectId(id);setProjectOpenError(null);
    try{
      const next=await getProject(id);
      setProject(next);
      setKnownProjects(getKnownProjects());
      setResumeAvailable(true);
      if(next.status==="ready"&&next.plan)setScreen("editor");
      else setScreen("processing");
    }catch(error){
      if(error instanceof ApiError&&(error.status===401||error.status===404)){
        forgetKnownProject(id);
        if(getLastProjectId()===id)forgetLastProject();
        setKnownProjects(getKnownProjects());
        setResumeAvailable(Boolean(getLastProjectId()));
        setProjectOpenError(error.status===401?"تعذر فتح المشروع لأن صلاحية هذا الجهاز لم تعد صالحة. استخدم نسخة JSON إن كانت لديك.":"المشروع لم يعد موجودًا في التخزين السحابي.");
      }else{
        setProjectOpenError(error instanceof Error?error.message:"تعذر الاتصال بالمشروع الآن. لم نحذف صلاحية الوصول؛ حاول مرة أخرى.");
      }
    }finally{
      setOpeningProjectId(null);
    }
  };
  const resume=async()=>{
    const id=getLastProjectId();
    if(!id)return;
    setResumeBusy(true);
    try{await openProject(id);}finally{setResumeBusy(false);}
  };
  const home=()=>{setScreen("home");setProjectOpenError(null);setResumeAvailable(Boolean(getLastProjectId()));setKnownProjects(getKnownProjects());};
  return <>{updateReady&&<UpdateBanner onInstall={installUpdate}/>}
    {screen==="home"&&<Home onStart={()=>{setProjectOpenError(null);setScreen("choice");}} onResume={resume} resumeAvailable={resumeAvailable} resumeBusy={resumeBusy} projects={knownProjects} onOpenProject={id=>void openProject(id)} openingProjectId={openingProjectId} openError={projectOpenError}/>}
    {screen==="choice"&&<Choice onEdit={()=>setScreen("upload")} onBack={home}/>}
    {screen==="upload"&&<Upload onBack={()=>setScreen("choice")} onStarted={p=>{setProject(p);setResumeAvailable(true);setKnownProjects(getKnownProjects());setScreen(p.status==="ready"&&p.plan?"editor":"processing");}}/>}
    {screen==="processing"&&project&&<Processing projectId={project.id} onReady={p=>{setProject(p);setScreen("editor");}} onHome={home}/>}
    {screen==="editor"&&project?.plan&&<Editor initialProject={project} onHome={home}/>}
  </>;
}
