# app/models/__init__.py
# Import all models here so Alembic autogenerate can find them
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.chat_session import ChatSession
from app.models.message import Message
from app.models.feedback import Feedback
from app.models.trace import Trace
from app.models.semantic_cache import SemanticCache
from app.models.eval_run import EvalRun

__all__ = [
    "User", "Workspace", "WorkspaceMember", "Document", "Chunk",
    "ChatSession", "Message", "Feedback", "Trace", "SemanticCache", "EvalRun",
]
