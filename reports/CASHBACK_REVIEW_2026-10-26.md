# Rà soát cashback 2026-10-26: câu chữ, UI/UX, kiến trúc

Phạm vi: bot Telegram + Zalo, Shopee + TikTok Shop (RioHub), màn `/admin`, web `/cashback`.
Cách làm: 3 lượt rà song song, chỉ đọc code, chạy bot trên DB tạm (không gọi mạng, không mở DB production). Claude Code tự kiểm lại mọi phát hiện P1 trong code.
Mức: **P1** sai hoặc hỏng · **P2** gây hiểu nhầm hoặc nợ kỹ thuật sắp gây lỗi · **P3** trau chuốt.

## Đợt 1 — bug thật (sửa ngay, 2026-10-26)

| # | Lỗi | Chỗ |
|---|---|---|
| 1 | Bấm "📦 Xem đơn" ở đơn TikTok thì báo "Nút này không còn hiệu lực" (Telegram + Zalo): bộ đọc nút không nhận dấu `:` trong mã `tt:…:…` | `customer_desk.py:53` |
| 2 | Đơn TikTok huỷ thì hoa hồng bị ghi lại bằng số ước tính, nên tin "không đủ điều kiện" ghi số hoàn **tăng** | `tiktok_sync.py:68` |
| 3 | Tin báo đơn huỷ vẫn in dòng "Hoàn tạm tính"; đơn TikTok huỷ hiện tiêu đề "không đủ điều kiện" thay vì "Đơn đã huỷ" | `messages.py` `order_update_notice` |
| 4 | Admin đang chờ nhập (🔍 Tìm, ✍️ mục tiêu, 🗄 thời hạn lưu) bấm sang màn khác vẫn chờ, nên tin kế tiếp (kể cả link Shopee) bị nuốt | `admin_policy.handle_callback` |
| 5 | Kéo đơn TikTok: thiếu trường `total` thì chỉ đọc trang đầu; chồng lấn chỉ 10 phút, RioHub ghi trễ hơn là mất đơn | `riohub_client.py:277`, `tiktok_sync.py` |
| 6 | Kéo đơn TikTok bị treo hoặc hỏng lâu không ai biết (🛠 Vận hành không kiểm) | `insights.operations` |
| 7 | Cookie Shopee hết hạn thì menu Shopee ẩn luôn 🧾 Duyệt hoa hồng / Đối soát / Tự đồng bộ (các mục này không cần cookie) | `admin_policy.py:524`, `admin_ui.py:47` |

## Đợt 2 — TikTok đúng "nền tảng" ở mọi màn (✅ đã làm 2026-10-26, trừ mục `pit` chờ quyết)

- Thêm cột `shopee_conversions.platform` (mặc định `shopee`, gán `tiktok` cho mã `tt:`), ghi cùng lúc với đơn.
- Lọc theo nền tảng ở:
  - khớp đối soát thanh toán `settlement.py:309`: hiện có thể đánh dấu nhầm đơn TikTok; đơn nhiều SKU chỉ khớp 1 dòng;
  - 📈 Thống kê (đang cộng đơn TikTok vào Shopee);
  - kiểm "đơn hoàn thành > 45 ngày chưa đối soát" (đơn TikTok sẽ báo đỏ mãi);
  - 🧾 Duyệt hoa hồng (ghi "nguồn: báo cáo Shopee", mã lý do thô `tiktok_pending`).
- Thêm trigger DB: chưa có nguồn đối soát TikTok thì dòng sổ TikTok không được `available`.
- Báo admin "🎉 Có đơn TikTok mới" như Shopee; tin lỗi đồng bộ viết thường, không dùng mã lỗi.
- Hoa hồng TikTok: đơn chốt có `pit` âm sẽ làm hoa hồng giảm từ 10% trở lên, kéo theo "cần kiểm tra" và tin "hoa hồng giảm" cho khách. Cần quyết cách xử lý trước khi gặp đơn như vậy.

## Đợt 3 — câu chữ cho khách (chờ duyệt, cỡ M)

**P1**
- Trang 💰 Cách tính (V1.1): "Số dự kiến chưa trừ thuế và phí" ngược với V3 "không trừ thêm thuế hay phí".
- Nút "🛡️ Để được ghi nhận" mở trang điều khoản (V2 đang công bố), nên trang mẹo ghi nhận không còn đường vào.
- Ví đang khoá giải thích sai lý do ("đang chờ Shopee xác minh và đối soát"). Lý do thật: bot chưa chi trả.
- Mẫu V3 chỉ nói Shopee: phải thêm TikTok Shop trước khi công bố V3 hoặc mở TikTok cho khách.

**P2**
- Zalo sai ngữ pháp khi đổi lệnh: "hãy dùng gõ hotro", "mở yêu cầu mới trong gõ hotro", "Mở lại gõ dieukien".
- Câu "bấm" của Telegram lọt sang Zalo: "Bấm vào đơn để xem tiến trình", "Nút này không còn hiệu lực".
- Menu số Zalo đánh số hai lần ("1 · 1. Áo Polo…"); sang trang 2 khách gõ số sai.
- Tin báo đơn trên Zalo thay menu số khách đang dùng (gõ "1" chạy nhầm).
- Gọi số tiền không thống nhất. Đề xuất quy ước: chưa có đơn → **hoàn dự kiến**; có đơn → **hoàn tạm tính**; vào ví → **tiền hoàn**.
- "Mã theo dõi" / "Mã link" / "Sub ID": chọn một tên là **Mã link**. Thẻ link không hiện mã này mà câu hỗ trợ lại bảo "xem trong tin bot gửi".
- Màn ví (khi mở) còn chữ "Shopee" cho khoản TikTok; có thể báo một đơn hai lần (luồng ví + luồng đơn).
- "Chờ duyệt tới dd/mm" dễ hiểu là tới ngày đó chắc có tiền. Đề xuất: "Sớm nhất vào ví ngày dd/mm".
- Từ "giao dịch" ở trang đơn: thay bằng "đơn".

**P3**
- Lặp cảnh báo trên Zalo.
- "xóa/xoá", "Hủy/huỷ" lẫn lộn.
- Xưng hô "Mình / Bot / admin / Người vận hành" lẫn lộn.
- Hai tên nút cho cùng trang Cách dùng.
- "Mã yêu cầu: Hoan tien…" thật ra là nội dung chuyển khoản.
- Ví hiện các dòng 0đ.
- Tin admin trả lời ticket không ghi "Hỗ trợ trả lời".

## Đợt 4 — màn admin (chờ duyệt, cỡ M)

**P1 / P2**
- Tin "Hoa hồng Shopee thay đổi" gửi cả khi chỉ đổi trạng thái (huỷ, cần kiểm tra), giá trị là mã thô (PENDING → REJECTED), nút dẫn tới danh sách rỗng.
- 📈 Thống kê ghi "💰 Tiền thật" cho số tạm tính, trong khi 💹 Dòng tiền ghi "Thực: 0đ".
- Menu `/admin` có 21 nút, trùng biểu tượng (2× 📈, 2× 🧮, 4× 🧾), việc ít dùng nằm chung với việc hằng ngày.
- Trang chủ admin không có "việc cần làm"; có chữ tiếng Anh ("Calculator V1.2"); "Đối soát & chi trả: Chưa mở" ghi cứng.
- Một khái niệm nhiều tên: "Admin còn", "= Admin", "Biên sau dự phòng", "biên"; "HH", "HH ròng", "Hoa hồng ròng", "HH sau cùng"… Cần bảng thuật ngữ chung.
- Mã thô hiện cho chủ bot: `ORDER_ORDER_NEW → suppressed`, `NOT_VERIFIED`, `v1.1:70`, `OPEN→IN_REVIEW`, `PENDING_REVIEW`.
- 🧾 Duyệt hoa hồng: số trên bảng khác số trên nút ("Cần kiểm tra 0" mà nút "(1)").
- Thông báo khách hiện giờ UTC. Các màn khác hiện giờ VN.
- Mở TikTok cho khách được cả khi chưa có khoá RioHub.
- Đổi rút tối thiểu không cần xác nhận, trong khi đổi số ngày giữ thì có.
- Cắt tin bằng `text[:4000]` có thể cắt giữa thẻ HTML, làm Telegram từ chối tin.

**Menu đề xuất**
```
📌 Việc cần làm: 2 ticket mới · 1 đơn cần kiểm tra · 🔴 backup
📅 Hôm nay: 3 đơn · HH 45.000đ (tạm tính)
[💹 Tiền & lãi] [📈 Tăng trưởng] [🎯 Mục tiêu]
[👥 Khách hàng] [🔍 Tìm] [📩 Hỗ trợ]
[🧾 Đơn & hoa hồng]   ← duyệt HH, đối soát, đơn cần đối soát (Shopee + TikTok)
[🛒 Shopee] [🎵 TikTok] [👛 Ví khách]
[🛠 Vận hành] [⚙️ Cài đặt]   ← chính sách, thuế & phí, mô phỏng, hoà vốn, điều khoản, thông báo khách, lịch sử…
```

## Đợt 5 — kiến trúc (chờ duyệt, làm dần)

| Mức | Việc | Cỡ |
|---|---|---|
| P2 | ✅ (2026-10-26) Mỗi việc định kỳ trong vòng poll chạy riêng (`poller._periodic`): một việc lỗi không chặn backup hoặc đồng bộ | S |
| P2 | SQLite bật WAL + `busy_timeout` thống nhất. ✅ Phần timeout (kết nối admin 15 giây). **WAL chưa bật**: web và insights mở DB `mode=ro`; DB WAL đọc chỉ-đọc cần file `-wal`/`-shm` có sẵn, nên phải thử trên bản sao trước khi bật | S |
| P2 | ✅ (2026-10-26) Trigger DB: phần khách ≤ hoa hồng (trừ dòng đã huỷ); khoá số tiền khi dòng sổ đã `available` | S |
| P2 | Backup: ✅ kiểm cả bảng tài chính. Chưa làm: backup thêm sau mỗi bước chi trả (ví còn khoá), diễn tập khôi phục | S/M |
| P2 | Gom tính tiền / trạng thái huỷ về một chỗ (đang có 3 định nghĩa "huỷ", 3 chỗ tính biên) | M |
| P2 | Tách dần `admin_policy.py` (1.617 dòng), `db.py` (1.932 dòng); `_connect` của admin chạy lại schema mỗi lần gọi | L |
| P3 | Tạo link TikTok gọi đồng bộ trong vòng poll (tối đa 60–90 giây nếu RioHub treo); phải đưa ra luồng riêng trước khi mở cho khách | S |
| P3 | ✅ (2026-10-26) `migrate()` có khoá file. Chưa có bảng phiên bản schema | S |

**Thứ tự đề xuất:** đợt 1 (đã sửa) → đợt 2 trước khi mở TikTok cho khách → đợt 5 phần S → đợt 3, 4 → phần còn lại của đợt 5.
