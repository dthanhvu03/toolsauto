# PLAN-056 — Video dài lên feed Page + khảo sát giỏ hàng

## Status: Video dài code done — giỏ hàng chờ khảo sát live (2026-08-21)

## Goal

Hai mục cuối của combo Page Master.

**Video dài.** Bài feed đã nhận video (`assert_feed_media`, `attach_media`), nhưng
`attach_media` chờ **cứng 20 giây** rồi đi tiếp bất kể file to nhỏ:

```python
wait_ms = 20000 if any(self.is_video(p) for p in existing) else 6000
self.page.wait_for_timeout(wait_ms)
```

Clip 15 giây thì thừa; video 10 phút thì chưa upload xong đã bấm Đăng — nút còn khoá
hoặc bài lên thiếu video. Đây là lý do "up video dài" chưa dám bán.

**Giỏ hàng.** Không có một dòng code nào (`grep -i "product_tag|shopping|cart"` → 0).
Gắn giỏ hàng phụ thuộc Page có bật Shop hay không — không khảo sát live thì không
thể viết đúng. Plan này **chỉ ra đề bài khảo sát**, không code mù.

## Scope

- Ngân sách chờ upload tính theo dung lượng thật thay vì hằng số
- Chờ tới khi có preview thật (thẻ `video` / ảnh blob) rồi mới đi tiếp; hết ngân sách
  mới chịu thua
- Nhãn UI nói rõ bài feed nhận video dài
- Giỏ hàng: viết TASK khảo sát live, không code

## Out of scope

- Đặt tiêu đề / thumbnail cho video dài — composer feed không có hai ô đó, phải đi
  qua Meta Business Suite (bề mặt khác hẳn, cần plan riêng)
- Gắn giỏ hàng (chờ kết quả khảo sát TASK-055)

## Implementation

| Piece | Path |
|-------|------|
| Ngân sách chờ theo dung lượng | `FacebookFeedComposer.upload_budget_ms()` |
| Chờ preview thật | `FacebookFeedComposer.wait_for_media_ready()` |
| Nhãn UI | `fragments/manual_job_form.html` |
| Test | `tests/test_long_video_upload.py` |

## Verify — 2026-08-21

| Hạng mục | Kết quả |
|---|---|
| Ảnh và bài chữ thuần vẫn chờ 6s như cũ | PASS |
| Video càng nặng ngân sách càng lớn; 60MB được chờ lâu hơn hằng số 20s cũ | PASS |
| Có trần 7 phút, một file hỏng không treo job vô hạn | PASS |
| Thấy preview là đi tiếp ngay, không ngồi hết ngân sách | PASS |
| Không đọc được dung lượng vẫn có ngân sách mặc định (50MB) | PASS |
| Lô có cả ảnh lẫn video thì tính theo video | PASS |

`tests/test_long_video_upload.py` — 9 test. Full suite **243 passed**.
Smoke: `app.main` import được, 3 template đổi đều parse sạch.

## Giỏ hàng — không code, đã chuyển thành khảo sát

`TASK-055-shop-product-tag-spike.md`. Lý do trong đó: không có gì trong repo để sửa,
và luồng gắn sản phẩm phụ thuộc Page có bật Shop hay không. Viết selector cho một hộp
thoại chưa từng nhìn thấy là cách chắc chắn nhất để ra tính năng hỏng ở máy khách.

## Ghi chú

`story_composer.attach_media` vẫn chờ cứng 25s cho video — cố ý để nguyên vì tin
Facebook giới hạn 60 giây, không có "tin dài". Gộp lại nếu sau này giới hạn đổi.

## Còn nợ

- [ ] **Live**: đăng một video > 5 phút lên Page nháp
- [ ] **Khảo sát**: TASK-055 (giỏ hàng)
