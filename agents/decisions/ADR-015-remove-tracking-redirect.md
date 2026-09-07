# ADR-015 — Gỡ link rút gọn `/r/{code}` (P0-2); đếm click bằng Sub ID của sàn

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-07 ("triển khai theo thứ tự
  từng mục"), mục 2 trong `docs/research/2026-09-07-tich-hop-mien-phi.md`
- **Liên quan**: PLAN-047 (affiliate lookup), PLAN-054 (story), ADR-014

## Bối cảnh — khảo sát 2026-09-07 (Postgres thật)

Tính năng "link rút gọn đếm click" hỏng ở 3 tầng, nhưng điểm cốt lõi khác với
những gì handoff cũ ghi:

- Cột `tracking_code`, `tracking_url`, `click_count`, `affiliate_url` nằm trên **`jobs`**
  (baseline `7387f2685758`), không phải `affiliate_links`.
- Route `GET /r/{code}` nằm sau tường đăng nhập → khách bấm bị đưa về `/login`.
- `VERCEL_REDIRECT_URL` trống trong `.env` → `tracking_url` **luôn** là `/r/{code}` tương đối.
- **Đang gây hại thật**: `JobService.attach_affiliate_to_job` (`job.py:1061`) thay `[LINK]`
  bằng `/r/{code}` trong `auto_comment_text` → đi thẳng ra comment Facebook;
  `FacebookAdapter.story_overlay_text` (`adapter.py:1662`) **ưu tiên `tracking_url`
  trước `affiliate_url`** → đốt chuỗi `/r/ab12cd34` lên ảnh Story; `job.py:1212` thay
  `{tracking_url}` trong comment người dùng gõ.
- Dữ liệu: 14 job, 2 có `tracking_url` (đều tương đối), **0 click, 0 comment nhiễm**.

Khảo sát tích hợp cùng ngày: Shopee Affiliate / AccessTrade đếm click sẵn theo
**Sub ID** nằm trong chính URL affiliate — cùng con số sàn dùng tính đơn.

## Quyết định — phương án C+

**Sửa 3 dòng để mọi chỗ dùng URL affiliate gốc; xoá route và UI; GIỮ cột.**

| Việc | File | Ghi chú |
|---|---|---|
| `[LINK]` → `url` gốc thay vì `/r/{code}` | `app/core/queue/job.py` `attach_affiliate_to_job` | 1 dòng |
| `{tracking_url}` → `clean_affiliate` | `app/core/queue/job.py` ~1212 | 1 dòng |
| Bỏ ưu tiên `tracking_url` trong chữ phủ Story | `app/features/facebook/adapter.py` `story_overlay_text` | xoá 1 dòng |
| Không sinh `tracking_url` khi tạo job; bỏ `_register_vercel_tracking` + call site không commit | `app/core/queue/job.py` ~487-503, 536, 573-594, 1104 | giữ sinh `tracking_code` |
| Xoá route `/r/{code}` + `track_redirect_click` | `app/platform/dashboard_shell/router.py`, `app/platform/dashboard_service.py` | |
| Xoá tự điền `{tracking_url}` vào ô auto-comment; badge "N clicks"; tooltip `/r/` | `app/templates/fragments/create_job_form.html`, `job_row.html`, `job_details.html` | |
| Gỡ 2 call site của `_register_vercel_tracking` (bổ sung khi làm — không gỡ thì `AttributeError` mỗi lần gắn affiliate) | `app/features/affiliates/lookup_queue.py`, `app/features/viral_intake/workers/ai_generator.py` | chỉ xoá |
| Test đang assert hành vi cũ | `tests/test_vip_monetize_strategic.py`, `tests/test_facebook_story_post.py` | đổi assert sang URL gốc |
| Tài liệu | `docs/sales/00-doi-chieu-thuc-luc.md` (mục D → "đã gỡ, dùng Sub ID sàn"), `docs/02_DATABASE_SCHEMA.md` (ghi cột giữ lại để làm Sub ID) | |

**Vì sao giữ cột:** `tracking_code` (uuid[:8], có index) là chỗ chứa Sub ID theo bài
sẵn có; drop cột cần migration trên bảng `jobs` nóng nhất, lợi = 2 cột nullable trên
14 dòng. Ngữ nghĩa mới: `tracking_code` = Sub ID gợi ý cho bài; `tracking_url` = để
trống (sau này có thể chứa URL affiliate cuối đã gắn Sub ID — cần PLAN riêng).

## Ngoài phạm vi

- Không viết migration. Không đổi `affiliate_links`.
- Không tự gắn `?sub_id=` vào URL — Owner đặt Sub ID trong chính URL khi lưu link
  (form `/affiliates/save` nhận URL tự do), hoặc PLAN sau.
- `health.py:174 total_clicks` và `daily_summary_message` "0 clicks" giữ nguyên (nợ
  nhỏ, ghi để dọn sau).
- Không gỡ `VERCEL_REDIRECT_URL` khỏi `.env.example` nếu agent khác đang sửa file đó —
  ghi nợ.

## Hết hiệu lực

Sau khi test xanh và `grep -rn "/r/" app/` không còn chỗ nào sinh link tương đối.
