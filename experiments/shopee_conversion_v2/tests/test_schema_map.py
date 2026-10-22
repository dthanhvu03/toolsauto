from experiments.shopee_conversion_v2.fixtures_factory import make_conversion
from experiments.shopee_conversion_v2.schema_map import (
    CLICK_FIELDS,
    CONVERSION_FIELDS,
    FieldVerification,
    build_raw_to_canonical_map,
    check_conversion_schema,
    get_all_canonical_names,
    get_required_conversion_fields,
)


class TestFieldMappings:
    def test_conversion_fields_not_empty(self):
        assert len(CONVERSION_FIELDS) > 0

    def test_click_fields_not_empty(self):
        assert len(CLICK_FIELDS) > 0

    def test_required_fields_exist(self):
        required = get_required_conversion_fields()
        assert "conversion_id" in required
        assert "conversion_status" in required

    def test_canonical_names_unique(self):
        names = get_all_canonical_names("conversion")
        assert len(names) == len(set(names))

    def test_raw_to_canonical_map(self):
        mapping = build_raw_to_canonical_map("conversion")
        assert mapping["conversion_id"] == "conversion_id"
        assert mapping["sub_id"] == "sub_id"

    def test_verified_fields_present(self):
        verified = [item for item in CONVERSION_FIELDS if item.verification == FieldVerification.VERIFIED]
        assert len(verified) > 0
        inferred = [item for item in CONVERSION_FIELDS if item.verification == FieldVerification.INFERRED]
        assert any(item.canonical == "order_sn" for item in inferred)


class TestSchemaCheck:
    def test_valid_record(self):
        result = check_conversion_schema(make_conversion())
        assert result.is_valid
        assert not result.has_drift

    def test_missing_required(self):
        rec = make_conversion()
        del rec["conversion_id"]
        del rec["conversion_status"]
        result = check_conversion_schema(rec)
        assert not result.is_valid
        assert "conversion_id" in result.missing_required
        assert "conversion_status" in result.missing_required

    def test_unknown_fields_detected(self):
        rec = make_conversion()
        rec["completely_new_field"] = "surprise"
        result = check_conversion_schema(rec)
        assert result.has_drift
        assert "completely_new_field" in result.unknown_fields

    def test_type_mismatch(self):
        rec = make_conversion(gross_commission="not_a_number")
        result = check_conversion_schema(rec)
        assert len(result.type_mismatches) > 0
        assert result.type_mismatches[0][0] == "gross_commission"

    def test_null_values_ok(self):
        rec = make_conversion(gross_commission=None, order_sn=None)
        result = check_conversion_schema(rec)
        assert len(result.type_mismatches) == 0
