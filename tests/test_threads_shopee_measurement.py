"""Campaign measurement distinguishes imported data, missing values and missing source."""

import importlib.util
import sqlite3
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "reports/threads-shopee-20261119/measure_trial.py"
SPEC = importlib.util.spec_from_file_location("threads_trial_measurement", SOURCE)
measurement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measurement)


def manifest():
    return {"attempt_started_at": "2026-11-19T17:06:10+00:00", "post_url": "https://threads.com/trial",
            "products": [{"sub_id": "TH180A01", "item_id": 42, "name": "Chân váy"}]}


def test_import_before_publication_is_not_live_engagement_and_missing_net_stays_unknown(tmp_path):
    path = tmp_path / "campaign.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE shopee_clicks(sub_id TEXT,click_time TEXT);
            CREATE TABLE shopee_conversions(sub_id TEXT,order_sn TEXT,gross_commission_vnd INTEGER,
              net_commission_vnd INTEGER,order_status TEXT,conversion_status TEXT,
              validation_status TEXT,settlement_status TEXT);
            CREATE TABLE shopee_sync_runs(id INTEGER,status TEXT,started_at TEXT,completed_at TEXT,
              window_start TEXT,window_end TEXT);
            INSERT INTO shopee_clicks VALUES('another1','2026-11-19T18:00:00Z');
            INSERT INTO shopee_conversions VALUES('TH180A01','private_order',1000,NULL,'PENDING',
              'PENDING','UNKNOWN',NULL);
            INSERT INTO shopee_conversions VALUES('another1','unrelated',9000,8000,'COMPLETE',
              'APPROVED','APPROVED','SETTLED');
            INSERT INTO shopee_sync_runs VALUES(1,'success','2026-11-19T13:45:33Z',
              '2026-11-19T13:45:47Z','2026-10-20T13:45:34Z','2026-11-19T13:45:34Z');
        """)
    before = path.read_bytes()
    result = measurement.measure(path, manifest())
    assert path.read_bytes() == before
    assert result["status"] == "available" and result["successful_import_completed_after_attempt"] is False
    assert result["successful_import_window_covers_attempt"] is False
    row = result["products"][0]
    assert row["imported_click_records"] == 0 and row["conversion_rows"] == 1
    assert row["gross_commission_recorded_vnd"] == 1000
    assert row["net_commission_recorded_vnd"] is None and row["rows_missing_net_commission"] == 1
    assert result["cash_received_vnd"] is None and result["impressions"] is None
    assert "private_order" not in str(result) and "unrelated" not in str(result)


def test_missing_source_is_unavailable_not_zero_and_is_not_created(tmp_path):
    path = tmp_path / "absent.sqlite"
    result = measurement.measure(path, manifest())
    assert result["status"] == "unavailable" and result["products"] == []
    assert not path.exists() and result["sync_requested"] is False
