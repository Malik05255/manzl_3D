ALTER TABLE projects ADD COLUMN active_floor_id TEXT;
ALTER TABLE revisions ADD COLUMN source_page INTEGER;
ALTER TABLE revisions ADD COLUMN preview_key TEXT;
ALTER TABLE revisions ADD COLUMN floor_id TEXT;

CREATE INDEX IF NOT EXISTS idx_revisions_project_page
ON revisions(project_id, source_page, revision DESC);

CREATE TABLE IF NOT EXISTS project_floors (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  source_page INTEGER NOT NULL,
  name TEXT NOT NULL,
  plan_key TEXT NOT NULL,
  preview_key TEXT,
  latest_revision INTEGER NOT NULL DEFAULT 0,
  elevation_m REAL,
  height_m REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  UNIQUE(project_id, source_page)
);

CREATE INDEX IF NOT EXISTS idx_project_floors_project
ON project_floors(project_id, source_page);
