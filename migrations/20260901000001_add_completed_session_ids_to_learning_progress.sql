-- Migration: 20260901000001_add_completed_session_ids_to_learning_progress.sql
-- Safely adds completed_session_ids_json to learning_progress for post-debate crash idempotency

ALTER TABLE public.learning_progress
ADD COLUMN IF NOT EXISTS completed_session_ids_json JSONB
NOT NULL DEFAULT '[]'::jsonb;
