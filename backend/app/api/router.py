"""
app/api/router.py
──────────────────
Central router that includes all sub-routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, workspaces, documents, chat, traces, eval as eval_router, admin

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(traces.router)
api_router.include_router(eval_router.router)
api_router.include_router(admin.router)
