import json

import pytest

from experiments.shopee_conversion_v2.database import ConversionDatabase
from experiments.shopee_conversion_v2.fixtures_factory import make_conversion
from experiments.shopee_conversion_v2.parser import parse_conversion_response
from experiments.shopee_conversion_v2.fixtures_factory import wrap_api_response


def _one(overrides=None):
    payload = wrap_api_response([make_conversion(**(overrides or {}))])
    return parse_conversion_response(payload).records[0]


class TestDatabaseMigration:
    def test_migrate_creates_tables(self, tmp_db: ConversionDatabase):
        conn = tmp_db.connect()
        try:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert "conversions" in names
        assert "sync_runs" in names
        assert "conversion_status_history" in names
        assert "attribution_matches" in names
        assert "schema_version" in names

    def test_migrate_idempotent(self, tmp_db: ConversionDatabase):
        tmp_db.migrate()
        assert tmp_db.count_conversions() == 0


class TestSyncRuns:
    def test_start_and_complete(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        tmp_db.complete_sync_run(run_id, {"total_raw": 1, "total_valid": 1, "total_errors": 0, "total_new": 1, "total_updated": 0, "total_unchanged": 0})
        runs = tmp_db.get_sync_runs()
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"
        assert runs[0]["total_new"] == 1

    def test_fail_sync_run(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        tmp_db.fail_sync_run(run_id, "Connection timeout")
        assert tmp_db.get_sync_runs()[0]["status"] == "failed"


class TestConversionUpsert:
    def test_insert_new(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        action, db_id = tmp_db.upsert_conversion(_one(), sync_run_id=run_id)
        assert action == "new"
        assert db_id > 0

    def test_duplicate_insert_unchanged(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        record = _one()
        action1, id1 = tmp_db.upsert_conversion(record, sync_run_id=run_id)
        action2, id2 = tmp_db.upsert_conversion(record, sync_run_id=run_id)
        assert action1 == "new"
        assert action2 == "unchanged"
        assert id1 == id2
        assert tmp_db.count_conversions() == 1

    def test_status_change_creates_history(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        tmp_db.upsert_conversion(_one(), sync_run_id=run_id)
        action, db_id = tmp_db.upsert_conversion(
            _one({"conversion_status": "2", "order_status": "SHIPPED"}),
            sync_run_id=run_id,
        )
        assert action == "updated"
        history = tmp_db.get_conversion_history(db_id)
        assert len(history) >= 2
        assert history[0]["change_type"] == "initial"
        assert history[1]["change_type"] == "status_change"
        assert history[1]["old_conversion_status"] == "1"
        assert history[1]["new_conversion_status"] == "2"

    def test_commission_change_creates_history(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        tmp_db.upsert_conversion(_one(), sync_run_id=run_id)
        action, db_id = tmp_db.upsert_conversion(_one({"affiliate_net_commission": 6000}), sync_run_id=run_id)
        assert action == "updated"
        history = tmp_db.get_conversion_history(db_id)
        change = next(item for item in history if item["change_type"] == "commission_change")
        assert change["old_affiliate_net_commission"] == 10000
        assert change["new_affiliate_net_commission"] == 6000

    def test_commission_reversed_to_zero(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        tmp_db.upsert_conversion(_one(), sync_run_id=run_id)
        action, db_id = tmp_db.upsert_conversion(
            _one({
                "conversion_status": "3",
                "order_status": "CANCELLED",
                "gross_commission": 0,
                "capped_commission": 0,
                "affiliate_net_commission": 0,
            }),
            sync_run_id=run_id,
        )
        assert action == "updated"
        conv = tmp_db.get_conversion("shopee_affiliate", "CONV_TEST_001") if False else tmp_db.get_conversion("shopee_affiliate", "CONV_SAMPLE_001")
        assert conv["affiliate_net_commission"] == 0
        assert conv["order_status_raw"] == "CANCELLED"
        assert conv["internal_status"] == "unknown"
        history = tmp_db.get_conversion_history(db_id)
        assert any(item["change_type"] == "both" for item in history)

    def test_missing_conversion_id_raises(self, tmp_db: ConversionDatabase):
        record = _one()
        record["conversion_id"] = None
        with pytest.raises(ValueError, match="conversion_id"):
            tmp_db.upsert_conversion(record)

    def test_multiple_conversions_same_sub_id(self, tmp_db: ConversionDatabase):
        run_id = tmp_db.start_sync_run("test", "conversion")
        for idx in range(3):
            action, _db_id = tmp_db.upsert_conversion(_one({"conversion_id": f"CONV_MULTI_{idx}"}), sync_run_id=run_id)
            assert action == "new"
        assert tmp_db.count_conversions() == 3

    def test_extra_fields_preserved(self, tmp_db: ConversionDatabase):
        record = _one()
        record["_extra_fields"] = {"unknown_field": "value"}
        tmp_db.upsert_conversion(record)
        conv = tmp_db.get_conversion("shopee_affiliate", "CONV_SAMPLE_001")
        extra = json.loads(conv["extra_fields_json"])
        assert extra["unknown_field"] == "value"

    def test_null_commission_stored(self, tmp_db: ConversionDatabase):
        tmp_db.upsert_conversion(_one({"gross_commission": None, "affiliate_net_commission": None}))
        conv = tmp_db.get_conversion("shopee_affiliate", "CONV_SAMPLE_001")
        assert conv["gross_commission"] is None
        assert conv["affiliate_net_commission"] is None

    def test_old_row_survives_unrelated_import(self, tmp_db: ConversionDatabase):
        tmp_db.upsert_conversion(_one({"conversion_id": "CONV_OLD_001"}))
        tmp_db.upsert_conversion(_one({"conversion_id": "CONV_OLD_002"}))
        assert tmp_db.get_conversion("shopee_affiliate", "CONV_OLD_001") is not None
        assert tmp_db.count_conversions() == 2


class TestDatabaseIndependence:
    def test_prototype_db_is_separate(self, tmp_db: ConversionDatabase, cashback_db_path):
        assert str(tmp_db.db_path) != str(cashback_db_path)
