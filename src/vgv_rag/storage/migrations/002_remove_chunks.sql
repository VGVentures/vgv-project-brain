-- 002_remove_chunks.sql
-- Vector storage moved from pgvector to Pinecone.
-- The chunks table, related indexes, RLS, and the match_chunks function are no longer needed.

DROP POLICY IF EXISTS "Users can read chunks from their projects" ON chunks;
DROP INDEX IF EXISTS chunks_embedding_idx;
DROP INDEX IF EXISTS chunks_project_artifact_idx;
DROP INDEX IF EXISTS chunks_project_tool_idx;
DROP FUNCTION IF EXISTS match_chunks;
DROP TABLE IF EXISTS chunks;
DROP EXTENSION IF EXISTS vector;
