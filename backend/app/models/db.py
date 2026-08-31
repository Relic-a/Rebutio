import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    onboarded = Column(Boolean, default=False, nullable=False)
    preferences_encrypted = Column(Text, nullable=True)
    save_transcripts = Column(Boolean, default=False, nullable=False)
    captions_enabled = Column(Boolean, default=True, nullable=False)

    progress = relationship("LearningProgress", back_populates="user", uselist=False, cascade="all, delete-orphan")
    speech_profile = relationship("SpeechProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    topic_inventory = relationship("TopicInventory", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("DebateSession", back_populates="user", cascade="all, delete-orphan")
    coach_threads = relationship("CoachThread", back_populates="user", cascade="all, delete-orphan")
    media_assets = relationship("MediaAsset", back_populates="user", cascade="all, delete-orphan")
    coaching_memories = relationship("CoachingMemoryItem", back_populates="user", cascade="all, delete-orphan")


class LearningProgress(Base):
    __tablename__ = "learning_progress"

    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    xp = Column(Integer, default=0, nullable=False)
    streak_days = Column(Integer, default=1, nullable=False)
    last_activity_date = Column(String(32), nullable=True)
    streak_history_json = Column(JSON, default=lambda: [1, 1, 1, 0, 1, 1, 1], nullable=False)
    debates_completed = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    draws = Column(Integer, default=0, nullable=False)
    stars_by_node_json = Column(JSON, default=dict, nullable=False)

    user = relationship("User", back_populates="progress")


class SpeechProfile(Base):
    __tablename__ = "speech_profiles"

    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    profile_encrypted = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="speech_profile")


class TopicInventory(Base):
    __tablename__ = "topic_inventory"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    topic_id = Column(String(64), nullable=False)
    topic_text = Column(Text, nullable=False)
    skill_id = Column(String(64), nullable=False)
    difficulty = Column(String(32), default="steady", nullable=False)
    turns = Column(Integer, default=4, nullable=False)
    estimated_minutes = Column(Integer, default=6, nullable=False)
    reminder = Column(Text, nullable=False)
    consumed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="topic_inventory")


class DebateSession(Base):
    __tablename__ = "debate_sessions"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    topic_id = Column(String(64), nullable=False)
    topic_text = Column(Text, nullable=False)
    skill_id = Column(String(64), nullable=False)
    skill_name = Column(String(128), nullable=False)
    skill_hint = Column(Text, nullable=False)
    skill_reminder = Column(Text, nullable=False)
    difficulty = Column(String(32), default="steady", nullable=False)
    user_side = Column(String(16), nullable=False)  # "agree" | "disagree"
    total_user_turns = Column(Integer, default=4, nullable=False)
    current_turn = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="active", nullable=False)  # "active" | "finished" | "error"
    pre_final_analysis_encrypted = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="sessions")
    turns = relationship("DebateTurn", back_populates="session", order_by="DebateTurn.turn_number, DebateTurn.created_at", cascade="all, delete-orphan")
    evidence = relationship("TemporaryTurnEvidence", back_populates="session", cascade="all, delete-orphan")
    review = relationship("DebateReview", back_populates="session", uselist=False, cascade="all, delete-orphan")
    coach_threads = relationship("CoachThread", back_populates="session", cascade="all, delete-orphan")


class DebateTurn(Base):
    __tablename__ = "debate_turns"

    id = Column(String(64), primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("debate_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    turn_number = Column(Integer, nullable=False)
    speaker = Column(String(16), nullable=False)  # "user" | "opponent"
    text_encrypted = Column(Text, nullable=True)
    audio_available = Column(Boolean, default=False, nullable=False)
    duration_sec = Column(Float, default=0.0, nullable=False)
    client_response_delay_ms = Column(Integer, default=0, nullable=False)
    idempotency_key = Column(String(128), nullable=True, index=True)

    # Conversational metadata
    move = Column(String(64), nullable=True)  # challenge_assumption | ask_clarification | counterexample | request_evidence | concede_and_press | answer_user_question | closing_challenge
    requires_response = Column(Boolean, default=True, nullable=False)
    addressed_claim = Column(Text, nullable=True)
    conversation_state = Column(String(32), default="unresolved", nullable=False)  # unresolved | advanced | ready_to_close
    media_asset_id = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    session = relationship("DebateSession", back_populates="turns")


class TemporaryTurnEvidence(Base):
    __tablename__ = "temporary_turn_evidence"

    id = Column(String(64), primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("debate_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    turn_number = Column(Integer, nullable=False)
    evidence_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    session = relationship("DebateSession", back_populates="evidence")


class DebateReview(Base):
    __tablename__ = "debate_reviews"

    session_id = Column(String(64), ForeignKey("debate_sessions.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    outcome = Column(String(32), default="undetermined", nullable=False)  # "user_win" | "opponent_win" | "draw" | "undetermined"
    stars = Column(Integer, default=1, nullable=False)
    completed = Column(Boolean, default=True, nullable=False)
    skill_demonstrated = Column(Boolean, default=False, nullable=False)
    mastery_note = Column(Text, nullable=True)
    skill_assessment_json = Column(JSON, nullable=True)
    argument_feedback_json = Column(JSON, nullable=True)
    language_feedback_encrypted = Column(Text, nullable=True)
    xp_earned = Column(Integer, default=60, nullable=False)
    streak_extended = Column(Boolean, default=False, nullable=False)
    next_level_unlocked = Column(Boolean, default=False, nullable=False)

    # 4 integer scores out of 10 with clear rubrics & highlights
    score_technique = Column(Integer, default=8, nullable=False)
    score_grammar = Column(Integer, default=8, nullable=False)
    score_vocabulary = Column(Integer, default=8, nullable=False)
    score_delivery = Column(Integer, default=8, nullable=False)
    score_technique_rubric = Column(Text, nullable=True)
    score_grammar_rubric = Column(Text, nullable=True)
    score_vocabulary_rubric = Column(Text, nullable=True)
    score_delivery_rubric = Column(Text, nullable=True)
    strongest_moment = Column(Text, nullable=True)
    improvement_opportunity = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    session = relationship("DebateSession", back_populates="review")


class ReviewFeedback(Base):
    __tablename__ = "review_feedback"

    id = Column(String(64), primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("debate_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    verdict = Column(String(32), default="disagree", nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Media Storage & Retention Models
# ---------------------------------------------------------------------------

class MediaAsset(Base):
    __tablename__ = "media_assets"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id = Column(String(64), ForeignKey("debate_sessions.id", ondelete="SET NULL"), index=True, nullable=True)
    turn_number = Column(Integer, nullable=True)
    source_type = Column(String(32), default="debate_turn", nullable=False)  # "debate_turn" | "coach_audio" | "practice_attempt"
    storage_path = Column(String(512), nullable=False)
    mime_type = Column(String(64), default="audio/webm", nullable=False)
    file_size_bytes = Column(Integer, default=0, nullable=False)
    duration_ms = Column(Integer, default=0, nullable=False)
    transcript_encrypted = Column(Text, nullable=True)
    phonemes_encrypted = Column(Text, nullable=True)  # JSON array of timestamped phonemes
    speech_metrics_json = Column(JSON, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="media_assets")
    derived_clips = relationship("DerivedAudioClip", back_populates="source_asset", cascade="all, delete-orphan")


class DerivedAudioClip(Base):
    __tablename__ = "derived_audio_clips"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    source_asset_id = Column(String(64), ForeignKey("media_assets.id", ondelete="CASCADE"), index=True, nullable=False)
    storage_path = Column(String(512), nullable=False)
    start_ms = Column(Integer, default=0, nullable=False)
    end_ms = Column(Integer, default=0, nullable=False)
    duration_ms = Column(Integer, default=0, nullable=False)
    purpose = Column(String(128), default="evidence", nullable=False)
    label = Column(String(128), default="Debate Evidence", nullable=False)
    transcript_excerpt = Column(Text, nullable=True)
    coach_note = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    source_asset = relationship("MediaAsset", back_populates="derived_clips")


# ---------------------------------------------------------------------------
# AI Coaching System Models
# ---------------------------------------------------------------------------

class CoachThread(Base):
    __tablename__ = "coach_threads"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id = Column(String(64), ForeignKey("debate_sessions.id", ondelete="SET NULL"), index=True, nullable=True)
    thread_type = Column(String(32), default="general", nullable=False)  # "debate_review" | "general"
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="coach_threads")
    session = relationship("DebateSession", back_populates="coach_threads")
    messages = relationship("CoachMessage", back_populates="thread", order_by="CoachMessage.created_at", cascade="all, delete-orphan")


class CoachMessage(Base):
    __tablename__ = "coach_messages"

    id = Column(String(64), primary_key=True, index=True)
    thread_id = Column(String(64), ForeignKey("coach_threads.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    sender = Column(String(16), nullable=False)  # "user" | "coach"
    message_type = Column(String(32), default="text", nullable=False)  # "text" | "audio" | "opening_analysis" | "evidence_card"
    text_encrypted = Column(Text, nullable=True)
    media_asset_id = Column(String(64), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True)
    evidence_clip_id = Column(String(64), ForeignKey("derived_audio_clips.id", ondelete="SET NULL"), nullable=True)
    structured_data_json = Column(JSON, nullable=True)
    processing_state = Column(String(32), default="ready", nullable=False)  # "recording" | "uploading" | "processing" | "ready" | "failed"
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    thread = relationship("CoachThread", back_populates="messages")
    media_asset = relationship("MediaAsset", foreign_keys=[media_asset_id])
    evidence_clip = relationship("DerivedAudioClip", foreign_keys=[evidence_clip_id])


class CoachingMemoryItem(Base):
    __tablename__ = "coaching_memory_items"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    pattern_type = Column(String(64), nullable=False)  # active_focus | grammar_pattern | vocabulary_pattern | delivery_pattern | pronunciation_pattern | argumentative_strength | confidence | user_preference
    label = Column(String(255), nullable=False)
    status = Column(String(32), default="active_focus", nullable=False)  # active_focus | monitoring | resolved | dismissed
    confidence = Column(Float, default=0.8, nullable=False)
    sessions_observed = Column(Integer, default=1, nullable=False)
    trend = Column(String(32), default="steady", nullable=False)  # improving | steady | needs_focus
    supporting_evidence_json = Column(JSON, default=list, nullable=False)
    counterevidence_json = Column(JSON, default=list, nullable=False)
    last_discussed_at = Column(DateTime(timezone=True), nullable=True)
    user_correction = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="coaching_memories")
