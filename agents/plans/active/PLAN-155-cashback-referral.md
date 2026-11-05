# PLAN-155: Mời bạn (aff) — cashback Telegram + Zalo

- **Executor:** Claude Code (chủ bot giao trực tiếp 2026-11-05)
- **Status:** Code xong + test. CHƯA bật (chờ chủ bot công bố điều khoản V5 rồi bật cờ).

## Quyết định của chủ bot (2026-11-05)
1. Người mời nhận **10% hoa hồng** mỗi đơn của người được mời, trong **6 tháng** kể từ lúc nhập mã. Trích từ phần bot.
2. Thưởng **vào ví theo đơn**: chờ cùng đơn gốc, vào ví khi đơn gốc vào ví, huỷ khi đơn gốc huỷ.
3. Đơn của người được mời **không tính** vào hạng của người mời. Một tầng.

## Cách làm
- `cashback_bot/referral.py`: `referral_codes`, `referrals`; `parse` (`/start ref_MÃ`, `ref MÃ`), `attach`
  (chỉ người mới: chưa tạo link, vào bot ≤ 7 ngày; không tự mời, không mời chéo, không đổi), `sync`, `stats`.
- Sổ: dòng `<conversion>:ref` trong `cashback_entries` của người mời, commission_vnd = 0, policy `ref-10`.
  Rút tiền / hạn mức / phân bổ dùng nguyên luồng ví.
- `db.py`: 6 trigger (`financial_lock_v2_entry_*`, `financial_lock_platform_entry_*`, `ledger_cashback_cap_*`) xét dòng
  `:ref` theo đơn gốc (SETTLED, nền tảng, trần = hoa hồng đơn gốc). `_migrate` xoá bản cũ thiếu `':ref'` để tạo lại.
  Dòng thường không đổi hành vi.
- `money_flow._entry_totals` cộng `:ref` vào đơn gốc (phần chi cho khách của đơn). `membership._COUNTED` bỏ `:ref`.
- `service.py`: nhận mã trước bảng lệnh; trang «🤝 Mời bạn» (`/moiban`, nút trang chủ); `_referral_sync` sau
  `wallet.refresh`; tin REFERRAL (có bạn dùng mã / có đơn / vào ví / huỷ).
- Zalo: lệnh `moiban`. Config: `CASHBACK_REFERRAL_ENABLED`, `CASHBACK_BOT_USERNAME` (mặc định zt_shopee_bot).
- Điều khoản mẫu **V5** = V4 + mục «🤝 Mời bạn» + dòng dữ liệu mời bạn ở mục 🛡.

## Bật trên production (chủ bot làm)
1. /admin → Điều khoản → «📝 Tạo bản nháp V5 từ mẫu» → xem → công bố.
2. `.env`: `CASHBACK_REFERRAL_ENABLED=true` → `systemctl restart cashback-bot cashback-zalo`.

## Proof
- `tests/test_cashback_referral.py` 16 qua; `tests/test_cashback_*.py` 1194 qua, 1 lỗi sẵn (`b9`).
- Bản sao DB thật: migrate thay 6 trigger, `money_flow.snapshot` trước/sau giống hệt, sync 0 dòng.

## Chưa làm / giới hạn
- Đơn gốc bị thu hồi một phần sau khi vào ví: thưởng giữ nguyên.
- Admin chưa có màn xem ai mời ai / huỷ thưởng gian lận (phải sửa DB).
