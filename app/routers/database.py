from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import logging

from app.main_templates import templates
from app.database.core import get_db
from sqlalchemy.orm import Session

from app.services.database_service import DatabaseService

router = APIRouter(prefix="/database", tags=["database"])
logger = logging.getLogger(__name__)

def _html_output(text: str) -> HTMLResponse:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"<pre class='text-sm text-green-400 font-mono whitespace-pre-wrap leading-relaxed p-4 bg-gray-900 rounded-lg'>{escaped}</pre>")

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def get_database(request: Request):
    tables_info = DatabaseService.get_all_tables_with_counts()
    return templates.TemplateResponse("pages/database.html", {
        "request": request, 
        "tables_info": tables_info,
        "active_tab": "database"
    })

@router.get("/fragments/db-explorer", response_class=HTMLResponse)
def frag_db_explorer(request: Request, table_name: str = None, limit: int = 50, q: str = ""):
    if not table_name:
        return _html_output('<div class="flex flex-col items-center justify-center p-12 text-gray-400">...</div>')

    data = DatabaseService.get_table_data(table_name, limit, q)
    if not data:
        return _html_output('<div class="text-sm text-red-500 p-4">Table không hợp lệ!</div>')

    return templates.TemplateResponse(
        "fragments/syspanel/db_explorer.html",
        {
            "request": request,
            "table_name": table_name,
            **data,
            "limit": limit,
            "q": q
        }
    )

@router.post("/execute-sql")
async def execute_sql(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        raw_sql = data.get("sql", "")
        confirmed = data.get("confirmed", False)
        ip = request.client.host if request.client else "unknown"
        
        return DatabaseService.execute_sql(db, raw_sql, confirmed, ip)
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/row")
async def delete_row(request: Request, table_name: str, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        pk_values = data.get("pk_values", {})
        ip = request.client.host if request.client else "unknown"
        
        count = DatabaseService.delete_row(db, table_name, pk_values, ip)
        return {"status": "success", "deleted": count}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/export-csv")
def export_csv(table_name: str, q: str = "", db: Session = Depends(get_db)):
    try:
        gen = DatabaseService.get_csv_generator(table_name, q)
        return StreamingResponse(
            gen(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={table_name}.csv"}
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Lỗi xuất file: {e}")
