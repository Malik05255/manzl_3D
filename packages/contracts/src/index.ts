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
  message?: string | null;
  error?: string | null;
  createdAt: string;
  updatedAt: string;
  plan?: FloorPlanModel | null;
  accessToken?: string;
}
export interface ProposalImpact {
  kind: "room_resize" | "wall_move" | "door_move" | "warning" | "info";
  text: string;
  severity: "info" | "warning" | "critical";
}
export interface EditProposal {
  id: string;
  title: string;
  summary: string;
  confidence: number;
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
export interface SaveRevisionRequest { summary: string; plan: FloorPlanModel; }
