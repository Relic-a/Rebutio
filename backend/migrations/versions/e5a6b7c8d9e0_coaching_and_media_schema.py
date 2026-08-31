"""coaching and media schema

Revision ID: e5a6b7c8d9e0
Revises: d4378b755c54
Create Date: 2026-08-30 22:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e5a6b7c8d9e0"
down_revision: Union[str, None] = "d4378b755c54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Media assets
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(64), primary_key=True, index=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("debate_sessions.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("turn_number", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(32), default="debate_turn", nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(64), default="audio/webm", nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), default=0, nullable=False),
        sa.Column("duration_ms", sa.Integer(), default=0, nullable=False),
        sa.Column("transcript_encrypted", sa.Text(), nullable=True),
        sa.Column("phonemes_encrypted", sa.Text(), nullable=True),
        sa.Column("speech_metrics_json", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Derived audio clips
    op.create_table(
        "derived_audio_clips",
        sa.Column("id", sa.String(64), primary_key=True, index=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("source_asset_id", sa.String(64), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("start_ms", sa.Integer(), default=0, nullable=False),
        sa.Column("end_ms", sa.Integer(), default=0, nullable=False),
        sa.Column("duration_ms", sa.Integer(), default=0, nullable=False),
        sa.Column("purpose", sa.String(128), default="evidence", nullable=False),
        sa.Column("label", sa.String(128), default="Debate Evidence", nullable=False),
        sa.Column("transcript_excerpt", sa.Text(), nullable=True),
        sa.Column("coach_note", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Coach threads
    op.create_table(
        "coach_threads",
        sa.Column("id", sa.String(64), primary_key=True, index=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("debate_sessions.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("thread_type", sa.String(32), default="general", nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Coach messages
    op.create_table(
        "coach_messages",
        sa.Column("id", sa.String(64), primary_key=True, index=True),
        sa.Column("thread_id", sa.String(64), sa.ForeignKey("coach_threads.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("sender", sa.String(16), nullable=False),
        sa.Column("message_type", sa.String(32), default="text", nullable=False),
        sa.Column("text_encrypted", sa.Text(), nullable=True),
        sa.Column("media_asset_id", sa.String(64), sa.ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_clip_id", sa.String(64), sa.ForeignKey("derived_audio_clips.id", ondelete="SET NULL"), nullable=True),
        sa.Column("structured_data_json", sa.JSON(), nullable=True),
        sa.Column("processing_state", sa.String(32), default="ready", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Coaching memory items
    op.create_table(
        "coaching_memory_items",
        sa.Column("id", sa.String(64), primary_key=True, index=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("pattern_type", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), default="active_focus", nullable=False),
        sa.Column("confidence", sa.Float(), default=0.8, nullable=False),
        sa.Column("sessions_observed", sa.Integer(), default=1, nullable=False),
        sa.Column("trend", sa.String(32), default="steady", nullable=False),
        sa.Column("supporting_evidence_json", sa.JSON(), nullable=False),
        sa.Column("counterevidence_json", sa.JSON(), nullable=False),
        sa.Column("last_discussed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_correction", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Add new turn metadata columns to debate_turns
    with op.batch_alter_table("debate_turns") as batch_op:
        batch_op.add_column(sa.Column("move", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("requires_response", sa.Boolean(), server_default=sa.text("1"), nullable=False))
        batch_op.add_column(sa.Column("addressed_claim", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("conversation_state", sa.String(32), server_default="unresolved", nullable=False))
        batch_op.add_column(sa.Column("media_asset_id", sa.String(64), nullable=True))

    # Add review-score and rubric columns to debate_reviews
    with op.batch_alter_table("debate_reviews") as batch_op:
        batch_op.add_column(sa.Column("score_technique", sa.Integer(), server_default="8", nullable=False))
        batch_op.add_column(sa.Column("score_grammar", sa.Integer(), server_default="8", nullable=False))
        batch_op.add_column(sa.Column("score_vocabulary", sa.Integer(), server_default="8", nullable=False))
        batch_op.add_column(sa.Column("score_delivery", sa.Integer(), server_default="8", nullable=False))
        batch_op.add_column(sa.Column("score_technique_rubric", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("score_grammar_rubric", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("score_vocabulary_rubric", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("score_delivery_rubric", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("strongest_moment", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("improvement_opportunity", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("debate_reviews") as batch_op:
        batch_op.drop_column("improvement_opportunity")
        batch_op.drop_column("strongest_moment")
        batch_op.drop_column("score_delivery_rubric")
        batch_op.drop_column("score_vocabulary_rubric")
        batch_op.drop_column("score_grammar_rubric")
        batch_op.drop_column("score_technique_rubric")
        batch_op.drop_column("score_delivery")
        batch_op.drop_column("score_vocabulary")
        batch_op.drop_column("score_grammar")
        batch_op.drop_column("score_technique")

    with op.batch_alter_table("debate_turns") as batch_op:
        batch_op.drop_column("media_asset_id")
        batch_op.drop_column("conversation_state")
        batch_op.drop_column("addressed_claim")
        batch_op.drop_column("requires_response")
        batch_op.drop_column("move")

    op.drop_table("coaching_memory_items")
    op.drop_table("coach_messages")
    op.drop_table("coach_threads")
    op.drop_table("derived_audio_clips")
    op.drop_table("media_assets")