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

def get_all_tables_with_counts():
    import sqlite3
    db_path = DB_PATH
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [r[0] for r in cur.fetchall()]
        
        results = []
        for t in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                count = cur.fetchone()[0]
                results.append({"name": t, "count": count})
            except:
                pass
        conn.close()
        results.sort(key=lambda x: x["name"])
        return results
    except Exception as e:
        logger.error(f"Error fetching schema: {e}")
        return []

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_database(request: Request):
    tables_info = get_all_tables_with_counts()
    return templates.TemplateResponse("pages/database.html", {
        "request": request, 
        "tables_info": tables_info,
        "active_tab": "database"
    })

@router.get("/fragments/db-explorer", response_class=HTMLResponse)
def frag_db_explorer(request: Request, table_name: str = None, limit: int = 50, q: str = ""):
    if not table_name:
        return _html_output('<div class="flex flex-col items-center justify-center p-12 text-gray-400"><svg class="w-12 h-12 mb-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"/></svg>Vui lòng chọn Table từ menu bên trái</div>')

    try:
        import sqlite3
        db_path = DB_PATH
        if not os.path.exists(db_path):
            return _html_output('<div class="text-sm text-red-500 p-4">Database file not found</div>')

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Validate table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        if not cur.fetchone():
            return _html_output('<div class="text-sm text-red-500 p-4">Table không hợp lệ!</div>')

        cur.execute(f"PRAGMA table_info({table_name})")
        columns_info = cur.fetchall()
        has_id = any(c['name'] == 'id' for c in columns_info)
        column_names = [c['name'] for c in columns_info]

        order_clause = "ORDER BY id DESC" if has_id else ""
        
        where_clause = ""
        params = []
        if q.strip():
            # Search over all columns (cheap wildcard search)
            from string import capwords
            search_clause = " OR ".join([f"{col} LIKE ?" for col in column_names])
            where_clause = f"WHERE {search_clause}"
            params = [f"%{q.strip()}%"] * len(column_names)

        query = f"SELECT * FROM {table_name} {where_clause} {order_clause} LIMIT ?"
        cur.execute(query, params + [limit])
        rows_data = cur.fetchall()

        # Lấy count tổng
        cur.execute(f"SELECT COUNT(*) FROM {table_name} {where_clause}", params)
        total_rows = cur.fetchone()[0]

        columns = [description[0] for description in cur.description] if cur.description else []
        rows = [dict(r) for r in rows_data]

        conn.close()

        return templates.TemplateResponse(
            "fragments/syspanel/db_explorer.html",
            {
                "request": request,
                "table_name": table_name,
                "columns": columns,
                "rows": rows,
                "limit": limit,
                "q": q,
                "total_rows": total_rows
            }
        )
    except Exception as e:
        logger.error(f"DB Explorer Error: {e}")
        return _html_output(f'<div class="text-sm text-red-500 p-4">Lỗi truy xuất: {e}</div>')
