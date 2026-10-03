"""Initial schema: all tables + pgvector + FTS trigger

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extensions ─────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("pw_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_users_email", "users", [sa.text("lower(email)")], unique=True)

    # ── workspaces ───────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── workspace_members ────────────────────────────────────────────────────
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_workspace_members_role"),
    )

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "content_hash", name="uq_documents_workspace_hash"),
        sa.CheckConstraint("status IN ('pending','processing','ready','failed','scanned_pdf')", name="ck_documents_status"),
    )
    op.create_index("idx_docs_workspace", "documents", ["workspace_id"])
    op.create_index("idx_docs_status", "documents", ["workspace_id", "status"])

    # ── chunks ────────────────────────────────────────────────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_title", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_cleaned", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),       # placeholder; overridden below
        sa.Column("fts_vector", sa.Text, nullable=True),      # populated by trigger
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Alter embedding to actual VECTOR type after table creation
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE VECTOR(384) USING NULL")
    op.execute("ALTER TABLE chunks ALTER COLUMN fts_vector TYPE TSVECTOR USING NULL")

    # pgvector HNSW index for ANN
    op.execute(
        "CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    # FTS GIN index
    op.execute("CREATE INDEX idx_chunks_fts ON chunks USING GIN (fts_vector)")
    op.create_index("idx_chunks_workspace", "chunks", ["workspace_id"])

    # FTS trigger — keeps fts_vector in sync automatically
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_fts_update() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          NEW.fts_vector := to_tsvector('english', COALESCE(NEW.content_cleaned, ''));
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER chunks_fts_trig
        BEFORE INSERT OR UPDATE ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_fts_update();
    """)

    # ── chat_sessions ─────────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_chat_sessions_workspace", "chat_sessions", ["workspace_id"])

    # ── messages ──────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations_json", postgresql.JSONB, nullable=True),
        sa.Column("refused", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("refusal_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
    )
    op.create_index("idx_messages_session", "messages", ["session_id"])

    # ── feedback ──────────────────────────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("rating IN (1, -1)", name="ck_feedback_rating"),
    )

    # ── traces ────────────────────────────────────────────────────────────────
    op.create_table(
        "traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_original", sa.Text, nullable=False),
        sa.Column("query_rewritten", sa.Text, nullable=True),
        sa.Column("retrieval_steps", postgresql.JSONB, nullable=True),
        sa.Column("rerank_order", postgresql.JSONB, nullable=True),
        sa.Column("llm_calls", postgresql.JSONB, nullable=True),
        sa.Column("grounding_result", postgresql.JSONB, nullable=True),
        sa.Column("cache_hit", sa.Boolean, nullable=True),
        sa.Column("refused", sa.Boolean, nullable=True),
        sa.Column("total_latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_traces_workspace", "traces", ["workspace_id", "created_at"])
    op.create_index("idx_traces_request", "traces", ["request_id"])

    # ── semantic_cache ────────────────────────────────────────────────────────
    op.create_table(
        "semantic_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_hash", sa.Text, nullable=False),
        sa.Column("question_emb", sa.Text, nullable=True),   # overridden below
        sa.Column("answer_json", postgresql.JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE semantic_cache ALTER COLUMN question_emb TYPE VECTOR(384) USING NULL")
    op.execute(
        "CREATE INDEX idx_cache_embedding ON semantic_cache USING hnsw (question_emb vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.create_index("idx_cache_workspace", "semantic_cache", ["workspace_id"])
    op.create_index("idx_cache_expires", "semantic_cache", ["expires_at"])

    # ── eval_runs ─────────────────────────────────────────────────────────────
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config_json", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("results_json", postgresql.JSONB, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_eval_runs_status"),
    )
    op.create_index("idx_eval_runs_workspace", "eval_runs", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("semantic_cache")
    op.drop_table("traces")
    op.drop_table("feedback")
    op.drop_table("messages")
    op.drop_table("chat_sessions")
    op.execute("DROP TRIGGER IF EXISTS chunks_fts_trig ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_fts_update()")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
