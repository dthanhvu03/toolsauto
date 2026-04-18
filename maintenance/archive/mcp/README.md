# MCP — kiểm thử trên trình duyệt / Browser testing

## Tiếng Việt

### 1) Cursor IDE — Playwright MCP (khuyến nghị)

1. Cài Node 18+.
2. Mở **Cursor Settings → MCP → Add new MCP server**, hoặc merge nội dung file [`cursor-mcp.json`](./cursor-mcp.json) vào cấu hình MCP của bạn (JSON gốc có thể nằm ở user settings, tùy phiên bản Cursor).
3. Bật server tên **`playwright`** (hoặc tên bạn đặt trong `mcpServers`).
4. Trong chat Agent, yêu cầu: *“Mở http://localhost:8000/compliance/ và chụp snapshot”* — agent sẽ gọi tool navigate/snapshot của MCP.

**Lưu ý:** Thư mục `.cursor/` của repo đang **gitignore**; nếu Cursor đọc `mcp.json` từ `.cursor/`, hãy **copy** `mcp/cursor-mcp.json` vào đó trên máy local (không commit).

### 2) Cursor — Simple Browser (tích hợp sẵn)

Nhiều bản Cursor có MCP **`cursor-ide-browser`** (điều khiển tab Simple Browser). Trong MCP settings, bật server đó nếu chưa bật. Luồng: `browser_navigate` → `browser_lock` → thao tác → `browser_unlock` (xem hướng dẫn trong MCP descriptor của Cursor).

### 3) Chạy MCP server tay (debug)

```bash
chmod +x scripts/run-mcp-playwright.sh
./scripts/run-mcp-playwright.sh
```

### 4) App cần chạy trước khi test UI

```bash
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 5) Gợi ý checklist E2E (agent + MCP)

| Bước | URL / hành động |
|------|------------------|
| Mở | `http://127.0.0.1:8000/compliance/` |
| Tab | Chuyển tab Lịch sử / Kiểm tra / Thống kê |
| Tester | Nhập caption → Kiểm tra → xem kết quả SAFE/WARNING |
| Affiliates | `http://127.0.0.1:8000/affiliates/` — form lưu + compliance |

---

### 6) n8n-lite Debug MCP Server (business logic)

Server Python riêng expose workflow/CTA/step toggle tools qua stdio transport.

```bash
# Chạy trực tiếp
PYTHONPATH=. venv/bin/python mcp_server.py

# Mở bằng MCP Inspector
npx -y @modelcontextprotocol/inspector -- venv/bin/python mcp_server.py
```

**Tools có sẵn:**

| Tool | Mô tả |
|------|--------|
| `get_workflow_steps` | Xem steps hiện tại từ workflow_definitions |
| `get_cta_templates` | Xem CTA templates từ DB |
| `inject_cta` | Preview CTA injection (read-only) |
| `preview_step_toggles` | Xem step nào active/skipped |
| `invalidate_workflow_cache` | Xoá cache để reload từ DB |

---

## English

1. Merge [`cursor-mcp.json`](./cursor-mcp.json) into your Cursor MCP configuration (or add the `playwright` server manually with `npx -y @playwright/mcp@latest`).
2. Start the FastAPI app on port **8000**, then use the agent to drive the browser via MCP tools (`navigate`, `snapshot`, `click`, etc.).
3. Use **`./scripts/run-mcp-playwright.sh`** only for debugging the MCP process outside Cursor.
4. Use **`PYTHONPATH=. venv/bin/python mcp_server.py`** for the n8n-lite debug tools (workflow, CTA, step toggles).

**Related:** Official package [@playwright/mcp](https://www.npmjs.com/package/@playwright/mcp).

