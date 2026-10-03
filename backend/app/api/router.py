"""
app/api/router.py
──────────────────
Central router that includes all sub-routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, workspaces

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)

# Stubs for routers added in later stages:
# from app.api.v1 import documents, chat, feedback, traces, eval, admin
# api_router.include_router(documents.router)
# api_router.include_router(chat.router)
# api_router.include_router(feedback.router)
# api_router.include_router(traces.router)
# api_router.include_router(eval.router)
# api_router.include_router(admin.router)
