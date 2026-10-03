"""
tests/integration/test_access_control.py
─────────────────────────────────────────
Integration tests for RBAC and multi-tenant access control:
  - Non-members are rejected with 403 from accessing workspace resources
  - Workspace members can read workspace documents
  - Only workspace owners can delete documents or delete workspaces
  - Membership revocation immediately blocks access
"""
from __future__ import annotations

from unittest.mock import patch
import pytest
from httpx import AsyncClient

from tests.conftest import make_user_payload


async def _register_and_get_auth(client: AsyncClient) -> tuple[dict, str]:
    payload = make_user_payload()
    reg = await client.post("/api/v1/auth/register", json=payload)
    user_data = reg.json()
    tok = await client.post("/api/v1/auth/token", json=payload)
    return user_data, tok.json()["access_token"]


def _mock_enqueue():
    return patch(
        "app.services.document_service.enqueue_ingestion",
        return_value="mock-job-id",
    )


@pytest.mark.asyncio
async def test_access_control_workflow(client: AsyncClient):
    # 1. User A creates Workspace A
    user_a, token_a = await _register_and_get_auth(client)
    res_ws_a = await client.post(
        "/api/v1/workspaces",
        json={"name": "Org A Workspace"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_ws_a.status_code == 201
    ws_a_id = res_ws_a.json()["id"]

    # 2. User A uploads a document to Workspace A
    with _mock_enqueue():
        up_res = await client.post(
            f"/api/v1/workspaces/{ws_a_id}/documents",
            files={"file": ("report.txt", b"Confidential Report", "text/plain")},
            headers={"Authorization": f"Bearer {token_a}"},
        )
    assert up_res.status_code == 202
    doc_id = up_res.json()["id"]

    # 3. User B (stranger) tries to access Workspace A documents -> 403 Forbidden
    user_b, token_b = await _register_and_get_auth(client)
    forbidden_list = await client.get(
        f"/api/v1/workspaces/{ws_a_id}/documents",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden_list.status_code == 403

    # Stranger tries to delete document -> 403 Forbidden
    forbidden_delete = await client.delete(
        f"/api/v1/workspaces/{ws_a_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden_delete.status_code == 403

    # 4. Owner adds User B as a member
    add_member_res = await client.post(
        f"/api/v1/workspaces/{ws_a_id}/members",
        json={"email": user_b["email"], "role": "member"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert add_member_res.status_code == 201

    # 5. User B can now list documents
    allowed_list = await client.get(
        f"/api/v1/workspaces/{ws_a_id}/documents",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert allowed_list.status_code == 200
    docs = allowed_list.json()
    assert len(docs) == 1
    assert docs[0]["id"] == doc_id

    # 6. User B (member, not owner) cannot delete document -> 403
    member_delete_doc = await client.delete(
        f"/api/v1/workspaces/{ws_a_id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert member_delete_doc.status_code == 403

    # 7. User B cannot delete workspace -> 403
    member_delete_ws = await client.delete(
        f"/api/v1/workspaces/{ws_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert member_delete_ws.status_code == 403

    # 8. Owner removes User B
    remove_member = await client.delete(
        f"/api/v1/workspaces/{ws_a_id}/members/{user_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert remove_member.status_code == 204

    # 9. User B is blocked again -> 403
    revoked_list = await client.get(
        f"/api/v1/workspaces/{ws_a_id}/documents",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert revoked_list.status_code == 403
