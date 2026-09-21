import { useEffect,useMemo,useRef,useState } from "react";
import { ArrowLeft,BrainCircuit,Check,ChevronLeft,Clock3,Cloud,DoorOpen,Download,FileImage,FileText,Hammer,Layers3,LoaderCircle,Redo2,RotateCcw,Ruler,Save,Settings2,ShieldCheck,Sparkles,Square,Trash2,Undo2,UploadCloud,WandSparkles,X } from "lucide-react";
import type { EditProposal,ElementProvenance,FloorPlanModel,Opening,Point,ProjectView,RevisionView,ValidationReport,WallRole } from "@manzil/contracts";
import { ApiError,activateFloor,applyProposal,askEngineer,clearProjectDraft,createProject,forgetKnownProject,forgetLastProject,getKnownProjects,getLastProjectId,getProject,getProjectPreview,importProjectBackup,inferSourceMime,listRevisions,resizeRoomPrecisely,restoreRevision,retryAnalysis,saveDraft,saveRevision,updateFloorMetadata,uploadSource,validateProject } from "./api";
import type { KnownProject } from "./api";
import { DEFAULT_PLAN_LAYERS,PlanCanvas,moveWallAndTopology } from "./PlanCanvas";
import type { PlanLayerVisibility } from "./PlanCanvas";
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

function provenanceLabel(value?:ElementProvenance){
  if(!value)return "قراءة آلية";
  const labels:Record<ElementProvenance,string>={
    "opencv":"OpenCV",
    "pdf-vector":"PDF متجهي",
    "ocr":"OCR محلي",
    "cloud-ocr":"OCR سحابي",
    "pdf-text":"نص PDF",
    "manual":"يدوي",
    "ai":"H Engineer",
    "mixed":"قراءة مدمجة",
  };
  return labels[value];
}

function manualProvenance(value?:ElementProvenance):ElementProvenance{
  return value?"mixed":"manual";
}

function openingHostProtected(plan:FloorPlanModel,openingId:string|null){
  if(!openingId)return false;
  const opening=[...plan.doors,...plan.windows].find(item=>item.id===openingId);
  if(!opening?.wallId)return false;
  const wall=plan.walls.find(item=>item.id===opening.wallId);
  return Boolean(wall?.locked||wall?.role==="structural");
}

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
  const input=useRef<HTMLInputElement|null>(null);const[busy,setBusy]=useState(false);const[dragActive,setDragActive]=useState(false);const[pct,setPct]=useState(0);const[error,setError]=useState<string|null>(null);const[mode,setMode]=useState<"upload"|"backup">("upload");
  const handle=async(file?:File)=>{
    if(!file)return;
    const backup=file.name.toLowerCase().endsWith(".json")||file.type==="application/json";
    const sourceMime=inferSourceMime(file);
    if(!backup&&!sourceMime){setError("الملف يجب أن يكون PDF أو PNG/JPG/WEBP أو نسخة مشروع JSON.");return;}
    if(backup&&file.size>12*1024*1024){setError("نسخة المشروع أكبر من الحد المدعوم 12MB.");return;}
    if(!backup&&file.size>50*1024*1024){setError("حجم المخطط يتجاوز الحد الأقصى 50MB.");return;}
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
  useEffect(()=>{
    const onPaste=(event:ClipboardEvent)=>{
      if(busy)return;
      const file=[...(event.clipboardData?.files??[])].find(item=>Boolean(inferSourceMime(item)));
      if(file){event.preventDefault();void handle(file);}
    };
    window.addEventListener("paste",onPaste);
    return()=>window.removeEventListener("paste",onPaste);
  },[busy]);
  return <main className="center-page"><div className="top-inline"><button className="ghost" onClick={onBack}><ArrowLeft size={18}/> رجوع</button><Brand compact/></div>
    <section className="upload-card"><span className="eyebrow"><Sparkles size={16}/> تعديل مخطط قائم</span><h2>ارفع المخطط</h2><p>ارفع PDF أو صورة للتحليل، أو استعد نسخة مشروع JSON سبق تصديرها من منزل H.</p>
      <button className={`drop-zone ${dragActive?"drag-active":""}`} onClick={()=>input.current?.click()} disabled={busy}
        onDragEnter={event=>{event.preventDefault();if(!busy)setDragActive(true);}}
        onDragOver={event=>{event.preventDefault();if(!busy)setDragActive(true);}}
        onDragLeave={event=>{event.preventDefault();if(event.currentTarget===event.target)setDragActive(false);}}
        onDrop={event=>{event.preventDefault();setDragActive(false);if(!busy)void handle(event.dataTransfer.files?.[0]);}}>
        {busy?<LoaderCircle className="spin" size={44}/>:<UploadCloud size={44}/>}
        <strong>{busy?(mode==="backup"?"جارٍ استعادة المشروع...":`جارٍ الرفع ${pct}%`):dragActive?"أفلت الملف هنا":"اختر ملفًا أو اسحبه هنا"}</strong>
        <span>PDF · PNG · JPG · WEBP · JSON · ويمكن لصق صورة مباشرة</span>
      </button>
      <input ref={input} hidden type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.json,application/pdf,application/json,image/png,image/jpeg,image/webp" onChange={e=>handle(e.target.files?.[0])}/>{error&&<div className="error-box">{error}</div>}
    </section>
  </main>;
}

function Processing({projectId,onReady,onHome}:{projectId:string;onReady:(p:ProjectView)=>void;onHome:()=>void}){
  const[project,setProject]=useState<ProjectView|null>(null);const[retryBusy,setRetryBusy]=useState(false);const[retryNonce,setRetryNonce]=useState(0);const[retryError,setRetryError]=useState<string|null>(null);
  useEffect(()=>{let alive=true;const poll=async()=>{try{const next=await getProject(projectId);if(!alive)return;setProject(next);if(next.status==="ready"&&next.plan){onReady(next);return;}if(next.status==="error")return;}catch{}if(alive)window.setTimeout(poll,1200);};poll();return()=>{alive=false;};},[projectId,onReady,retryNonce]);
  const retry=async()=>{if(!project)return;setRetryBusy(true);setRetryError(null);try{const next=await retryAnalysis(projectId,project.revision);setProject(next);setRetryNonce(value=>value+1);}catch(e){setRetryError(e instanceof Error?e.message:"تعذر إعادة التحليل");}finally{setRetryBusy(false);}};
  const progress=Math.max(0,Math.min(100,project?.progress??10));
  return <main className="processing-page"><Brand/><section className="processing-card">
    <div className="progress-ring" style={{"--p":`${progress*3.6}deg`} as React.CSSProperties}><div><strong>{progress}%</strong><span>تحليل حقيقي</span></div></div>
    <h2>{phaseLabels[project?.phase??"upload"]}</h2><p>{project?.message??"نعالج المخطط ونبني نموذجًا هندسيًا قابلًا للتعديل."}</p>
    {project?.status==="error"&&<div className="error-box processing-error"><span>{project.error??"تعذر تحليل المخطط."}</span><div className="processing-error-actions"><button className="ghost" disabled={retryBusy} onClick={()=>void retry()}>{retryBusy?<LoaderCircle className="spin" size={16}/>:<RotateCcw size={16}/>} إعادة التحليل</button><button className="ghost" onClick={onHome}>الرئيسية</button></div></div>}
    {retryError&&<div className="error-box">{retryError}</div>}
    <div className="stage-list">{["preprocess","ocr","geometry","rooms","validation"].map(p=><span key={p} className={project?.phase===p?"current":""}>{phaseLabels[p]}</span>)}</div>
  </section></main>;
}

function Editor({initialProject,onHome}:{initialProject:ProjectView;onHome:()=>void}){
  const[project,setProject]=useState(initialProject);const[plan,setPlan]=useState<FloorPlanModel>(initialProject.plan!);const[savedPlan,setSavedPlan]=useState<FloorPlanModel>(initialProject.plan!);const[undoStack,setUndoStack]=useState<FloorPlanModel[]>([]);const[redoStack,setRedoStack]=useState<FloorPlanModel[]>([]);
  const[selectedWall,setSelectedWall]=useState<string|null>(null);const[wallThicknessCm,setWallThicknessCm]=useState("");const[wallMoveCm,setWallMoveCm]=useState("10");const[selectedRoom,setSelectedRoom]=useState<string|null>(null);const[selectedOpening,setSelectedOpening]=useState<string|null>(null);const[openingWidth,setOpeningWidth]=useState("");const[openingPosition,setOpeningPosition]=useState(50);const[exactName,setExactName]=useState("");const[exactWidth,setExactWidth]=useState("");const[exactHeight,setExactHeight]=useState("");const[command,setCommand]=useState("");const[thinking,setThinking]=useState(false);const[proposals,setProposals]=useState<EditProposal[]>([]);const[preview,setPreview]=useState<EditProposal|null>(null);const[saving,setSaving]=useState(false);const[notice,setNotice]=useState<string|null>(null);
  const[calibrating,setCalibrating]=useState(false);const[calibrationPoints,setCalibrationPoints]=useState<Point[]>([]);const[knownDistance,setKnownDistance]=useState("");
  const[sourcePreview,setSourcePreview]=useState<string|null>(null);const[sourceOpacity,setSourceOpacity]=useState(.42);const[sourcePreviewNonce,setSourcePreviewNonce]=useState(0);const[sourcePageInput,setSourcePageInput]=useState(String(initialProject.plan?.source.page??1));const[pageSwitchBusy,setPageSwitchBusy]=useState(false);
  const[layerOpen,setLayerOpen]=useState(false);const[layers,setLayers]=useState<PlanLayerVisibility>({...DEFAULT_PLAN_LAYERS});
  const[floorSettingsOpen,setFloorSettingsOpen]=useState(false);const[floorName,setFloorName]=useState("");const[floorElevation,setFloorElevation]=useState("");const[floorHeight,setFloorHeight]=useState("");const[floorMetaBusy,setFloorMetaBusy]=useState(false);
  const[historyOpen,setHistoryOpen]=useState(false);const[historyBusy,setHistoryBusy]=useState(false);const[revisions,setRevisions]=useState<RevisionView[]>([]);const[exportOpen,setExportOpen]=useState(false);const[exportBusy,setExportBusy]=useState(false);
  const[validationReport,setValidationReport]=useState<ValidationReport|null>(null);const[validationBusy,setValidationBusy]=useState(false);const[draftState,setDraftState]=useState<"idle"|"saving"|"saved"|"error">(initialProject.hasDraft?"saved":"idle");const[recoveredDraft,setRecoveredDraft]=useState(initialProject.hasDraft);
  const draftGeneration=useRef(0);const draftChain=useRef<Promise<void>>(Promise.resolve());const openingPositionBase=useRef<FloorPlanModel|null>(null);
  const localDirty=useMemo(()=>JSON.stringify(plan)!==JSON.stringify(savedPlan),[plan,savedPlan]);
  const dirty=localDirty||recoveredDraft;
  const activeFloor=useMemo(()=>project.floors?.find(item=>item.id===project.activeFloorId)??project.floors?.find(item=>item.sourcePage===plan.source.page)??null,[project.floors,project.activeFloorId,plan.source.page]);
  useEffect(()=>{
    if(!activeFloor){setFloorName("");setFloorElevation("");setFloorHeight("");return;}
    setFloorName(activeFloor.name);
    setFloorElevation(activeFloor.elevationM==null?"":String(activeFloor.elevationM));
    setFloorHeight(activeFloor.heightM==null?"":String(activeFloor.heightM));
  },[activeFloor?.id,activeFloor?.name,activeFloor?.elevationM,activeFloor?.heightM]);
  const toggleLayer=(key:keyof PlanLayerVisibility)=>setLayers(current=>({...current,[key]:!current[key]}));
  const selectedContextLabel=useMemo(()=>{
    if(selectedRoom)return `الغرفة · ${plan.rooms.find(room=>room.id===selectedRoom)?.name??"محددة"}`;
    if(selectedOpening){
      const opening=[...plan.doors,...plan.windows].find(item=>item.id===selectedOpening);
      return opening?`${opening.kind==="door"?"الباب":"النافذة"} المحدد`:"الفتحة المحددة";
    }
    if(selectedWall)return "الجدار المحدد";
    return null;
  },[selectedRoom,selectedOpening,selectedWall,plan.rooms,plan.doors,plan.windows]);
  const reviewItems=useMemo(()=>{
    const items:Array<{key:string;kind:"room"|"wall"|"opening";id:string;label:string;confidence:number;provenance?:ElementProvenance}>=[];
    for(const room of plan.rooms)if(!room.reviewed&&room.confidence<.78)items.push({key:`room:${room.id}`,kind:"room",id:room.id,label:room.name||"غرفة غير مسماة",confidence:room.confidence,provenance:room.provenance});
    for(const wall of plan.walls)if(!wall.reviewed&&wall.confidence<.72)items.push({key:`wall:${wall.id}`,kind:"wall",id:wall.id,label:"جدار يحتاج تأكيد",confidence:wall.confidence,provenance:wall.provenance});
    for(const opening of [...plan.doors,...plan.windows])if(!opening.reviewed&&opening.confidence<.84)items.push({key:`opening:${opening.id}`,kind:"opening",id:opening.id,label:opening.kind==="door"?"باب يحتاج تأكيد":"نافذة تحتاج تأكيد",confidence:opening.confidence,provenance:opening.provenance});
    return items.sort((a,b)=>a.confidence-b.confidence);
  },[plan.rooms,plan.walls,plan.doors,plan.windows]);
  const selectedReviewItem=useMemo(()=>reviewItems.find(item=>
    (item.kind==="room"&&item.id===selectedRoom)||
    (item.kind==="wall"&&item.id===selectedWall)||
    (item.kind==="opening"&&item.id===selectedOpening)
  )??null,[reviewItems,selectedRoom,selectedWall,selectedOpening]);
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
    setPlan(previous);setSelectedWall(null);setWallThicknessCm("");setSelectedRoom(null);setSelectedOpening(null);setPreview(null);setProposals([]);
  };
  const redoLocal=()=>{
    const next=redoStack.at(-1);
    if(!next)return;
    setRedoStack(stack=>stack.slice(0,-1));
    setUndoStack(stack=>[...stack.slice(-49),plan]);
    setPlan(next);setSelectedWall(null);setWallThicknessCm("");setSelectedRoom(null);setSelectedOpening(null);setPreview(null);setProposals([]);
  };
  const selectWall=(wallId:string|null)=>{
    setSelectedWall(wallId);setSelectedRoom(null);setSelectedOpening(null);setPreview(null);setProposals([]);
    const wall=plan.walls.find(item=>item.id===wallId);
    if(!wall||!plan.metersPerPixel){setWallThicknessCm("");return;}
    setWallThicknessCm((wall.thicknessPx*plan.metersPerPixel*100).toFixed(1));
  };
  const updateWallThickness=()=>{
    if(!selectedWall||!plan.metersPerPixel)return;
    const selected=plan.walls.find(item=>item.id===selectedWall);
    if(selected?.locked){setNotice("الجدار محمي. فك الحماية قبل تعديل سماكته.");return;}
    const cm=Number(wallThicknessCm.replace(",","."));
    if(!Number.isFinite(cm)||cm<2||cm>100){setNotice("أدخل سماكة جدار بين 2 و100 سم.");return;}
    const px=(cm/100)/plan.metersPerPixel;
    if(px<=0||px>200){setNotice("السماكة المطلوبة لا تتوافق مع مقياس المخطط الحالي.");return;}
    applyLocalPlan({...plan,walls:plan.walls.map(wall=>wall.id===selectedWall?{...wall,thicknessPx:Number(px.toFixed(2)),reviewed:true,provenance:manualProvenance(wall.provenance)}:wall)});
    setNotice("تم تحديث سماكة الجدار محليًا.");
  };
  const moveSelectedWallExact=(direction:-1|1)=>{
    if(!selectedWall||!plan.metersPerPixel)return;
    const wall=plan.walls.find(item=>item.id===selectedWall);
    if(!wall)return;
    if(wall.locked){setNotice("الجدار محمي. فك الحماية قبل تحريكه.");return;}
    const cm=Number(wallMoveCm.replace(",","."));
    if(!Number.isFinite(cm)||cm<=0||cm>1000){setNotice("أدخل مسافة تحريك بين 0 و1000 سم.");return;}
    const delta=(cm/100)/plan.metersPerPixel*direction;
    const vertical=Math.abs(wall.a.x-wall.b.x)<=Math.abs(wall.a.y-wall.b.y);
    const candidate=vertical
      ?{...wall,a:{...wall.a,x:wall.a.x+delta},b:{...wall.b,x:wall.b.x+delta}}
      :{...wall,a:{...wall.a,y:wall.a.y+delta},b:{...wall.b,y:wall.b.y+delta}};
    const next=moveWallAndTopology(plan,wall,candidate);
    const moved=next.walls.find(item=>item.id===wall.id);
    if(!moved)return;
    const actualPx=vertical?Math.abs(moved.a.x-wall.a.x):Math.abs(moved.a.y-wall.a.y);
    if(actualPx<0.5){setNotice("لا يمكن تحريك الجدار بهذا الاتجاه بسبب حدود الغرف المجاورة.");return;}
    applyLocalPlan(next);
    const actualCm=actualPx*plan.metersPerPixel*100;
    setNotice(actualCm+0.5<cm?`تم تحريك الجدار ${actualCm.toFixed(1)} سم فقط للحفاظ على الحد الأدنى للفراغات.`:`تم تحريك الجدار ${actualCm.toFixed(1)} سم.`);
  };
  const updateSelectedWallRole=(role:WallRole)=>{
    if(!selectedWall)return;
    applyLocalPlan({...plan,walls:plan.walls.map(wall=>wall.id===selectedWall?{
      ...wall,role,locked:role==="structural"||role==="exterior"?true:wall.locked,
      reviewed:true,provenance:manualProvenance(wall.provenance)
    }:wall)});
    setNotice(role==="structural"?"تم تصنيف الجدار كإنشائي وحمايته تلقائيًا.":role==="exterior"?"تم تصنيف الجدار كخارجي وحمايته تلقائيًا.":"تم تحديث تصنيف الجدار.");
  };
  const toggleSelectedWallLock=()=>{
    if(!selectedWall)return;
    const wall=plan.walls.find(item=>item.id===selectedWall);
    if(!wall)return;
    if(wall.role==="structural"&&wall.locked){setNotice("غيّر تصنيف الجدار الإنشائي أولًا قبل فك الحماية.");return;}
    applyLocalPlan({...plan,walls:plan.walls.map(item=>item.id===wall.id?{
      ...item,locked:!wall.locked,reviewed:true,provenance:manualProvenance(item.provenance)
    }:item)});
    setNotice(wall.locked?"تم فك حماية الجدار. راجع أثر أي تعديل بعناية.":"تمت حماية الجدار من التعديل والحركة.");
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
    const wall=plan.walls.find(item=>item.id===selectedWall);
    if(wall?.locked){setNotice("الجدار محمي. فك الحماية قبل إضافة باب أو نافذة.");return;}
    const next=addOpeningToWall(plan,selectedWall,kind);
    if(!next){setNotice("لا توجد مساحة كافية على الجدار المحدد لإضافة فتحة جديدة.");return;}
    const beforeIds=new Set([...plan.doors,...plan.windows].map(item=>item.id));
    const created=[...next.doors,...next.windows].find(item=>!beforeIds.has(item.id));
    applyLocalPlan(next);setSelectedRoom(null);setSelectedWall(null);setNotice(kind==="door"?"تمت إضافة باب. اضبط عرضه وموقعه ثم احفظ.":"تمت إضافة نافذة. اضبط عرضها وموقعها ثم احفظ.");
    if(created){
      const metrics=openingMetrics(next,created.id);
      setSelectedOpening(created.id);
      setOpeningWidth(metrics?.widthM?.toFixed(2)??"");
      setOpeningPosition(Math.round(metrics?.positionPct??50));
    }
  };
  const updateOpeningWidth=()=>{
    if(!selectedOpening)return;
    if(openingHostProtected(plan,selectedOpening)){setNotice("الفتحة على جدار محمي. فك حماية الجدار أولًا.");return;}
    const width=Number(openingWidth.replace(",","."));
    const next=resizeOpening(plan,selectedOpening,width);
    if(!next){setNotice("تعذر تطبيق العرض المطلوب على هذا الجدار.");return;}
    applyLocalPlan(next);
    const metrics=openingMetrics(next,selectedOpening);
    setOpeningWidth(metrics?.widthM?.toFixed(2)??openingWidth);
    setOpeningPosition(Math.round(metrics?.positionPct??openingPosition));
    setNotice("تم تحديث عرض الفتحة محليًا.");
  };
  const startOpeningPositionEdit=()=>{if(!openingPositionBase.current)openingPositionBase.current=plan;};
  const finishOpeningPositionEdit=()=>{
    const base=openingPositionBase.current;
    if(base)commitTransientPlan(base);
    openingPositionBase.current=null;
  };
  const updateOpeningPosition=(position:number)=>{
    if(!selectedOpening)return;
    if(openingHostProtected(plan,selectedOpening)){setNotice("الفتحة على جدار محمي. فك حماية الجدار أولًا.");return;}
    const next=positionOpening(plan,selectedOpening,position);
    if(!next)return;
    applyLocalPlan(next,false);setOpeningPosition(position);
  };
  const updateOpeningKind=(kind:Opening["kind"])=>{
    if(!selectedOpening)return;
    if(openingHostProtected(plan,selectedOpening)){setNotice("الفتحة على جدار محمي. فك حماية الجدار أولًا.");return;}
    const next=changeOpeningKind(plan,selectedOpening,kind);
    if(!next)return;
    applyLocalPlan(next);setNotice(kind==="door"?"تم تصحيح الفتحة إلى باب.":"تم تصحيح الفتحة إلى نافذة.");
  };
  const deleteOpening=()=>{
    if(!selectedOpening)return;
    if(openingHostProtected(plan,selectedOpening)){setNotice("الفتحة على جدار محمي. فك حماية الجدار أولًا.");return;}
    applyLocalPlan(removeOpening(plan,selectedOpening));setSelectedOpening(null);setOpeningWidth("");setNotice("تم حذف الفتحة محليًا. يمكنك التراجع قبل الحفظ.");
  };
  const focusReviewItem=(item:{kind:"room"|"wall"|"opening";id:string})=>{
    if(item.kind==="room"){selectRoom(item.id);return;}
    if(item.kind==="wall"){selectWall(item.id);return;}
    selectOpening(item.id);
  };
  const confirmSelectedReading=()=>{
    const item=selectedReviewItem;
    if(!item)return;
    if(item.kind==="room"){
      applyLocalPlan({...plan,rooms:plan.rooms.map(room=>room.id===item.id?{...room,reviewed:true}:room)});
    }else if(item.kind==="wall"){
      applyLocalPlan({...plan,walls:plan.walls.map(wall=>wall.id===item.id?{...wall,reviewed:true}:wall)});
    }else{
      applyLocalPlan({
        ...plan,
        doors:plan.doors.map(opening=>opening.id===item.id?{...opening,reviewed:true}:opening),
        windows:plan.windows.map(opening=>opening.id===item.id?{...opening,reviewed:true}:opening),
      });
    }
    setNotice("تم تأكيد قراءة العنصر. سيُحفظ ضمن المسودة السحابية تلقائيًا.");
  };
  const renameSelectedRoom=()=>{
    const room=plan.rooms.find(item=>item.id===selectedRoom);
    const name=exactName.trim().replace(/\s+/g," ").slice(0,80);
    if(!room||!name||name===room.name)return;
    applyLocalPlan({...plan,rooms:plan.rooms.map(item=>item.id===room.id?{...item,name,reviewed:true,provenance:manualProvenance(item.provenance)}:item)});
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
      const result=await resizeRoomPrecisely(project.id,room.id,width,height,project.revision);
      setCommand(canonical);setProposals(result.proposals);
      if(result.needsClarification)setNotice(result.needsClarification);
    }catch(e){setNotice(e instanceof Error?e.message:"تعذر إنشاء المعاينة الهندسية");}
    finally{setThinking(false);}
  };

  useEffect(()=>{
    let active=true;let objectUrl:string|null=null;
    getProjectPreview(project.id).then(url=>{objectUrl=url;if(active)setSourcePreview(url);else if(url)URL.revokeObjectURL(url);}).catch(()=>undefined);
    return()=>{active=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[project.id,sourcePreviewNonce]);
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
      const target=event.target as HTMLElement|null;
      const tag=target?.tagName?.toLowerCase();
      const typing=tag==="input"||tag==="textarea"||tag==="select"||target?.isContentEditable;
      if(event.key==="Escape"){
        setLayerOpen(false);setFloorSettingsOpen(false);setPreview(null);setProposals([]);setSelectedWall(null);setSelectedRoom(null);setSelectedOpening(null);
        return;
      }
      if(typing)return;
      if((event.key==="Delete"||event.key==="Backspace")&&selectedOpening&&!openingHostProtected(plan,selectedOpening)){
        event.preventDefault();deleteOpening();return;
      }
      const modifier=event.ctrlKey||event.metaKey;
      if(!modifier)return;
      if(event.key.toLowerCase()==="z"&&!event.shiftKey){event.preventDefault();undoLocal();}
      else if((event.key.toLowerCase()==="z"&&event.shiftKey)||event.key.toLowerCase()==="y"){event.preventDefault();redoLocal();}
    };
    window.addEventListener("keydown",handle);
    return()=>window.removeEventListener("keydown",handle);
  },[undoStack,redoStack,plan,selectedOpening]);
  const ask=async()=>{if(!command.trim())return;setThinking(true);setNotice(null);setPreview(null);try{await syncPlanForEngineer();const r=await askEngineer(project.id,command.trim(),project.revision,{targetRoomId:selectedRoom,targetWallId:selectedWall,targetOpeningId:selectedOpening});setProposals(r.proposals);if(r.needsClarification)setNotice(r.needsClarification);}catch(e){setNotice(e instanceof Error?e.message:"تعذر تحليل الطلب");}finally{setThinking(false);}};
  const save=async()=>{setSaving(true);const generation=++draftGeneration.current;try{await draftChain.current.catch(()=>undefined);if(generation!==draftGeneration.current)return;const u=await saveRevision(project.id,plan,"تعديل يدوي",project.revision);const canonical=u.plan??plan;setProject(u);setPlan(canonical);setSavedPlan(canonical);setRecoveredDraft(false);setDraftState("idle");setValidationReport(null);setNotice("تم حفظ التعديل في السحابة وتوحيد العلاقات الهندسية.");}catch(e){const report=validationFromApiError(e);if(report)setValidationReport(report);setNotice(e instanceof Error?e.message:"تعذر الحفظ");}finally{setSaving(false);}};
  const openHistory=async()=>{setHistoryOpen(true);setHistoryBusy(true);try{const r=await listRevisions(project.id);setRevisions(r.items);}catch(e){setNotice(e instanceof Error?e.message:"تعذر تحميل سجل النسخ");setHistoryOpen(false);}finally{setHistoryBusy(false);}};
  const runValidation=async()=>{setValidationBusy(true);setNotice(null);try{setValidationReport(await validateProject(project.id,plan));}catch(e){setNotice(e instanceof Error?e.message:"تعذر فحص المخطط");}finally{setValidationBusy(false);}};
  const saveFloorMetadata=async()=>{
    if(!activeFloor)return;
    if(dirty){setNotice("احفظ التعديلات الحالية أو تجاهل المسودة قبل تعديل بيانات الطابق.");return;}
    const name=floorName.trim().replace(/\s+/g," ").slice(0,100);
    const elevation=floorElevation.trim()===""?null:Number(floorElevation.replace(",","."));
    const height=floorHeight.trim()===""?null:Number(floorHeight.replace(",","."));
    if(!name){setNotice("اكتب اسمًا للطابق.");return;}
    if(elevation!==null&&!Number.isFinite(elevation)){setNotice("منسوب الطابق غير صالح.");return;}
    if(height!==null&&(!Number.isFinite(height)||height<0.5||height>20)){setNotice("ارتفاع الطابق يجب أن يكون بين 0.5 و20 متر.");return;}
    setFloorMetaBusy(true);setNotice(null);
    try{
      const fresh=await updateFloorMetadata(project.id,activeFloor.id,{expectedRevision:project.revision,name,elevationM:elevation,heightM:height});
      setProject(fresh);setFloorSettingsOpen(false);setNotice("تم حفظ بيانات الطابق في المشروع السحابي.");
    }catch(e){setNotice(e instanceof Error?e.message:"تعذر حفظ بيانات الطابق.");}
    finally{setFloorMetaBusy(false);}
  };
  const loadFloorProject=(fresh:ProjectView,message:string)=>{
    if(!fresh.plan)throw new Error("المخطط المختار غير متوفر.");
    setProject(fresh);setPlan(fresh.plan);setSavedPlan(fresh.plan);setUndoStack([]);setRedoStack([]);
    setSelectedWall(null);setWallThicknessCm("");setSelectedRoom(null);setSelectedOpening(null);
    setPreview(null);setProposals([]);setValidationReport(null);setRecoveredDraft(false);setDraftState("idle");
    setSourcePageInput(String(fresh.plan.source.page));setSourcePreviewNonce(value=>value+1);
    setNotice(message);
  };
  const activateKnownFloor=async(floorId:string,page:number)=>{
    if(page===plan.source.page)return;
    if(dirty){setNotice("احفظ التعديلات الحالية أو تجاهل المسودة قبل تبديل الطابق.");return;}
    setPageSwitchBusy(true);setNotice(`جارٍ فتح الصفحة ${page}...`);
    try{
      const fresh=await activateFloor(project.id,floorId,project.revision);
      loadFloorProject(fresh,`تم فتح الصفحة ${page} مباشرة من النسخة السحابية المحللة.`);
    }catch(e){setNotice(e instanceof Error?e.message:"تعذر فتح الطابق المحدد.");}
    finally{setPageSwitchBusy(false);}
  };
  const reanalyzeSourcePage=async()=>{
    const page=Number(sourcePageInput);
    const pageCount=plan.source.pageCount??1;
    if(!Number.isInteger(page)||page<1||page>pageCount){setNotice(`اختر صفحة بين 1 و${pageCount}.`);return;}
    if(page===plan.source.page){setNotice("هذه هي الصفحة الحالية بالفعل.");return;}
    if(dirty){setNotice("احفظ التعديلات الحالية قبل الانتقال إلى صفحة PDF أخرى.");return;}
    const known=project.floors?.find(item=>item.sourcePage===page);
    if(known){await activateKnownFloor(known.id,page);return;}

    setPageSwitchBusy(true);setNotice(`جارٍ تحليل الصفحة ${page} من ${pageCount} لأول مرة...`);
    try{
      const baselineRevision=project.revision;
      await retryAnalysis(project.id,project.revision,page);
      let fresh:ProjectView|null=null;
      for(let attempt=0;attempt<140;attempt++){
        await new Promise(resolve=>window.setTimeout(resolve,1200));
        const candidate=await getProject(project.id);
        if(candidate.status==="error")throw new Error(candidate.error??"تعذر تحليل الصفحة المحددة.");
        if(candidate.status==="ready"&&candidate.plan&&candidate.revision>baselineRevision&&candidate.plan.source.page===page){
          fresh=candidate;break;
        }
      }
      if(!fresh?.plan)throw new Error("استغرق تحليل الصفحة وقتًا أطول من المتوقع. يمكنك إعادة المحاولة دون رفع الملف.");
      loadFloorProject(fresh,`تم تحليل الصفحة ${page} وحفظها كطابق مستقل داخل المشروع.`);
    }catch(e){setNotice(e instanceof Error?e.message:"تعذر تحليل الصفحة المحددة.");}
    finally{setPageSwitchBusy(false);}
  };
  const focusValidationFinding=(item:ValidationReport["findings"][number])=>{
    if(item.roomIds[0]){selectRoom(item.roomIds[0]);return;}
    if(item.wallIds?.[0]){selectWall(item.wallIds[0]);return;}
    if(item.openingIds?.[0]){selectOpening(item.openingIds[0]);}
  };
  const runExport=async(format:"svg"|"png"|"json")=>{setExportBusy(true);setNotice(null);try{if(format==="svg")exportPlanSvg(plan,project.name);else if(format==="json")exportPlanJson(plan,project.name);else await exportPlanPng(plan,project.name);setExportOpen(false);}catch{setNotice("تعذر إنشاء ملف التصدير. جرّب صيغة أخرى.");}finally{setExportBusy(false);}};
  const restore=async(revision:number)=>{if(localDirty){setNotice("احفظ التغييرات الحالية أو تراجع عنها قبل استعادة نسخة سابقة.");return;}setSaving(true);++draftGeneration.current;try{await draftChain.current.catch(()=>undefined);const u=await restoreRevision(project.id,revision);if(u.plan){setPlan(u.plan);setSavedPlan(u.plan);setUndoStack([]);setRedoStack([]);setSourcePageInput(String(u.plan.source.page));setSourcePreviewNonce(value=>value+1);}setProject(u);setRecoveredDraft(false);setHistoryOpen(false);setNotice(`تمت استعادة النسخة ${revision} كنسخة جديدة محفوظة.`);}catch(e){setNotice(e instanceof Error?e.message:"تعذر استعادة النسخة");}finally{setSaving(false);}};
  const apply=async()=>{if(!preview)return;setSaving(true);++draftGeneration.current;try{await draftChain.current.catch(()=>undefined);const u=await applyProposal(project.id,{command,proposal:preview,expectedRevision:project.revision,targetRoomId:selectedRoom,targetWallId:selectedWall,targetOpeningId:selectedOpening});if(u.plan){setPlan(u.plan);setSavedPlan(u.plan);setUndoStack([]);setRedoStack([]);}setProject(u);setRecoveredDraft(false);setPreview(null);setProposals([]);setCommand("");setSelectedRoom(null);setSelectedOpening(null);setExactName("");setExactWidth("");setExactHeight("");setValidationReport(null);setNotice("تم اعتماد التعديل وحفظ نسخة جديدة.");}catch(e){const report=validationFromApiError(e);if(report)setValidationReport(report);setNotice(e instanceof Error?e.message:"تعذر تطبيق التعديل");}finally{setSaving(false);}};
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
    {historyOpen&&<div className="history-backdrop" onClick={()=>setHistoryOpen(false)}><section className="history-modal" onClick={e=>e.stopPropagation()}><div className="history-head"><div><strong>سجل النسخ</strong><span>الاستعادة لا تحذف أي نسخة؛ تُنشئ نسخة جديدة من الحالة المختارة.</span></div><button className="icon-button" onClick={()=>setHistoryOpen(false)} aria-label="إغلاق"><X size={17}/></button></div>{localDirty&&<div className="inline-warning">لديك تغييرات محلية غير محفوظة. احفظها أو تراجع عنها قبل الاستعادة.</div>}{recoveredDraft&&!localDirty&&<div className="notice-box">أنت تعرض مسودة تلقائية مستعادة. يمكنك استعادة أي نسخة محفوظة دون أن تضيع من سجل النسخ.</div>}<div className="history-list">{historyBusy?<div className="history-loading"><LoaderCircle className="spin" size={24}/> تحميل النسخ...</div>:revisions.length?revisions.map((item,index)=><div className="history-item" key={item.revision}><div><strong>نسخة {item.revision}{index===0?" · الأحدث":""}</strong><span>{item.summary}{item.floorName?` · ${item.floorName}`:item.sourcePage?` · صفحة ${item.sourcePage}`:""}</span>{(item.floorElevationM!==null&&item.floorElevationM!==undefined)||(item.floorHeightM!==null&&item.floorHeightM!==undefined)?<small>{item.floorElevationM!==null&&item.floorElevationM!==undefined?`منسوب ${item.floorElevationM} م`:""}{item.floorElevationM!==null&&item.floorElevationM!==undefined&&item.floorHeightM!==null&&item.floorHeightM!==undefined?" · ":""}{item.floorHeightM!==null&&item.floorHeightM!==undefined?`ارتفاع ${item.floorHeightM} م`:""}</small>:null}<small>{new Date(item.createdAt).toLocaleString("ar-SA")}</small></div><button className="ghost" disabled={localDirty||saving||(!recoveredDraft&&index===0)} onClick={()=>restore(item.revision)}>{index===0?(recoveredDraft?"استعادة آخر حفظ":localDirty?"آخر حفظ":"الحالية"):"استعادة"}</button></div>):<div className="history-empty">لا توجد نسخ محفوظة بعد.</div>}</div></section></div>}
    <header className="editor-header"><Brand compact/><div className="project-name"><FileText size={17}/><strong>{project.name}</strong></div><div className="editor-actions"><button className="ghost" onClick={openHistory}><Clock3 size={17}/> النسخ</button><button className="ghost" onClick={onHome}><ArrowLeft size={17}/> الرئيسية</button><button className="ghost" disabled={!undoStack.length} onClick={undoLocal}><Undo2 size={17}/> تراجع</button><button className="ghost" disabled={!redoStack.length} onClick={redoLocal}><Redo2 size={17}/> إعادة</button><button className="primary small" disabled={!dirty||saving} onClick={save}><Save size={17}/> حفظ</button></div></header>
    <div className={`editor-workspace ${pageSwitchBusy?"reanalyzing":""}`}>
      {pageSwitchBusy&&<div className="reanalyze-overlay" aria-live="polite"><div><LoaderCircle className="spin" size={24}/><strong>إعادة تحليل صفحة PDF</strong><span>نبني نموذج الصفحة الجديدة ونحفظ الصفحة السابقة في سجل النسخ.</span></div></div>}
      <section className="plan-panel"><div className="panel-title"><div><strong>منطقة التعديل</strong><span>اسحب جدارًا لتحريكه أو استخدم H Engineer</span></div><div className="panel-status"><span className={`draft-pill ${draftState}`}>{draftState==="saving"?"حفظ...":draftState==="saved"?"مسودة سحابية":draftState==="error"?"تعذر الحفظ":"سحابي"}</span><div className="layer-control-wrap"><button className={`validate-chip ${layerOpen?"active":""}`} onClick={()=>setLayerOpen(value=>!value)}><Layers3 size={14}/> الطبقات</button>{layerOpen&&<div className="layer-popover">{([
  ["source","المخطط الأصلي"],
  ["rooms","الغرف"],
  ["walls","الجدران"],
  ["openings","الأبواب والنوافذ"],
  ["labels","نصوص OCR والأبعاد"],
  ["validation","نتائج الفحص"],
  ["uncertainty","إبراز القراءة غير المؤكدة"],
] as Array<[keyof PlanLayerVisibility,string]>).map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggleLayer(key)}/><span>{label}</span></label>)}<button className="ghost layer-reset" onClick={()=>setLayers({...DEFAULT_PLAN_LAYERS})}>إظهار الكل</button></div>}</div>{activeFloor&&<div className="floor-control-wrap"><button className={`validate-chip ${floorSettingsOpen?"active":""}`} disabled={dirty} onClick={()=>setFloorSettingsOpen(value=>!value)}><Settings2 size={14}/> الطابق</button>{floorSettingsOpen&&<div className="floor-meta-popover"><div className="floor-meta-head"><strong>بيانات الطابق</strong><span>صفحة المصدر {activeFloor.sourcePage}</span></div><label><span>الاسم</span><input value={floorName} maxLength={100} onChange={e=>setFloorName(e.target.value)}/></label><div className="floor-meta-grid"><label><span>المنسوب م</span><input inputMode="decimal" value={floorElevation} onChange={e=>setFloorElevation(e.target.value)} placeholder="اختياري"/></label><label><span>الارتفاع م</span><input inputMode="decimal" value={floorHeight} onChange={e=>setFloorHeight(e.target.value)} placeholder="اختياري"/></label></div><button className="primary small" disabled={floorMetaBusy} onClick={()=>void saveFloorMetadata()}>{floorMetaBusy?<LoaderCircle className="spin" size={14}/>:<Check size={14}/>} حفظ بيانات الطابق</button><small>المنسوب والارتفاع محفوظان كأساس هندسي ولا يغيران الرسم ثنائي الأبعاد حاليًا.</small></div>}</div>}<button className="validate-chip export-chip" onClick={()=>setExportOpen(true)}><Download size={14}/> تصدير</button>{sourcePreview&&<label className="overlay-control"><span>الأصل</span><input type="range" min="0" max=".85" step=".05" value={sourceOpacity} onChange={e=>setSourceOpacity(Number(e.target.value))}/></label>}<button className="validate-chip" disabled={validationBusy} onClick={runValidation}>{validationBusy?<LoaderCircle className="spin" size={14}/>:<ShieldCheck size={14}/>} فحص</button>{(plan.source.pageCount??1)>1&&<div className="source-page-control"><span>PDF {plan.source.page}/{plan.source.pageCount}</span><input type="number" min="1" max={plan.source.pageCount??1} value={sourcePageInput} disabled={pageSwitchBusy||dirty} onChange={e=>setSourcePageInput(e.target.value)}/><button className="ghost" disabled={pageSwitchBusy||dirty||Number(sourcePageInput)===plan.source.page} onClick={()=>void reanalyzeSourcePage()}>{pageSwitchBusy?<LoaderCircle className="spin" size={13}/>:null} {project.floors?.some(item=>item.sourcePage===Number(sourcePageInput))?"فتح الصفحة":"تحليل الصفحة"}</button></div>}<div className="quality-pill">جودة التحليل {Math.round(plan.quality.overall*100)}%</div></div></div>
        {(project.floors?.length??0)>1&&<div className="floor-strip"><span>الطوابق المحللة</span><div>{project.floors!.map(item=><button key={item.id} className={item.id===project.activeFloorId?"active":""} disabled={pageSwitchBusy||dirty||item.id===project.activeFloorId} onClick={()=>void activateKnownFloor(item.id,item.sourcePage)}>{item.name}</button>)}</div></div>}
        {recoveredDraft&&<div className="recovered-draft"><div><strong>تمت استعادة مسودة تلقائية</strong><span>هذه التغييرات محفوظة سحابيًا لكنها ليست Revision رسمية بعد.</span></div><div><button className="ghost" disabled={saving} onClick={()=>void discardRecoveredDraft()}>تجاهل المسودة</button><button className="primary small" disabled={saving} onClick={save}><Save size={15}/> حفظ كنسخة</button></div></div>}
        <PlanCanvas plan={preview?.previewPlan??plan} readonly={Boolean(preview)||pageSwitchBusy} selectedWallId={selectedWall} onSelectWall={selectWall} selectedRoomId={selectedRoom} onSelectRoom={selectRoom} selectedOpeningId={selectedOpening} onSelectOpening={selectOpening} onPlanChange={applyLocalPlan} onPlanCommit={commitTransientPlan}
          calibrationMode={calibrating} calibrationPoints={calibrationPoints}
          onCalibrationPoint={point=>setCalibrationPoints(points=>points.length<2?[...points,point]:points)}
          backgroundUrl={sourcePreview} backgroundOpacity={sourceOpacity} comparisonPlan={preview?plan:null} validationFindings={validationReport?.findings??[]} layers={layers}/>
        {plan.quality.needsCalibration&&!calibrating&&<div className="inline-warning calibration-warning"><span>تعذر تثبيت المقياس تلقائيًا. ثبته مرة واحدة لتفعيل أوامر الأمتار بدقة.</span><button className="ghost" onClick={()=>{setCalibrating(true);setCalibrationPoints([]);}}>معايرة الآن</button></div>}
        {calibrating&&<div className="calibration-bar"><div><strong>معايرة المقياس</strong><span>{calibrationPoints.length<2?`حدد نقطتين على بُعد معروف · ${calibrationPoints.length}/2`:"أدخل المسافة الحقيقية بين النقطتين"}</span></div>{calibrationPoints.length===2&&<input inputMode="decimal" value={knownDistance} onChange={e=>setKnownDistance(e.target.value)} placeholder="مثال: 4.20 م"/>}<button className="ghost" onClick={()=>{setCalibrating(false);setCalibrationPoints([]);setKnownDistance("");}}>إلغاء</button>{calibrationPoints.length===2&&<button className="primary small" onClick={applyCalibration}><Check size={16}/> تثبيت</button>}</div>}
      </section>
      <aside className="ai-panel"><div className="ai-title"><div className="ai-avatar"><BrainCircuit size={22}/></div><div><strong>H Engineer</strong><span>يفهم الأثر قبل التنفيذ</span></div></div>
        {reviewItems.length>0&&<div className="reading-review-card"><div className="reading-review-head"><div><strong>مراجعة القراءة</strong><span>{reviewItems.length} عنصر منخفض الثقة يحتاج نظرة سريعة</span></div><span className="review-count">{reviewItems.length}</span></div><div className="reading-review-list">{reviewItems.slice(0,6).map(item=><button type="button" key={item.key} className={`reading-review-item ${selectedReviewItem?.key===item.key?"active":""}`} onClick={()=>focusReviewItem(item)}><span>{item.label}</span><small>{provenanceLabel(item.provenance)} · {Math.round(item.confidence*100)}%</small></button>)}</div>{selectedReviewItem&&<div className="reading-review-actions"><button className="primary small" onClick={confirmSelectedReading}><Check size={15}/> تأكيد القراءة</button>{selectedReviewItem.kind==="opening"&&<button className="delete-opening compact" onClick={deleteOpening}><Trash2 size={14}/> حذف العنصر</button>}</div>}<small className="review-note">التأكيد يسجل مراجعتك البشرية دون تغيير درجة ثقة الاستخراج الأصلية، ويمكن التراجع عنه قبل الحفظ.</small></div>}
        {validationReport&&<div className="validation-card"><div className="validation-summary"><div><strong>الفحص الهندسي الداخلي</strong><span>سلامة النموذج {Math.round(validationReport.score*100)}%</span></div><div className={`validation-score ${validationReport.findings.some(item=>item.severity==="critical")?"bad":validationReport.findings.length?"warn":"good"}`}>{Math.round(validationReport.score*100)}</div></div>{validationReport.findings.length?<div className="validation-findings">{validationReport.findings.slice(0,6).map((item,index)=><button type="button" key={`${item.code}-${index}`} className={`validation-finding ${item.severity} ${item.roomIds.length||(item.wallIds?.length??0)||(item.openingIds?.length??0)?"clickable":""}`} disabled={!(item.roomIds.length||(item.wallIds?.length??0)||(item.openingIds?.length??0))} onClick={()=>focusValidationFinding(item)}><span>{item.severity==="critical"?"!":"•"}</span><p>{item.text}</p></button>)}</div>:<div className="validation-clean"><Check size={16}/> لا توجد مشاكل هندسية واضحة في النموذج الحالي.</div>}<small>هذا فحص اتساق واستخدام داخلي، وليس اعتمادًا لكود البناء.</small></div>}
        {selectedWall&&plan.walls.find(wall=>wall.id===selectedWall)&&<div className="wall-editor"><div className="precise-title"><div><strong>تعديل الجدار</strong><span>{plan.metersPerPixel?`الطول ${(Math.hypot((plan.walls.find(w=>w.id===selectedWall)!.b.x-plan.walls.find(w=>w.id===selectedWall)!.a.x),(plan.walls.find(w=>w.id===selectedWall)!.b.y-plan.walls.find(w=>w.id===selectedWall)!.a.y))*plan.metersPerPixel).toFixed(2)} م`:"ثبّت المقياس لعرض القياسات الحقيقية"}</span></div><Ruler size={18}/></div><div className="wall-safety"><label><span>تصنيف الجدار</span><select value={plan.walls.find(w=>w.id===selectedWall)?.role??"unknown"} onChange={e=>updateSelectedWallRole(e.target.value as WallRole)}><option value="unknown">غير محدد</option><option value="interior">داخلي</option><option value="exterior">خارجي</option><option value="structural">إنشائي</option></select></label><button className={`ghost ${plan.walls.find(w=>w.id===selectedWall)?.locked?"wall-protected":""}`} onClick={toggleSelectedWallLock}>{plan.walls.find(w=>w.id===selectedWall)?.locked?"فك الحماية":"حماية الجدار"}</button>{plan.walls.find(w=>w.id===selectedWall)?.locked&&<span className="wall-protection-note">محمي من الحركة والتعديل التلقائي</span>}</div><label className="wall-thickness"><span>سماكة الجدار بالسنتيمتر</span><div><input inputMode="decimal" disabled={!plan.metersPerPixel||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} value={wallThicknessCm} onChange={e=>setWallThicknessCm(e.target.value)} placeholder={plan.metersPerPixel?"20.0":"ثبّت المقياس"}/><button className="ghost" disabled={!plan.metersPerPixel||!wallThicknessCm||Boolean(preview)||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} onClick={updateWallThickness}>تطبيق</button></div></label><div className="wall-move"><span>تحريك دقيق بالسنتيمتر</span><div><input inputMode="decimal" disabled={!plan.metersPerPixel||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} value={wallMoveCm} onChange={e=>setWallMoveCm(e.target.value)} placeholder="10"/><button className="ghost" disabled={!plan.metersPerPixel||!wallMoveCm||Boolean(preview)||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} onClick={()=>moveSelectedWallExact(-1)}>{(()=>{const w=plan.walls.find(item=>item.id===selectedWall);return w&&Math.abs(w.a.x-w.b.x)<=Math.abs(w.a.y-w.b.y)?"يسار":"أعلى";})()}</button><button className="ghost" disabled={!plan.metersPerPixel||!wallMoveCm||Boolean(preview)||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} onClick={()=>moveSelectedWallExact(1)}>{(()=>{const w=plan.walls.find(item=>item.id===selectedWall);return w&&Math.abs(w.a.x-w.b.x)<=Math.abs(w.a.y-w.b.y)?"يمين":"أسفل";})()}</button></div></div><div className="wall-opening-actions"><button className="ghost" disabled={Boolean(preview)||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} onClick={()=>addOpening("door")}><DoorOpen size={16}/> إضافة باب</button><button className="ghost" disabled={Boolean(preview)||Boolean(plan.walls.find(w=>w.id===selectedWall)?.locked)} onClick={()=>addOpening("window")}><Square size={15}/> إضافة نافذة</button></div></div>}
        {selectedOpening&&findOpening(plan,selectedOpening)&&<div className="opening-editor"><div className="precise-title"><div><strong>تعديل الفتحة</strong><span>صحح النوع والعرض والموقع على الجدار</span></div>{findOpening(plan,selectedOpening)?.kind==="door"?<DoorOpen size={19}/>:<Square size={18}/>}</div>{openingHostProtected(plan,selectedOpening)&&<div className="inline-warning opening-protected-note">هذه الفتحة على جدار محمي. فك حماية الجدار قبل تعديلها.</div>}<div className="opening-kind"><button disabled={openingHostProtected(plan,selectedOpening)} className={findOpening(plan,selectedOpening)?.kind==="door"?"active":""} onClick={()=>updateOpeningKind("door")}>باب</button><button disabled={openingHostProtected(plan,selectedOpening)} className={findOpening(plan,selectedOpening)?.kind==="window"?"active":""} onClick={()=>updateOpeningKind("window")}>نافذة</button></div><label className="opening-width"><span>العرض بالمتر</span><div><input inputMode="decimal" disabled={!plan.metersPerPixel||openingHostProtected(plan,selectedOpening)} value={openingWidth} onChange={e=>setOpeningWidth(e.target.value)} placeholder={plan.metersPerPixel?"0.90":"ثبّت المقياس"}/><button className="ghost" disabled={!plan.metersPerPixel||!openingWidth||openingHostProtected(plan,selectedOpening)} onClick={updateOpeningWidth}>تطبيق</button></div></label><label className="opening-position"><span>الموقع على الجدار · {openingPosition}%</span><input type="range" min="2" max="98" step="1" disabled={openingHostProtected(plan,selectedOpening)} value={openingPosition} onFocus={startOpeningPositionEdit} onBlur={finishOpeningPositionEdit} onPointerDown={startOpeningPositionEdit} onPointerUp={finishOpeningPositionEdit} onChange={e=>updateOpeningPosition(Number(e.target.value))}/></label><button className="delete-opening" disabled={openingHostProtected(plan,selectedOpening)} onClick={deleteOpening}><Trash2 size={15}/> حذف الفتحة</button></div>}
        <div className="precise-editor"><div className="precise-title"><div><strong>تعديل دقيق</strong><span>اختر الغرفة ثم أدخل المقاس بالمتر</span></div><Ruler size={19}/></div>
          <select value={selectedRoom??""} onChange={e=>selectRoom(e.target.value||null)}><option value="">اختر غرفة</option>{plan.rooms.map(room=><option key={room.id} value={room.id}>{room.name}</option>)}</select>
          {selectedRoom&&<div className="room-name-edit"><label><span>اسم الغرفة</span><input value={exactName} onChange={e=>setExactName(e.target.value)} maxLength={80}/></label><button className="ghost" disabled={!exactName.trim()||exactName.trim()===plan.rooms.find(room=>room.id===selectedRoom)?.name||Boolean(preview)} onClick={renameSelectedRoom}>تحديث</button></div>}
          <div className="dimension-grid"><label><span>العرض</span><input inputMode="decimal" value={exactWidth} onChange={e=>setExactWidth(e.target.value)} placeholder="5.00"/></label><label><span>الطول</span><input inputMode="decimal" value={exactHeight} onChange={e=>setExactHeight(e.target.value)} placeholder="4.00"/></label></div>
          <button className="ghost precise-preview" disabled={thinking||!selectedRoom||!exactWidth||!exactHeight||!plan.metersPerPixel} onClick={precisePreview}>{thinking?<LoaderCircle className="spin" size={17}/>:<Ruler size={17}/>} معاينة هندسية</button>
        </div>
        <div className="prompt-divider"><span>أو اكتب طلبك</span></div>
        <div className="prompt-box">{selectedContextLabel&&<div className="prompt-context">{selectedContextLabel}</div>}<textarea value={command} onChange={e=>setCommand(e.target.value)} placeholder={selectedOpening?"مثال: اجعل عرضه 90 سم أو حركه يمين 30 سم":selectedWall?"مثال: حركه يمين 30 سم أو اجعل سماكته 20 سم":selectedRoom?"مثال: اجعلها 5×5 أو زد عرضها متر":"مثال: عدّل غرفة النوم إلى 5×5"}/><button className="primary" disabled={thinking||!command.trim()} onClick={ask}>{thinking?<LoaderCircle className="spin" size={18}/>:<Sparkles size={18}/>} تحليل الطلب</button></div>
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
