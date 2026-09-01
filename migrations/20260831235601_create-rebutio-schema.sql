-- Rebutio Core Schema for InsForge PostgreSQL

CREATE TABLE IF NOT EXISTS public.users (
  id VARCHAR(64) PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  onboarded BOOLEAN NOT NULL DEFAULT FALSE,
  preferences_encrypted TEXT,
  save_transcripts BOOLEAN NOT NULL DEFAULT FALSE,
  captions_enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS public.learning_progress (
  user_id VARCHAR(64) PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  xp INTEGER NOT NULL DEFAULT 0,
  streak_days INTEGER NOT NULL DEFAULT 1,
  last_activity_date VARCHAR(32),
  streak_history_json JSONB NOT NULL DEFAULT '[1, 1, 1, 0, 1, 1, 1]'::jsonb,
  debates_completed INTEGER NOT NULL DEFAULT 0,
  wins INTEGER NOT NULL DEFAULT 0,
  losses INTEGER NOT NULL DEFAULT 0,
  draws INTEGER NOT NULL DEFAULT 0,
  stars_by_node_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  placement_completed BOOLEAN NOT NULL DEFAULT FALSE,
  placement_skill_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS public.speech_profiles (
  user_id VARCHAR(64) PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  profile_encrypted TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.topic_inventory (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  topic_id VARCHAR(64) NOT NULL,
  topic_text TEXT NOT NULL,
  skill_id VARCHAR(64) NOT NULL,
  difficulty VARCHAR(32) NOT NULL DEFAULT 'steady',
  turns INTEGER NOT NULL DEFAULT 4,
  estimated_minutes INTEGER NOT NULL DEFAULT 6,
  reminder TEXT NOT NULL DEFAULT '',
  consumed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_topic_inventory_user_consumed ON public.topic_inventory (user_id, consumed);

CREATE TABLE IF NOT EXISTS public.debate_sessions (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  topic_id VARCHAR(64) NOT NULL,
  topic_text TEXT NOT NULL,
  skill_id VARCHAR(64) NOT NULL,
  skill_name VARCHAR(128) NOT NULL,
  skill_hint TEXT NOT NULL,
  skill_reminder TEXT NOT NULL,
  difficulty VARCHAR(32) NOT NULL DEFAULT 'steady',
  user_side VARCHAR(16) NOT NULL,
  total_user_turns INTEGER NOT NULL DEFAULT 4,
  current_turn INTEGER NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  is_onboarding BOOLEAN NOT NULL DEFAULT FALSE,
  pre_final_analysis_encrypted TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_debate_sessions_user_status ON public.debate_sessions (user_id, status);

CREATE TABLE IF NOT EXISTS public.debate_turns (
  id VARCHAR(64) PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL REFERENCES public.debate_sessions(id) ON DELETE CASCADE,
  turn_number INTEGER NOT NULL,
  speaker VARCHAR(16) NOT NULL,
  text_encrypted TEXT,
  audio_available BOOLEAN NOT NULL DEFAULT FALSE,
  duration_sec FLOAT NOT NULL DEFAULT 0.0,
  client_response_delay_ms INTEGER NOT NULL DEFAULT 0,
  idempotency_key VARCHAR(128),
  move VARCHAR(64),
  requires_response BOOLEAN NOT NULL DEFAULT TRUE,
  addressed_claim TEXT,
  conversation_state VARCHAR(32) NOT NULL DEFAULT 'unresolved',
  media_asset_id VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_debate_turns_session_num ON public.debate_turns (session_id, turn_number);
CREATE INDEX IF NOT EXISTS idx_debate_turns_idempotency ON public.debate_turns (session_id, idempotency_key);

CREATE TABLE IF NOT EXISTS public.temporary_turn_evidence (
  id VARCHAR(64) PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL REFERENCES public.debate_sessions(id) ON DELETE CASCADE,
  turn_number INTEGER NOT NULL,
  evidence_encrypted TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.debate_reviews (
  session_id VARCHAR(64) PRIMARY KEY REFERENCES public.debate_sessions(id) ON DELETE CASCADE,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  outcome VARCHAR(32) NOT NULL DEFAULT 'undetermined',
  stars INTEGER NOT NULL DEFAULT 1,
  completed BOOLEAN NOT NULL DEFAULT TRUE,
  skill_demonstrated BOOLEAN NOT NULL DEFAULT FALSE,
  mastery_note TEXT,
  skill_assessment_json JSONB,
  argument_feedback_json JSONB,
  language_feedback_encrypted TEXT,
  xp_earned INTEGER NOT NULL DEFAULT 60,
  streak_extended BOOLEAN NOT NULL DEFAULT FALSE,
  next_level_unlocked BOOLEAN NOT NULL DEFAULT FALSE,
  score_technique INTEGER NOT NULL DEFAULT 8,
  score_grammar INTEGER NOT NULL DEFAULT 8,
  score_vocabulary INTEGER NOT NULL DEFAULT 8,
  score_delivery INTEGER NOT NULL DEFAULT 8,
  score_technique_rubric TEXT,
  score_grammar_rubric TEXT,
  score_vocabulary_rubric TEXT,
  score_delivery_rubric TEXT,
  strongest_moment TEXT,
  improvement_opportunity TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_debate_reviews_user ON public.debate_reviews (user_id);

CREATE TABLE IF NOT EXISTS public.review_feedback (
  id VARCHAR(64) PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL REFERENCES public.debate_sessions(id) ON DELETE CASCADE,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  verdict VARCHAR(32) NOT NULL DEFAULT 'disagree',
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.media_assets (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  session_id VARCHAR(64) REFERENCES public.debate_sessions(id) ON DELETE SET NULL,
  turn_number INTEGER,
  source_type VARCHAR(32) NOT NULL DEFAULT 'debate_turn',
  storage_path VARCHAR(512) NOT NULL,
  mime_type VARCHAR(64) NOT NULL DEFAULT 'audio/webm',
  file_size_bytes INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  transcript_encrypted TEXT,
  phonemes_encrypted TEXT,
  speech_metrics_json JSONB,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_media_assets_user_session ON public.media_assets (user_id, session_id);

CREATE TABLE IF NOT EXISTS public.derived_audio_clips (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  source_asset_id VARCHAR(64) NOT NULL REFERENCES public.media_assets(id) ON DELETE CASCADE,
  storage_path VARCHAR(512) NOT NULL,
  start_ms INTEGER NOT NULL DEFAULT 0,
  end_ms INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  purpose VARCHAR(128) NOT NULL DEFAULT 'evidence',
  label VARCHAR(128) NOT NULL DEFAULT 'Debate Evidence',
  transcript_excerpt TEXT,
  coach_note TEXT,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_derived_clips_user_asset ON public.derived_audio_clips (user_id, source_asset_id);

CREATE TABLE IF NOT EXISTS public.coach_threads (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  session_id VARCHAR(64) REFERENCES public.debate_sessions(id) ON DELETE SET NULL,
  thread_type VARCHAR(32) NOT NULL DEFAULT 'general',
  title VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coach_threads_user_session ON public.coach_threads (user_id, session_id);

CREATE TABLE IF NOT EXISTS public.coach_messages (
  id VARCHAR(64) PRIMARY KEY,
  thread_id VARCHAR(64) NOT NULL REFERENCES public.coach_threads(id) ON DELETE CASCADE,
  user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  sender VARCHAR(16) NOT NULL,
  message_type VARCHAR(32) NOT NULL DEFAULT 'text',
  text_encrypted TEXT,
  media_asset_id VARCHAR(64) REFERENCES public.media_assets(id) ON DELETE SET NULL,
  evidence_clip_id VARCHAR(64) REFERENCES public.derived_audio_clips(id) ON DELETE SET NULL,
  structured_data_json JSONB,
  processing_state VARCHAR(32) NOT NULL DEFAULT 'ready',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coach_messages_thread_created ON public.coach_messages (thread_id, created_at);

CREATE TABLE IF NOT EXISTS public.coach_memory (
  user_id VARCHAR(64) PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  memory_markdown_encrypted TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
