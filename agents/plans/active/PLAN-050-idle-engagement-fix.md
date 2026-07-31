# PLAN-050 — Idle engagement: sửa nguồn dữ liệu + ghi lịch sử phiên

## Status: Done

## Bối cảnh

Kiểm tra tính năng "nuôi tài khoản lúc rảnh" theo yêu cầu Owner (2026-07-31).
Nhìn log thì 5/5 phiên đều "completed successfully", nhưng đọc kỹ thì 2 phiên
`spy_competitor` không mở được trang nào.

## Root cause

`competitor_urls` là nguồn REUP TikTok, lưu JSON các object:

```json
[{"target_page": "https://www.facebook.com/kids0810", "url": "https://www.tiktok.com/@leehi9869"}]
```

Nhưng `_maybe_idle_engagement()` đưa nó qua `parse_niche_topics()` — hàm này
`str()` cả object thành chuỗi `{'target_page': ...}`, không bắt đầu bằng `http`
nên bị ghép tiền tố thành `https://{'target_page': ...` → `page.goto()` hỏng.

Hai lỗi cộng hưởng:

1. **Sai nguồn dữ liệu** — một cột gánh hai nghĩa (nguồn reup vs page để dạo)
2. **Thất bại im lặng** — `_action_spy_competitor` bắt lỗi rồi `return`, nhưng
   `run_random_action` vẫn set `ok=True` → log ghi "completed successfully"

Hệ quả: `spy_competitor` chiếm **40% trọng số** (cao nhất khi có competitor) mà
chưa từng chạy được lần nào. Thêm nữa `niche_topics` trống nên `search_topic`
cũng không bao giờ vào pool → thực tế chỉ 2/4 hành động hoạt động.

## Fix

| Việc | Path |
|---|---|
| Parser riêng, chỉ nhận URL facebook.com | `engagement.parse_competitor_urls()` |
| Thất bại không báo thành công giả | `_action_spy_competitor` trả `False`; `run_random_action` phản ánh |
| Cột riêng cho page để dạo | `accounts.engagement_page_urls` |
| Bảng lịch sử phiên | `engagement_sessions` |
| Ghi lịch sử mỗi phiên | `publisher._record_engagement_session()` |
| Ô nhập trong UI | `fragments/account_details.html` |
| Migration | `h6c3d4e5f6a7` |

Đã điền `niche_topics` cho account FB (6 từ khoá skincare) để mở khoá `search_topic`.

## Verify

Phân bố hành động đo trên 400 lần quay, với dữ liệu thật của account:

| Hành động | Trước | Sau |
|---|---|---|
| `spy_competitor` | 40% (luôn hỏng) | 0% (không có page → không cấp trọng số) |
| `scroll_news_feed` | 30% | 40% |
| `watch_reels` | 15% | 34% |
| `search_topic` | 0% (niche trống) | 27% |

Migration đã `alembic upgrade head` thành công trên DB thật. Test: 175 passed
(14 test mới, dùng đúng giá trị JSON thật trong DB làm dữ liệu test).

## Còn lại

Ô "Page FB để dạo khi rảnh" đang trống → `spy_competitor` vẫn 0%. Owner cần dán
vài link page Facebook cùng ngách thì hành động này mới bật lại. Link TikTok dán
vào đó sẽ bị lọc bỏ (browser đang đăng nhập FB, mở TikTok không nuôi được acc).
