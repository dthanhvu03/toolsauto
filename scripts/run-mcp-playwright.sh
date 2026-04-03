#!/usr/bin/env bash
# Chạy Playwright MCP server thủ công (debug ngoài Cursor).
# Trong Cursor: dùng cấu hình trong mcp/cursor-mcp.json (xem mcp/README.md).
set -euo pipefail
cd "$(dirname "$0")/.."
exec npx -y @playwright/mcp@latest "$@"
