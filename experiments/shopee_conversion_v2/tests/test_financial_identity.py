import json
from decimal import Decimal

from experiments.shopee_conversion_v2.fixtures_factory import load_fixture
from experiments.shopee_conversion_v2.money import live_raw_to_vnd, payable_vnd
from experiments.shopee_conversion_v2.parser import parse_conversion_response
from experiments.shopee_conversion_v2.pipeline import import_conversions


LIVE_ID = "inferred:AFF_SCOPE_001:CHK_LIVE_001:ORD_LIVE_001"


def _row():
    return load_fixture("live_nested_sanitized")


class TestVerifiedMoney:
    def test_dashboard_scale_on_the_observed_order(self):
        assert live_raw_to_vnd(8200000000) == Decimal("82000")
        assert live_raw_to_vnd(205000000) == Decimal("2050")
        assert live_raw_to_vnd(246000000) == Decimal("2460")
        assert live_raw_to_vnd(451000000) == Decimal("4510")
        assert Decimal("2050") + Decimal("2460") == Decimal("4510")
        assert payable_vnd() is None

    def test_zero_and_negative_vnd(self):
        assert live_raw_to_vnd(0) == Decimal("0")
        assert live_raw_to_vnd("-100000") == Decimal("-1")

    def test_live_record_keeps_raw_and_marks_components(self):
        record = parse_conversion_response(_row()).records[0]
        extra = record["_extra_fields"]
        assert record["gross_commission"] == 205000000
        assert extra["gross_vnd"] == "2050"
        assert extra["estimated_vnd"] == "4510"
        assert extra["affiliate_net_vnd"] == "4510"
        assert extra["do_not_sum_components"] is True
        assert extra["payable_vnd"] is None
        assert extra["status_conflict"] is True
        assert extra["identity_official"] is False


class TestIdentityScope:
    def test_same_order_id_stays_separate_per_affiliate(self, tmp_db):
        first = _row()
        second = _row()
        second["data"]["list"][0]["affiliate_id"] = "AFF_SCOPE_002"
        import_conversions(first, tmp_db, source_label="a", skip_reconciliation=True)
        import_conversions(second, tmp_db, source_label="b", skip_reconciliation=True)
        assert tmp_db.count_conversions() == 2
        assert tmp_db.get_conversion("shopee_affiliate", LIVE_ID) is not None
        assert tmp_db.get_conversion(
            "shopee_affiliate", "inferred:AFF_SCOPE_002:CHK_LIVE_001:ORD_LIVE_001"
        ) is not None

    def test_missing_affiliate_is_quarantined(self, tmp_db):
        payload = _row()
        del payload["data"]["list"][0]["affiliate_id"]
        result = import_conversions(payload, tmp_db, source_label="q", skip_reconciliation=True)
        again = import_conversions(payload, tmp_db, source_label="q2", skip_reconciliation=True)
        assert result.total_new == 0
        assert result.total_quarantined == 1
        assert again.total_quarantined == 0
        assert tmp_db.count_conversions() == 0
        assert tmp_db.count_quarantine() == 1

    def test_duplicate_identity_does_not_merge(self, tmp_db):
        payload = _row()
        payload["data"]["list"].append(json.loads(json.dumps(payload["data"]["list"][0])))
        result = import_conversions(payload, tmp_db, source_label="dup", skip_reconciliation=True)
        assert result.total_new == 1
        assert tmp_db.count_conversions() == 1
        assert tmp_db.count_quarantine() == 1

    def test_missing_order_id_is_quarantined(self, tmp_db):
        payload = _row()
        payload["data"]["list"][0]["orders"][0]["order_id"] = ""
        result = import_conversions(payload, tmp_db, source_label="noid", skip_reconciliation=True)
        assert result.total_new == 0
        assert tmp_db.count_quarantine() == 1

    def test_status_conflict_stays_unknown(self, tmp_db):
        result = import_conversions(_row(), tmp_db, source_label="st", skip_reconciliation=True)
        assert result.total_new == 1
        conv = tmp_db.get_conversion("shopee_affiliate", LIVE_ID)
        assert conv["order_status_raw"] == "COMPLETED"
        assert conv["checkout_status_raw"] == "Waiting for payment"
        assert conv["internal_status"] == "unknown"

    def test_commission_change_is_history_not_a_second_row(self, tmp_db):
        payload = _row()
        import_conversions(payload, tmp_db, source_label="c1", skip_reconciliation=True)
        payload["data"]["list"][0]["gross_commission"] = 0
        payload["data"]["list"][0]["conversion_status"] = 3
        second = import_conversions(payload, tmp_db, source_label="c2", skip_reconciliation=True)
        assert second.total_updated == 1
        assert tmp_db.count_conversions() == 1
        conv = tmp_db.get_conversion("shopee_affiliate", LIVE_ID)
        assert conv["gross_commission"] == 0
        assert conv["conversion_status_raw"] == "3"
        assert conv["internal_status"] == "unknown"
        assert len(tmp_db.get_conversion_history(conv["id"])) == 2
