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
