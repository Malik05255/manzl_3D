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
  access_hash: string | null;
  created_at: string;
  updated_at: string;
}
