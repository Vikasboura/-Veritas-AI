"""
tests/integration/test_retrieval_filters.py
─────────────────────────────────────────────
Integration tests for RetrievalService:
  - Strict workspace isolation (no cross-tenant leakage)
  - Document status filtering (only 'ready' documents are searchable)
  - Specific document filtering via doc_ids
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.document import Document
from app.models.chunk import Chunk
from app.services.retrieval_service import RetrievalService
from app.services.ingestion_service import get_embedder


async def _create_test_workspace_with_user(db: AsyncSession, name: str) -> tuple[User, Workspace]:
    user = User(
        id=uuid.uuid4(),
        email=f"user_{uuid.uuid4().hex[:6]}@example.com",
        pw_hash=hash_password("Password123!"),
    )
    db.add(user)
    await db.flush()

    ws = Workspace(
        id=uuid.uuid4(),
        name=name,
        owner_id=user.id,
    )
    db.add(ws)
    await db.flush()

    member = WorkspaceMember(
        workspace_id=ws.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)
    await db.flush()
    return user, ws


async def _create_document_and_chunks(
    db: AsyncSession,
    workspace: Workspace,
    user: User,
    filename: str,
    contents: list[str],
    status: str = "ready",
) -> Document:
    embedder = get_embedder()
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        uploaded_by=user.id,
        filename=filename,
        content_hash=uuid.uuid4().hex,
        file_type="txt",
        file_size_bytes=sum(len(c.encode()) for c in contents),
        status=status,
    )
    db.add(doc)
    await db.flush()

    for idx, text in enumerate(contents):
        emb = embedder.encode(text, normalize_embeddings=True).tolist()
        chunk = Chunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            workspace_id=workspace.id,
            chunk_index=idx,
            page_number=idx + 1,
            section_title=f"Section {idx}",
            content=text,
            content_cleaned=text,
            token_count=len(text.split()),
            embedding=emb,
        )
        db.add(chunk)
    await db.flush()
    return doc


@pytest.mark.asyncio
async def test_retrieval_workspace_isolation(db_session: AsyncSession):
    """
    CRITICAL SECURITY INVARIANT:
    Chunks from Workspace A must NEVER be returned to Workspace B,
    even when searching with the exact same keywords.
    """
    user_a, ws_a = await _create_test_workspace_with_user(db_session, "Tenant Alpha")
    user_b, ws_b = await _create_test_workspace_with_user(db_session, "Tenant Beta")

    # Workspace A has secret information
    secret_text = "Project Prometheus confidential launch date is October 15th."
    await _create_document_and_chunks(
        db_session, ws_a, user_a, "alpha_secret.txt", [secret_text], status="ready"
    )

    # Workspace B has ordinary information
    public_text = "Quarterly financial report summary and balance sheet."
    await _create_document_and_chunks(
        db_session, ws_b, user_b, "beta_public.txt", [public_text], status="ready"
    )

    # Search in Workspace B for Prometheus
    results_in_b = await RetrievalService.retrieve(
        db=db_session,
        workspace_id=ws_b.id,
        query="Project Prometheus launch date",
        rerank=False,
    )

    # Must NOT find any chunk from Workspace A
    for r in results_in_b:
        assert r.workspace_id == ws_b.id
        assert "Prometheus" not in r.content

    # Search in Workspace A finds it
    results_in_a = await RetrievalService.retrieve(
        db=db_session,
        workspace_id=ws_a.id,
        query="Project Prometheus launch date",
        rerank=False,
    )
    assert len(results_in_a) > 0
    assert results_in_a[0].workspace_id == ws_a.id
    assert "Prometheus" in results_in_a[0].content


@pytest.mark.asyncio
async def test_retrieval_filters_out_unready_documents(db_session: AsyncSession):
    """Chunks from documents not in 'ready' status must never be returned."""
    user, ws = await _create_test_workspace_with_user(db_session, "StatusTestWS")

    # Document pending
    await _create_document_and_chunks(
        db_session, ws, user, "pending.txt", ["Pending document secret content."], status="pending"
    )
    # Document processing
    await _create_document_and_chunks(
        db_session, ws, user, "processing.txt", ["Processing document secret content."], status="processing"
    )
    # Document failed
    await _create_document_and_chunks(
        db_session, ws, user, "failed.txt", ["Failed document secret content."], status="failed"
    )
    # Document ready
    await _create_document_and_chunks(
        db_session, ws, user, "ready.txt", ["Ready document verified content."], status="ready"
    )

    results = await RetrievalService.retrieve(
        db=db_session,
        workspace_id=ws.id,
        query="secret verified content",
        rerank=False,
    )

    assert len(results) > 0
    for res in results:
        assert "Ready document" in res.content
        assert "Pending" not in res.content
        assert "Processing" not in res.content
        assert "Failed" not in res.content


@pytest.mark.asyncio
async def test_retrieval_doc_ids_filter(db_session: AsyncSession):
    """Providing doc_ids restricts retrieval to only those documents."""
    user, ws = await _create_test_workspace_with_user(db_session, "DocFilterWS")

    doc1 = await _create_document_and_chunks(
        db_session, ws, user, "doc1.txt", ["Target topic information in document one."], status="ready"
    )
    doc2 = await _create_document_and_chunks(
        db_session, ws, user, "doc2.txt", ["Target topic information in document two."], status="ready"
    )

    # Filter strictly by doc1
    results = await RetrievalService.retrieve(
        db=db_session,
        workspace_id=ws.id,
        query="Target topic information",
        doc_ids=[doc1.id],
        rerank=False,
    )

    assert len(results) > 0
    for r in results:
        assert r.document_id == doc1.id
