import { useEffect,useMemo,useRef,useState } from "react";
import type { ElementProvenance,FloorPlanModel,Point,ValidationFinding,Wall } from "@manzil/contracts";
import { Hand,Magnet,Maximize2,Minus,PenLine,Plus,RotateCcw,Ruler } from "lucide-react";
import { easePreview,interpolatePlan } from "./previewInterpolation";

export interface PlanLayerVisibility{
  source:boolean;
  rooms:boolean;
  walls:boolean;
  openings:boolean;
  labels:boolean;
  validation:boolean;
  uncertainty:boolean;
}

export const DEFAULT_PLAN_LAYERS:PlanLayerVisibility={
  source:true,
  rooms:true,
  walls:true,
  openings:true,
  labels:true,
  validation:true,
  uncertainty:true,
};

interface Props{
  plan:FloorPlanModel;
  selectedWallId?:string|null;
  onSelectWall?:(id:string|null)=>void;
  selectedRoomId?:string|null;
  onSelectRoom?:(id:string|null)=>void;
  selectedOpeningId?:string|null;
  onSelectOpening?:(id:string|null)=>void;
  selectedDimensionId?:string|null;
  onSelectDimension?:(id:string|null)=>void;
  onPlanChange?:(plan:FloorPlanModel,recordHistory?:boolean)=>void;
  onPlanCommit?:(basePlan:FloorPlanModel)=>void;
  onAddWall?:(a:Point,b:Point)=>void;
  readonly?:boolean;
  calibrationMode?:boolean;
  calibrationPoints?:Point[];
  onCalibrationPoint?:(point:Point)=>void;
  backgroundUrl?:string|null;
  backgroundOpacity?:number;
  comparisonPlan?:FloorPlanModel|null;
  validationFindings?:ValidationFinding[];
  layers?:Partial<PlanLayerVisibility>;
}
type DragState={wallId:string;startClient:Point;original:Wall;basePlan:FloorPlanModel;changed:boolean}|null;
type PanDragState={pointerId:number;startClient:Point;scrollLeft:number;scrollTop:number}|null;

function overlap(a1:number,a2:number,b1:number,b2:number){
  return Math.max(0,Math.min(a2,b2)-Math.max(a1,b1));
}

function manualProvenance(value?:ElementProvenance):ElementProvenance{
  return value?"mixed":"manual";
}

export function snapAxis(value:number,metersPerPixel?:number|null,stepM=.05){
  if(!metersPerPixel||metersPerPixel<=0||stepM<=0)return value;
  const stepPx=stepM/metersPerPixel;
  return Math.round(value/stepPx)*stepPx;
}

function polygonArea(points:Point[]){
  let sum=0;
  for(let i=0;i<points.length;i++){
    const a=points[i]; const b=points[(i+1)%points.length];
    sum+=a.x*b.y-b.x*a.y;
  }
  return Math.abs(sum)/2;
}

function roomVisualMetrics(room:FloorPlanModel["rooms"][number],metersPerPixel?:number|null){
  const xs=room.polygon.map(p=>p.x),ys=room.polygon.map(p=>p.y);
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

export function moveWallAndTopology(plan:FloorPlanModel,original:Wall,next:Wall):FloorPlanModel{
  const vertical=Math.abs(original.a.x-original.b.x)<=Math.abs(original.a.y-original.b.y);
  const oldAxis=vertical?(original.a.x+original.b.x)/2:(original.a.y+original.b.y)/2;
  const desired=vertical?(next.a.x+next.b.x)/2:(next.a.y+next.b.y)/2;
  const span1=vertical?Math.min(original.a.y,original.b.y):Math.min(original.a.x,original.b.x);
  const span2=vertical?Math.max(original.a.y,original.b.y):Math.max(original.a.x,original.b.x);
  const tolerance=Math.max(6,original.thicknessPx*2);
  const minSizePx=plan.metersPerPixel?Math.max(28,.8/plan.metersPerPixel):32;

  let lower=0;
  let upper=vertical?plan.widthPx:plan.heightPx;

  for(const room of plan.rooms){
    const xs=room.polygon.map(p=>p.x); const ys=room.polygon.map(p=>p.y);
    const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
    const shared=vertical?overlap(top,bottom,span1,span2):overlap(left,right,span1,span2);
    if(shared<=tolerance) continue;
    if(vertical){
      if(Math.abs(left-oldAxis)<=tolerance) upper=Math.min(upper,right-minSizePx);
      if(Math.abs(right-oldAxis)<=tolerance) lower=Math.max(lower,left+minSizePx);
    }else{
      if(Math.abs(top-oldAxis)<=tolerance) upper=Math.min(upper,bottom-minSizePx);
      if(Math.abs(bottom-oldAxis)<=tolerance) lower=Math.max(lower,top+minSizePx);
    }
  }

  const axis=Math.max(lower,Math.min(upper,desired));
  const delta=axis-oldAxis;
  const movedWallIds=new Set(plan.walls.filter(wall=>{
    const wallVertical=Math.abs(wall.a.x-wall.b.x)<=Math.abs(wall.a.y-wall.b.y);
    if(wallVertical!==vertical)return false;
    const wallAxis=vertical?(wall.a.x+wall.b.x)/2:(wall.a.y+wall.b.y)/2;
    if(Math.abs(wallAxis-oldAxis)>tolerance)return false;
    const wallSpan1=vertical?Math.min(wall.a.y,wall.b.y):Math.min(wall.a.x,wall.b.x);
    const wallSpan2=vertical?Math.max(wall.a.y,wall.b.y):Math.max(wall.a.x,wall.b.x);
    return overlap(wallSpan1,wallSpan2,span1,span2)>0;
  }).map(wall=>wall.id));
  movedWallIds.add(original.id);

  const walls=plan.walls.map(wall=>{
    if(movedWallIds.has(wall.id)){
      const metadata={reviewed:wall.id===original.id?true:wall.reviewed,provenance:manualProvenance(wall.provenance)};
      return vertical
        ?{...wall,...metadata,a:{...wall.a,x:wall.a.x+delta},b:{...wall.b,x:wall.b.x+delta}}
        :{...wall,...metadata,a:{...wall.a,y:wall.a.y+delta},b:{...wall.b,y:wall.b.y+delta}};
    }

    const wallVertical=Math.abs(wall.a.x-wall.b.x)<=Math.abs(wall.a.y-wall.b.y);
    if(wallVertical===vertical)return wall;

    if(vertical){
      const movePoint=(point:Point)=>Math.abs(point.x-oldAxis)<=tolerance&&point.y>=span1-tolerance&&point.y<=span2+tolerance?{...point,x:axis}:point;
      const a=movePoint(wall.a),b=movePoint(wall.b);
      const changed=a!==wall.a||b!==wall.b;
      return changed?{...wall,a,b,provenance:manualProvenance(wall.provenance)}:wall;
    }
    const movePoint=(point:Point)=>Math.abs(point.y-oldAxis)<=tolerance&&point.x>=span1-tolerance&&point.x<=span2+tolerance?{...point,y:axis}:point;
    const a=movePoint(wall.a),b=movePoint(wall.b);
    const changed=a!==wall.a||b!==wall.b;
    return changed?{...wall,a,b,provenance:manualProvenance(wall.provenance)}:wall;
  });

  const rooms=plan.rooms.map(room=>{
    const xs=room.polygon.map(p=>p.x); const ys=room.polygon.map(p=>p.y);
    const left=Math.min(...xs),right=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
    const shared=vertical?overlap(top,bottom,span1,span2):overlap(left,right,span1,span2);
    if(shared<=tolerance) return room;
    const touches=vertical
      ?Math.abs(left-oldAxis)<=tolerance||Math.abs(right-oldAxis)<=tolerance
      :Math.abs(top-oldAxis)<=tolerance||Math.abs(bottom-oldAxis)<=tolerance;
    if(!touches) return room;
    const polygon=room.polygon.map(point=>{
      if(vertical&&Math.abs(point.x-oldAxis)<=tolerance) return {...point,x:axis};
      if(!vertical&&Math.abs(point.y-oldAxis)<=tolerance) return {...point,y:axis};
      return point;
    });
    return {...room,polygon,areaM2:plan.metersPerPixel?Number((polygonArea(polygon)*plan.metersPerPixel*plan.metersPerPixel).toFixed(2)):room.areaM2,provenance:manualProvenance(room.provenance)};
  });

  const openings=[...plan.doors,...plan.windows];
  const movedOpenings=new Map(openings.filter(o=>o.wallId&&movedWallIds.has(o.wallId)).map(o=>[
    o.id,
    vertical
      ?{...o,a:{...o.a,x:o.a.x+delta},b:{...o.b,x:o.b.x+delta},provenance:manualProvenance(o.provenance)}
      :{...o,a:{...o.a,y:o.a.y+delta},b:{...o.b,y:o.b.y+delta},provenance:manualProvenance(o.provenance)}
  ]));

  return {
    ...plan,
    walls,
    rooms,
    doors:plan.doors.map(o=>movedOpenings.get(o.id)??o),
    windows:plan.windows.map(o=>movedOpenings.get(o.id)??o),
  };
}

export function PlanCanvas({plan,selectedWallId,onSelectWall,selectedRoomId,onSelectRoom,selectedOpeningId,onSelectOpening,selectedDimensionId,onSelectDimension,onPlanChange,onPlanCommit,onAddWall,readonly,calibrationMode=false,calibrationPoints=[],onCalibrationPoint,backgroundUrl=null,backgroundOpacity=.38,comparisonPlan=null,validationFindings=[],layers}:Props){
  const[zoom,setZoom]=useState(1);
  const layerState=useMemo(()=>({...DEFAULT_PLAN_LAYERS,...layers}),[layers]);
  const[drag,setDrag]=useState<DragState>(null);
  const[panMode,setPanMode]=useState(()=>typeof window!=="undefined"&&window.matchMedia?.("(pointer: coarse)").matches===true);
  const[spacePan,setSpacePan]=useState(false);
  const[panDrag,setPanDrag]=useState<PanDragState>(null);
  const[measureMode,setMeasureMode]=useState(false);
  const[drawWallMode,setDrawWallMode]=useState(false);
  const[wallDrawStart,setWallDrawStart]=useState<Point|null>(null);
  const[wallDrawCursor,setWallDrawCursor]=useState<Point|null>(null);
  const[snapEnabled,setSnapEnabled]=useState(true);
  const[measurePoints,setMeasurePoints]=useState<Point[]>([]);
  const[previewProgress,setPreviewProgress]=useState(1);
  const svgRef=useRef<SVGSVGElement|null>(null);
  const viewportRef=useRef<HTMLDivElement|null>(null);
  const effectivePan=panMode||spacePan;
  useEffect(()=>{
    const down=(event:KeyboardEvent)=>{
      const target=event.target as HTMLElement|null;
      const tag=target?.tagName?.toLowerCase();
      if(tag==="input"||tag==="textarea"||tag==="select"||target?.isContentEditable)return;
      if(event.code==="Space"){
        event.preventDefault();
        setSpacePan(true);
      }
      if(event.key==="Escape"){
        setMeasureMode(false);
        setMeasurePoints([]);
        setDrawWallMode(false);
        setWallDrawStart(null);
        setWallDrawCursor(null);
      }
    };
    const up=(event:KeyboardEvent)=>{if(event.code==="Space")setSpacePan(false);};
    const blur=()=>setSpacePan(false);
    window.addEventListener("keydown",down);
    window.addEventListener("keyup",up);
    window.addEventListener("blur",blur);
    return()=>{window.removeEventListener("keydown",down);window.removeEventListener("keyup",up);window.removeEventListener("blur",blur);};
  },[]);

  useEffect(()=>{
    if(!comparisonPlan){setPreviewProgress(1);return;}
    if(typeof window!=="undefined"&&window.matchMedia?.("(prefers-reduced-motion: reduce)").matches){setPreviewProgress(1);return;}
    setPreviewProgress(0);
    let frame=0;
    const started=performance.now();
    const duration=620;
    const tick=(now:number)=>{
      const progress=Math.min(1,(now-started)/duration);
      setPreviewProgress(progress);
      if(progress<1)frame=requestAnimationFrame(tick);
    };
    frame=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(frame);
  },[comparisonPlan,plan]);
  const viewBox=useMemo(()=>`0 0 ${Math.max(plan.widthPx,1)} ${Math.max(plan.heightPx,1)}`,[plan.widthPx,plan.heightPx]);
  const renderPlan=useMemo(
    ()=>comparisonPlan&&previewProgress<1?interpolatePlan(comparisonPlan,plan,easePreview(previewProgress)):plan,
    [comparisonPlan,plan,previewProgress]
  );
  const zoomStageStyle=useMemo(()=>({
    width:`min(${zoom*100}%, ${Math.round(1100*zoom)}px)`,
    aspectRatio:`${Math.max(plan.widthPx,1)} / ${Math.max(plan.heightPx,1)}`,
  }),[zoom,plan.widthPx,plan.heightPx]);

  const validationByRoom=useMemo(()=>{
    const rank={info:1,warning:2,critical:3} as const;
    const result=new Map<string,ValidationFinding["severity"]>();
    for(const finding of validationFindings){
      for(const roomId of finding.roomIds){
        const current=result.get(roomId);
        if(!current||rank[finding.severity]>rank[current])result.set(roomId,finding.severity);
      }
    }
    return result;
  },[validationFindings]);
  const validationByWall=useMemo(()=>{
    const rank={info:1,warning:2,critical:3} as const;
    const result=new Map<string,ValidationFinding["severity"]>();
    for(const finding of validationFindings){
      for(const wallId of finding.wallIds??[]){
        const current=result.get(wallId);
        if(!current||rank[finding.severity]>rank[current])result.set(wallId,finding.severity);
      }
    }
    return result;
  },[validationFindings]);
  const validationByOpening=useMemo(()=>{
    const rank={info:1,warning:2,critical:3} as const;
    const result=new Map<string,ValidationFinding["severity"]>();
    for(const finding of validationFindings){
      for(const openingId of finding.openingIds??[]){
        const current=result.get(openingId);
        if(!current||rank[finding.severity]>rank[current])result.set(openingId,finding.severity);
      }
    }
    return result;
  },[validationFindings]);
  const validationByDimension=useMemo(()=>{
    const rank={info:1,warning:2,critical:3} as const;
    const result=new Map<string,ValidationFinding["severity"]>();
    for(const finding of validationFindings){
      for(const dimensionId of finding.dimensionIds??[]){
        const current=result.get(dimensionId);
        if(!current||rank[finding.severity]>rank[current])result.set(dimensionId,finding.severity);
      }
    }
    return result;
  },[validationFindings]);

  const screenToPlan=(clientX:number,clientY:number):Point=>{
    const svg=svgRef.current;if(!svg)return{x:0,y:0};
    const rect=svg.getBoundingClientRect();
    return{x:(clientX-rect.left)*(plan.widthPx/rect.width),y:(clientY-rect.top)*(plan.heightPx/rect.height)};
  };
  const toPlanDelta=(dx:number,dy:number)=>{
    const svg=svgRef.current;if(!svg)return{x:0,y:0};
    const rect=svg.getBoundingClientRect();
    return{x:dx*(plan.widthPx/rect.width),y:dy*(plan.heightPx/rect.height)};
  };
  const move=(event:React.PointerEvent)=>{
    if(drawWallMode&&wallDrawStart&&!effectivePan&&!calibrationMode){
      setWallDrawCursor(screenToPlan(event.clientX,event.clientY));
    }
    if(panDrag&&effectivePan&&!calibrationMode){
      const viewport=viewportRef.current;
      if(viewport){
        viewport.scrollLeft=panDrag.scrollLeft-(event.clientX-panDrag.startClient.x);
        viewport.scrollTop=panDrag.scrollTop-(event.clientY-panDrag.startClient.y);
      }
      return;
    }
    if(!drag||!onPlanChange||readonly||calibrationMode||measureMode||effectivePan)return;
    const d=toPlanDelta(event.clientX-drag.startClient.x,event.clientY-drag.startClient.y);
    const horizontal=Math.abs(drag.original.a.y-drag.original.b.y)<Math.abs(drag.original.a.x-drag.original.b.x);
    const rawAxis=horizontal?drag.original.a.y+d.y:drag.original.a.x+d.x;
    const axis=snapEnabled&&!event.shiftKey?snapAxis(rawAxis,plan.metersPerPixel,.05):rawAxis;
    const candidate:Wall=horizontal
      ?{...drag.original,a:{...drag.original.a,y:axis},b:{...drag.original.b,y:axis}}
      :{...drag.original,a:{...drag.original.a,x:axis},b:{...drag.original.b,x:axis}};
    const next=moveWallAndTopology(drag.basePlan,drag.original,candidate);
    onPlanChange(next,false);
    if(!drag.changed&&Math.hypot(d.x,d.y)>.5)setDrag(current=>current?{...current,changed:true}:current);
  };
  const finishDrag=(event?:React.PointerEvent)=>{
    if(panDrag){
      if(event&&event.currentTarget instanceof HTMLElement&&event.currentTarget.hasPointerCapture?.(panDrag.pointerId)){
        event.currentTarget.releasePointerCapture(panDrag.pointerId);
      }
      setPanDrag(null);
    }
    if(drag?.changed)onPlanCommit?.(drag.basePlan);
    setDrag(null);
  };
  const startPan=(event:React.PointerEvent<HTMLDivElement>)=>{
    if(!effectivePan||calibrationMode||event.button!==0)return;
    const viewport=viewportRef.current;
    if(!viewport)return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setPanDrag({
      pointerId:event.pointerId,
      startClient:{x:event.clientX,y:event.clientY},
      scrollLeft:viewport.scrollLeft,
      scrollTop:viewport.scrollTop,
    });
  };

  const snapDrawPoint=(point:Point)=>{
    let next={...point};
    if(snapEnabled&&plan.metersPerPixel){
      next={x:snapAxis(next.x,plan.metersPerPixel,.05),y:snapAxis(next.y,plan.metersPerPixel,.05)};
    }
    const tolerance=plan.metersPerPixel?Math.max(6,.12/plan.metersPerPixel):10;
    let best:Point|null=null;let bestDistance=tolerance;
    for(const wall of plan.walls){
      for(const endpoint of [wall.a,wall.b]){
        const d=Math.hypot(endpoint.x-next.x,endpoint.y-next.y);
        if(d<bestDistance){best=endpoint;bestDistance=d;}
      }
    }
    return best?{...best}:next;
  };
  const handleCanvasPointer=(event:React.PointerEvent<SVGSVGElement>)=>{
    if(calibrationMode){
      if(!onCalibrationPoint||calibrationPoints.length>=2)return;
      onCalibrationPoint(screenToPlan(event.clientX,event.clientY));
      return;
    }
    if(drawWallMode){
      if(readonly||!onAddWall)return;
      const point=snapDrawPoint(screenToPlan(event.clientX,event.clientY));
      if(!wallDrawStart){
        setWallDrawStart(point);setWallDrawCursor(point);return;
      }
      onAddWall(wallDrawStart,point);
      setWallDrawStart(null);setWallDrawCursor(null);
      return;
    }
    if(!measureMode)return;
    const point=screenToPlan(event.clientX,event.clientY);
    setMeasurePoints(points=>points.length>=2?[point]:[...points,point]);
  };
  const measurement=measurePoints.length===2
    ?Math.hypot(measurePoints[1].x-measurePoints[0].x,measurePoints[1].y-measurePoints[0].y)
    :null;
  const measurementLabel=measurement===null
    ?""
    :plan.metersPerPixel
      ?`${(measurement*plan.metersPerPixel).toFixed(2)} م`
      :"ثبّت المقياس";
  const wheelZoom=(event:React.WheelEvent<HTMLDivElement>)=>{
    if(!event.ctrlKey&&!event.metaKey)return;
    event.preventDefault();
    const step=event.deltaY>0?-.10:.10;
    setZoom(value=>Math.max(.45,Math.min(3,value+step)));
  };

  return <div className={`canvas-shell ${calibrationMode?"calibration-active":""} ${measureMode?"measure-active":""} ${drawWallMode?"wall-draw-active":""} ${effectivePan&&!calibrationMode?"pan-active":""}`}>
    <div className="canvas-toolbar">
      <button className="icon-button" onClick={()=>setZoom(z=>Math.min(z+.15,2.5))} aria-label="تكبير"><Plus size={18}/></button>
      <span>{Math.round(zoom*100)}%</span>
      <button className="icon-button" onClick={()=>setZoom(z=>Math.max(z-.15,.45))} aria-label="تصغير"><Minus size={18}/></button>
      <button className="icon-button" onClick={()=>setZoom(1)} aria-label="إعادة الضبط"><RotateCcw size={18}/></button><button className="icon-button" onClick={()=>{setZoom(1);const viewport=viewportRef.current;if(viewport){viewport.scrollLeft=0;viewport.scrollTop=0;}}} aria-label="ملاءمة المخطط للشاشة" title="ملاءمة المخطط"><Maximize2 size={17}/></button>
      <button className={`icon-button ${effectivePan&&!calibrationMode?"active-tool":""}`} disabled={calibrationMode} onClick={()=>{setPanMode(value=>!value);setMeasureMode(false);setDrawWallMode(false);setWallDrawStart(null);setWallDrawCursor(null);setMeasurePoints([]);setDrag(null);setPanDrag(null);}} aria-label="تحريك مساحة العمل" title="وضع التحريك يمنع تعديل العناصر بالخطأ"><Hand size={17}/></button>
      <button className={`icon-button ${snapEnabled?"active-tool":""}`} disabled={!plan.metersPerPixel||calibrationMode||measureMode||panMode} onClick={()=>setSnapEnabled(value=>!value)} aria-label="محاذاة تلقائية كل 5 سم" title="محاذاة 5 سم · اضغط Shift للتجاوز"><Magnet size={17}/></button>
      <button className={`icon-button ${drawWallMode?"active-tool":""}`} disabled={readonly||calibrationMode||!onAddWall} onClick={()=>{setDrawWallMode(value=>!value);setPanMode(false);setMeasureMode(false);setMeasurePoints([]);setWallDrawStart(null);setWallDrawCursor(null);setDrag(null);setPanDrag(null);}} aria-label="إضافة جدار" title="انقر نقطتين لإضافة جدار يدويًا"><PenLine size={17}/></button>
      <button className={`icon-button ${measureMode?"active-tool":""}`} disabled={calibrationMode} onClick={()=>{setMeasureMode(value=>!value);setDrawWallMode(false);setWallDrawStart(null);setWallDrawCursor(null);setPanMode(false);setMeasurePoints([]);setDrag(null);setPanDrag(null);}} aria-label="قياس مسافة"><Ruler size={17}/></button>
    </div>
    <div ref={viewportRef} className="canvas-viewport" onWheel={wheelZoom} onPointerDown={startPan} onPointerMove={move} onPointerUp={finishDrag} onPointerCancel={finishDrag}>
      <div className="plan-zoom-stage" style={zoomStageStyle}>
      <svg ref={svgRef} className="plan-svg" viewBox={viewBox} onPointerDown={handleCanvasPointer}>
        <rect width={plan.widthPx} height={plan.heightPx} fill="#fff"/>
        {layerState.source&&backgroundUrl&&<image href={backgroundUrl} x={0} y={0} width={plan.widthPx} height={plan.heightPx} preserveAspectRatio="none" opacity={backgroundOpacity} pointerEvents="none"/>}
        {comparisonPlan&&previewProgress>=1&&comparisonPlan.rooms.map(oldRoom=>{
          const current=plan.rooms.find(room=>room.id===oldRoom.id);
          const oldPoints=oldRoom.polygon.map(p=>`${p.x},${p.y}`).join(" ");
          const currentPoints=current?.polygon.map(p=>`${p.x},${p.y}`).join(" ");
          if(!current||oldPoints===currentPoints)return null;
          return <polygon key={`old-room-${oldRoom.id}`} points={oldPoints} fill="rgba(244,63,94,.045)" stroke="#e11d48" strokeWidth={3} strokeDasharray="12 8" pointerEvents="none"/>;
        })}
        {comparisonPlan&&previewProgress>=1&&comparisonPlan.walls.map(oldWall=>{
          const current=plan.walls.find(wall=>wall.id===oldWall.id);
          if(!current)return null;
          const changed=Math.abs(current.a.x-oldWall.a.x)>1||Math.abs(current.a.y-oldWall.a.y)>1||Math.abs(current.b.x-oldWall.b.x)>1||Math.abs(current.b.y-oldWall.b.y)>1;
          if(!changed)return null;
          return <line key={`old-wall-${oldWall.id}`} x1={oldWall.a.x} y1={oldWall.a.y} x2={oldWall.b.x} y2={oldWall.b.y} stroke="#e11d48" strokeWidth={Math.max(3,oldWall.thicknessPx)} strokeDasharray="12 8" opacity={.8} pointerEvents="none"/>;
        })}
        {layerState.rooms&&renderPlan.rooms.map(room=>{
          const metrics=roomVisualMetrics(room,renderPlan.metersPerPixel);
          const showMetrics=Boolean(renderPlan.metersPerPixel)&&metrics.widthPx>=70&&metrics.heightPx>=55;
          const selected=selectedRoomId===room.id;
          const validationSeverity=validationByRoom.get(room.id);
          const uncertain=layerState.uncertainty&&!room.reviewed&&room.confidence<.78;
          return <g key={room.id}>
            <polygon
              points={room.polygon.map(p=>`${p.x},${p.y}`).join(" ")}
              fill={selected?"rgba(37,99,235,.14)":uncertain?"rgba(217,119,6,.055)":"rgba(37,99,235,.055)"}
              stroke={selected?"#2563eb":uncertain?"#d97706":"rgba(37,99,235,.16)"}
              strokeWidth={selected?3:uncertain?2:1}
              strokeDasharray={!selected&&uncertain?"8 6":undefined}
              className={readonly||calibrationMode||measureMode?undefined:"editable-room"}
              onPointerDown={event=>{if(readonly||calibrationMode||measureMode||drawWallMode||effectivePan)return;event.stopPropagation();onSelectDimension?.(null);onSelectRoom?.(room.id);}}
            />
            {layerState.validation&&validationSeverity&&<polygon
              points={room.polygon.map(p=>`${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke={validationSeverity==="critical"?"#e11d48":validationSeverity==="warning"?"#d97706":"#2563eb"}
              strokeWidth={validationSeverity==="critical"?5:3}
              strokeDasharray={validationSeverity==="critical"?"14 7":"10 7"}
              opacity={.9}
              pointerEvents="none"
              className={`validation-room-outline ${validationSeverity}`}
            />}
            {room.polygon.length>0&&<text x={metrics.cx} y={metrics.cy} textAnchor="middle" dominantBaseline="middle" className="room-label">
              <tspan x={metrics.cx} dy={showMetrics?-10:0}>{room.name||"غرفة"}</tspan>
              {showMetrics&&<tspan x={metrics.cx} dy={18} className="room-dimensions">{metrics.widthM!.toFixed(2)} × {metrics.heightM!.toFixed(2)} م</tspan>}
              {showMetrics&&metrics.areaM2!==null&&<tspan x={metrics.cx} dy={16} className="room-area">{metrics.areaM2.toFixed(1)} م²</tspan>}
            </text>}
          </g>;
        })}
        {layerState.walls&&renderPlan.walls.map(wall=>{
          const severity=validationByWall.get(wall.id);
          const uncertain=layerState.uncertainty&&!wall.reviewed&&wall.confidence<.72;
          const stroke=selectedWallId===wall.id?"#2563eb":severity==="critical"?"#e11d48":severity==="warning"?"#d97706":severity==="info"?"#2563eb":uncertain?"#d97706":"#0f172a";
          return <line key={wall.id}
            x1={wall.a.x} y1={wall.a.y} x2={wall.b.x} y2={wall.b.y}
            stroke={stroke}
            strokeWidth={Math.max(wall.thicknessPx,selectedWallId===wall.id?5:severity==="critical"?5:3)}
            strokeLinecap="round" className={readonly||calibrationMode||measureMode?undefined:wall.locked?"editable-wall locked-wall":"editable-wall"}
            strokeDasharray={severity&&!selectedWallId?severity==="critical"?"14 6":"10 6":uncertain&&!selectedWallId?"7 5":wall.locked&&!selectedWallId?"5 5":undefined}
            onPointerDown={e=>{if(readonly||calibrationMode||measureMode||drawWallMode||effectivePan)return;onSelectDimension?.(null);onSelectOpening?.(null);onSelectWall?.(wall.id);if(wall.locked)return;e.currentTarget.setPointerCapture(e.pointerId);setDrag({wallId:wall.id,startClient:{x:e.clientX,y:e.clientY},original:wall,basePlan:plan,changed:false});}}
          />;
        })}
        {layerState.openings&&renderPlan.doors.map(o=>{
          const severity=validationByOpening.get(o.id);
          const uncertain=layerState.uncertainty&&!o.reviewed&&o.confidence<.84;
          const stroke=selectedOpeningId===o.id?"#1d4ed8":severity==="critical"?"#e11d48":severity==="warning"?"#d97706":uncertain?"#d97706":"#0ea5e9";
          return <g key={o.id} className={readonly||calibrationMode||measureMode?undefined:"editable-opening"} onPointerDown={event=>{if(readonly||calibrationMode||measureMode||drawWallMode||effectivePan)return;event.stopPropagation();onSelectDimension?.(null);onSelectOpening?.(o.id);}}>
            {!readonly&&!calibrationMode&&<line x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke="transparent" strokeWidth={18}/>}
            <line x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke={stroke} strokeWidth={selectedOpeningId===o.id?7:severity==="critical"?6:4} strokeLinecap="round" strokeDasharray={severity&&!selectedOpeningId?"9 5":uncertain&&!selectedOpeningId?"7 5":undefined}/>
          </g>;
        })}
        {layerState.openings&&renderPlan.windows.map(o=>{
          const severity=validationByOpening.get(o.id);
          const uncertain=layerState.uncertainty&&!o.reviewed&&o.confidence<.84;
          const stroke=selectedOpeningId===o.id?"#1d4ed8":severity==="critical"?"#e11d48":severity==="warning"?"#d97706":uncertain?"#d97706":"#38bdf8";
          return <g key={o.id} className={readonly||calibrationMode||measureMode?undefined:"editable-opening"} onPointerDown={event=>{if(readonly||calibrationMode||measureMode||drawWallMode||effectivePan)return;event.stopPropagation();onSelectDimension?.(null);onSelectOpening?.(o.id);}}>
            {!readonly&&!calibrationMode&&<line x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke="transparent" strokeWidth={18}/>}
            <line x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke={stroke} strokeWidth={selectedOpeningId===o.id?6:severity==="critical"?5:3} strokeLinecap="round" strokeDasharray={severity&&!selectedOpeningId?"9 5":uncertain&&!selectedOpeningId?"7 5":undefined}/>
          </g>;
        })}
        {layerState.labels&&renderPlan.labels.filter(label=>label.kind!=="dimension"||!(renderPlan.dimensions??[]).some(item=>item.sourceLabelId===label.id)).map(label=>{
          const low=layerState.uncertainty&&!label.reviewed&&label.confidence<.78;
          const className=`plan-ocr-label ${label.kind} ${low?"uncertain":""}`;
          return <text key={label.id} x={label.center.x} y={label.center.y} textAnchor="middle" dominantBaseline="middle" className={className} pointerEvents="none">
            {label.text}
          </text>;
        })}
        {layerState.labels&&(renderPlan.dimensions??[]).map(dimension=>{
          const selected=selectedDimensionId===dimension.id;
          const severity=validationByDimension.get(dimension.id);
          const uncertain=layerState.uncertainty&&!dimension.reviewed&&dimension.confidence<.84;
          const stroke=selected?"#1d4ed8":severity==="critical"?"#e11d48":severity==="warning"?"#d97706":uncertain?"#d97706":"#7c3aed";
          return <g key={dimension.id} className={readonly||calibrationMode||measureMode?undefined:"editable-dimension"} onPointerDown={event=>{
            if(readonly||calibrationMode||measureMode||drawWallMode||effectivePan)return;
            event.stopPropagation();
            onSelectRoom?.(null);onSelectWall?.(null);onSelectOpening?.(null);onSelectDimension?.(dimension.id);
          }}>
            {!readonly&&!calibrationMode&&<circle cx={dimension.center.x} cy={dimension.center.y} r={16} fill="transparent"/>}
            <circle cx={dimension.center.x} cy={dimension.center.y} r={selected?7:5} fill="#fff" stroke={stroke} strokeWidth={selected?3:2}/>
            <text x={dimension.center.x+10} y={dimension.center.y-10} textAnchor="start" className="plan-dimension-evidence" fill={stroke}>{dimension.text}</text>
          </g>;
        })}
        {drawWallMode&&wallDrawStart&&wallDrawCursor&&<g pointerEvents="none">
          <line x1={wallDrawStart.x} y1={wallDrawStart.y} x2={wallDrawCursor.x} y2={wallDrawCursor.y} stroke="#2563eb" strokeWidth={4} strokeDasharray="9 6"/>
          <circle cx={wallDrawStart.x} cy={wallDrawStart.y} r={7} fill="#2563eb"/>
          <circle cx={wallDrawCursor.x} cy={wallDrawCursor.y} r={6} fill="#ffffff" stroke="#2563eb" strokeWidth={3}/>
        </g>}
        {measurement!==null&&measurePoints.length===2&&<g pointerEvents="none">
          <line x1={measurePoints[0].x} y1={measurePoints[0].y} x2={measurePoints[1].x} y2={measurePoints[1].y} stroke="#7c3aed" strokeWidth={3} strokeDasharray="9 6"/>
          <circle cx={measurePoints[0].x} cy={measurePoints[0].y} r={7} fill="#7c3aed"/>
          <circle cx={measurePoints[1].x} cy={measurePoints[1].y} r={7} fill="#7c3aed"/>
          <g transform={`translate(${(measurePoints[0].x+measurePoints[1].x)/2} ${(measurePoints[0].y+measurePoints[1].y)/2})`}>
            <rect x={-48} y={-18} width={96} height={28} rx={8} fill="#ffffff" stroke="#c4b5fd"/>
            <text x={0} y={-1} textAnchor="middle" dominantBaseline="middle" className="measure-label">{measurementLabel}</text>
          </g>
        </g>}
        {measureMode&&measurePoints.length===1&&<circle cx={measurePoints[0].x} cy={measurePoints[0].y} r={8} fill="#7c3aed" pointerEvents="none"/>}
        {calibrationPoints.length===2&&<line x1={calibrationPoints[0].x} y1={calibrationPoints[0].y} x2={calibrationPoints[1].x} y2={calibrationPoints[1].y} stroke="#e11d48" strokeWidth={3} strokeDasharray="10 7"/>}
        {calibrationPoints.map((point,index)=><g key={index}><circle cx={point.x} cy={point.y} r={9} fill="#e11d48"/><text x={point.x+14} y={point.y-12} className="calibration-label">{index+1}</text></g>)}
      </svg>
      </div>
    </div>
  </div>;
}
