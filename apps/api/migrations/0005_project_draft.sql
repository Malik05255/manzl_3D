ALTER TABLE projects ADD COLUMN draft_key TEXT;

UPDATE projects
SET draft_key=plan_key,
    plan_key=(
      SELECT r.plan_key
      FROM revisions r
      WHERE r.project_id=projects.id
      ORDER BY r.revision DESC
      LIMIT 1
    )
WHERE plan_key LIKE '%/draft/%';
