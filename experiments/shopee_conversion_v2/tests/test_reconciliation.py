import pytest

from experiments.shopee_conversion_v2.fixtures_factory import make_conversion, wrap_api_response
from experiments.shopee_conversion_v2.parser import parse_conversion_response
from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader, ReconciliationEngine


def _store(tmp_db, records):
    payload = wrap_api_response(records)
    parsed = parse_conversion_response(payload)
    for record in parsed.records:
        tmp_db.upsert_conversion(record)


class TestCashbackDBReader:
    def test_verify_readonly(self, cashback_reader):
        assert cashback_reader.verify_readonly()

    def test_lookup_existing_sub_id(self, cashback_reader):
        results = cashback_reader.lookup_sub_id("G3lkg1JK")
        assert len(results) == 1
        assert results[0]["telegram_user_id"] == 111222333

    def test_lookup_nonexistent_sub_id(self, cashback_reader):
        assert cashback_reader.lookup_sub_id("zZzZzZzZ") == []

    def test_case_sensitive_lookup(self, cashback_reader):
        assert cashback_reader.lookup_sub_id("g3lkg1jk") == []

    def test_get_all_sub_ids(self, cashback_reader):
        all_ids = cashback_reader.get_all_sub_ids()
        assert "G3lkg1JK" in all_ids
        assert "6mnSXpbe" in all_ids

    def test_nonexistent_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            CashbackDBReader(tmp_path / "nonexistent.sqlite")


class TestReconciliationEngine:
    def test_matched_exact_sub_id(self, tmp_db, cashback_reader):
        _store(tmp_db, [make_conversion()])
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.matched == 1
        assert result.details[0]["telegram_user_id"] == 111222333
        assert result.details[0]["method"] == "exact_sub_id"

    def test_unmatched_no_sub_id(self, tmp_db, cashback_reader):
        _store(tmp_db, [make_conversion(conversion_id="CONV_NOSUB_001", sub_id=None)])
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.missing_sub_id == 1
        assert result.unmatched == 0
        assert result.details[0]["method"] == "no_sub_id"

    def test_unmatched_dash_sub_id(self, tmp_db, cashback_reader):
        _store(tmp_db, [make_conversion(conversion_id="CONV_DASH_001", sub_id="----")])
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.missing_sub_id == 1
        assert result.unmatched == 0
        assert result.details[0]["method"] == "dash_sub_id"

    def test_unmatched_unknown_sub_id(self, tmp_db, cashback_reader):
        _store(tmp_db, [make_conversion(conversion_id="CONV_UNKNOWN_001", sub_id="zZzZzZzZ")])
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.unmatched == 1
        assert result.details[0]["method"] == "sub_id_not_found"

    def test_case_mismatch_not_matched(self, tmp_db, cashback_reader):
        _store(tmp_db, [make_conversion(conversion_id="CONV_CASE_001", sub_id="g3lkg1jk")])
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.matched == 0
        assert result.details[0]["method"] == "sub_id_not_found"

    def test_multiple_conversions_same_sub_id(self, tmp_db, cashback_reader):
        records = [make_conversion(conversion_id=f"CONV_MULTI_{idx}") for idx in range(3)]
        _store(tmp_db, records)
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.matched == 3
        assert result.total == 3

    def test_no_cashback_reader(self, tmp_db):
        _store(tmp_db, [make_conversion()])
        result = ReconciliationEngine(tmp_db, None).reconcile_all()
        assert result.unmatched == 1
        assert result.details[0]["method"] == "no_cashback_db"

    def test_empty_conversions(self, tmp_db, cashback_reader):
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.total == 0

    def test_mixed_results(self, tmp_db, cashback_reader):
        _store(tmp_db, [
            make_conversion(conversion_id="C1", sub_id="G3lkg1JK"),
            make_conversion(conversion_id="C2", sub_id=None),
            make_conversion(conversion_id="C3", sub_id="----"),
            make_conversion(conversion_id="C4", sub_id="XXXXXXXX"),
            make_conversion(conversion_id="C5", sub_id="6mnSXpbe"),
        ])
        result = ReconciliationEngine(tmp_db, cashback_reader).reconcile_all()
        assert result.matched == 2
        assert result.unmatched == 1
        assert result.missing_sub_id == 2
        assert result.ambiguous == 0

    def test_ambiguous_when_duplicate_link_rows(self, tmp_db, tmp_path):
        import sqlite3

        db_path = tmp_path / "cashback_ambiguous.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE link_requests (
                id INTEGER PRIMARY KEY,
                telegram_user_id INTEGER,
                sub_id TEXT,
                item_id INTEGER,
                shop_id INTEGER,
                product_name TEXT,
                price_vnd INTEGER,
                estimated_commission INTEGER,
                estimated_cashback INTEGER,
                cashback_rate_percent INTEGER,
                link_status TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO link_requests VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?)
            """,
            [
                (1, 111222333, "G3lkg1JK", "created", "2026-10-22T01:00:00Z"),
                (2, 444555666, "G3lkg1JK", "created", "2026-10-22T02:00:00Z"),
            ],
        )
        conn.commit()
        conn.close()
        reader = CashbackDBReader(db_path)
        _store(tmp_db, [make_conversion(conversion_id="C_AMB")])
        result = ReconciliationEngine(tmp_db, reader).reconcile_all()
        assert result.ambiguous == 1
        assert result.details[0]["method"] == "multiple_link_requests"
        assert result.details[0]["telegram_user_id"] is None
