# Shopee Conversion Sync V2 — prototype

Module độc lập để đọc fixture conversion/click, chuẩn hóa, lưu SQLite riêng và đối chiếu `sub_id` với `data/cashback.sqlite` ở chế độ chỉ đọc.

Không có worker, không đăng nhập Shopee, không ví, không thanh toán, không sửa Cashback Bot.

## Chạy

```bash
python -m experiments.shopee_conversion_v2.cli schema-check experiments/shopee_conversion_v2/fixtures/single_matched.json
python -m experiments.shopee_conversion_v2.cli import-fixture single_matched
python -m experiments.shopee_conversion_v2.cli reconcile
python -m experiments.shopee_conversion_v2.cli report
python -m pytest experiments/shopee_conversion_v2/tests -q
```

Database prototype: `experiments/shopee_conversion_v2/data/conversion_poc.sqlite`.

Fixture là dữ liệu synthetic. Test pass không có nghĩa Shopee đã ghi nhận sub id của bot.
