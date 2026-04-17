from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
import logging
import csv
import io
from typing import List, Dict, Any, Optional

from app.main_templates import templates
from app.database.core import get_db, engine 
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect

# New service imports
from app.services.db_acl import check_table_permission, READONLY_TABLES, WRITABLE_TABLES
from app.services.sql_validator import analyze_sql, SQLRiskLevel
from app.services.audit_logger import audit_log

router = APIRouter(prefix="/database", tags=["database"])
logger = logging.getLogger(__name__)

def require_admin(request: Request):
    pass

def _html_output(text: str) -> HTMLResponse:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed p-4 bg-gray-900 rounded-lg'>{escaped}</pre>")

def get_primary_keys(table_name: str) -> List[str]:
    inspector = inspect(engine)
    pks = inspector.get_pk_constraint(table_name).get('constrained_columns', [])
    if not pks:
        raise ValueError(f"Bảng '{table_name}' không có Primary Key, không thể xóa an toàn.")
    return pks

def get_all_tables_with_counts():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    results = []
    with engine.connect() as conn:
        for t in tables:
            try:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                results.append({"name": t, "count": count})
            except:
                pass
    results.sort(key=lambda x: x["name"])
    return results

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
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            return _html_output('<div class="text-sm text-red-500 p-4">Table không hợp lệ!</div>')

        columns_info = inspector.get_columns(table_name)
        column_names = [c['name'] for c in columns_info]
        pks = inspector.get_pk_constraint(table_name).get('constrained_columns', [])
        has_pk = len(pks) > 0

        order_clause = ""
        if pks:
            order_clause = f"ORDER BY {pks[0]} DESC"
        
        where_clause = ""
        params = {}
        if q.strip():
            search_clause = " OR ".join([f"CAST({col} AS TEXT) ILIKE :q" for col in column_names])
            where_clause = f"WHERE {search_clause}"
            params["q"] = f"%{q.strip()}%"

        with engine.connect() as conn:
            query = f"SELECT * FROM {table_name} {where_clause} {order_clause} LIMIT :limit"
            params["limit"] = limit
            rows_data = conn.execute(text(query), params).mappings().all()
            rows = [dict(r) for r in rows_data]

            count_query = f"SELECT COUNT(*) FROM {table_name} {where_clause}"
            total_rows = conn.execute(text(count_query), params).scalar()

        return templates.TemplateResponse(
            "fragments/syspanel/db_explorer.html",
            {
                "request": request,
                "table_name": table_name,
                "columns": column_names,
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


@router.get("/validate-sql")
def validate_sql_endpoint(sql: str = Query(...)):
    try:
        risk, normalized = analyze_sql(sql)
        return {"status": "success", "risk": risk.value, "normalized": normalized}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/execute-sql")
async def execute_sql(request: Request, db: Session = Depends(get_db)):
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
            
        ip = request.client.host if request.client else "unknown"
        user_id = 1 
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
    try:
        if not check_table_permission(table_name, "delete"):
            raise HTTPException(403, f"Bảng '{table_name}' không được phép xóa dữ liệu qua UI.")
            
        data = await request.json()
        pk_values = data.get("pk_values", {})
        
        pks = get_primary_keys(table_name)
        if not all(pk in pk_values for pk in pks):
            raise HTTPException(400, "Thiếu giá trị Primary Key để định danh bản ghi.")
            
        conditions = " AND ".join([f"{pk} = :{pk}" for pk in pks])
        
        query = text(f"DELETE FROM {table_name} WHERE {conditions}")
        result = db.execute(query, pk_values)
        db.commit()
        
        ip = request.client.host if request.client else "unknown"
        audit_log(user_id=1, action="delete_row", ip_address=ip, table=table_name, pk_values=pk_values, affected_rows=result.rowcount)
        
        return {"status": "success", "deleted": result.rowcount}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

@router.get("/export-csv")
def export_csv(table_name: str, q: str = "", db: Session = Depends(get_db)):
    try:
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            raise HTTPException(400, f"Bảng '{table_name}' không tồn tại.")

        def generate():
            columns = [c['name'] for c in inspector.get_columns(table_name)]
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_ALL)
            writer.writerow(columns)
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)
            
            where_clause = ""
            params = {}
            if q.strip():
                search_clause = " OR ".join([f"CAST({col} AS TEXT) ILIKE :q" for col in columns])
                where_clause = f"WHERE {search_clause}"
                params["q"] = f"%{q.strip()}%"
                
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {table_name} {where_clause}"), params)
                while True:
                    rows = result.fetchmany(1000)
                    if not rows:
                        break
                    for row in rows:
                        writer.writerow(row)
                    yield output.getvalue()
                    output.truncate(0)
                    output.seek(0)

        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={table_name}.csv"}
        )
    except Exception as e:
        raise HTTPException(500, f"Lỗi xuất file: {e}")
