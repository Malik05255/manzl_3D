import { useMemo,useRef,useState } from "react";
import type { FloorPlanModel,Point,Wall } from "@manzil/contracts";
import { Minus,Plus,RotateCcw } from "lucide-react";

interface Props{
  plan:FloorPlanModel;
  selectedWallId?:string|null;
  onSelectWall?:(id:string|null)=>void;
  onPlanChange?:(plan:FloorPlanModel)=>void;
  readonly?:boolean;
}
type DragState={wallId:string;startClient:Point;original:Wall}|null;

export function PlanCanvas({plan,selectedWallId,onSelectWall,onPlanChange,readonly}:Props){
  const [zoom,setZoom]=useState(1);
  const [drag,setDrag]=useState<DragState>(null);
  const svgRef=useRef<SVGSVGElement|null>(null);
  const viewBox=useMemo(()=>`0 0 ${Math.max(plan.widthPx,1)} ${Math.max(plan.heightPx,1)}`,[plan.widthPx,plan.heightPx]);

  const toPlanDelta=(dx:number,dy:number)=>{
    const svg=svgRef.current;if(!svg)return{x:0,y:0};
    const rect=svg.getBoundingClientRect();
    return{x:dx*(plan.widthPx/rect.width),y:dy*(plan.heightPx/rect.height)};
  };
  const move=(event:React.PointerEvent)=>{
    if(!drag||!onPlanChange||readonly)return;
    const d=toPlanDelta(event.clientX-drag.startClient.x,event.clientY-drag.startClient.y);
    const horizontal=Math.abs(drag.original.a.y-drag.original.b.y)<Math.abs(drag.original.a.x-drag.original.b.x);
    const moved:Wall=horizontal
      ?{...drag.original,a:{...drag.original.a,y:drag.original.a.y+d.y},b:{...drag.original.b,y:drag.original.b.y+d.y}}
      :{...drag.original,a:{...drag.original.a,x:drag.original.a.x+d.x},b:{...drag.original.b,x:drag.original.b.x+d.x}};
    onPlanChange({...plan,walls:plan.walls.map(w=>w.id===moved.id?moved:w)});
  };

  return <div className="canvas-shell">
    <div className="canvas-toolbar">
      <button className="icon-button" onClick={()=>setZoom(z=>Math.min(z+.15,2.5))} aria-label="تكبير"><Plus size={18}/></button>
      <span>{Math.round(zoom*100)}%</span>
      <button className="icon-button" onClick={()=>setZoom(z=>Math.max(z-.15,.45))} aria-label="تصغير"><Minus size={18}/></button>
      <button className="icon-button" onClick={()=>setZoom(1)} aria-label="إعادة الضبط"><RotateCcw size={18}/></button>
    </div>
    <div className="canvas-viewport" onPointerMove={move} onPointerUp={()=>setDrag(null)} onPointerCancel={()=>setDrag(null)}>
      <svg ref={svgRef} className="plan-svg" viewBox={viewBox} style={{transform:`scale(${zoom})`}} onPointerDown={e=>{if(e.target===e.currentTarget)onSelectWall?.(null);}}>
        <rect width={plan.widthPx} height={plan.heightPx} fill="#fff"/>
        {plan.rooms.map(room=><g key={room.id}>
          <polygon points={room.polygon.map(p=>`${p.x},${p.y}`).join(" ")} fill="rgba(37,99,235,.055)" stroke="rgba(37,99,235,.16)" strokeWidth={1}/>
          {room.polygon.length>0&&<text
            x={room.polygon.reduce((s,p)=>s+p.x,0)/room.polygon.length}
            y={room.polygon.reduce((s,p)=>s+p.y,0)/room.polygon.length}
            textAnchor="middle" dominantBaseline="middle" className="room-label">{room.name||"غرفة"}</text>}
        </g>)}
        {plan.walls.map(wall=><line key={wall.id}
          x1={wall.a.x} y1={wall.a.y} x2={wall.b.x} y2={wall.b.y}
          stroke={selectedWallId===wall.id?"#2563eb":"#0f172a"}
          strokeWidth={Math.max(wall.thicknessPx,selectedWallId===wall.id?5:3)}
          strokeLinecap="round" className={readonly?undefined:"editable-wall"}
          onPointerDown={e=>{if(readonly)return;e.currentTarget.setPointerCapture(e.pointerId);onSelectWall?.(wall.id);setDrag({wallId:wall.id,startClient:{x:e.clientX,y:e.clientY},original:wall});}}
        />)}
        {plan.doors.map(o=><line key={o.id} x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke="#0ea5e9" strokeWidth={4}/>)}
        {plan.windows.map(o=><line key={o.id} x1={o.a.x} y1={o.a.y} x2={o.b.x} y2={o.b.y} stroke="#38bdf8" strokeWidth={3}/>)}
      </svg>
    </div>
  </div>;
}
