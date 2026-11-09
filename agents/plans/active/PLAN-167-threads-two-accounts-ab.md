# PLAN-167 — Kéo khách Threads chạy 2 tài khoản, mỗi tài khoản một bot, đổi vai để so tỉ lệ chốt

- Trạng thái: **NHÁP do Claude Code soạn (09/11) — chờ Anti duyệt + chọn Executor (backend → Codex).** Chủ bot đã đồng ý chiến lược.
- Bối cảnh: worker `Threads_Growth` chỉ chạy 1 profile (`instagram_5` = @us28qt), một tài khoản mời cả Cashbot lẫn AI Pass Store.
  Số liệu 06–09/11 (mã `src:threads_*`): Store 48 reply → 30 khách (~62%), 3 người mua; Cashbot 209 reply → 10 khách (~5%), 1 đơn.
  Nguồn bài đủ điểm từ 08/11: Store ~4/ngày, Cashbot ~11/ngày → nút thắt là nguồn bài, không phải giới hạn reply.
- Tài khoản 2: @anlinh_08_10 «An Linh» (183 follower, nghỉ từ 17/09), không liên quan @us28qt (chủ bot xác nhận).
  Profile đã nạp: `storage/profiles/threads_anlinh` (09/11, ĐĂNG NHẬP OK). Đang làm ấm: 1 bài/ngày, Claude Code đăng tay.

## Mục tiêu
1. Worker chạy được N tài khoản; mỗi tài khoản gán 1 bot (`cashbot` | `ai_store`), giới hạn reply riêng, bài riêng riêng.
2. Đo tỉ lệ chốt theo tài khoản: mỗi tài khoản một mã `?start=` riêng cho link bio (reply không chèn link — reply có link
   hay bị ẩn: 6/30 biến mất so với 0/20 reply không link), reply nhắc «link ở bio».
3. Lịch đổi vai: T2–3: @us28qt=cashbot, An Linh=ai_store · T4–5: đổi ngược. Báo cáo khách / người mua trên 100 reply theo tài khoản × bot.
4. Mở rộng từ khoá AI Pass Store theo hàng đang bán: Canva Pro, CapCut Pro, Office 365, Duolingo, Gemini, Grok/Cursor, API Claude.

## Lỗi kèm theo (đã phát hiện 09/11, nên sửa cùng đợt)
- `replies_to_me` bỏ sót trả lời của chủ post (#646 vivian_global_realty trả lời 08/11 20:47Z, worker kiểm 09/11 12:44Z, bảng `followups` = 0).
- `create_post` bài riêng @us28qt lỗi 6/6 «hộp soạn không đóng». Thử tay trên An Linh 09/11: nút «New thread» không có; luồng
  đúng = bấm chữ «What’s new?» → dialog → gõ → nút «Post» → toast «Posted». Cần kiểm bài @us28qt có lên thật không.

## Hướng kỹ thuật đã chốt (chủ bot duyệt 09/11): nghe response, không gửi request trực tiếp
- ĐỌC: mở rộng `GrowthBrowser._capture` (đã có, chỉ dùng cho quét) cho mọi luồng — replies dưới reply của mình (sửa lỗi
  followup), like / reply count, hồ sơ. Lấy dữ liệu từ JSON GraphQL Threads trả cho chính trang đang mở; DOM chỉ là dự phòng.
- GHI (đăng bài, reply): vẫn thao tác giao diện như người (gõ, bấm, nghỉ ngẫu nhiên). Xác nhận thành công = bắt được response
  của mutation tạo bài (lấy code / URL bài mới), không đoán bằng «hộp soạn đóng». Hỗ trợ cả 2 kiểu nút: «New thread» và
  ô «What’s new?» trên đầu feed.
- KHÔNG: dựng request GraphQL (doc_id, token) từ Python để đăng / reply — khớp DECISION-004 (private API chỉ đọc).
- Không dùng Threads API chính thức ở đợt này (cần app Meta + duyệt quyền keyword search).

## Ngoài phạm vi
- Không dùng tài khoản này để xác nhận / khen bot dưới reply của tài khoản kia.
