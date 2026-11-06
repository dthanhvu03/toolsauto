# PLAN-158 — Threads Kéo khách: quét Threads thật + tự đăng reply (web + Telegram), dọn profile cũ

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-158 |
| **Status** | Đang chạy tự động (06/11) — worker `Threads_Growth` online, Telegram chỉ báo cáo |
| **Executor** | Claude Code (chủ bot duyệt trực tiếp, >3 file) |
| **Related** | PLAN-153, ADR-066 |
| **Created** | 2026-11-06 |

## Context
Gói `app/features/threads/growth/` (A/B Cashbot + AI Pass Store) chỉ nạp bài mẫu, chưa quét / chưa đăng thật.
Chủ bot chốt: tự đăng bài đủ điểm, bài thấp hơn chờ duyệt; quản lý ở web + Telegram; từ khóa + câu A/B sửa trên web;
đăng nhập Threads bằng profile `instagram_5`; dọn profile trình duyệt cũ (kể cả `facebook_15…20`), giữ `facebook_scanner`
(quét video FB → Buffer → TikTok).

## Scope đã làm
- **Bước 0**: xoá 4 bài mẫu (`data/threads_growth.sqlite`, bản sao `…bak-20261106`); xoá 16 profile (1,57 GB) sau 4 bước kiểm
  (không code dùng, không đang mở, không cookie đăng nhập sau 25/10, chỉ 15–20 gắn tài khoản — anh duyệt). Giữ
  `facebook_scanner`, `instagram_5`, `common`, `profiles/fb_acc_01_profile`. Dòng accounts 15–20 để nguyên.
- **Hạ tầng**: `playwright install chromium` (bản 1208 bị thiếu — mọi tính năng Playwright đều không mở được trình duyệt).
- **Đăng nhập**: `app/scripts/login_browser.py` thêm `--platform threads` (URL + cookie `sessionid`, không dựa ô mật khẩu vì
  trang chủ có ô ẩn); `growth/session.py` (tài khoản `threads_growth` id 52, `is_active=False` để worker Threads cũ không nhận).
- **Trình duyệt**: `growth/browser.py` — đọc bài từ JSON trang tìm kiếm (`code`, `user.username`, `caption.text`, `taken_at`,
  `text_post_app_info.is_reply/can_reply/has_viewer_replied`), DOM dự phòng; `reply()` qua `ThreadsAdapter`.
- **Worker** `growth/worker.py` + PM2 `Threads_Growth` (khai trong `ecosystem.config.js`, CHƯA start): lọc tiếng Việt, bài gốc,
  tuổi bài, cooldown tác giả → AI → tự duyệt theo ngưỡng (câu mẫu khi AI lỗi luôn chờ duyệt) → đăng trong hạn mức →
  checkpoint thì tự tắt `growth.enabled` + báo Telegram.
- **Cấu hình web** (section «Threads — Kéo khách», 23 khoá `growth.*`): bật/tắt, chu kỳ, ngưỡng, tuổi bài, cooldown, lọc,
  từ khóa 2 bot, 8 câu A/B, hạn mức.
- **Web** `/app/go/threads-growth` (`frontend/src/features/threads-growth/`) + API `/threads-growth/api/*`; mục sidebar SPA + Jinja.
- **Telegram**: tin chờ duyệt có nút `gr:ok|no|ab:<id>`, lệnh `/keokhach` (A/B + hạn mức + Bật/Tắt) — qua `feature_hooks`.

## Proof
- `pytest tests/test_threads_growth.py` → 26 passed; test telegram/settings: 170 passed, 1 failed sẵn có
  (`test_telegram_schedule::test_edit_post_gui_kem_gio_va_chu`, lỗi ở `buffer/client.py`, không đụng).
- `ruff` sạch; `lint-imports` không thêm vi phạm (2 contract BROKEN có sẵn); `npx tsc --noEmit` sạch; `npm run build` OK.
- Đăng nhập kiểm ngầm: `@us28qt`, `login_status=ACTIVE`.
- Probe chỉ đọc «voucher shopee»: 18 bài JSON / 8 bài DOM; sau lọc còn 3 bài tiếng Việt.
- Quét thử đủ 14 từ khóa (ngưỡng tự đăng 101 → không đăng): 130 bài → 40 qua lọc → 10 bài ≥ 40 điểm vào «Chờ duyệt»,
  AI Gemini viết reply cả 10, Telegram báo đủ 10. Web_Dashboard restart, `/threads-growth/api/overview` trả đúng.

## Đăng thật (06/11)
- Telegram: lần bấm đầu mất vì poller nằm trong PM2 **Maintenance** (chạy code cũ) → restart Maintenance; bấm lại → #13 approved.
- Theo chủ bot: bỏ chữ «VietQR» (nói «về tài khoản»), prompt viết giọng người dùng Threads; `clean_reply()` thay mọi link
  t.me bằng link tracking đúng (AI từng viết dính «thếtps://…»). Viết lại 10 bài chờ.
- Đăng #13: lần 1 không thấy nút (trang bài có ô «Reply to …» inline), lần 2 nút gửi là mũi tên svg `aria-label="Reply"`,
  lần 3 **đăng được** → https://www.threads.com/@us28qt/post/DfYVsfpks3_ (bình luận 4→5). Bước xác nhận cũ tìm chữ trên
  trang bị hụt → đổi sang «ô soạn trống lại = đã đăng» để không bao giờ đăng 2 lần.

## Còn lại
1. ~~Reply đầu tiên~~ — xong (#13).
2. ~~Start worker~~ — xong 06/11; chế độ tự động hoàn toàn (`auto_post_min_relevance`=40, `telegram_review`=tắt).
3. Prompt mới → AI đang chèn link `?start=` vào mọi reply; theo dõi Threads có hạ reply có link không.
