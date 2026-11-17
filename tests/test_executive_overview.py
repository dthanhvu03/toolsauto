"""Executive dashboard reads real fixture schemas and keeps unavailable sources separate."""

import sqlite3
from datetime import datetime, timezone

import pytest

from app.core.database.models import StudioProject, StudioTask
from app.platform.admin_api import executive
from tests.test_admin_api_lists import _client
from tests.test_bot_users import STORE_BUYER, _cashback, _store


def test_executive_aggregates_and_read_only_store(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    bot = _cashback(tmp_path)
    store_path = _store(tmp_path, now)
    threads_path = tmp_path / "threads.sqlite"
    with sqlite3.connect(threads_path) as conn:
        conn.execute("CREATE TABLE growth_posts (status TEXT)")
        conn.executemany("INSERT INTO growth_posts VALUES (?)", [("posted",), ("posted",), ("pending",)])
    monkeypatch.setenv("CASHBACK_DB_PATH", str(bot.repo.path))
    monkeypatch.setenv("STORE_DB_PATH", str(store_path))
    monkeypatch.setenv("STORE_ADMIN_IDS", "99999")
    monkeypatch.setattr(executive, "THREADS_DB_PATH", threads_path)
    engine, factory, client = _client(tmp_path)
    try:
        with factory() as db:
            db.add(StudioProject(spec={}, status="REVIEW"))
            db.add(StudioTask(flow="upload", stage="render", status="QUEUED"))
            db.commit()
        before = [path.stat().st_mtime_ns for path in (store_path, threads_path)]
        response = client.get("/api/admin/executive")
        assert response.status_code == 200
        data = response.json()
        assert data["errors"] == {}
        assert data["threads"]["counts"] == {"pending": 1, "posted": 2}
        assert data["studio"]["projects"] == {"REVIEW": 1}
        assert data["studio"]["tasks"] == {"QUEUED": 1}
        assert data["store"]["revenue"] == 1100
        assert "net_commission" in data["cashback"]
        assert [path.stat().st_mtime_ns for path in (store_path, threads_path)] == before
        with executive.ReadOnlyStore(str(store_path))._read() as conn:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("DELETE FROM users")

        monkeypatch.setenv("STORE_ADMIN_IDS", str(STORE_BUYER))
        assert client.get("/api/admin/executive").json()["store"]["revenue"] == 0
        monkeypatch.setenv("STORE_DB_PATH", str(tmp_path / "missing.sqlite"))
        partial = client.get("/api/admin/executive").json()
        assert partial["store"] is None and "store" in partial["errors"]
        assert partial["threads"] and partial["studio"] and partial["cashback"]
        assert not (tmp_path / "missing.sqlite").exists()
    finally:
        engine.dispose()
