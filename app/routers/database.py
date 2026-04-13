from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import os
import logging
import sqlite3
import csv
import io
from typing import List, Dict, Any, Optional

from app.main_templates import templates
from app.config import DB_PATH
from app.database.core import get_db 
from sqlalchemy.orm import Session
from sqlalchemy import text

# New service imports
from app.services.db_acl import check_table_permission, READONLY_TABLES, WRITABLE_TABLES
from app.services.sql_validator import analyze_sql, SQLRiskLevel
from app.services.audit_logger import audit_log

router = APIRouter(prefix="/database", tags=["database"])
logger = logging.getLogger(__name__)

# Mock require_admin for now if not globally defined, 
# but in this project, it's usually handled by session/cookie check in templates
def require_admin(request: Request):
    # This is a placeholder; real implementation depends on the app's auth system.
    # For now, we assume the user is authorized if they reached this admin-only route.
    pass

def _html_output(text: str) -> HTMLResponse:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed p-4 bg-gray-900 rounded-lg'>{escaped}</pre>")

def get_primary_keys(table_name: str) -> List[str]:
    """
    Get primary key columns for a SQLite table.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    conn.close()
    
    # row[5] is the pk flag (1 if PK, 0 if not)
    pks = [col[1] for col in columns if col[5] > 0]
    if not pks:
        raise ValueError(f"Bảng '{table_name}' không có Primary Key, không thể xóa an toàn.")
    return pks

def get_all_tables_with_counts():
    if not os.path.exists(DB_PATH):
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
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
        return _html_output('<div class="flex flex-col items-center justify-center p-12 text-gray-400">...</div>')

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Validate table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        if not cur.fetchone():
            return _html_output('<div class="text-sm text-red-500 p-4">Table không hợp lệ!</div>')

        cur.execute(f"PRAGMA table_info({table_name})")
        columns_info = cur.fetchall()
        has_pk = any(c[5] > 0 for c in columns_info)
        column_names = [c[1] for c in columns_info]

        order_clause = ""
        pks = [c[1] for c in columns_info if c[5] > 0]
        if pks:
            order_clause = f"ORDER BY {pks[0]} DESC"
        
        where_clause = ""
        params = []
        if q.strip():
            search_clause = " OR ".join([f"{col} LIKE ?" for col in column_names])
            where_clause = f"WHERE {search_clause}"
            params = [f"%{q.strip()}%"] * len(column_names)

        query = f"SELECT * FROM {table_name} {where_clause} {order_clause} LIMIT ?"
        cur.execute(query, params + [limit])
        rows_data = cur.fetchall()
        
        columns = [description[0] for description in cur.description] if cur.description else []
        rows = [dict(r) for r in rows_data]

        cur.execute(f"SELECT COUNT(*) FROM {table_name} {where_clause}", params)
        total_rows = cur.fetchone()[0]
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
                "total_rows": total_rows,
                "has_pk": has_pk,
                "pks": pks
            }
        )
    except Exception as e:
        logger.error(f"DB Explorer Error: {e}")
        return _html_output(f"Lỗi truy xuất: {e}")

# --- NEW PRODUCTION-GRADE ENDPOINTS ---

@router.get("/validate-sql")
def validate_sql_endpoint(sql: str = Query(...)):
    """Live risk assessment for the frontend."""
    try:
        risk, normalized = analyze_sql(sql)
        return {"status": "success", "risk": risk.value, "normalized": normalized}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/execute-sql")
async def execute_sql(request: Request, db: Session = Depends(get_db)):
    """Execute raw SQL with validation and audit."""
    try:
        data = await request.json()
        raw_sql = data.get("sql", "")
        confirmed = data.get("confirmed", False)
        
        risk, normalized_sql = analyze_sql(raw_sql)
        
        if risk == SQLRiskLevel.DANGEROUS:
            ip = request.client.host if request.client else "unknown"
            logger.warning("Blocked DANGEROUS SQL from %s: %.200s", ip, normalized_sql)
            return {"status": "error", "message": "Câu lệnh này bị chặn hoàn toàn vì lý do an toàn (DANGEROUS)."}
            
        if risk == SQLRiskLevel.MODERATE and not confirmed:
            return {
                "status": "require_confirm", 
                "risk": risk.value, 
                "normalized": normalized_sql,
                "message": "Đây là câu lệnh thay đổi dữ liệu. Vui lòng xác nhận để thực thi."
            }
            
        # Audit before execution
        ip = request.client.host if request.client else "unknown"
        # In a real app, get user_id from auth dependency
        user_id = 1 
        
        # Select execution logic
        is_select = risk == SQLRiskLevel.SAFE
        
        try:
            result = db.execute(text(normalized_sql))
            
            audit_log(
                user_id=user_id,
                action="execute_sql",
                ip_address=ip,
                sql=normalized_sql,
                risk=risk.value,
                affected_rows=result.rowcount if not is_select else 0
            )
            
            if is_select and result.returns_rows:
                cols = list(result.keys())
                rows = [dict(zip(cols, row)) for row in result.fetchmany(500)]
                db.commit()
                return {"status": "success", "columns": cols, "rows": rows}
            else:
                affected = result.rowcount
                db.commit()
                return {"status": "success", "affected_rows": affected}
                
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": f"Lỗi thực thi SQL: {e}"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/row")
async def delete_row(request: Request, table_name: str, db: Session = Depends(get_db)):
    """Delete a specific row using PK detection."""
    try:
        if not check_table_permission(table_name, "delete"):
            raise HTTPException(403, f"Bảng '{table_name}' không được phép xóa dữ liệu qua UI.")
            
        data = await request.json()
        pk_values = data.get("pk_values", {})
        
        pks = get_primary_keys(table_name)
        if not all(pk in pk_values for pk in pks):
            raise HTTPException(400, "Thiếu giá trị Primary Key để định danh bản ghi.")
            
        # Build parameterized WHERE clause
        conditions = " AND ".join([f"{pk} = :{pk}" for pk in pks])
        
        query = text(f"DELETE FROM {table_name} WHERE {conditions}")
        result = db.execute(query, pk_values)
        db.commit()
        
        ip = request.client.host if request.client else "unknown"
        audit_log(
            user_id=1, 
            action="delete_row", 
            ip_address=ip, 
            table=table_name, 
            pk_values=pk_values,
            affected_rows=result.rowcount
        )
        
        return {"status": "success", "deleted": result.rowcount}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Delete row error: {e}")
        raise HTTPException(500, str(e))

@router.get("/export-csv")
def export_csv(table_name: str, q: str = "", db: Session = Depends(get_db)):
    """Streaming CSV export for large tables."""
    try:
        # Validate table name exists before any query — prevents injection via table_name param
        conn_check = sqlite3.connect(DB_PATH)
        cur_check = conn_check.cursor()
        cur_check.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        if not cur_check.fetchone():
            conn_check.close()
            raise HTTPException(400, f"Bảng '{table_name}' không tồn tại.")
        conn_check.close()

        def generate():
            # Get columns
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = [c[1] for c in cur.fetchall()]
            
            # Write header
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_ALL)
            writer.writerow(columns)
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)
            
            # Fetch data in chunks
            where_clause = ""
            params = []
            if q.strip():
                search_clause = " OR ".join([f"{col} LIKE ?" for col in columns])
                where_clause = f"WHERE {search_clause}"
                params = [f"%{q.strip()}%"] * len(columns)
                
            cur.execute(f"SELECT * FROM {table_name} {where_clause}", params)
            
            while True:
                rows = cur.fetchmany(1000)
                if not rows:
                    break
                for row in rows:
                    writer.writerow(row)
                yield output.getvalue()
                output.truncate(0)
                output.seek(0)
            
            conn.close()

        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={table_name}.csv"}
        )
    except Exception as e:
        logger.error(f"Export CSV error: {e}")
        raise HTTPException(500, f"Lỗi xuất file: {e}")
