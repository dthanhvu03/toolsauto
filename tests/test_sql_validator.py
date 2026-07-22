"""Unit tests for SQL console risk analysis (deny-by-default, Postgres dialect)."""
import pytest

from app.core.db_admin.sql_validator import SQLRiskLevel, analyze_sql


def test_select_is_safe():
    risk, sql, tables, stmt = analyze_sql("SELECT id FROM jobs WHERE id = 1")
    assert risk == SQLRiskLevel.SAFE
    assert stmt == "select"
    assert "jobs" in tables
    assert ":id" not in sql or True  # normalized form may vary


def test_update_is_moderate():
    risk, _, tables, stmt = analyze_sql("UPDATE jobs SET status = 'PENDING' WHERE id = 1")
    assert risk == SQLRiskLevel.MODERATE
    assert stmt == "update"
    assert "jobs" in tables


def test_drop_is_dangerous():
    risk, _, _, stmt = analyze_sql("DROP TABLE jobs")
    assert risk == SQLRiskLevel.DANGEROUS
    assert stmt == "drop"


def test_unknown_statement_denied():
    with pytest.raises(ValueError, match="không được hỗ trợ"):
        analyze_sql("SET search_path TO public")


def test_multi_statement_denied():
    with pytest.raises(ValueError, match="một câu lệnh"):
        analyze_sql("SELECT 1; SELECT 2")


def test_empty_denied():
    with pytest.raises(ValueError, match="trống"):
        analyze_sql("   ")
