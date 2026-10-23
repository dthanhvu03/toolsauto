# ADR-049: Sổ hoàn tiền và ví khách trên Telegram

Ngày: 2026-10-23. Trạng thái: đã chốt, code PLAN-066. Thay phần "Không ví" của ADR-045.

## Bối cảnh

PLAN-065 kéo được click và đơn thật từ Shopee Affiliate. User muốn làm như Addlivetag (gom đơn theo người, đã hoàn/chưa hoàn, khai ngân hàng, rút tiền) nhưng trên Telegram. ADR-045 đã để sẵn hướng: trạng thái click, hoa hồng, tiền được chi và đã chi phải tách bảng/cột.

## Quyết định

- **Một đơn khớp link bot = một dòng `cashback_entries`**, trạng thái `pending → holding → available`, hoặc `cancelled`. Dựng lại sau mỗi lần đồng bộ (`CashbackService.refresh_wallet`).
- **Có thể rút khi đơn `COMPLETED` + N ngày giữ** (mặc định 30, admin chọn 0/7/15/30/45). Không cộng ngay khi hoàn thành như Addlivetag (0 ngày): Shopee còn đối soát theo tháng, trả hàng/gian lận có thể trừ lại, chủ bot phải ứng trước.
- **Số tiền hoàn đi qua cửa `pricing.py`** với hoa hồng thật (`affiliate_net_commission`), theo chính sách hiệu lực **lúc tạo link** (V1.2: `active_reserve/active_share(link.created_at)`; V1.1: tỷ lệ lưu trên link). Đã `available` thì chốt số, không tính lại.
- **Số dư không lưu**, luôn tính: rút được = Σ available − Σ yêu cầu đang chờ − Σ đã trả. Đơn đã vào ví mà Shopee huỷ sau đó → `cancelled`, số dư có thể âm, admin được báo.
- **Rút**: một yêu cầu mở mỗi khách, rút toàn bộ số rút được, tối thiểu mặc định 10.000 đ. Ghi `BEGIN IMMEDIATE`. Chụp lại ngân hàng vào yêu cầu (khách đổi ngân hàng sau không ảnh hưởng yêu cầu cũ).
- **Chi trả tay**: admin xem số TK, số tiền, nội dung `Hoan tien NNNNNN` dạng `<code>` và link VietQR (`img.vietqr.io`), chuyển xong bấm ✅ (có bước xác nhận). Không tích hợp ngân hàng.
- **Công tắc `wallet_enabled` mặc định tắt.** Tắt: sổ vẫn ghi, khách không thấy ví, không nhận tin, chữ "chưa theo dõi đơn và chưa chi trả" giữ nguyên. Bật: trang chủ có 👛, /cachtinh đổi câu cuối, khách nhận tin đơn đổi trạng thái.
- Tin báo khách đi chung outbox `admin_notifications` (gửi theo `chat_id` từng dòng, khoá `wallet:{conversion_id}:{status}` chống trùng). Đơn cũ hơn 7 ngày lần đầu thấy thì không báo "đơn mới".

## Hệ quả

- Bảng mới: `cashback_entries`, `cashback_payouts`, `bank_accounts`; cột mới trên `shopee_conversions`. Tạo khi khởi động (`CREATE IF NOT EXISTS` / `ADD COLUMN`), không đụng dữ liệu cũ.
- Outbox chỉ gửi khi admin notify bật (`AdminNotifier._active`). Production đang bật.
- Mô tả bot và menu lệnh (`/vi`) chỉ đổi khi restart sau lúc bật ví.
- Chưa có: đối soát theo `conversion_status`/tháng duyệt Shopee (mới lưu `validation_month`), chi trả tự động, khoản âm tự bù.
