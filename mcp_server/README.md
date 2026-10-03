# CiteBase Pro — Model Context Protocol (MCP) Server

Connect your favorite AI agent, IDE, or chat interface (Cursor, Claude Desktop, Antigravity) directly to your CiteBase Pro workspace documents with verifiable citations and grounding guarantees.

---

## 🛠️ Tools Exposed

### `search_docs`
Searches documents within a specific workspace using hybrid vector + full-text search and reciprocal rank fusion.

**Arguments:**
- `workspace_id` (string, required): UUID of the workspace
- `query` (string, required): The search query or question
- `top_k` (integer, optional): Maximum candidate passages to return (default: `5`)

**Returns:**
List of chunks with filename, page number, similarity score, and excerpt text.

---

### `ask_workspace`
Asks a question against workspace documents and returns an answer generated exclusively from verified citations.

**Arguments:**
- `workspace_id` (string, required): UUID of the workspace
- `question` (string, required): The question to answer

**Returns:**
- `answer`: Grounded response
- `citations`: Source passages with provenance (filename, page, chunk id)
- `refused`: `true` if evidence is insufficient to answer without hallucinating
- `refusal_reason`: Diagnostic reason code

---

## 🚀 Setup & Configuration

### Environment Variables
- `CITEBASE_API_URL`: URL of the CiteBase Pro backend (default: `http://localhost:8000/api/v1`)
- `CITEBASE_API_KEY`: User or Workspace JWT access token

### Claude Desktop Configuration
Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "citebase": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "CITEBASE_API_URL": "http://localhost:8000/api/v1",
        "CITEBASE_API_KEY": "<your-jwt-token>"
      }
    }
  }
}
```

### Cursor IDE Configuration
In **Cursor Settings > Features > MCP**:
- Name: `citebase`
- Type: `command`
- Command: `python -m mcp_server.server`
