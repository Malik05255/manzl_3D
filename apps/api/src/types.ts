export interface Env {
  DB: D1Database;
  ASSETS: R2Bucket;
  ANALYZE_QUEUE: Queue<AnalyzeMessage>;
  ANALYZER_URL: string;
  API_PUBLIC_URL: string;
  INTERNAL_TOKEN: string;
  APP_VERSION?: string;
  ALLOWED_ORIGIN?: string;
}

export interface AnalyzeMessage {
  projectId: string;
  sourceKey: string;
  fileName: string;
  mimeType: string;
  sourcePage?: number;
  expectedRevision: number;
}

export interface ProjectRow {
  id: string;
  name: string;
  status: string;
  phase: string;
  progress: number;
  message: string | null;
  error: string | null;
  source_key: string | null;
  preview_key: string | null;
  plan_key: string | null;
  draft_key: string | null;
  revision: number;
  active_floor_id: string | null;
  access_hash: string | null;
  created_at: string;
  updated_at: string;
}


export interface FloorRow {
  id: string;
  project_id: string;
  source_page: number;
  name: string;
  plan_key: string;
  preview_key: string | null;
  latest_revision: number;
  elevation_m: number | null;
  height_m: number | null;
  created_at: string;
  updated_at: string;
}
