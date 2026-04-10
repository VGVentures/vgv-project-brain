-- 003_add_programs.sql
-- Add programs table and program-project relationship for auto-onboarding.

CREATE TABLE IF NOT EXISTS programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    notion_page_url TEXT NOT NULL UNIQUE,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add program_id to projects (nullable — legacy projects may not have a program)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS program_id UUID REFERENCES programs(id) ON DELETE SET NULL;

-- Add program_id to sources (for program-level sources; mutually exclusive with project_id)
ALTER TABLE sources ADD COLUMN IF NOT EXISTS program_id UUID REFERENCES programs(id) ON DELETE CASCADE;

-- Enforce mutual exclusivity: a source belongs to a project OR a program, not both
ALTER TABLE sources ADD CONSTRAINT sources_owner_check
    CHECK (num_nonnulls(project_id, program_id) = 1);

-- Drop old unique constraint (can't handle NULL project_id for program-level sources)
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_project_id_connector_source_id_key;

-- New unique constraint using COALESCE to handle nullable project_id/program_id
CREATE UNIQUE INDEX IF NOT EXISTS sources_owner_connector_source_id_idx
    ON sources (COALESCE(project_id, program_id), connector, source_id);

-- Index for looking up sources by program
CREATE INDEX IF NOT EXISTS sources_program_id_idx ON sources (program_id);

-- RPC function: return distinct programs where a user is a member of any child project
CREATE OR REPLACE FUNCTION list_programs_for_user(p_user_email TEXT)
RETURNS SETOF programs
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT prog.*
    FROM programs prog
    JOIN projects proj ON proj.program_id = prog.id
    JOIN project_members pm ON pm.project_id = proj.id
    WHERE pm.user_email = p_user_email;
$$;
