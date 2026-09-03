-- Migration: fix-streak-defaults
-- New users must start with no streak (0 days, empty 7-day history) instead of
-- the placeholder 1-day streak. Existing rows are left untouched; the app's
-- lazy streak maintenance normalizes inactive/new users on read.

ALTER TABLE public.learning_progress
ALTER COLUMN streak_days SET DEFAULT 0;

ALTER TABLE public.learning_progress
ALTER COLUMN streak_history_json SET DEFAULT '[0, 0, 0, 0, 0, 0, 0]'::jsonb;
