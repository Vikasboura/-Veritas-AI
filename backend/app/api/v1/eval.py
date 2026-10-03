"""
app/api/v1/eval.py
──────────────────
Evaluation experiment management endpoints.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_owner
from app.db.session import get_db
from app.models.user import User
from app.schemas.eval import EvalRunCreate, EvalRunResponse
from app.services.eval_service import EvalService

router = APIRouter(prefix="/workspaces/{workspace_id}/eval", tags=["eval"])


@router.post(
    "/runs",
    response_model=EvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger an evaluation run against a golden dataset",
)
async def create_eval_run(
    workspace_id: uuid.UUID,
    payload: EvalRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_owner),
) -> EvalRunResponse:
    run = await EvalService.create_run(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
        config=payload.config.model_dump(),
    )
    # Check if golden dataset file exists to run benchmark
    golden_path = Path("eval/golden") / payload.config.golden_dataset_path
    sample_dataset = []
    if golden_path.exists():
        with open(golden_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    sample_dataset.append(json.loads(line))

    # Execute evaluation run
    if sample_dataset:
        await EvalService.execute_run_sync(db, run.id, sample_dataset)

    updated_run = await EvalService.get_run(db, run.id)
    return EvalRunResponse.model_validate(updated_run or run)


@router.get(
    "/runs",
    response_model=list[EvalRunResponse],
    summary="List all evaluation runs for a workspace",
)
async def list_eval_runs(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_owner),
) -> list[EvalRunResponse]:
    runs = await EvalService.list_runs(db, workspace_id)
    return [EvalRunResponse.model_validate(r) for r in runs]


@router.get(
    "/runs/{run_id}",
    response_model=EvalRunResponse,
    summary="Get details and results of an evaluation run",
)
async def get_eval_run(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_workspace_owner),
) -> EvalRunResponse:
    run = await EvalService.get_run(db, run_id)
    if not run or run.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    return EvalRunResponse.model_validate(run)
