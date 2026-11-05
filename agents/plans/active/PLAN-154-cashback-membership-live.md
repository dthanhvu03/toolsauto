# PLAN-154: Hạng thành viên Đồng / Bạc / Vàng xét theo 2 tháng (cashback Telegram + Zalo)

- **Executor:** Claude Code (chủ bot giao trực tiếp 2026-11-05)
- **Status:** Code xong + test. CHƯA bật production (chờ chủ bot công bố điều khoản V4 rồi bật cờ).
- **Nền:** ADR-046 (`ranks.py`: Đồng 60%, Bạc 65%, Vàng 70%, snapshot theo link).

## Quyết định của chủ bot (2026-11-05)
1. Khách mới mặc định **Đồng**.
2. Khách đã có lúc bật hạng → **Vàng**, giữ tới hết **31/12/2026**; từ 01/01/2027 xét như mọi người.
3. Xét theo **2 tháng** (tháng trước + tháng này), đếm **đơn hoàn thành** (status holding/available có completed_at).
4. Đủ ngưỡng → lên ngay. Ngày 1 mỗi tháng xét theo 2 tháng vừa qua, thiếu → xuống **một bậc**. Ngày 24 nhắc khách sắp xuống.
5. Ngưỡng **admin cấu hình** (/admin → Cài đặt → 🎖️ Hạng thành viên → 🎯 Điều kiện lên hạng), mặc định Bạc 2 đơn + 30k, Vàng 6 đơn + 90k.

## Cách làm
- `cashback_bot/membership.py`: bảng `member_ranks` + `member_rank_events`; `seed_existing` (một lần, khoá
  `membership:seeded_at`); `tick` = xét tháng (`membership:reviewed_month`) + lên hạng + nhắc (`membership:reminded_month`),
  BEGIN IMMEDIATE vì hai bot cùng chạy; ngưỡng ở `bot_state membership_thresholds`; tháng theo giờ VN.
- `service.py`: `_resolve_for(user)` thay `share_bps` theo hạng (trần = tỷ lệ chia chung) → link Shopee/TikTok,
  snapshot, ví. `tick` lúc khởi động và sau `refresh_wallet`; tin `RANK_UP` (lên / xuống / nhắc) qua admin_notifications
  audience customer. `/hang` hiện hạng, số 2 tháng, phần còn thiếu để lên / giữ.
- `watchlist.py` theo hạng khách; `deals.py` tin chung theo mức Đồng.
- `messages.py`: `hang_message`, `rank_up_notice`, `rank_down_notice`, `rank_keep_notice` — không có %.
- `terms_content.py`: mẫu **V4** = V3 + mục «🏅 Hạng thành viên» (không ghi số ngưỡng, dẫn sang /hang).
- Admin: `admin/handlers/membership.py` (c:mb:*), nút trong RANK_KEYBOARD, route sau `policy`, Lịch sử `membership_thresholds`.
- `config.py`: cờ `CASHBACK_MEMBERSHIP_ENABLED` (mặc định tắt).

## Bật trên production (chủ bot làm)
1. /admin → Điều khoản → «📝 Tạo bản nháp V4 từ mẫu» → xem → công bố.
2. (tuỳ chọn) chỉnh ngưỡng ở 🎯 Điều kiện lên hạng.
3. `.env`: `CASHBACK_MEMBERSHIP_ENABLED=true` → `systemctl restart cashback-bot cashback-zalo`.
4. Kiểm: log «22 khách cũ lên Vàng»; /hang; 🎯 Điều kiện lên hạng «Đang chạy».

## Proof
- `tests/test_cashback_membership_live.py`: 17 passed.
- `tests/test_cashback_*.py`: 1176 passed, 1 failed (`test_b9…` hỏng sẵn trước khi sửa). `test_backup_never_touches…` chập chờn (mtime), chạy lại qua.
- Bản sao DB thật (scratchpad, đã xoá): seed 22 → GOLD; 24/12 nhắc 22; 01/01/2027 22 → SILVER nếu không có đơn mới.

## Chưa làm
- Admin sửa hạng từng khách bằng tay.
- Chương trình mời bạn (aff) — mới tư vấn.
