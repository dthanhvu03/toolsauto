# PLAN-171 — AI agent trả lời tin nhắn riêng (DM) Threads để chốt khách

- Trạng thái: chủ bot giao trực tiếp 13/11 («anh cho em toàn quyền inbox, reply làm sao em chốt được khách… AI agent đảm
  nhiệm hết»). Executor: Claude Code.
- Bối cảnh (khảo sát chỉ đọc 13/11, bản sao hồ sơ @us28qt): web Threads có `/messages` (Inbox) + `/messages/requests`
  (Requests, phải bấm **Accept** mới nhắn được). Cuộc trò chuyện `/messages/t/<id>/`; ô nhập `[role=textbox]`
  «Message...». Bong bóng của mình nền tối, nằm bên phải; của khách nền sáng, bên trái. Tin không đi qua GraphQL → đọc DOM.
  Requests 13/11: 4 người xin slot Canva free (1 ngày → 1 tuần, chưa ai trả lời) + tin rác / sàm sỡ từ 1 năm trước.

## Phạm vi
1. `app/features/threads/growth/dm.py` — trình duyệt: danh sách Inbox / Requests, đọc cuộc trò chuyện (mình / khách),
   gửi tin (bấm Accept nếu là Requests). Đóng theo `with GrowthBrowser`, nghỉ ngẫu nhiên giữa thao tác.
2. `app/features/threads/growth/dm_agent.py` — AI đọc cả cuộc trò chuyện + kiến thức (bảng giá AI Store đọc `store.sqlite`
   chỉ đọc, quy tắc mua Cashbot, luồng tặng Canva của chủ bot, kho tâm lý PLAN-170) → JSON
   `{action: reply | handoff | skip, reply, note, bot, hot}`.
   - Chỉ trả lời người **tự nhắn tới** (không nhắn trước cho người lạ). Requests quá 14 ngày / rác / người bán → bỏ, không Accept.
   - handoff: khiếu nại, hoàn tiền, lỗi đơn / bảo hành, thanh toán, mua sỉ / đại lý, đòi người thật, khách đã làm xong bước
     tặng Canva (chủ bot gửi slot) → báo Telegram chủ bot; agent im 24 giờ ở cuộc đó.
   - Không hỏi mật khẩu / OTP / thẻ; giá chỉ lấy từ bảng giá; không hứa ngoài mô tả sản phẩm; khách hỏi thẳng có phải
     bot không → nói thật là trợ lý tự động, cần thì báo chủ shop.
   - Link mã nguồn riêng `threads_cb_dm` / `threads_ai_dm` (đo khách từ inbox).
3. `storage.py`: bảng `dm_threads`, `dm_messages` (ghi mọi tin vào / ra).
4. `worker.py`: bước `dm_inbox` mỗi 10 phút cho tài khoản có `dm: true` (file vai tài khoản); hạn mức 40 tin / ngày,
   8 / giờ, 6 / cuộc / ngày; mở tối đa 8 cuộc / nhịp.
5. `notify.py`: báo vòng có tin DM; báo handoff riêng.

## Ngoài phạm vi
- Không nhắn chủ động người lạ; không tự mua hàng FatCat để tặng (chủ bot tự gửi slot).
- Chưa bật cho An Linh (chưa khảo sát inbox).

## Proof (13/11, Claude Code)
- Code: `dm.py` (DmBrowser list / read / send, rows_from, messages_from, unanswered, signature), `dm_agent.py` (catalog,
  cashbot_user, build_prompt, parse_decision, decide, handle_inbox), `storage.py` (dm_threads, dm_messages),
  `config.py` (AccountRole.dm, CHANNELS «dm»), `worker.py` (dm_inbox mỗi 10 phút, report.dms), `notify.py`
  (dòng «nhắn riêng», dm_handoff_text). Requests đọc trước Inbox. Link tặng Canva giữ `?start=canva` của chủ bot.
- tests/test_threads_dm.py 13 test (đọc hàng / tuổi, tin chưa đáp, JSON, trả lời + không mở lại, cuộc cũ / tin cuối của
  mình, skip không Accept, handoff + im 24 giờ, hạn mức, gửi lỗi, AI lỗi, prompt có bảng giá / link / kiểm username,
  vai dm, báo cáo). Threads + psych 118 passed; ruff sạch.
- Chạy thử thật KHÔNG GỬI (bản sao hồ sơ, DB tạm): 5 Requests xin Canva (natalie.chilly, uld.dh, qua_n_leon,
  ineedicecream_please, hai_kien251) → reply hướng dẫn đúng luồng, hot 85; khanh.nhakhoatam «Dạ» → skip.
- Bật: `storage/db/config/threads_growth_accounts.json` us28qt `"dm": true`. Cần `pm2 restart Threads_Growth`.
- Chạy thật 13/11: lần 1 (16:45Z) 5/5 gửi hụt «Không thấy ô nhập» — nút Accept là div[role=button] chứa div chữ, CSS
  `:text-is` không khớp → sửa `get_by_role("button", name=…)` + Requests không thấy Accept thì báo lỗi rõ. Bước DM chuyển
  lên ĐẦU vòng (quét + AI đọc bài > 20 phút) — test `test_worker_doc_hop_tin_truoc_khi_quet`; Threads 119 passed.
  Mở lại 5 cuộc (UPDATE dm_threads về open). Lần 2 (16:54–17:00Z): 5/5 đã gửi; kiểm chỉ đọc: cả 5 đã sang Inbox, tin cuối
  là của mình (hướng dẫn `?start=canva`).

