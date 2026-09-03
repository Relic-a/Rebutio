-- Rebutio persists application data through the authenticated FastAPI service.
-- Browser clients use InsForge for authentication only and must not access the
-- underlying application tables through PostgREST, even when authenticated.

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.speech_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.topic_inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debate_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debate_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.temporary_turn_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.debate_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.derived_audio_clips ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coach_memory ENABLE ROW LEVEL SECURITY;

-- InsForge grants broad DML privileges to runtime roles by default. Revoke
-- them explicitly so access remains denied even if a policy is later added by
-- mistake. The project-admin database connection used by FastAPI is unaffected.
REVOKE ALL PRIVILEGES ON TABLE public.users FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.learning_progress FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.speech_profiles FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.topic_inventory FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.debate_sessions FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.debate_turns FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.temporary_turn_evidence FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.debate_reviews FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.review_feedback FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.media_assets FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.derived_audio_clips FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.coach_threads FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.coach_messages FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.coach_memory FROM anon, authenticated;
