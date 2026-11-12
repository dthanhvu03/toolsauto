# PLAN-170 — Kho tâm lý khách (RAG) cho reply Threads, tin bot và hỏi đáp của chủ bot

Executor: Claude Code (chủ bot giao trực tiếp 12/11) · Trạng thái: XONG code + test — chờ restart & kiểm thật

## Context
Hôm nay có khách trả lời trên Threads là «sợ ấn vào link lạ», và câu dặn AI cũ dễ khiến nó gửi lại đúng cái link đó.
Chủ bot muốn AI hiểu tâm lý, hành vi và cảm xúc khách tốt hơn, và chọn:
- **Dùng ở 3 chỗ:** reply và trả lời lại trên Threads; soạn tin trong bot; hỏi đáp riêng cho chủ bot.
- **Nguồn kiến thức:** chủ bot muốn Claude **tra các học thuyết tâm lý học trên internet rồi chắt lọc phần cốt lõi**,
  không theo một cuốn sách cụ thể. Viết bằng lời của mình, mỗi mục ghi nguồn, không chép nguyên văn.
- **Dạng lưu:** kho tra cứu (RAG). Mỗi lần trả lời, AI tìm các đoạn liên quan rồi dựa vào đó.

Hiện code chưa có kho tri thức hay embedding nào. Mọi lời gọi AI đều đi qua `AIUseCases.generate_text_async`
([app/core/ai/use_cases.py:101](app/core/ai/use_cases.py#L101)), và không có API embedding.
→ Bản đầu tìm theo **từ khoá BM25, viết bằng Python thuần** (có sẵn numpy, không thêm thư viện, không thêm lượt gọi AI).
Sau này có sách thật hoặc khóa embedding Gemini thì thay bộ tìm mà không đổi định dạng kho.

## Thiết kế
### 0. Tra cứu và chắt lọc (làm trước, chỉ đọc web)
Với mỗi học thuyết dưới đây: tìm nguồn gốc (tác giả, năm, bài báo hoặc sách gốc) và ít nhất 1 nguồn uy tín
(đại học, tạp chí, meta-analysis, Wikipedia có trích dẫn). Ghi rõ chỗ nào bằng chứng còn yếu, không lấy blog marketing làm bằng chứng.
Đã tra sơ bộ khi lập kế hoạch (12/11):

| Học thuyết | Cốt lõi dùng cho bot |
|---|---|
| Cialdini, *Influence* (6 nguyên tắc; thêm Unity năm 2016) | bằng chứng xã hội (khách thật, số thật), có qua có lại, đồng điệu nhóm («hội săn sale») |
| Fogg Behavior Model B=MAP (2009, *Tiny Habits* 2019) | khách làm khi động lực × độ dễ × lời nhắc cùng lúc; làm cho dễ hiệu quả hơn ép động lực |
| Reactance, Brehm 1966 (meta-analysis của Ma, Ebesu & Dillard) | ép, giục, ra lệnh thì khách phản kháng → đưa lựa chọn, nói kiểu gợi ý |
| Prospect theory / loss aversion, Kahneman & Tversky 1979; framing | sợ mất mạnh hơn muốn được: «khỏi mất oan hoàn» hơn «được thêm tiền» (không dọa giả) |
| Nhận thức rủi ro và niềm tin khi mua online (nghiên cứu về phishing và lừa đảo; khảo sát Which? UK) | khách từng bị lừa thì chỉ tin kênh quen → cho tự tìm bot, nói rõ bot không đòi gì |
| Giao tiếp phi bạo lực (NVC), Rosenberg | quan sát → cảm xúc → nhu cầu → đề nghị: đồng cảm trước khi gợi ý |
| Bổ sung khi làm | Kahneman Hệ 1 / Hệ 2, ELM (Petty & Cacioppo), bất hòa nhận thức (Festinger), hiệu ứng tiếp xúc (Zajonc), Self-Determination (Deci & Ryan), mô hình cảm xúc (Plutchik / Ekman), FOMO |

Kết quả: file `storage/db/config/psych_kb/_nguon.md` liệt kê từng học thuyết, nguồn (URL), mức độ chắc chắn,
và các mục kho lấy từ nó. Chủ bot xem file này để biết AI đang dựa vào đâu.

### 1. Kho kiến thức — `storage/db/config/psych_kb/` (đúng quy tắc config runtime)
- Mỗi chủ đề một file `.md`, khoảng 8 file, tổng khoảng 60–80 mục, ví dụ: `niem-tin.md` (sợ link lạ, sợ lừa, «có thật ko»),
  `chan-chu.md`, `gia-va-gia-tri.md`, `cam-xuc-mua-sam.md` (FOMO sale, hối hận vì không mua),
  `dong-cam-ngon-ngu.md`, `ban-be-xa-hoi.md` (bằng chứng xã hội, mời bạn), `ranh-gioi-dao-duc.md`.
- Mỗi mục có các phần: `## Tiêu đề` · `Dấu hiệu:` (cách khách nói, teencode) · `Vì sao:` (tâm lý phía sau)
  · `Nên:` · `Tránh:` · `Ví dụ:` (1–2 câu kiểu Threads) · `Dùng cho:` (threads / bot / all) · `Nguồn:` (tên học thuyết).
- `ranh-gioi-dao-duc.md` luôn được đưa vào kèm: không bịa số liệu, không gây sợ hãi giả, không thúc ép, không giả làm khách thật đã mua.
  Mục này giữ đúng các quy tắc sẵn có: tiền hoàn là ước tính, phải có lưu ý mua.

### 2. Module tra cứu — `app/features/psych_kb/` (mới)
- `store.py`:
  - `load_entries(path=KB_DIR)` đọc các file .md thành `Entry(id, title, body, tags, use_for)`.
  - Nạp lại khi mtime đổi, để chủ bot sửa file là có hiệu lực, không cần restart.
- `search.py`:
  - `search(query, k=3, use_for=None)`: BM25 trên chữ đã bỏ dấu và hạ chữ thường; tách từ đơn và cặp 2 từ cho tiếng Việt.
  - Phần `Dấu hiệu:` được nhân trọng số ×2.
  - Không mục nào đạt ngưỡng điểm thì trả `[]`, prompt giữ nguyên như hiện tại.
- `prompting.py`: `guidance_block(query, use_for, k)` → khối chữ ngắn ≤ 900 ký tự, kèm ranh giới đạo đức, để chèn vào prompt.

### 3. Gắn vào reply Threads (tối thiểu, không đổi luồng)
- [content.py](app/features/threads/growth/content.py) `write_followup`: query là bình luận của khách; chèn `guidance_block(comment, "threads")`
  trước phần «Văn phong». Câu dặn «sợ link lạ» vừa thêm vẫn giữ.
- [evaluator.py](app/features/threads/growth/evaluator.py) `generate_reply` (~dòng 291): query là nội dung bài; chèn khối k=2.
- Không đổi `with_link`, hạn mức hay bộ lọc. Ghi id các mục đã dùng vào `ai_analysis`
  (vd «· kb: niem-tin/so-link-la») để sau này đo mục nào kéo được khách.

### 4. Hỏi đáp và soạn tin cho chủ bot — lệnh admin Cashbot `/tamly <câu hỏi>`
- Thêm `_TAMLY_COMMAND` cạnh `_USERS_COMMAND` trong [panel.py:180](cashback_bot/admin/panel.py#L180),
  và thêm vào `ADMIN_COMMANDS` ([messages.py:127](cashback_bot/messages.py#L127)).
- Handler `cashback_bot/admin/handlers/tamly.py`:
  1. tìm k=4 mục;
  2. gọi AI với vai «cố vấn tâm lý khách cho chủ bot», được hỏi hoặc soạn tin (vd «soạn tin nhắc khách chưa tạo link»);
  3. trả lời kèm danh sách mục đã dựa vào.
- `/tamly` không kèm chữ: in danh sách chủ đề.
- **Lưu ý khi làm:** panel chạy đồng bộ, mà lỗi `asyncio.run()` trong vòng lặp đang chạy vừa gặp ở Threads hôm nay.
  Phải gọi AI qua luồng riêng giống `_run_async` ([worker.py](app/features/threads/growth/worker.py)), hoặc theo cách các handler
  admin khác đang gọi AI. Kiểm trước khi viết. Nếu không gọi an toàn được thì DỪNG và báo chủ bot.
- Tin trong bot vẫn là chữ cố định (`START_ANNOUNCE`…). Kho chỉ giúp soạn bản nháp qua `/tamly`, chủ bot duyệt rồi mới thay. Không tự đổi tin.

## File
- **Mới:**
  - `storage/db/config/psych_kb/*.md`
  - `app/features/psych_kb/{__init__,store,search,prompting}.py`
  - `cashback_bot/admin/handlers/tamly.py`
  - `tests/test_psych_kb.py`
  - `agents/plans/active/PLAN-170-psych-kb.md`
- **Sửa:**
  - `app/features/threads/growth/content.py`, `evaluator.py`
  - `cashback_bot/admin/panel.py`, `cashback_bot/messages.py`

Tổng cộng 4 file sửa. Đây là tính năng mới, không phải sửa lỗi, và do chủ bot giao trực tiếp.

## Kiểm
1. `tests/test_psych_kb.py`:
   - đọc kho;
   - «sợ ấn vào link lạ» → mục niem-tin đứng đầu;
   - «hqua ko mua tiếc ghê» → mục FOMO / hối hận;
   - câu không liên quan → `[]`;
   - `guidance_block` ≤ 900 ký tự và luôn có ranh giới đạo đức.
2. Prompt của `write_followup` và `generate_reply` có khối kb khi khớp, và giữ nguyên prompt cũ khi không khớp (dùng `fake_ai` như test hiện có).
3. `/tamly` dùng AI giả: có danh sách nguồn; `/tamly` không kèm chữ thì in chủ đề.
4. `pytest tests/test_threads_growth.py tests/test_login_browser_threads.py tests/test_psych_kb.py` và nhóm test admin cashback; chạy `ruff`.
5. Sau khi chủ bot `pm2 restart Threads_Growth` + `systemctl restart cashback-bot cashback-zalo`:
   - thử `/tamly khách sợ bấm link lạ thì nói sao`;
   - xem `ai_analysis` của các reply mới có ghi «kb:»;
   - sau khoảng 1 tuần, so tỉ lệ khách có mã threads giữa reply có kb và không có kb.
6. Ghi proof vào PLAN-170 và `current-status.md`.

## Kết quả (12/11)
- Đổi so với kế hoạch: kho gốc ở `app/features/psych_kb/kb/` (theo git) vì `storage/` bị .gitignore — deploy sẽ không có kho.
  Chủ bot sửa: chép file sang `storage/db/config/psych_kb/` (cùng tên đè, tên mới thêm), nạp lại theo mtime.
- Kho: 8 chủ đề, 41 mục + `_nguon.md` (12 học thuyết, link nguồn, mức chắc chắn). BM25 bỏ dấu + cặp âm tiết, MIN_SCORE 12.
- Threads: `write_followup` + `generate_reply` chèn khối gợi ý (≤ 900 ký tự, không câu ví dụ); ai_analysis ghi «· kb: …».
- `/tamly`: chặn trong `CashbackService.handle_text` (trước panel), AI ở luồng nền (pool TikTok), trả lời qua hàng đợi
  (audience customer, category tamly — không phụ thuộc công tắc thông báo admin). cashback_bot giờ import app.core.ai (chỉ tamly.py).
- Proof: tests/test_psych_kb.py 23 passed; Threads + cashback + store 1427 passed, 1 hỏng sẵn (test_b9); ruff sạch.
  Thử AI thật 1 lần: trả lời đúng hướng (không gửi link, tự tìm bot, không hỏi OTP), 2 bản nháp, ghi mục kho.
- Cần: `pm2 restart Threads_Growth` + `systemctl restart cashback-bot cashback-zalo`. Kiểm: `/tamly`, ai_analysis có «kb:».
