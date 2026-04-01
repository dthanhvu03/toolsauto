from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
import os
import logging
from app.main_templates import templates
from app.config import DB_PATH

router = APIRouter(prefix="/database", tags=["database"])
logger = logging.getLogger(__name__)

def _html_output(text: str) -> HTMLResponse:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed'>{escaped}</pre>")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_database(request: Request):
    return templates.TemplateResponse("pages/database.html", {"request": request})

@router.get("/fragments/db-explorer", response_class=HTMLResponse)
def frag_db_explorer(request: Request, table_name: str = None):
    if not table_name:
        return _html_output('<div class="text-sm text-gray-400">Please select a table to view data</div>')

    allowed_tables = {'accounts', 'jobs', 'pages', 'viral_materials', 'system_state'}
    if table_name not in allowed_tables:
        return _html_output('<div class="text-sm text-red-500">Invalid table selected!</div>')

    try:
        import sqlite3
        db_path = DB_PATH
        if not os.path.exists(db_path):
            return _html_output('<div class="text-sm text-red-500">Database file not found</div>')

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(f"PRAGMA table_info({table_name})")
        columns_info = cur.fetchall()
        has_id = any(c['name'] == 'id' for c in columns_info)

        order_clause = "ORDER BY id DESC" if has_id else ""
        cur.execute(f"SELECT * FROM {table_name} {order_clause} LIMIT 50")
        rows_data = cur.fetchall()

        columns = [description[0] for description in cur.description] if cur.description else []
        rows = [dict(r) for r in rows_data]

        conn.close()

        return templates.TemplateResponse(
            "fragments/syspanel/db_explorer.html",
            {
                "request": request,
                "table_name": table_name,
                "columns": columns,
                "rows": rows
            }
        )
    except Exception as e:
        logger.error(f"DB Explorer Error: {e}")
        return _html_output(f'<div class="text-sm text-red-500">Query Error: {e}</div>')
