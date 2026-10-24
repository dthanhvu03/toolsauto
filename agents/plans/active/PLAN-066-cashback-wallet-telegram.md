# PLAN-066 — Đối soát đầy đủ + ví hoàn tiền trên Telegram (theo mô hình Addlivetag)

| | |
|---|---|
| Trạng thái | **APPROVED (user giao trực tiếp Claude Code, 2026-10-23: "em làm tất cả cho anh")** |
| Executor | Claude Code (ngoại lệ backend như ADR-010; ghi lại để Anti nắm) |
| Bối cảnh | PLAN-065 đã kéo được click/đơn thật. User xem Addlivetag (màn Chuyển đổi, Thống kê, Thành viên ZaloBot) và muốn làm tương tự trên Telegram. |
| Phạm vi | `cashback_bot/` (db, shopee_sync, admin_stats, admin_ui, admin_policy, poller, service, messages, telegram_api, `wallet.py` mới, `admin_wallet.py` mới), tests, ADR-049. |

## Quyết định mặc định (đổi được trong /admin, không cần sửa code)

- **Ví khách mặc định TẮT.** Chữ khách đang thấy là "chưa theo dõi đơn và chưa chi trả". Chỉ khi admin bật, khách mới thấy ví, nhận báo đơn, rút tiền.
- **Có thể rút:** đơn `COMPLETED` + **30 ngày** (Addlivetag để 0). Shopee còn đối soát theo tháng, trả hàng/gian lận có thể trừ lại.
- **Rút tối thiểu:** 10.000 đ.
- **Chi trả:** admin chuyển khoản tay; bot đưa số tài khoản, số tiền, nội dung `Hoan tien NNNNNN` dạng bấm-để-chép và link mã VietQR.
- **Tiền hoàn của một đơn** = hoa hồng thật (`affiliate_net_commission`) đi qua cùng công thức `pricing.py`, theo chính sách đang hiệu lực **lúc tạo link** (V1.1: tỷ lệ đã lưu trên link).

## Bước

1. **Số liệu:** lưu Doanh số (`items.actual_amount`), Số lượng, HH gốc, phí MCN, HH sau cùng, tên món, giờ hoàn thành. Thống kê thêm doanh số, HH gốc → phí → sau cùng, đơn huỷ, HH mất do huỷ, bảng 7 ngày. Nút 🔄 trả lời ngay, poller chạy và báo kết quả. Xuất CSV đơn 30 ngày.
2. **Báo khách:** đơn mới qua link, đơn hoàn thành, tiền vào ví, đơn huỷ (chỉ khi ví bật).
3. **Ví:** sổ `cashback_entries` (mỗi đơn khớp bot một dòng: pending → holding → available / cancelled), `cashback_payouts`, `bank_accounts`. Số dư = available − đã yêu cầu − đã trả.
4. **Rút tiền:** khách khai ngân hàng (`MB 0123456789 NGUYEN VAN A`), bấm Rút → admin nhận yêu cầu → ✅ Đã chuyển / ✖️ Từ chối → khách được báo.

## Definition of Done
- [x] Bước 1–4 có test, pytest `tests/test_cashback_*.py` xanh, ruff sạch.
- [x] Chạy migration trên bản sao DB thật.
- [x] Ví tắt: khách không thấy gì khác.
- [x] ADR-049 ghi quyết định sổ cái.

## Proof — Claude Code, 2026-10-23

- Code: `wallet.py` (sổ, số dư, rút, ngân hàng, VietQR), `admin_wallet.py` (màn 👛 Ví khách), `shopee_sync._order_details`, `admin_stats` (doanh số, HH gốc/phí/sau cùng, huỷ, bảng 7 ngày, CSV), `poller` (🔄 chạy nền qua cờ `shopee_sync_requested`, `refresh_wallet` sau đồng bộ, gửi file), `service` (/vi, `u:w:*`, khai ngân hàng, `_real_cashback`), `messages`/`admin_ui` (chữ).
- pytest `tests/test_cashback_*.py`: **217 passed** (199 + 19 mới trong `tests/test_cashback_wallet.py`, bỏ 1 test 🔄 cũ đã thay). ruff sạch.
- Test canh cũ `test_nut_khong_co_chi_tra` (ADR-045: admin không có nút ví) viết lại thành `test_vi_mac_dinh_tat_khach_khong_thay_chi_tra`: admin có màn ví, ví mặc định tắt, khách không thấy nút, /vi báo chưa mở.
- Test bắt lỗi thật: `link_requests.estimate_policy` chỉ có sau migration 001 → `refresh` tự dùng NULL khi thiếu cột.
- Bản sao DB thật + Shopee thật: migration ok; đơn 23/09 có doanh số 1.630.300 đ, 4 món, tên món, giờ hoàn thành; bảng 7 ngày 21/10 = 4 click, 22/10 = 3 click — **khớp ảnh Addlivetag**. Màn 👛: ⚪ ĐANG TẮT; trang chủ khách không có nút ví.

### VietQR tự tạo + chọn ngân hàng bằng nút — 2026-10-23

- `cashback_bot/vietqr.py`: chuỗi EMVCo/NAPAS (GUID `A000000727`, BIN, STK, `QRIBFTTA`, 53=704, 54=số tiền, 58=VN, 62/08=nội dung ≤25 ký tự ASCII, CRC16-CCITT-FALSE), ảnh PNG bằng `qrcode==8.0` (thêm vào requirements, đã cài `.venv`). Bỏ `img.vietqr.io`: thông tin khách không rời máy chủ.
- Admin mở yêu cầu rút → bot gửi ảnh QR (chỉ khi còn `requested`); không tạo được (ngân hàng bỏ khỏi danh sách, STK hỏng, thiếu thư viện) → hiện lý do, chuyển tay theo số dạng chữ. Gửi ảnh lỗi không chặn tin chữ.
- Khách bấm chọn ngân hàng (30 ngân hàng, thêm Cake, Ubank, Timo, KienlongBank, PVcomBank, ABBANK, VietABank, NCB, BVBank, Shinhan), gõ `STK + tên`; STK tách nhóm được ghép; sai thì vẫn chờ để gõ lại; dán link Shopee khi đang chờ → thoát chờ, tạo link.
- Proof: CRC `123456789` = `29B1` (giá trị chuẩn). `tests/test_cashback_vietqr.py` 59 ca ngoại lệ; tổng `tests/test_cashback_*.py` **279 passed**, ruff sạch. **Chưa quét bằng app ngân hàng thật** — cần user thử.
### Hoa hồng thật khác ước tính — 2026-10-24

- 2 đơn thật qua bot: DOPI ước tính 30.510 đ, thật 17.368 đ = (5% + 2,5%) × 231.570 thực trả. Cọ mắt ước tính 1.663 đ, thật 1.372 đ. Lệch vì giá thực trả và tỷ lệ Shopee thật, không phải lỗi đồng bộ.
- Sửa: HH gốc = `estimated_total_commission` (trước đây chỉ là phần Shopee). Checkout nhiều đơn có cộng `capped_brand_commission` của shop. Test dùng số thật; 281 passed.
