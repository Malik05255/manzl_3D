import { useMemo,useRef,useState } from "react";
import type { FloorPlanModel,Point,Wall } from "@manzil/contracts";
import { Minus,Plus,RotateCcw } from "lucide-react";

interface Props{
  plan:FloorPlanModel;
  selectedWallId?:string|null;
  onSelectWall?:(id:string|null)=>void;
  selectedRoomId?:string|null;
  onSelectRoom?:(id:string|null)=>void;
  onPlanChange?:(plan:FloorPlanModel)=>void;
  readonly?:boolean;
  calibrationMode?:boolean;
  calibrationPoints?:Point[];
  onCalibrationPoint?:(point:Point)=>void;
  backgroundUrl?:string|null;
  backgroundOpacity?:number;
  comparisonPlan?:FloorPlanModel|null;
}
type DragState={wallId:string;startClient:Point;original:Wall}|null;

function overlap(a1:number,a2:number,b1:number,b2:number){
  return Math.max(0,Math.min(a2,b2)-Math.max(a1,b1));
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

function moveWallAndTopology(plan:FloorPlanModel,original:Wall,next:Wall):FloorPlanModel{
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
  const movedWall:Wall=vertical
    ?{...original,a:{...original.a,x:axis},b:{...original.b,x:axis}}
    :{...original,a:{...original.a,y:axis},b:{...original.b,y:axis}};

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
    return {...room,polygon,areaM2:plan.metersPerPixel?Number((polygonArea(polygon)*plan.metersPerPixel*plan.metersPerPixel).toFixed(2)):room.areaM2};
  });

  const openings=[...plan.doors,...plan.windows];
  const movedOpenings=new Map(openings.filter(o=>o.wallId===original.id).map(o=>[
    o.id,
    vertical?{...o,a:{...o.a,x:o.a.x+delta},b:{...o.b,x:o.b.x+delta}}:{...o,a:{...o.a,y:o.a.y+delta},b:{...o.b,y:o.b.y+delta}}
  ]));

  return {
    ...plan,
    walls:plan.walls.map(w=>w.id===original.id?movedWall:w),
    rooms,
    doors:plan.doors.map(o=>movedOpenings.get(o.id)??o),
    windows:plan.windows.map(o=>movedOpenings.get(o.id)??o),
  };
}

export function PlanCanvas({plan,selectedWallId,onSelectWall,selectedRoomId,onSelectRoom,onPlanChange,readonly,calibrationMode=false,calibrationPoints=[],onCalibrationPoint,backgroundUrl=null,backgroundOpacity=.38,comparisonPlan=null}:Props){
  const[zoom,setZoom]=useState(1);
  const[drag,setDrag]=useState<DragState>(null);
  const svgRef=useRef<SVGSVGElement|null>(null);
  const viewBox=useMemo(()=>`0 0 ${Math.max(plan.widthPx,1)} ${Math.max(plan.heightPx,1)}`,[plan.widthPx,plan.heightPx]);

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
    if(!drag||!onPlanChange||readonly||calibrationMode)return;
    const d=toPlanDelta(event.clientX-drag.startClient.x,event.clientY-drag.startClient.y);
    const horizontal=Math.abs(drag.original.a.y-drag.original.b.y)<Math.abs(drag.original.a.x-drag.original.b.x);
    const candidate:Wall=horizontal
      ?{...drag.original,a:{...drag.original.a,y:drag.original.a.y+d.y},b:{...drag.original.b,y:drag.original.b.y+d.y}}
      :{...drag.original,a:{...drag.original.a,x:drag.original.a.x+d.x},b:{...drag.original.b,x:drag.original.b.x+d.x}};
    onPlanChange(moveWallAndTopology(plan,drag.original,candidate));
  };

  const addCalibrationPoint=(event:React.PointerEvent<SVGSVGElement>)=>{
    if(!calibrationMode||!onCalibrationPoint||calibrationPoints.length>=2)return;
    onCalibrationPoint(screenToPlan(event.clientX,event.clientY));
  };

  return <div className={`canvas-shell ${calibrationMode?"calibration-active":""}`}>
    <div className="canvas-toolbar">
      <button className="icon-button" onClick={()=>setZoom(z=>Math.min(z+.15,2.5))} aria-label="تكبير"><Plus size={18}/></button>
      <span>{Math.round(zoom*100)}%</span>
      <button className="icon-button" onClick={()=>setZoom(z=>Math.max(z-.15,.45))} aria-label="تصغير"><Minus size={18}/></button>
      <button className="icon-button" onClick={()=>setZoom(1)} aria-label="إعادة الضبط"><RotateCcw size={18}/></button>
    </div>
    <div className="canvas-viewport" onPointerMove={move} onPointerUp={()=>setDrag(null)} onPointerCancel={()=>setDrag(null)}>
      <svg ref={svgRef} className="plan-svg" viewBox={viewBox} style={{transform:`scale(${zoom})`}} onPointerDown={addCalibrationPoint}>
        <rect width={plan.widthPx} height={plan.heightPx} fill="#fff"/>
        {backgroundUrl&&<image href={backgroundUrl} x={0} y={0} width={plan.widthPx} height={plan.heightPx} preserveAspectRatio="none" opacity={backgroundOpacity} pointerEvents="none"/>}
        {comparisonPlan&&comparisonPlan.rooms.map(oldRoom=>{
          const current=plan.rooms.find(room=>room.id===oldRoom.id);
          const oldPoints=oldRoom.polygon.map(p=>`${p.x},${p.y}`).join(" ");
          const currentPoints=current?.polygon.map(p=>`${p.x},${p.y}`).join(" ");
          if(!current||oldPoints===currentPoints)return null;
          return <polygon key={`old-room-${oldRoom.id}`} points={oldPoints} fill="rgba(244,63,94,.045)" stroke="#e11d48" strokeWidth={3} strokeDasharray="12 8" pointerEvents="none"/>;
        })}
        {comparisonPlan&&comparisonPlan.walls.map(oldWall=>{
          const current=plan.walls.find(wall=>wall.id===oldWall.id);
          if(!current)return null;
          const changed=Math.abs(current.a.x-oldWall.a.x)>1||Math.abs(current.a.y-oldWall.a.y)>1||Math.abs(current.b.x-oldWall.b.x)>1||Math.abs(current.b.y-oldWall.b.y)>1;
          if(!changed)return null;
          return <line key={`old-wall-${oldWall.id}`} x1={oldWall.a.x} y1={oldWall.a.y} x2={oldWall.b.x} y2={oldWall.b.y} stroke="#e11d48" strokeWidth={Math.max(3,oldWall.thicknessPx)} strokeDasharray="12 8" opacity={.8} pointerEvents="none"/>;
        })}
        {plan.rooms.map(room=>{
          const metrics=roomVisualMetrics(room,plan.metersPerPixel);
          const showMetrics=Boolean(plan.metersPerPixel)&&metrics.widthPx>=70&&metrics.heightPx>=55;
          const selected=selectedRoomId===room.id;
          return <g key={room.id}>
            <polygon
              points={room.polygon.map(p=>`${p.x},${p.y}`).join(" ")}
              fill={selected?"rgba(37,99,235,.14)":"rgba(37,99,235,.055)"}
              stroke={selected?"#2563eb":"rgba(37,99,235,.16)"}
              strokeWidth={selected?3:1}
              className={readonly||calibrationMode?undefined:"editable-room"}
              onPointerDown={event=>{if(readonly||calibrationMode)return;event.stopPropagation();onSelectRoom?.(room.id);}}
            />
            {room.polygon.length>0&&<text x={metrics.cx} y={metrics.cy} textAnchor="middle" dominantBaseline="middle" className="room-label">
              <tspan x={metrics.cx} dy={showMetrics?-10:0}>{room.name||"غرفة"}</tspan>
              {showMetrics&&<tspan x={metrics.cx} dy={18} className="room-dimensions">{metrics.widthM!.toFixed(2)} × {metrics.heightM!.toFixed(2)} م</tspan>}
              {showMetrics&&metrics.areaM2!==null&&<tspan x={metrics.cx} dy={16} className="room-area">{metrics.areaM2.toFixed(1)} م²</tspan>}
            </text>}
          </g>;
        })}
        {plan.walls.map(wall=><line key={wall.id}
          x1={wall.a.x} y1={wall.a.y} x2={wall.b.x} y2={wall.b.y}
          stroke={selectedWallId===wall.id?"#2563eb":"#0f172a"}
          strokeWidth={Math.max(wall.thicknessPx,selectedWallId===wall.id?5:3)}
          strokeLinecap="round" className={readonly||calibrationMode?undefined:"editable-wall"}
          onPointerDown={e=>{if(readonly||calibrationMode)return;e.currentTarget.setPointerCapture(e.pointerId);onSelectWall?.(wall.id);setDrag({wallId:wall.id,startClient:{x:e.clientX,y:e.clientY},original:wall});}}
        />)}
        {plan.doors.map(o=><line key={o.id} x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke="#0ea5e9" strokeWidth={4}/>)}
        {plan.windows.map(o=><line key={o.id} x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke="#38bdf8" strokeWidth={3}/>)}
        {calibrationPoints.length===2&&<line x1={calibrationPoints[0].x} y1={calibrationPoints[0].y} x2={calibrationPoints[1].x} y2={calibrationPoints[1].y} stroke="#e11d48" strokeWidth={3} strokeDasharray="10 7"/>}
        {calibrationPoints.map((point,index)=><g key={index}><circle cx={point.x} cy={point.y} r={9} fill="#e11d48"/><text x={point.x+14} y={point.y-12} className="calibration-label">{index+1}</text></g>)}
      </svg>
    </div>
  </div>;
}
