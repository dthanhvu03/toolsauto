# ADR-067 — Claude Code vận hành và tăng trưởng Cashbot + AI Pass Store

- Ngày: 2026-11-15
- Trạng thái: Accepted (chủ bot giao trực tiếp)
- Liên quan: ADR-010 (ngoại lệ backend cho Claude Code), PLAN-172

## Bối cảnh
Chủ bot: «anh giao quyền cho em quản lý vận hành 2 bot này, mục tiêu tăng trưởng do em quyết định».
Hai bot đã chạy ổn về kỹ thuật, nhưng khách vào rồi bỏ: 153 khách, chỉ 24 người dùng trong 7 ngày (15/11).
Không ai chịu trách nhiệm cho con số này. Quy trình Anti → PLAN → executor quá chậm cho việc thử câu chữ hằng ngày.

## Quyết định
1. Claude Code là người vận hành hai bot **Cashbot** (Telegram + Zalo) và **AI Pass Store**, kèm quyền dùng **9Router**.
   Claude tự đặt mục tiêu, tự chọn thử nghiệm, tự sửa code / câu chữ của hai bot để đạt mục tiêu.
2. Đây là ngoại lệ vai trò so với CLAUDE.md («không viết core business logic»), chỉ trong phạm vi hai bot này.
   Mỗi thay đổi vẫn có: test, commit nhỏ, ghi vào PLAN-172 + current-status.
3. Anti / Codex không sửa luồng khách của hai bot mà không báo Claude, để không đè lên thử nghiệm đang chạy.

## Giới hạn vẫn giữ (dù có toàn quyền)
- **Tiền**: ví khách, rút tiền, hoàn tiền, nạp FatCat, giá vốn → chủ bot quyết.
- **Nhắn khách**: chỉ người đã tự vào bot; tối đa 1 tin nhắc / người / tuần; luôn có nút «không nhắc nữa».
  Không nhắn hàng loạt người lạ trên bất kỳ nền tảng nào.
- **Shopee**: không tự gọi / thử đồng bộ. **FatCat**: không tự gọi /api/buy.
- **Restart**: Claude đưa lệnh, chủ bot chạy (`systemctl restart cashback-bot cashback-zalo` / `store-bot`).
- **DB**: sao lưu trước khi sửa cấu trúc; không xoá dữ liệu khách.

## Hệ quả
- Có một người chịu trách nhiệm số khách; vòng thử → đo → giữ/bỏ rút còn khoảng 1 tuần.
- Rủi ro: Claude chỉ làm việc khi được gọi. Cần có báo cáo tự chạy hằng ngày (PLAN-172, tuần 1).
