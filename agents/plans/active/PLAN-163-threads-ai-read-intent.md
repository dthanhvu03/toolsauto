# PLAN-163 — Kéo khách Threads: AI đọc tâm lý / nhu cầu từng bài trước khi chọn và viết reply

- Executor: Claude Code · Duyệt: chủ bot (07/11: «AI phải đọc tâm lý hành vi cảm xúc, và từng câu chữ của người dùng thì tỉ lệ
  chốt cao hơn»; trước đó chọn hướng lọc bài theo nhu cầu, không theo từ khoá)
- Dữ liệu: 221 reply 06–07/11 — Cashbot 42% bài là người bán, 27% có câu hỏi, 0,04 khách/reply; AI Pass Store 42% có câu hỏi,
  0,55 khách/reply. Đếm từ khoá không phân biệt người cần mua với người bán.

## Thay đổi (gói `app/features/threads/growth/`)
1. `evaluator.py`
   - `looks_like_seller()`: lọc rẻ (không gọi AI) bài chào hàng rõ ràng: inbox / ib, link bio, chốt đơn, nhận order, giá sỉ,
     nhanh tay, mua ngay, freeship, zalo…
   - `read_post()` (AI, JSON): người bán?, ý định (hỏi / than phiền / chia sẻ / khoe / chào hàng), cảm xúc, nhu cầu thật,
     giai đoạn mua, băn khoăn, câu chữ đắt của họ, góc nên nói, `buy_score` 0–100 (khả năng thành khách của bot này).
   - `generate_reply(..., reading=)`: prompt nhận bản đọc → phản chiếu đúng cảm xúc, dùng lại chữ của họ, giải quyết đúng nhu
     cầu / băn khoăn trước rồi mới nhắc bot như trải nghiệm riêng.
2. `runner.py` `ingest_scanned_post`: lọc từ khoá (giữ, làm cổng rẻ) → lọc người bán → AI đọc. Đọc được: điểm = `buy_score`;
   người bán hoặc điểm < `min_relevance` (sàn 40) → lưu `rejected` kèm lý do (không đọc lại, không tốn suất); từ sàn tới dưới
   `auto_post_min` → `pending` như cũ (giữ chế độ duyệt Telegram). AI đọc lỗi → điểm từ khoá nhưng KHÔNG BAO GIỜ tự đăng.
3. `storage.py` `approved_queue`: điểm cao trước (theo nấc 10), rồi độ phủ.

## Không làm
- Mã riêng từng reply, tin chào trong bot (chờ quyết riêng). Không đổi schema (dùng cột sẵn: relevance_score, ai_analysis).

## Proof (07/11)
- pytest tests/test_threads_growth.py 62 passed (55 cũ + 7 mới: lọc người bán không gọi AI, AI báo người bán → rejected & không
  đọc lại, điểm dưới sàn, prompt reply mang bản đọc, parse JSON hỏng, thứ tự hàng chờ, AI lỗi → không tự đăng). ruff sạch.
  Sửa test cũ: AI giả trả JSON cho bước đọc; `test_reply_uses_ai_with_purpose` nay 2 lượt gọi (đọc + viết).
- Chạy thật bước đọc (Gemini) trên 6 bài đã reply: 5/6 là người bán (AI 0–5 điểm; regex chỉ bắt 1/5), 1 người cần thật (95).
- `growth.auto_post_min_relevance` 40 → 60 (updated_by=claude_code_plan163).
- Lọc lại 114 bài approved (sao lưu trước: scratchpad threads_growth.before-plan163.sqlite): 97 người bán + 14 ít khả năng →
  rejected; giữ 2 approved (viết lại reply theo bản đọc) + 1 pending. AI lỗi `no_api_key` khi gọi dồn → chạy lại giãn 8–20 giây.
- Lưu ý: mỗi bài qua cổng rẻ tốn 2 lượt AI; vòng quét 60 phút × 14 từ khoá → theo dõi hạn mức AI (9Router circuit_open,
  Gemini dự phòng có lúc no_api_key).
- Còn: `pm2 restart Threads_Growth Web_Dashboard` (chủ bot) để worker dùng code mới.
