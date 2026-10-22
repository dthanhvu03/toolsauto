import json

from experiments.shopee_conversion_v2.fixtures_factory import load_fixture
from experiments.shopee_conversion_v2.parser import parse_conversion_response
from experiments.shopee_conversion_v2.pipeline import import_conversions
from experiments.shopee_conversion_v2.schema_map import check_live_conversion_schema


def _live(**overrides):
    payload = load_fixture("live_nested_sanitized")
    row = payload["data"]["list"][0]
    row.update(overrides)
    return payload


class TestLiveNestedParser:
    def test_reads_live_envelope_and_items(self):
        result = parse_conversion_response(load_fixture("live_nested_sanitized"), source_label="live_shape")
        assert result.error_count == 0
        assert result.valid_count == 1
        record = result.records[0]
        assert record["conversion_id"] == "inferred:AFF_SCOPE_001:CHK_LIVE_001:ORD_LIVE_001"
        assert record["sub_id"] == "----"
        assert record["order_status"] == "COMPLETED"
        assert record["checkout_status"] == "Waiting for payment"
        assert record["conversion_status"] == "2"
        assert record["affiliate_net_commission"] == 451000000
        assert record["item_commission"] == 155000000
        assert len(record["_items"]) == 2
        assert record["_extra_fields"]["identity_verified"] is False
        assert result.source_meta["api_total"] == 1

    def test_exact_utm_content_becomes_sub_id(self):
        payload = _live(utm_content="G3lkg1JK")
        record = parse_conversion_response(payload).records[0]
        assert record["sub_id"] == "G3lkg1JK"

    def test_case_sensitive_utm(self):
        payload = _live(utm_content="g3lkg1jk")
        assert parse_conversion_response(payload).records[0]["sub_id"] == "g3lkg1jk"

    def test_missing_utm_is_null_not_dash(self):
        payload = _live()
        del payload["data"]["list"][0]["utm_content"]
        assert parse_conversion_response(payload).records[0]["sub_id"] is None

    def test_schema_drift_on_unknown_key(self):
        payload = _live(brand_new_field="x")
        result = parse_conversion_response(payload)
        assert result.has_schema_drift

    def test_known_live_shape_has_no_drift(self):
        result = check_live_conversion_schema(load_fixture("live_nested_sanitized")["data"]["list"][0])
        assert result.is_valid
        assert not result.has_drift

    def test_two_orders_do_not_duplicate_checkout_commission(self):
        payload = load_fixture("live_nested_sanitized")
        row = payload["data"]["list"][0]
        second = json.loads(json.dumps(row["orders"][0]))
        second["order_id"] = "ORD_LIVE_002"
        row["orders"].append(second)
        records = parse_conversion_response(payload).records
        assert len(records) == 2
        assert records[0]["gross_commission"] == 205000000
        assert records[1]["gross_commission"] is None
        assert records[0]["_extra_fields"]["review_status"] == "needs_review"
        assert records[1]["conversion_id"] != records[0]["conversion_id"]


class TestLivePipeline:
    def test_import_reimport_and_items(self, tmp_db, cashback_reader):
        payload = load_fixture("live_nested_sanitized")
        payload["data"]["list"][0]["utm_content"] = "G3lkg1JK"
        first = import_conversions(payload, tmp_db, cashback_reader, source_label="live1")
        second = import_conversions(payload, tmp_db, cashback_reader, source_label="live2")
        assert first.total_new == 1
        assert second.total_unchanged == 1
        assert second.total_new == 0
        assert tmp_db.count_conversions() == 1
        conv = tmp_db.get_conversion("shopee_affiliate", "inferred:AFF_SCOPE_001:CHK_LIVE_001:ORD_LIVE_001")
        assert conv["internal_status"] == "unknown"
        assert len(tmp_db.get_items(conv["id"])) == 2
        assert first.reconciliation.matched == 1
        assert first.reconciliation.details[0]["method"] == "exact_sub_id"

    def test_negative_and_zero_commission_kept(self, tmp_db):
        payload = load_fixture("live_nested_sanitized")
        row = payload["data"]["list"][0]
        row["gross_commission"] = 0
        row["capped_commission"] = 0
        row["estimated_total_commission"] = -100000
        row["affiliate_net_commission"] = "-100000"
        row["orders"][0]["items"] = [row["orders"][0]["items"][1]]
        result = import_conversions(payload, tmp_db, source_label="neg", skip_reconciliation=True)
        assert result.total_new == 1
        conv = tmp_db.get_conversion("shopee_affiliate", "inferred:AFF_SCOPE_001:CHK_LIVE_001:ORD_LIVE_001")
        assert conv["gross_commission"] == 0
        assert conv["affiliate_net_commission"] == -100000
        assert conv["item_commission"] == -50000000

    def test_flat_fixture_still_imports(self, tmp_db):
        from experiments.shopee_conversion_v2.fixtures_factory import fixture_single_matched

        result = import_conversions(fixture_single_matched(), tmp_db, source_label="flat", skip_reconciliation=True)
        assert result.total_new == 1
        assert tmp_db.get_conversion("shopee_affiliate", "CONV_SAMPLE_001")["sub_id"] == "G3lkg1JK"
