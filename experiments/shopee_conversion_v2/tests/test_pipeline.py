import hashlib
from pathlib import Path

from experiments.shopee_conversion_v2.fixtures_factory import (
    fixture_duplicate_import_batch,
    fixture_empty,
    fixture_missing_required_fields,
    fixture_single_matched,
    fixture_single_unmatched_no_sub_id,
    fixture_unknown_fields,
    make_conversion,
    wrap_api_response,
)
from experiments.shopee_conversion_v2.pipeline import import_conversions


class TestPipelineEmpty:
    def test_empty_response(self, tmp_db):
        result = import_conversions(fixture_empty(), tmp_db, source_label="test_empty", skip_reconciliation=True)
        assert result.total_new == 0
        assert tmp_db.count_conversions() == 0


class TestPipelineSingleConversion:
    def test_single_matched(self, tmp_db, cashback_reader):
        result = import_conversions(fixture_single_matched(), tmp_db, cashback_reader, source_label="test_single")
        assert result.total_new == 1
        assert result.reconciliation.matched == 1

    def test_single_no_sub_id(self, tmp_db, cashback_reader):
        result = import_conversions(fixture_single_unmatched_no_sub_id(), tmp_db, cashback_reader, source_label="test_nosub")
        assert result.reconciliation.missing_sub_id == 1
        assert result.reconciliation.details[0]["method"] == "no_sub_id"


class TestPipelineIdempotency:
    def test_duplicate_import_no_duplicates(self, tmp_db):
        payload = fixture_duplicate_import_batch()
        result1 = import_conversions(payload, tmp_db, source_label="batch1", skip_reconciliation=True)
        result2 = import_conversions(payload, tmp_db, source_label="batch2", skip_reconciliation=True)
        assert result1.total_new == 1
        assert result2.total_unchanged == 1
        assert result2.total_new == 0
        assert tmp_db.count_conversions() == 1

    def test_triple_import(self, tmp_db):
        payload = fixture_single_matched()
        for idx in range(3):
            import_conversions(payload, tmp_db, source_label=f"run_{idx}", skip_reconciliation=True)
        assert tmp_db.count_conversions() == 1


class TestPipelineStatusChange:
    def test_status_change_updates_not_creates(self, tmp_db):
        first = wrap_api_response([make_conversion(conversion_id="CONV_SC_001", conversion_status="1", order_status="PENDING")])
        second = wrap_api_response([make_conversion(conversion_id="CONV_SC_001", conversion_status="2", order_status="COMPLETED")])
        result1 = import_conversions(first, tmp_db, source_label="run1", skip_reconciliation=True)
        result2 = import_conversions(second, tmp_db, source_label="run2", skip_reconciliation=True)
        assert result1.total_new == 1
        assert result2.total_updated == 1
        assert tmp_db.count_conversions() == 1
        conv = tmp_db.get_conversion("shopee_affiliate", "CONV_SC_001")
        history = tmp_db.get_conversion_history(conv["id"])
        assert len(history) >= 2
        assert history[-1]["old_order_status"] == "PENDING"
        assert history[-1]["new_order_status"] == "COMPLETED"


class TestPipelineCommissionChange:
    def test_commission_reduced(self, tmp_db):
        first = wrap_api_response([make_conversion(conversion_id="CONV_COMM_001", affiliate_net_commission=10000, capped_commission=12000)])
        second = wrap_api_response([make_conversion(conversion_id="CONV_COMM_001", affiliate_net_commission=6000, capped_commission=8000)])
        import_conversions(first, tmp_db, source_label="run1", skip_reconciliation=True)
        result2 = import_conversions(second, tmp_db, source_label="run2", skip_reconciliation=True)
        assert result2.total_updated == 1
        conv = tmp_db.get_conversion("shopee_affiliate", "CONV_COMM_001")
        assert conv["affiliate_net_commission"] == 6000
        assert conv["capped_commission"] == 8000
        assert tmp_db.count_conversions() == 1

    def test_commission_reversed_to_zero(self, tmp_db):
        first = wrap_api_response([make_conversion(conversion_id="CONV_REV_001")])
        second = wrap_api_response([
            make_conversion(
                conversion_id="CONV_REV_001",
                conversion_status="3",
                order_status="CANCELLED",
                gross_commission=0,
                capped_commission=0,
                estimated_total_commission=0,
                affiliate_net_commission=0,
                item_commission=0,
            )
        ])
        import_conversions(first, tmp_db, source_label="run1", skip_reconciliation=True)
        result2 = import_conversions(second, tmp_db, source_label="run2", skip_reconciliation=True)
        assert result2.total_updated == 1
        conv = tmp_db.get_conversion("shopee_affiliate", "CONV_REV_001")
        assert conv["affiliate_net_commission"] == 0
        assert conv["order_status_raw"] == "CANCELLED"
        history = tmp_db.get_conversion_history(conv["id"])
        assert history[-1]["new_affiliate_net_commission"] == 0


class TestPipelineOldConversionsNotLost:
    def test_old_conversion_not_lost(self, tmp_db):
        first = wrap_api_response([
            make_conversion(conversion_id="CONV_OLD_001"),
            make_conversion(conversion_id="CONV_OLD_002"),
        ])
        second = wrap_api_response([make_conversion(conversion_id="CONV_OLD_002", order_status="SHIPPED", conversion_status="2")])
        import_conversions(first, tmp_db, source_label="run1", skip_reconciliation=True)
        import_conversions(second, tmp_db, source_label="run2", skip_reconciliation=True)
        assert tmp_db.count_conversions() == 2
        assert tmp_db.get_conversion("shopee_affiliate", "CONV_OLD_001")["order_status_raw"] == "COMPLETED"


class TestPipelineSchemaIssues:
    def test_unknown_fields_logged(self, tmp_db):
        result = import_conversions(fixture_unknown_fields(), tmp_db, source_label="test_drift", skip_reconciliation=True)
        assert result.parse_result.has_schema_drift
        assert result.total_new == 1

    def test_missing_required_fields(self, tmp_db):
        result = import_conversions(fixture_missing_required_fields(), tmp_db, source_label="test_missing", skip_reconciliation=True)
        assert result.total_errors >= 1
        assert tmp_db.count_conversions() == 0


class TestPipelineSyncRunTracking:
    def test_sync_runs_recorded(self, tmp_db):
        import_conversions(fixture_single_matched(), tmp_db, source_label="test_sync", skip_reconciliation=True)
        runs = tmp_db.get_sync_runs()
        assert len(runs) == 1
        assert runs[0]["source"] == "test_sync"
        assert runs[0]["status"] == "completed"
        assert runs[0]["total_new"] == 1


class TestProductionDBSafety:
    def test_production_db_not_modified(self, tmp_db, cashback_reader, cashback_db_path: Path):
        digest_before = hashlib.md5(cashback_db_path.read_bytes()).hexdigest()
        import_conversions(fixture_single_matched(), tmp_db, cashback_reader, source_label="test_safe")
        digest_after = hashlib.md5(cashback_db_path.read_bytes()).hexdigest()
        assert digest_before == digest_after

    def test_live_cashback_file_unchanged_when_present(self, tmp_db):
        live = Path("/home/vu/toolsauto/data/cashback.sqlite")
        if not live.exists():
            return
        digest_before = hashlib.md5(live.read_bytes()).hexdigest()
        from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader

        reader = CashbackDBReader(live)
        assert reader.verify_readonly()
        import_conversions(fixture_single_matched(), tmp_db, reader, source_label="live_readonly_probe")
        digest_after = hashlib.md5(live.read_bytes()).hexdigest()
        assert digest_before == digest_after
        matched = [item for item in tmp_db.get_all_attributions() if item["match_status"] == "matched"]
        assert matched
        assert matched[0]["sub_id"] == "G3lkg1JK"
