"""
tests/unit/test_eval_metrics.py
───────────────────────────────
Unit tests for evaluation metrics:
  - Recall@k
  - Mean Reciprocal Rank (MRR)
  - Token F1
  - Faithfulness calculation
  - EvalService run execution lifecycle
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.models.workspace import Workspace
from app.services.eval_service import (
    compute_recall_at_k,
    compute_mrr,
    compute_token_f1,
    compute_faithfulness,
    EvalService,
)


def test_recall_at_k():
    retrieved = ["doc_a", "doc_b", "doc_c", "doc_d", "doc_e"]

    # Target is #1
    assert compute_recall_at_k(retrieved, "doc_a", k=1) == 1.0
    # Target is #3
    assert compute_recall_at_k(retrieved, "doc_c", k=1) == 0.0
    assert compute_recall_at_k(retrieved, "doc_c", k=3) == 1.0
    # Target is not in top 5
    assert compute_recall_at_k(retrieved, "doc_z", k=5) == 0.0
    # Empty inputs
    assert compute_recall_at_k([], "doc_a", k=5) == 0.0


def test_mean_reciprocal_rank():
    # Query 1: target at rank 1 -> 1/1 = 1.0
    # Query 2: target at rank 2 -> 1/2 = 0.5
    # Query 3: target at rank 4 -> 1/4 = 0.25
    # Query 4: target not found -> 0.0
    retrieved_list = [
        ["doc_1", "doc_2", "doc_3"],
        ["doc_x", "doc_y", "doc_z"],
        ["a", "b", "c", "d"],
        ["alpha", "beta"],
    ]
    targets = ["doc_1", "doc_y", "d", "gamma"]

    expected_mrr = (1.0 + 0.5 + 0.25 + 0.0) / 4.0  # 1.75 / 4 = 0.4375
    assert pytest.approx(compute_mrr(retrieved_list, targets), rel=1e-4) == expected_mrr


def test_token_f1():
    # Exact match
    assert compute_token_f1("The launch date is June 1st.", "The launch date is June 1st.") == 1.0
    # Complete mismatch (0 shared tokens)
    assert compute_token_f1("Apples bananas", "Cars airplanes") == 0.0
    # Partial match
    pred = "deployment on June 1st"
    gt = "scheduled deployment on June 1st by engineering"
    f1 = compute_token_f1(pred, gt)
    assert 0.0 < f1 < 1.0


def test_faithfulness():
    context = "The Prometheus project was established in 2024 to modernize cloud infrastructure."
    claims = ["established in 2024", "modernize cloud infrastructure"]
    assert compute_faithfulness(claims, context) == 1.0

    unsupported = ["Established in 1999", "Builds spacecraft"]
    assert compute_faithfulness(unsupported, context) == 0.0


@pytest.mark.asyncio
async def test_eval_service_lifecycle(db_session: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        email=f"eval_{uuid.uuid4().hex[:6]}@example.com",
        pw_hash=hash_password("Pass123!"),
    )
    db_session.add(user)
    await db_session.flush()

    ws = Workspace(id=uuid.uuid4(), name="EvalWS", owner_id=user.id)
    db_session.add(ws)
    await db_session.flush()

    run = await EvalService.create_run(
        db=db_session,
        workspace_id=ws.id,
        user_id=user.id,
        config={"name": "test_experiment", "golden_dataset_path": "sample.jsonl"},
    )
    assert run.status == "queued"

    sample_data = [
        {
            "question": "What is the policy?",
            "source_doc": "policy.pdf",
            "expected_answer": "Policy requires badge scan",
            "retrieved_docs": ["policy.pdf", "other.pdf"],
            "actual_answer": "Policy requires badge scan",
        }
    ]

    results = await EvalService.execute_run_sync(db_session, run.id, sample_data)
    assert results["num_questions"] == 1
    assert results["recall_at_1"] == 1.0
    assert results["mrr"] == 1.0

    updated_run = await EvalService.get_run(db_session, run.id)
    assert updated_run is not None
    assert updated_run.status == "done"
    assert updated_run.results_json is not None
