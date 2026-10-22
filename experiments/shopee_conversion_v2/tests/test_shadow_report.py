import hashlib
import json
from pathlib import Path

from experiments.shopee_conversion_v2.fixtures_factory import load_fixture
from experiments.shopee_conversion_v2.pipeline import import_click_snapshot, import_conversions
from experiments.shopee_conversion_v2.shadow_report import build_shadow_report, dataset_class


def _clicks():
    return load_fixture("clicks_poc04_summary")


class TestDatasetClass:
    def test_live_sanitized_stays_separate_from_synthetic_and_click_summary(self):
        assert dataset_class("live_sanitized:poc07") == "live_sanitized"
        assert dataset_class("live_verified:poc04") == "live_verified_summary"
        assert dataset_class("synthetic:live_nested_sanitized") == "synthetic"


class TestShadowClicks:
    def test_click_import_does_not_create_conversion(self, tmp_db, cashback_reader):
        first = import_click_snapshot(_clicks(), tmp_db, "live_verified:poc04", "live_verified_summary")
        second = import_click_snapshot(_clicks(), tmp_db, "live_verified:poc04", "live_verified_summary")
        assert first["new"] == 5
        assert first["created_conversions"] == 0
        assert second["unchanged"] == 5
        assert tmp_db.count_conversions() == 0
        report = build_shadow_report(tmp_db, cashback_reader)
        assert report["clicks"]["total"] == 5
        assert report["clicks"]["missing_sub_id"] == 3
        assert report["clicks"]["conversions_created_from_clicks"] == 0
        assert report["payable_vnd"] is None

    def test_known_sub_ids_match_real_cashback_file(self, tmp_db):
        live = Path("/home/vu/toolsauto/data/cashback.sqlite")
        if not live.exists():
            return
        before = hashlib.md5(live.read_bytes()).hexdigest()
        from experiments.shopee_conversion_v2.reconciliation import CashbackDBReader

        reader = CashbackDBReader(live)
        import_click_snapshot(_clicks(), tmp_db, "live_verified:poc04", "live_verified_summary")
        report = build_shadow_report(tmp_db, reader)
        assert report["clicks"]["matched"] == 2
        assert hashlib.md5(live.read_bytes()).hexdigest() == before


class TestShadowSnapshots:
    def test_same_snapshot_twice_and_missing_old_row(self, tmp_db, cashback_reader):
        payload = load_fixture("live_nested_sanitized")
        payload["data"]["list"][0]["utm_content"] = "G3lkg1JK"
        first = import_conversions(payload, tmp_db, cashback_reader, source_label="synthetic:snap1")
        second = import_conversions(payload, tmp_db, cashback_reader, source_label="synthetic:snap2")
        assert first.total_new == 1
        assert second.total_unchanged == 1
        shrunk = json.loads(json.dumps(payload))
        shrunk["data"]["list"] = []
        import_conversions(shrunk, tmp_db, cashback_reader, source_label="synthetic:snap3")
        assert tmp_db.count_conversions() == 1
        report = build_shadow_report(tmp_db, cashback_reader)
        assert report["conversions"]["matched"] == 1
        assert report["conversions"]["matched_internal_status_unknown"] == 1
        assert report["duplicate_rows_prevented"] >= 1
        money = report["money_by_dataset"]["synthetic"]
        assert money["estimated_commission_vnd"] == "4510"
        assert money["reported_commission_vnd"] == "4510"
        assert money["platform_component_vnd"] == "2050"
        assert money["payable_vnd"] is None
        assert "live_verified_summary" not in report["money_by_dataset"]

    def test_commission_to_zero_is_history(self, tmp_db):
        payload = load_fixture("live_nested_sanitized")
        import_conversions(payload, tmp_db, source_label="synthetic:before", skip_reconciliation=True)
        payload["data"]["list"][0]["gross_commission"] = 0
        payload["data"]["list"][0]["estimated_total_commission"] = 0
        payload["data"]["list"][0]["affiliate_net_commission"] = "0"
        updated = import_conversions(payload, tmp_db, source_label="synthetic:after", skip_reconciliation=True)
        assert updated.total_updated == 1
        report = build_shadow_report(tmp_db, None)
        assert report["history_changes"] >= 1
        assert report["money_by_dataset"]["synthetic"]["estimated_commission_vnd"] == "0"

    def test_quarantine_then_valid_snapshot_keeps_both(self, tmp_db):
        payload = load_fixture("live_nested_sanitized")
        del payload["data"]["list"][0]["affiliate_id"]
        blocked = import_conversions(payload, tmp_db, source_label="synthetic:bad", skip_reconciliation=True)
        assert blocked.total_quarantined == 1
        recovered = load_fixture("live_nested_sanitized")
        imported = import_conversions(recovered, tmp_db, source_label="synthetic:good", skip_reconciliation=True)
        assert imported.total_new == 1
        assert tmp_db.count_quarantine() == 1
        report = build_shadow_report(tmp_db, None)
        assert report["quarantine"]["count"] == 1
        assert report["quarantine"]["reasons"]["missing_affiliate_id"] == 1
        assert report["conversions"]["total"] == 1

    def test_schema_drift_is_noted(self, tmp_db):
        payload = load_fixture("live_nested_sanitized")
        payload["data"]["list"][0]["brand_new_field"] = "x"
        result = import_conversions(payload, tmp_db, source_label="synthetic:drift", skip_reconciliation=True)
        assert result.parse_result.has_schema_drift
        report = build_shadow_report(tmp_db, None)
        assert report["schema_or_identity_runs"] == 1

    def test_duplicate_identity_is_not_summed_twice(self, tmp_db):
        payload = load_fixture("live_nested_sanitized")
        payload["data"]["list"].append(json.loads(json.dumps(payload["data"]["list"][0])))
        import_conversions(payload, tmp_db, source_label="synthetic:dup", skip_reconciliation=True)
        report = build_shadow_report(tmp_db, None)
        assert report["conversions"]["total"] == 1
        assert report["quarantine"]["count"] == 1
        assert report["money_by_dataset"]["synthetic"]["estimated_commission_vnd"] == "4510"
