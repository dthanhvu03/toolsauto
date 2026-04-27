from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from app.database.core import engine
import csv
import io
import logging
from app.services.db_acl import check_table_permission
from app.services.sql_validator import analyze_sql, SQLRiskLevel
from app.services.audit_logger import audit_log

logger = logging.getLogger(__name__)

class DatabaseService:
    @staticmethod
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

    @staticmethod
    def get_table_data(table_name: str, limit: int = 50, q: str = ""):
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            return None

        columns_info = inspector.get_columns(table_name)
        column_names = [c['name'] for c in columns_info]
        pks = inspector.get_pk_constraint(table_name).get('constrained_columns', [])
        
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

        return {
            "columns": column_names,
            "rows": rows,
            "total_rows": total_rows,
            "has_pk": len(pks) > 0,
            "pks": pks
        }

    @staticmethod
    def execute_sql(db: Session, raw_sql: str, confirmed: bool, client_host: str):
        risk, normalized_sql = analyze_sql(raw_sql)
        
        if risk == SQLRiskLevel.DANGEROUS:
            return {"status": "error", "message": "Câu lệnh này bị chặn hoàn toàn vì lý do an toàn (DANGEROUS)."}
            
        if risk == SQLRiskLevel.MODERATE and not confirmed:
            return {
                "status": "require_confirm", 
                "risk": risk.value, 
                "normalized": normalized_sql,
                "message": "Đây là câu lệnh thay đổi dữ liệu. Vui lòng xác nhận để thực thi."
            }
            
        user_id = 1 
        is_select = risk == SQLRiskLevel.SAFE
        
        try:
            result = db.execute(text(normalized_sql))
            
            audit_log(
                user_id=user_id,
                action="execute_sql",
                ip_address=client_host,
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

    @staticmethod
    def delete_row(db: Session, table_name: str, pk_values: dict, client_host: str):
        if not check_table_permission(table_name, "delete"):
            raise ValueError(f"Bảng '{table_name}' không được phép xóa dữ liệu qua UI.")
            
        inspector = inspect(engine)
        pks = inspector.get_pk_constraint(table_name).get('constrained_columns', [])
        if not pks:
            raise ValueError(f"Bảng '{table_name}' không có Primary Key, không thể xóa an toàn.")
            
        if not all(pk in pk_values for pk in pks):
            raise ValueError("Thiếu giá trị Primary Key để định danh bản ghi.")
            
        conditions = " AND ".join([f"{pk} = :{pk}" for pk in pks])
        
        try:
            query = text(f"DELETE FROM {table_name} WHERE {conditions}")
            result = db.execute(query, pk_values)
            db.commit()
            
            audit_log(user_id=1, action="delete_row", ip_address=client_host, table=table_name, pk_values=pk_values, affected_rows=result.rowcount)
            return result.rowcount
        except Exception as e:
            db.rollback()
            raise e

    @staticmethod
    def get_csv_generator(table_name: str, q: str = ""):
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            raise ValueError(f"Bảng '{table_name}' không tồn tại.")

        columns = [c['name'] for c in inspector.get_columns(table_name)]
        
        where_clause = ""
        params = {}
        if q.strip():
            search_clause = " OR ".join([f"CAST({col} AS TEXT) ILIKE :q" for col in columns])
            where_clause = f"WHERE {search_clause}"
            params["q"] = f"%{q.strip()}%"

        def generate():
            output = io.StringIO()
            writer = csv.writer(output, quoting=csv.QUOTE_ALL)
            writer.writerow(columns)
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)
            
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
        
        return generate
