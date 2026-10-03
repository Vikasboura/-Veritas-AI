# CiteBase Pro — Security Threat Model (STRIDE)

CiteBase Pro employs a defense-in-depth posture specifically tailored for multi-tenant enterprise RAG systems.

---

## 🛡️ STRIDE Threat Assessment

| Threat Category | Attack Vector | CiteBase Pro Mitigation |
|---|---|---|
| **Spoofing** | Stolen or forged JWT token | Short-lived access tokens (30 min), SHA-256 JWT signatures, secret key validation (minimum 32 characters enforced at startup). |
| **Tampering** | Uploading forged embeddings or tampering with documents | Content-hash (SHA-256) calculated server-side; client cannot provide embeddings; chunks are derived strictly by server-side workers. |
| **Repudiation** | Admin or user denies taking an action | Full query execution telemetry and immutable structured JSON audit trails recorded in `traces` table. |
| **Information Disclosure** | Cross-tenant data leakage in vector search or semantic cache | `workspace_id` is mandatory in EVERY SQL query filter and vector ANN index constraint; 100% verified via automated integration tests in CI. |
| **Information Disclosure** | Prompt injection attacks embedded in uploaded document text | Context documents are strictly quarantined in fenced delimiter blocks (`=== BEGIN CONTEXT DOCUMENTS ===`); system prompt instructs model to treat context as untrusted data and ignore override instructions. |
| **Denial of Service** | Upload flooding or oversized document attacks | File size capped at 50MB; MIME and extension whitelist enforced; sliding window rate limiting via Redis. |
| **Elevation of Privilege** | Normal user attempting to delete documents or workspaces | Route-level RBAC dependencies (`require_workspace_owner` vs `require_workspace_member`). |

---

## 🔒 Multi-Tenant Isolation Invariant

Every SQL query interacting with documents, chunks, traces, or semantic cache enforces the tenant constraint:

```sql
WHERE workspace_id = :workspace_id
```

Integration test `tests/integration/test_retrieval_filters.py` and `tests/unit/test_cache_isolation.py` programmatically verify that data in Tenant A cannot be searched, retrieved, or returned to Tenant B under any circumstance.
