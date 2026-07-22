import sqlglot
from enum import Enum
from sqlglot import exp
from typing import List, Tuple


class SQLRiskLevel(Enum):
    SAFE = "safe"           # SELECT
    MODERATE = "moderate"   # INSERT, UPDATE, DELETE
    DANGEROUS = "dangerous" # DROP, TRUNCATE, ALTER, CREATE


# Statements that modify data but keep schema intact
MODERATE_STATEMENTS = {"insert", "update", "delete"}

# Statements that modify schema or permissions
DANGEROUS_STATEMENTS = {
    "drop", "truncate", "alter", "create",
    "grant", "revoke", "analyze", "vacuum",
}


def analyze_sql(raw_sql: str) -> Tuple[SQLRiskLevel, str, List[str], str]:
    """
    Parse AST for absolute validation.
    Returns (risk_level, normalized_sql, table_names, statement_type).
    Raises ValueError for invalid, multi-statement, or unsupported queries.
    """
    if not raw_sql.strip():
        raise ValueError("Câu lệnh SQL không được để trống.")

    try:
        # Runtime DB is PostgreSQL — parse with matching dialect.
        statements = sqlglot.parse(raw_sql, read="postgres")
    except sqlglot.errors.ParseError as e:
        raise ValueError(f"SQL không hợp lệ: {e}")

    if len(statements) > 1:
        raise ValueError("Chỉ cho phép thực thi một câu lệnh mỗi lần.")

    stmt = statements[0]
    if stmt is None:
        raise ValueError("Câu lệnh SQL không hợp lệ.")

    stmt_type = (stmt.key or "").lower()
    normalized_sql = stmt.sql(dialect="postgres")
    tables = sorted({
        (t.name or "").lower()
        for t in stmt.find_all(exp.Table)
        if t.name
    })

    if stmt_type in DANGEROUS_STATEMENTS:
        return SQLRiskLevel.DANGEROUS, normalized_sql, tables, stmt_type

    if stmt_type in MODERATE_STATEMENTS:
        return SQLRiskLevel.MODERATE, normalized_sql, tables, stmt_type

    if stmt_type == "select":
        return SQLRiskLevel.SAFE, normalized_sql, tables, stmt_type

    # Deny-by-default: unknown / unsupported statement types are blocked.
    raise ValueError(f"Loại câu lệnh không được hỗ trợ: {stmt_type or 'unknown'}")
