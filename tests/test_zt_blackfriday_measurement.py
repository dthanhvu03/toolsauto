"""Channel first-touch reports use temporary data and do not infer members or purchases."""
import importlib.util
import sqlite3
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "reports/zt-blackfriday-20261120/measure_trial.py"
SPEC = importlib.util.spec_from_file_location("bf_measurement", SOURCE)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)


def test_only_new_source_cohort_and_created_links_excluding_admins(tmp_path):
    path = tmp_path / "cash.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE telegram_users(telegram_user_id INTEGER,created_at TEXT);
            CREATE TABLE bot_state(key TEXT,value TEXT);
            CREATE TABLE link_requests(id INTEGER,telegram_user_id INTEGER,link_status TEXT,created_at TEXT);
            INSERT INTO telegram_users VALUES(1,'2026-11-20T02:00:00Z'),(2,'2026-11-20T02:00:00Z'),
              (3,'2026-11-20T02:00:00Z'),(4,'2026-11-19T02:00:00Z');
            INSERT INTO bot_state VALUES('src:1','zt_bf26_guide'),('src:2','zt_bf26_guide'),
              ('src:3','different'),('src:4','zt_bf26_guide');
            INSERT INTO link_requests VALUES(10,1,'created','2026-11-20T03:00:00Z'),
              (11,1,'failed','2026-11-20T03:01:00Z'),(12,2,'created','2026-11-20T03:00:00Z'),
              (13,3,'created','2026-11-20T03:00:00Z'),(14,4,'created','2026-11-20T03:00:00Z');
        """)
    before = path.read_bytes()
    report = trial.business(path, "zt_bf26_guide", "2026-11-20T01:00:00Z", "2026-11-20T04:00:00Z", (2,))
    assert report == {"status": "available", "new_customers": 1, "new_customers_created_link": 1,
                      "created_links": 1, "configured_exclusions": 1}
    assert path.read_bytes() == before


def test_missing_database_is_unavailable_not_zero_or_created(tmp_path):
    path = tmp_path / "missing.sqlite"
    result = trial.business(path, "zt_bf26_guide", "2026-11-20T01:00:00Z", "2026-11-20T04:00:00Z")
    assert result["status"] == "unavailable" and result["new_customers"] is None
    assert not path.exists()
