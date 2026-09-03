-- Keep the production review schema aligned with the SQLAlchemy DebateReview model.
ALTER TABLE public.debate_reviews
  ADD COLUMN IF NOT EXISTS grammar_advice TEXT,
  ADD COLUMN IF NOT EXISTS vocabulary_advice TEXT,
  ADD COLUMN IF NOT EXISTS pronunciation_advice TEXT;
