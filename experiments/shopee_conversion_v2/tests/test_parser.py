from experiments.shopee_conversion_v2.fixtures_factory import (
    fixture_clicks_dash_sub_id,
    fixture_clicks_with_sub_id,
    fixture_empty,
    fixture_missing_commission,
    fixture_missing_required_fields,
    fixture_multi_item_order,
    fixture_single_matched,
    fixture_single_unmatched_dash_sub_id,
    fixture_single_unmatched_no_sub_id,
    fixture_unknown_fields,
    fixture_utc_plus7_timestamp,
    wrap_api_response,
)
from experiments.shopee_conversion_v2.parser import (
    normalize_timestamp,
    parse_click_response,
    parse_conversion_response,
)


class TestNormalizeTimestamp:
    def test_iso_utc(self):
        assert normalize_timestamp("2026-10-22T03:00:00Z") == "2026-10-22T03:00:00Z"

    def test_iso_with_tz(self):
        assert normalize_timestamp("2026-10-22 10:00:00+07:00") == "2026-10-22T03:00:00Z"

    def test_iso_no_tz(self):
        assert normalize_timestamp("2026-10-22T03:00:00") == "2026-10-22T03:00:00_NO_TZ"

    def test_unix_epoch_seconds(self):
        result = normalize_timestamp(1792633056)
        assert result.startswith("2026-")

    def test_unix_epoch_milliseconds(self):
        result = normalize_timestamp(1792633056000)
        assert result.startswith("2026-")

    def test_none(self):
        assert normalize_timestamp(None) is None

    def test_empty_string(self):
        assert normalize_timestamp("") is None

    def test_date_only(self):
        assert normalize_timestamp("2026-10-22") == "2026-10-22T00:00:00_NO_TZ"

    def test_unparseable(self):
        assert normalize_timestamp("not-a-date") == "not-a-date"


class TestParseConversionResponse:
    def test_empty_response(self):
        result = parse_conversion_response(fixture_empty(), source_label="test_empty")
        assert result.total_raw == 0
        assert result.records == []
        assert result.error_count == 0

    def test_single_valid_conversion(self):
        result = parse_conversion_response(fixture_single_matched(), source_label="test_single")
        assert result.valid_count == 1
        record = result.records[0]
        assert record["conversion_id"] == "CONV_SAMPLE_001"
        assert record["sub_id"] == "G3lkg1JK"
        assert record["gross_commission"] == 15000
        assert record["affiliate_net_commission"] == 10000

    def test_no_sub_id(self):
        result = parse_conversion_response(fixture_single_unmatched_no_sub_id())
        assert result.records[0]["sub_id"] is None

    def test_dash_sub_id(self):
        result = parse_conversion_response(fixture_single_unmatched_dash_sub_id())
        assert result.records[0]["sub_id"] == "----"

    def test_missing_commission_fields(self):
        result = parse_conversion_response(fixture_missing_commission())
        assert result.records[0]["gross_commission"] is None
        assert result.records[0]["estimated_total_commission"] is None

    def test_unknown_fields_detected(self):
        result = parse_conversion_response(fixture_unknown_fields())
        assert result.has_schema_drift
        assert "new_unknown_field" in result.records[0]["_extra_fields"]

    def test_missing_required_fields(self):
        result = parse_conversion_response(fixture_missing_required_fields())
        assert result.error_count > 0
        assert any("Missing required" in error.error for error in result.errors)

    def test_utc_plus7_timestamp(self):
        result = parse_conversion_response(fixture_utc_plus7_timestamp())
        assert result.records[0]["purchase_time"] == "2026-10-22T03:00:00Z"

    def test_multi_item_order(self):
        result = parse_conversion_response(fixture_multi_item_order())
        assert result.valid_count == 2
        assert result.records[0]["item_id"] == "ITEM_A"
        assert result.records[1]["item_id"] == "ITEM_B"
        assert result.records[0]["order_id"] == result.records[1]["order_id"]

    def test_invalid_envelope_no_data(self):
        result = parse_conversion_response({"code": 0})
        assert result.error_count == 1
        assert result.records == []

    def test_invalid_envelope_no_list(self):
        result = parse_conversion_response({"data": {"total": 1}})
        assert result.error_count == 1

    def test_non_dict_record(self):
        result = parse_conversion_response({"data": {"list": ["not_a_dict"]}})
        assert result.error_count == 1
        assert result.records == []

    def test_status_codes_stay_raw(self):
        result = parse_conversion_response(fixture_single_matched())
        assert result.records[0]["conversion_status"] == "1"
        assert result.records[0]["order_status"] == "COMPLETED"


class TestParseClickResponse:
    def test_clicks_with_sub_id(self):
        result = parse_click_response(fixture_clicks_with_sub_id())
        assert result.valid_count == 1
        assert result.records[0]["sub_id"] == "G3lkg1JK"

    def test_clicks_dash_sub_id(self):
        result = parse_click_response(fixture_clicks_dash_sub_id())
        assert result.records[0]["sub_id"] == "----"

    def test_empty_clicks(self):
        result = parse_click_response(wrap_api_response([]))
        assert result.records == []
