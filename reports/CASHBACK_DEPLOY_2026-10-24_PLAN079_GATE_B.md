# Triển khai PLAN-079 Gate A.1 + Gate B — Bật thông báo đơn hàng cho khách

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code (merge, kiểm tra); chủ bot (sửa `.env`, restart, thử trên Telegram) |
| Duyệt | Chủ bot: "oke thực hiện 3 mục cho anh đi em" |
| Code | `main@792397d` (nhánh `cursor/cashback-plan079-gate-b`) |
| Review | `reports/CASHBACK_PLAN079_GATE_B_REVIEW.md` |
| Kết quả | **Thông báo đơn BẬT cho mọi khách** từ 2026-10-24 09:21:19 UTC (16:21 giờ VN), PID 644839 |

## Diễn biến

| Bước | Giờ (UTC) | Nội dung | Kết quả |
|---|---|---|---|
| Backup | 08:48:07 | `data/backups/cashback-20261024T084807Z.sqlite`, 0600 | Kiểm tra trong lệnh backup: 41 bảng, 35 link |
| Merge | 08:49 | `main` fast-forward `e36281c` → `792397d` | 606 passed, ruff sạch, đã push |
| **1. Gate A.1** (cờ tắt) | 08:52:42 | Chủ bot restart, PID 641777 | Log: `thông báo đơn: off → off`; 0 lỗi, 0 token; `gate_b_check` OK |
| **2. Chế độ test** | 08:55:32 | `.env`: `CUSTOMER_NOTIFICATIONS_ENABLED=1`, `CUSTOMER_NOTIFICATIONS_TEST_IDS=<ID admin>`; restart, PID 642178 | Log: `off → test`, mốc 08:55:32Z |
| **3. Bật cho mọi khách** | 09:21:18 | Bỏ `CUSTOMER_NOTIFICATIONS_TEST_IDS`; restart, PID 644839 | Log: `test → on`, mốc 09:21:19Z; 0 lỗi, 0 token |

## Kết quả thử với tài khoản test (chế độ test)

| Thử | Bằng chứng trong DB | Đạt |
|---|---|---|
| Tin thử tới đúng tài khoản test | `smoke:…:1`, `smoke:…:2`: `sent`, có mã tin Telegram, đúng chat của admin | ✅ |
| Xử lý lại cùng sự kiện không thành tin thứ hai | Audit #22 (`repeat: true`, khoá `smoke:…:2`): không có dòng mới | ✅ |
| Tài khoản test tắt "Đơn mới" | `smoke:…:3`: `suppressed: pref_off`, không gửi | ✅ |
| Bật lại "Đơn mới" thì gửi bình thường | Tuỳ chọn bật lại 09:09:09Z; `smoke:…:4`: `sent` | ✅ |
| Không có tin đơn tới khách ngoài danh sách test | `gate_b_check`: 0 | ✅ |
| Restart không mất hàng đợi | Qua 3 lần restart: 42 dòng admin giữ `sent`, không có dòng `sending` | ✅ |
| Không có câu "đã duyệt" / "rút được" sai | `gate_b_check`: 0 / 0 | ✅ |
| 2 khoản pending, khoá tài chính | 12.157đ / 960đ; ví 0, available 0, payout 0; trigger 6/6; `quick_check` ok | ✅ |
| Khách chặn bot không ảnh hưởng khách khác | Không thử thật (chưa có tài khoản phụ); đã có test tự động `test_d4_…` | — |
| Đồng bộ 🔄 trong chế độ test không gửi khách thật | Không chạy thật (chủ bot chưa bấm 🔄); đã có test tự động `test_a1_…` và diễn tập trên bản sao | — |

## Trạng thái sau khi bật (`gate_b_check`, 09:21 UTC)

```
mode=on baseline=2026-10-24T09:21:19Z
  history 2026-10-24T08:52:44Z off baseline=None
  history 2026-10-24T08:55:32Z test baseline=2026-10-24T08:55:32Z
  history 2026-10-24T09:21:19Z on baseline=2026-10-24T09:21:19Z
queue admin/sent=42
queue customer/sent=3
queue customer/suppressed=1
conversions with more than one «new order» event: 0
order notices with withdraw/paid wording: 0; «approved» without APPROVED: 0
entries pending: 2 · 13117đ
entry amounts: 12157đ, 960đ
wallet_enabled=0 available=0 payouts=0
financial lock triggers 6/6
quick_check=ok
OK
```

4 dòng tin khách đều là tin thử gửi cho admin. Chưa có tin đơn nào gửi khách thật.

## Nghiệp vụ đã áp dụng (chủ bot chấp nhận khi duyệt thực hiện)

- **Ngưỡng báo thay đổi tiền hoàn:** chênh ≥ 500đ **hoặc** ≥ 10%, tính trên tiền hoàn theo snapshot của link. Về 0 luôn báo.
- **Luôn báo, không xét ngưỡng:** đơn mới được ghi nhận, người mua thanh toán, đơn hoàn thành, đơn huỷ, hoa hồng bị từ chối.
- **Đơn mua trước mốc 09:21:19Z** không báo "đơn mới".
- **Đơn đã có từ trước mà có thay đổi sau mốc:** báo "cập nhật". 2 khách thật có thể nhận tin loại này ở lần 🔄 tới.
- **Trạng thái "cần kiểm tra thêm"** (`NEEDS_REVIEW`): không báo khách.
- **Tin chỉ phát sinh khi chủ bot bấm 🔄.** Tự đồng bộ 4 giờ vẫn tắt.

## Theo dõi

- Sau mỗi lần 🔄: chạy `.venv/bin/python -m cashback_bot.gate_b_check`; trên Telegram xem /admin → 🔔 Thông báo khách (gửi lỗi, không rõ kết quả, khách chặn bot).
- **Tắt nhanh (R0):** xoá dòng `CUSTOMER_NOTIFICATIONS_ENABLED=1` khỏi `.env`, rồi restart. Tin chưa gửi chuyển "bỏ qua"; bật lại sau không gửi dồn.
- **Rollback code:** theo mục 4 của báo cáo review. Bỏ cờ trước; về code trước PLAN-079 thì dùng nhánh `rollback/plan079-compat` (`f3ab6ec`). Không dùng `UPDATE … SET status='sent'`.
