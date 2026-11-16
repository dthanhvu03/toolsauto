# PLAN-172 — Vận hành tăng trưởng Cashbot + AI Pass Store (đến 12/12)

- Executor: Claude Code (ADR-067: chủ bot giao toàn quyền vận hành 15/11)
- Script đo (chỉ đọc): scratchpad f74d4a4a/funnel.py → sẽ chuyển vào repo cùng báo cáo hằng ngày (tuần 1).

## Mục tiêu (Claude chọn)
**Chỉ số chính: số khách dùng thật trong 7 ngày, gộp 2 bot** (Cashbot: tạo link; Store: nạp xong hoặc có đơn).

| Chỉ số | 15/11 (gốc) | 12/12 |
|---|---|---|
| Khách dùng thật 7 ngày (2 bot) | 24 | **60** |
| Store: khách Threads có đơn đầu | 7% (6/76) | 20% |
| Store: khách mua ≥2 lần | 1 | 8 |
| Cashbot: khách đến qua mời bạn | 0 | 10 |
| Cashbot: khách tạo link ngày 12/12 | — | 30 |

## Bảng số gốc 15/11 (chỉ đọc DB)
**AI Pass Store** (99 khách)
| nguồn | vào | tạo mã nạp | nạp xong | có đơn | mua ≥2 |
|---|---|---|---|---|---|
| threads | 76 | 10 (13%) | 6 (7%) | 6 (7%) | 0 |
| tự vào | 23 | 6 (26%) | 6 (26%) | 6 (26%) | 1 |
- 46/76 khách Threads rời bot trong vòng 10 phút. Doanh thu đơn done 494.300đ (Threads 215.600đ).
- Mã nạp: 13 paid / 12 cancelled — khách tạo mã rồi bỏ gần một nửa.

**Cashbot** (54 khách)
| nguồn | vào | tạo link | bấm link | có đơn | quay lại ≥2 ngày |
|---|---|---|---|---|---|
| tự vào | 39 | 30 (76%) | 21 (53%) | 9 (23%) | 15 (38%) |
| threads | 13 | 3 (23%) | 3 (23%) | 1 (7%) | 1 (7%) |
- Từ chối 40 lần, trong đó 25 lần «invalid_link» là khách gõ chữ thường (0–48 ký tự): khách muốn hỏi chuyện, bot không hiểu.
- Mời bạn: 4 mã đã tạo, **0** người được mời.

## Chẩn đoán
1. **Store rơi ở bước đầu**: khách đến vì bài «giá AI» (threads_ai_price 50/76) → thấy danh sách → đi. Bot bắt nạp ví trước
   (tối thiểu 10.000đ) rồi mới mua, nhiều bước với món giá 1.100–34.000đ.
2. **Cashbot sản phẩm tốt, kênh sai**: khách tự vào dùng 76%, khách Threads 23%. Tin nhắn chữ không có link bị từ chối, khách đi.
3. **Mời bạn chưa chạy**: chưa ai mời được ai.

## Thử nghiệm (mỗi lần tối đa 2, đo sau 7 ngày, giữ hoặc bỏ)
- [x] **T1 (bắt đầu 15/11) Store — khách mới vào thẳng danh sách món**: trước đó /start → trang chủ «Số dư 0đ · trừ thẳng
      vào số dư» (khách tưởng phải nạp trước) → bấm Mua hàng → … Giờ khách mới thấy luôn danh sách + câu «Không cần nạp
      trước: chọn món → quét QR → bot gửi hàng ngay» (cũng ở trang chủ). Link `buy_<id>` + QR đúng số tiền đã có sẵn.
      Đo 22/11: khách Threads mới từ 16/11 có đơn đầu (gốc 7%).
- [x] **T2 (bắt đầu 15/11) Cashbot — tin chữ → AI (9Router) trả lời**: `cashback_bot/chat_ai.py`. Tin có nội dung (≥4 ký tự,
      không «ok/cảm ơn», không dáng link) → «💬 đang trả lời» → AI trả lời ở luồng nền, qua hàng đợi chung (TG + Zalo).
      AI lỗi / SKIP → câu mẫu cũ. 1 câu AI / khách / 45 giây. Tắt nhanh: bot_state `chat_ai:off`. Không lưu nội dung tin.
      Bật chỉ trong poller.py / zalo_bot.py (`chat_ai_enabled`). Thử thật 9Router 4 câu: đúng, không bịa, rác → SKIP (~12s/câu).
      Đo 22/11: khách bị invalid_link (chữ) có tạo link trong 24h không (gốc: đa số đi luôn).
- [ ] T3 (tuần 2) Nhắc 1 lần sau 24h cho khách vào mà chưa làm gì. Dùng lại `engagement.py` (đã có LINK_NUDGE cho link chưa
      mua, đang bật; nhắc sale Black Friday 27/11 tối + 12/12 đã được chủ bot duyệt từ 27/10) — chỉ thiếu nhánh «vào chưa tạo link».
- [ ] T4 (tuần 2) Store → Cashbot: sau đơn done, mời dùng Cashbot.
- [ ] T5 (tuần 3) Mời bạn: tìm vì sao 0 lượt; khách vừa nhận tiền → đề nghị chia sẻ kèm ảnh.
- [ ] T6 (tuần 4) 12/12: bài ghim + đếm ngược + nhắc khách cũ.

## Hạ tầng (tuần 1)
- [x] Báo cáo 8h sáng (16/11): `cashback_bot/growth_report.py` (chỉ đọc 2 DB) + nối vào vòng poller; một lần / ngày
      (bot_state `growth_report_day`), qua hàng đợi admin. Bản 16/11 gửi tay lúc 08:28 (sent). Tự chạy từ 17/11 sau restart cashback-bot.

## Nhật ký
- 15/11: nhận quyền, đo số gốc, chọn mục tiêu, viết ADR-067.
- 15/11: làm T1 + T2. Proof: test_store_bot (+1) / store_nudge 101 passed; test_cashback_chat_ai 6 passed; bộ cashback + store
  + bot_users + psych_kb chạy lại (xem current-status). Cần restart: `systemctl restart store-bot cashback-bot cashback-zalo`.
- 16/11: chủ bot hỏi sao sáng không có báo cáo — 15/11 mới ghi «next», chưa làm. Làm growth_report + test (2 passed),
  gửi bản 16/11. Số sáng 16/11: dùng thật 7 ngày 25; Store 15/11 vào 50 khách (Threads); T1 0/13 có đơn (qua đêm).
