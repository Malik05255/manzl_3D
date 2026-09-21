export type ProjectStatus = "created" | "uploaded" | "queued" | "analyzing" | "ready" | "error";
export type AnalysisPhase = "created" | "upload" | "preprocess" | "ocr" | "geometry" | "rooms" | "validation" | "ready" | "error";

export interface Point { x: number; y: number; }
export type ElementProvenance = "opencv" | "pdf-vector" | "ocr" | "cloud-ocr" | "pdf-text" | "manual" | "ai" | "mixed";
export type WallRole = "unknown" | "interior" | "exterior" | "structural";
export interface Wall { id: string; a: Point; b: Point; thicknessPx: number; confidence: number; heightM?: number | null; role?: WallRole; locked?: boolean; reviewed?: boolean; provenance?: ElementProvenance; }
export interface Room { id: string; name: string; polygon: Point[]; confidence: number; areaM2?: number | null; ceilingHeightM?: number | null; boundaryWallIds?: string[]; reviewed?: boolean; provenance?: ElementProvenance; }
export type DoorSubtype = "unknown" | "single_swing" | "double_swing" | "sliding";
export interface Opening {
  id: string;
  kind: "door" | "window";
  doorSubtype?: DoorSubtype;
  wallId?: string | null;
  a: Point;
  b: Point;
  confidence: number;
  heightM?: number | null;
  sillHeightM?: number | null;
  reviewed?: boolean;
  provenance?: ElementProvenance;
}
export type SymbolKind = "sink" | "toilet" | "bathtub" | "shower" | "cooktop" | "stairs";
export interface PlanSymbol {
  id: string;
  kind: SymbolKind;
  a: Point;
  b: Point;
  confidence: number;
  reviewed?: boolean;
  provenance?: ElementProvenance;
}
export interface PlanLabel {
  id: string;
  text: string;
  center: Point;
  confidence: number;
  kind: "room_name" | "dimension" | "note" | "unknown";
  reviewed?: boolean;
  provenance?: ElementProvenance;
}
export interface Dimension {
  id: string;
  sourceLabelId?: string | null;
  text: string;
  center: Point;
  valueM?: number | null;
  unit: "m" | "cm" | "mm" | "unknown";
  orientation: "horizontal" | "vertical" | "unknown";
  referenceWallId?: string | null;
  spanA?: Point | null;
  spanB?: Point | null;
  confidence: number;
  reviewed?: boolean;
  provenance?: ElementProvenance;
}
export interface AnalysisMetadata {
  pipelineVersion: string;
  analyzedAt: string;
  sourceSha256: string;
  engines: string[];
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
  dimensions?: Dimension[];
  symbols?: PlanSymbol[];
  quality: FloorPlanQuality;
  source: { fileName: string; mimeType: string; page: number; pageCount?: number | null; };
  analysis?: AnalysisMetadata;
}
export interface ProjectFloorView {
  id: string;
  sourcePage: number;
  name: string;
  latestRevision: number;
  previewAvailable: boolean;
  elevationM?: number | null;
  heightM?: number | null;
  updatedAt: string;
}

export interface ProjectView {
  id: string;
  name: string;
  status: ProjectStatus;
  phase: AnalysisPhase;
  progress: number;
  revision: number;
  hasDraft: boolean;
  activeFloorId?: string | null;
  floors?: ProjectFloorView[];
  message?: string | null;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  plan?: FloorPlanModel | null;
  accessToken?: string;
}
export interface ProposalImpact {
  kind: "room_resize" | "room_remove" | "wall_move" | "wall_update" | "door_move" | "opening_update" | "opening_remove" | "warning" | "info";
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
export interface ApplyProposalRequest { command: string; proposal: EditProposal; expectedRevision: number; targetRoomId?: string | null; targetWallId?: string | null; targetOpeningId?: string | null; }
export interface SaveRevisionRequest { summary: string; plan: FloorPlanModel; expectedRevision: number; }
export interface RevisionView { revision: number; summary: string; createdAt: string; sourcePage?: number | null; floorId?: string | null; floorName?: string | null; floorElevationM?: number | null; floorHeightM?: number | null; }

export interface ValidationFinding {
  code: string;
  severity: "info" | "warning" | "critical";
  text: string;
  roomIds: string[];
  wallIds?: string[];
  openingIds?: string[];
  dimensionIds?: string[];
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
function fpElementMetadata(value:Record<string,unknown>){
  const provenance=value.provenance;
  return (value.reviewed===undefined||typeof value.reviewed==="boolean")
    &&(provenance===undefined||["opencv","pdf-vector","ocr","cloud-ocr","pdf-text","manual","ai","mixed"].includes(String(provenance)));
}
function fpPoint(value:unknown):value is Point{
  return fpObject(value)&&fpFinite(value.x)&&fpFinite(value.y);
}
function fpWall(value:unknown):value is Wall{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&fpPoint(value.a)&&fpPoint(value.b)
    &&fpFinite(value.thicknessPx)&&value.thicknessPx>0&&value.thicknessPx<=200
    &&fpConfidence(value.confidence)
    &&(value.heightM===undefined||value.heightM===null||(fpFinite(value.heightM)&&value.heightM>=0.5&&value.heightM<=20))
    &&(value.role===undefined||["unknown","interior","exterior","structural"].includes(String(value.role)))
    &&(value.locked===undefined||typeof value.locked==="boolean")
    &&fpElementMetadata(value);
}
function fpRoom(value:unknown):value is Room{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&typeof value.name==="string"&&value.name.length<=160
    &&Array.isArray(value.polygon)&&value.polygon.length>=3&&value.polygon.length<=500
    &&value.polygon.every(fpPoint)
    &&fpConfidence(value.confidence)
    &&(value.areaM2===undefined||value.areaM2===null||(fpFinite(value.areaM2)&&value.areaM2>=0&&value.areaM2<=100000))
    &&(value.ceilingHeightM===undefined||value.ceilingHeightM===null||(fpFinite(value.ceilingHeightM)&&value.ceilingHeightM>=0.5&&value.ceilingHeightM<=20))
    &&(value.boundaryWallIds===undefined||(Array.isArray(value.boundaryWallIds)&&value.boundaryWallIds.length<=500&&value.boundaryWallIds.every(item=>typeof item==="string"&&item.length>0&&item.length<=200)&&new Set(value.boundaryWallIds).size===value.boundaryWallIds.length))
    &&fpElementMetadata(value);
}
function fpOpening(value:unknown):value is Opening{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&(value.kind==="door"||value.kind==="window")
    &&(value.doorSubtype===undefined||["unknown","single_swing","double_swing","sliding"].includes(String(value.doorSubtype)))
    &&(value.wallId===undefined||value.wallId===null||typeof value.wallId==="string")
    &&fpPoint(value.a)&&fpPoint(value.b)
    &&fpConfidence(value.confidence)
    &&(value.heightM===undefined||value.heightM===null||(fpFinite(value.heightM)&&value.heightM>=0.2&&value.heightM<=10))
    &&(value.sillHeightM===undefined||value.sillHeightM===null||(fpFinite(value.sillHeightM)&&value.sillHeightM>=0&&value.sillHeightM<=10))
    &&fpElementMetadata(value);
}
function fpSymbol(value:unknown):value is PlanSymbol{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&["sink","toilet","bathtub","shower","cooktop","stairs"].includes(String(value.kind))
    &&fpPoint(value.a)&&fpPoint(value.b)
    &&value.b.x>value.a.x&&value.b.y>value.a.y
    &&fpConfidence(value.confidence)
    &&fpElementMetadata(value);
}
function fpLabel(value:unknown):value is PlanLabel{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&typeof value.text==="string"&&value.text.length<=500
    &&fpPoint(value.center)
    &&fpConfidence(value.confidence)
    &&["room_name","dimension","note","unknown"].includes(String(value.kind))
    &&fpElementMetadata(value);
}
function fpDimension(value:unknown):value is Dimension{
  return fpObject(value)
    &&typeof value.id==="string"&&value.id.length>0
    &&(value.sourceLabelId===undefined||value.sourceLabelId===null||typeof value.sourceLabelId==="string")
    &&typeof value.text==="string"&&value.text.length<=500
    &&fpPoint(value.center)
    &&(value.valueM===undefined||value.valueM===null||(fpFinite(value.valueM)&&value.valueM>0&&value.valueM<=1000))
    &&["m","cm","mm","unknown"].includes(String(value.unit))
    &&["horizontal","vertical","unknown"].includes(String(value.orientation))
    &&(value.referenceWallId===undefined||value.referenceWallId===null||typeof value.referenceWallId==="string")
    &&(value.spanA===undefined||value.spanA===null||fpPoint(value.spanA))
    &&(value.spanB===undefined||value.spanB===null||fpPoint(value.spanB))
    &&((value.spanA===undefined||value.spanA===null)===(value.spanB===undefined||value.spanB===null))
    &&fpConfidence(value.confidence)
    &&fpElementMetadata(value);
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
  if(value.dimensions!==undefined&&(!Array.isArray(value.dimensions)||value.dimensions.length>10000||!value.dimensions.every(fpDimension)))return "PLAN_DIMENSIONS";
  if(value.symbols!==undefined&&(!Array.isArray(value.symbols)||value.symbols.length>5000||!value.symbols.every(fpSymbol)))return "PLAN_SYMBOLS";

  if(!fpObject(value.quality))return "PLAN_QUALITY";
  const quality=value.quality;
  if(!fpConfidence(quality.overall)||!fpConfidence(quality.walls)||!fpConfidence(quality.rooms)||!fpConfidence(quality.text)||!fpConfidence(quality.dimensions)||typeof quality.needsCalibration!=="boolean"||!Array.isArray(quality.warnings)||quality.warnings.length>500||!quality.warnings.every(item=>typeof item==="string"&&item.length<=500))return "PLAN_QUALITY";

  if(!fpObject(value.source)||typeof value.source.fileName!=="string"||value.source.fileName.length>500||typeof value.source.mimeType!=="string"||value.source.mimeType.length>160||!fpFinite(value.source.page)||!Number.isInteger(value.source.page)||value.source.page<1||value.source.page>10000)return "PLAN_SOURCE";
  if(value.source.pageCount!==undefined&&value.source.pageCount!==null&&(!fpFinite(value.source.pageCount)||!Number.isInteger(value.source.pageCount)||value.source.pageCount<1||value.source.pageCount>10000||value.source.page>value.source.pageCount))return "PLAN_SOURCE";

  if(value.analysis!==undefined){
    if(!fpObject(value.analysis))return "PLAN_ANALYSIS";
    if(typeof value.analysis.pipelineVersion!=="string"||value.analysis.pipelineVersion.length<1||value.analysis.pipelineVersion.length>120)return "PLAN_ANALYSIS";
    if(typeof value.analysis.analyzedAt!=="string"||value.analysis.analyzedAt.length<10||value.analysis.analyzedAt.length>80)return "PLAN_ANALYSIS";
    if(typeof value.analysis.sourceSha256!=="string"||!/^[0-9a-f]{64}$/i.test(value.analysis.sourceSha256))return "PLAN_ANALYSIS";
    if(!Array.isArray(value.analysis.engines)||value.analysis.engines.length>30||!value.analysis.engines.every(item=>typeof item==="string"&&item.length>0&&item.length<=80))return "PLAN_ANALYSIS";
  }

  const ids=[
    ...value.walls.map(item=>(item as Wall).id),
    ...value.rooms.map(item=>(item as Room).id),
    ...value.doors.map(item=>(item as Opening).id),
    ...value.windows.map(item=>(item as Opening).id),
    ...(value.dimensions??[]).map(item=>(item as Dimension).id),
    ...(value.symbols??[]).map(item=>(item as PlanSymbol).id),
  ];
  if(new Set(ids).size!==ids.length)return "PLAN_DUPLICATE_IDS";

  const wallIds=new Set(value.walls.map(item=>(item as Wall).id));
  const labelIds=new Set(value.labels.map(item=>(item as PlanLabel).id));
  for(const room of value.rooms as Room[]){
    if(room.boundaryWallIds?.some(id=>!wallIds.has(id)))return "PLAN_ROOM_WALL";
  }
  for(const opening of [...value.doors,...value.windows] as Opening[]){
    if(opening.wallId&& !wallIds.has(opening.wallId))return "PLAN_OPENING_WALL";
  }
  for(const dimension of (value.dimensions??[]) as Dimension[]){
    if(dimension.referenceWallId&& !wallIds.has(dimension.referenceWallId))return "PLAN_DIMENSION_WALL";
    if(dimension.sourceLabelId&& !labelIds.has(dimension.sourceLabelId))return "PLAN_DIMENSION_LABEL";
  }
  return null;
}

export function isFloorPlanModel(value:unknown,expectedId?:string):value is FloorPlanModel{
  return floorPlanValidationError(value,expectedId)===null;
}
