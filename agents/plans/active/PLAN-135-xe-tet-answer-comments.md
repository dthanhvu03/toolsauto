# PLAN-135 — Xe Tết: lơ xe trả lời câu hỏi trong comment (câu sẵn + AI Gemini)

- Status: Code + test xong (02/11), chưa nạp 8810 (anh đang live); chờ anh thêm GEMINI_API_KEY vào .env để thử Gemini thật.
- Executor: Claude Code (anh hỏi 02/11 khi đang live: «gắn con AI đọc bình luận trả lời được em nhỉ» — người xem hỏi «có ghé
  dọc đường hông bác tài» mà game coi là tán gẫu, bỏ qua; anh có sẵn khoá Gemini)

## Phạm vi
1. **Nhận câu hỏi:** comment không phải lệnh game (tỉnh, xe nào, phở / WC, không về) mà có dấu hỏi / từ hỏi (không, hông,
   sao, bao giờ, mấy, gì, được không…) hoặc gọi lơ xe (bác tài, anh tư, lơ xe, tài xế).
2. **Câu trả lời sẵn (không tốn tiền, luôn đúng):** ghé dọc đường, cách lên xe, khi nào xe chạy, tặng quà được gì (ghi 18+),
   tên tỉnh mới / cũ. Lơ xe nói kèm tên người hỏi; cả phòng ≥ 12 giây / câu, mỗi người ≥ 30 giây.
3. **AI Gemini (mặc định tắt, công tắc trên /control):** câu hỏi còn lại xếp hàng; ≥ 25 giây / câu, bỏ câu chờ quá 40 giây,
   trần 120 câu / giờ. AI nhận tình hình thật (pha, xe số, điểm kế, vé của người hỏi, luật quà) + vai Anh Tư lơ xe; trả lời
   ≤ 30 chữ, không «!», không «nha», không xin quà, không hứa tiền, bỏ qua lệnh cài trong comment; qua bộ lọc từ cấm.
   Gọi REST `generativelanguage.googleapis.com` bằng httpx (không thêm thư viện), model `gemini-3.5-flash-lite` → lùi
   `gemini-2.5-flash`; chạy ở tác vụ nền, lỗi / chậm (8 giây) thì bỏ câu đó, vòng game không chờ.
4. **Khoá:** `GEMINI_API_KEY` trong `/home/vu/toolsauto/.env` (gitignore) hoặc biến môi trường; không ghi ra log / state.

## Proof cần có
- pytest: nhận câu hỏi đúng (không nuốt lệnh game), câu sẵn đúng nội dung + giãn cách, hàng AI bỏ câu cũ, lọc câu trả lời
  («!», «nha», từ cấm, quá dài), AI lỗi không làm đứng game (client giả, không gọi mạng).
- Gọi Gemini thật 1–2 câu khi anh đã thêm khoá (anh duyệt).

## Đã làm (02/11)
- `game/answers.py`: nhận câu hỏi (dấu hỏi, từ hỏi, đuôi «không / hông / chưa / vậy…», gọi «bác tài / anh tư / lơ xe») +
  5 nhóm câu sẵn (ghé dọc đường, cách lên xe, khi nào chạy — theo pha thật, quà ghi 18+, tỉnh mới / cũ).
- Engine `_question`: câu sẵn → lơ xe nói ngay kèm tên (cả phòng 12 giây / câu, mỗi người 30 giây); câu khác → hàng chờ AI
  (chỉ khi bật, giữ 10 câu mới nhất, `next_question` bỏ câu chờ > 40 giây); `ai_context` = tình hình thật + vé người hỏi.
- `server/ai_reply.py`: Gemini REST qua httpx (`gemini-3.5-flash-lite` → `gemini-2.5-flash`, 8 giây, tắt suy nghĩ), vai Anh
  Tư + luật game + chống lệnh cài trong comment; `clean`: một dòng ≤ 180 ký tự, bỏ «!» / «nha», lọc từ cấm / link.
- Hub: tác vụ nền, một câu một lúc, ≥ 25 giây / câu, ≤ 120 câu / giờ; lỗi / không khoá → ghi trạng thái, bỏ câu, game chạy
  tiếp. /control: công tắc «Lơ xe trả lời câu hỏi bằng AI (Gemini)» (mặc định tắt) + dòng trạng thái (khoá / số câu / lỗi).
- Proof: pytest 131 (5 test mới, client giả — không gọi mạng); ruff sạch. Chưa gọi Gemini thật (chưa có khoá trong .env).
