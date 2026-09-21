CREATE UNIQUE INDEX IF NOT EXISTS idx_revisions_project_revision_unique
ON revisions(project_id, revision);
