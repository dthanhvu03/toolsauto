import sqlglot
from enum import Enum
from typing import Tuple

class SQLRiskLevel(Enum):
    SAFE = "safe"           # SELECT
    MODERATE = "moderate"   # INSERT, UPDATE, DELETE
    DANGEROUS = "dangerous" # DROP, TRUNCATE, ALTER, CREATE

# Statements that modify data but keep schema intact
MODERATE_STATEMENTS = {"insert", "update", "delete"}

# Statements that modify schema or permissions
DANGEROUS_STATEMENTS = {
    "drop", "truncate", "alter", "create", 
    "grant", "revoke", "analyze", "vacuum"
}

def analyze_sql(raw_sql: str) -> Tuple[SQLRiskLevel, str]:
    """
    Parse AST for absolute validation. 
    Returns (risk_level, normalized_sql).
    Raises ValueError for invalid or multi-statement queries.
    """
    if not raw_sql.strip():
        raise ValueError("Câu lệnh SQL không được để trống.")

    try:
        # Use sqlite dialect since the project uses SQLite
        statements = sqlglot.parse(raw_sql, read="sqlite")
    except sqlglot.errors.ParseError as e:
        raise ValueError(f"SQL không hợp lệ: {e}")

    if len(statements) > 1:
        raise ValueError("Chỉ cho phép thực thi một câu lệnh mỗi lần.")

    stmt = statements[0]
    
    # Identify statement type from AST node
    # sqlglot expression types are subclasses of Expression
    stmt_type = stmt.key
    
    normalized_sql = stmt.sql(dialect="sqlite")

    if any(danger in stmt_type for danger in DANGEROUS_STATEMENTS):
        return SQLRiskLevel.DANGEROUS, normalized_sql

    if any(mod in stmt_type for mod in MODERATE_STATEMENTS):
        return SQLRiskLevel.MODERATE, normalized_sql

    # Default to SAFE if it's a SELECT or other non-modifying statement
    return SQLRiskLevel.SAFE, normalized_sql
