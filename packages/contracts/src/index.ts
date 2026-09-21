export type ProjectStatus = "created" | "uploaded" | "queued" | "analyzing" | "ready" | "error";
export type AnalysisPhase = "created" | "upload" | "preprocess" | "ocr" | "geometry" | "rooms" | "validation" | "ready" | "error";

export interface Point { x: number; y: number; }
export interface Wall { id: string; a: Point; b: Point; thicknessPx: number; confidence: number; }
export interface Room { id: string; name: string; polygon: Point[]; confidence: number; areaM2?: number | null; }
export interface Opening {
  id: string;
  kind: "door" | "window";
  wallId?: string | null;
  a: Point;
  b: Point;
  confidence: number;
}
export interface PlanLabel {
  id: string;
  text: string;
  center: Point;
  confidence: number;
  kind: "room_name" | "dimension" | "note" | "unknown";
}
export interface FloorPlanQuality {
  overall: number;
  walls: number;
  rooms: number;
  text: number;
  dimensions: number;
  needsCalibration: boolean;
  warnings: string[];
}
export interface FloorPlanModel {
  schemaVersion: 1;
  id: string;
  widthPx: number;
  heightPx: number;
  metersPerPixel?: number | null;
  calibrationConfidence?: number | null;
  walls: Wall[];
  rooms: Room[];
  doors: Opening[];
  windows: Opening[];
  labels: PlanLabel[];
  quality: FloorPlanQuality;
  source: { fileName: string; mimeType: string; page: number; };
}
export interface ProjectView {
  id: string;
  name: string;
  status: ProjectStatus;
  phase: AnalysisPhase;
  progress: number;
  revision: number;
  hasDraft: boolean;
  message?: string | null;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  plan?: FloorPlanModel | null;
  accessToken?: string;
}
export interface ProposalImpact {
  kind: "room_resize" | "room_remove" | "wall_move" | "door_move" | "warning" | "info";
  text: string;
  severity: "info" | "warning" | "critical";
}
export interface EditProposal {
  id: string;
  title: string;
  summary: string;
  confidence: number;
  validationScore?: number;
  impacts: ProposalImpact[];
  warnings: string[];
  previewPlan: FloorPlanModel;
}
export interface EditProposalResponse {
  command: string;
  proposals: EditProposal[];
  needsClarification?: string | null;
}
export interface ApplyProposalRequest { command: string; proposal: EditProposal; }
export interface SaveRevisionRequest { summary: string; plan: FloorPlanModel; expectedRevision: number; }
export interface RevisionView { revision: number; summary: string; createdAt: string; }

export interface ValidationFinding {
  code: string;
  severity: "info" | "warning" | "critical";
  text: string;
  roomIds: string[];
}
export interface ValidationReport {
  score: number;
  findings: ValidationFinding[];
}


function fpObject(value:unknown):value is Record<string,unknown>{
  return typeof value==="object"&&value!==null&&!Array.isArray(value);
}
function fpFinite(value:unknown):value is number{
  return typeof value==="number"&&Number.isFinite(value);
}
function fpConfidence(value:unknown){
  return fpFinite(value)&&value>=0&&value<=1;
}
function fpPoint(value:unknown):value is Point{
  return fpObject(value)&&fpFinite(value.x)&&fpFinite(value.y);
}
function fpWall(value:unknown):value is Wall{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&fpPoint(value.a)&&fpPoint(value.b)
    &&fpFinite(value.thicknessPx)&&value.thicknessPx>0&&value.thicknessPx<=200
    &&fpConfidence(value.confidence);
}
function fpRoom(value:unknown):value is Room{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&typeof value.name==="string"&&value.name.length<=160
    &&Array.isArray(value.polygon)&&value.polygon.length>=3&&value.polygon.length<=500
    &&value.polygon.every(fpPoint)
    &&fpConfidence(value.confidence)
    &&(value.areaM2===undefined||value.areaM2===null||(fpFinite(value.areaM2)&&value.areaM2>=0&&value.areaM2<=100000));
}
function fpOpening(value:unknown):value is Opening{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&(value.kind==="door"||value.kind==="window")
    &&(value.wallId===undefined||value.wallId===null||typeof value.wallId==="string")
    &&fpPoint(value.a)&&fpPoint(value.b)
    &&fpConfidence(value.confidence);
}
function fpLabel(value:unknown):value is PlanLabel{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&typeof value.text==="string"&&value.text.length<=500
    &&fpPoint(value.center)
    &&fpConfidence(value.confidence)
    &&["room_name","dimension","note","unknown"].includes(String(value.kind));
}

export function floorPlanValidationError(value:unknown,expectedId?:string):string|null{
  if(!fpObject(value)||value.schemaVersion!==1)return "PLAN_SCHEMA";
  if(typeof value.id!=="string"||!value.id)return "PLAN_ID";
  if(expectedId&&value.id!==expectedId)return "PLAN_ID";
  if(!fpFinite(value.widthPx)||!fpFinite(value.heightPx)||!Number.isInteger(value.widthPx)||!Number.isInteger(value.heightPx)||value.widthPx<=0||value.heightPx<=0||value.widthPx>30000||value.heightPx>30000)return "PLAN_SIZE";
  if(value.metersPerPixel!==undefined&&value.metersPerPixel!==null&&(!fpFinite(value.metersPerPixel)||value.metersPerPixel<=0||value.metersPerPixel>10))return "PLAN_SCALE";
  if(value.calibrationConfidence!==undefined&&value.calibrationConfidence!==null&&!fpConfidence(value.calibrationConfidence))return "PLAN_CALIBRATION";

  if(!Array.isArray(value.walls)||value.walls.length>10000||!value.walls.every(fpWall))return "PLAN_WALLS";
  if(!Array.isArray(value.rooms)||value.rooms.length>5000||!value.rooms.every(fpRoom))return "PLAN_ROOMS";
  if(!Array.isArray(value.doors)||value.doors.length>5000||!value.doors.every(fpOpening))return "PLAN_DOORS";
  if(!Array.isArray(value.windows)||value.windows.length>5000||!value.windows.every(fpOpening))return "PLAN_WINDOWS";
  if(!Array.isArray(value.labels)||value.labels.length>10000||!value.labels.every(fpLabel))return "PLAN_LABELS";

  if(!fpObject(value.quality))return "PLAN_QUALITY";
  const quality=value.quality;
  if(!fpConfidence(quality.overall)||!fpConfidence(quality.walls)||!fpConfidence(quality.rooms)||!fpConfidence(quality.text)||!fpConfidence(quality.dimensions)||typeof quality.needsCalibration!=="boolean"||!Array.isArray(quality.warnings)||quality.warnings.length>500||!quality.warnings.every(item=>typeof item==="string"&&item.length<=500))return "PLAN_QUALITY";

  if(!fpObject(value.source)||typeof value.source.fileName!=="string"||value.source.fileName.length>500||typeof value.source.mimeType!=="string"||value.source.mimeType.length>160||!fpFinite(value.source.page)||!Number.isInteger(value.source.page)||value.source.page<1||value.source.page>10000)return "PLAN_SOURCE";

  const ids=[
    ...value.walls.map(item=>(item as Wall).id),
    ...value.rooms.map(item=>(item as Room).id),
    ...value.doors.map(item=>(item as Opening).id),
    ...value.windows.map(item=>(item as Opening).id),
  ];
  if(new Set(ids).size!==ids.length)return "PLAN_DUPLICATE_IDS";

  const wallIds=new Set(value.walls.map(item=>(item as Wall).id));
  for(const opening of [...value.doors,...value.windows] as Opening[]){
    if(opening.wallId&& !wallIds.has(opening.wallId))return "PLAN_OPENING_WALL";
  }
  return null;
}

export function isFloorPlanModel(value:unknown,expectedId?:string):value is FloorPlanModel{
  return floorPlanValidationError(value,expectedId)===null;
}
