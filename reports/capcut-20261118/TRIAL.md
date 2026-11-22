# Đợt thử CapCut — chuẩn bị phát hành

**Trạng thái: ĐÃ ĐĂNG VÀ XÁC MINH.** Chủ bot đã duyệt thử đề xuất; mã và nội dung cụ thể ở trial-manifest.json. Một bài riêng trên tài khoản An Linh hiện có, không DM/broadcast, không giảm giá/chạy quảng cáo, không thay quota.

## Nội dung được chuẩn bị

~~~text
Shop có CapCut Pro 30 ngày — tài khoản cấp sẵn, giá đang niêm yết 34.000đ. Mô tả món ghi tối đa 2 thiết bị. Bạn cần dùng trong tháng có thể mở đúng món để xem thông tin và giá hiện tại trước khi quyết định:
https://t.me/aipass_shop_bot?start=buy_2_threads_ai_cc18_anlinh_p1
~~~

273 ký tự. Handler mới đã chạy sau restart store-bot16:11VN; link được kiểm qua đầy đủ fake journey trước khi phát hành.

## Đo và giới hạn

Nguồn riêng threads_ai_cc18_anlinh_p1 thuộc An Linh / bài riêng, không trộn vào reply A/B. Theo dõi khách mới / xem món / QR / đơn giao / doanh thu sau hoàn bằng store_campaign. Tôn trọng first-touch, không gán lại khách cũ; số bấm link trước Start và impression chưa được ghi. Thiếu first product marker không chứng minh bỏ màn.

## Điều kiện còn lại

Chủ bot đã trả lời «Cho em restart riêng store-bot». Đã restart lúc16:11:03VN, PID3966961, active/running; log16:11:06 xác nhận @aipass_shop_bot sẵn sàng. Không restart store-api hoặc worker khác. Mapping conversion trên Dashboard cần Web_Dashboard reload để process cũ nạp config mới; báo cáo CLI dùng process mới đo được ngay.

Kiểm account ACTIVE, profile không bị dùng, quota hiện tại và catalog còn đúng trước khi đăng một lần. Nếu publish có kết quả không rõ, ghi unknown và xác minh trước mọi retry; không đăng lại mù. Chưa thêm scheduler hoặc công cụ đăng tự động mới.

## Proof code và readiness

243 tests passed in22.77s; Ruff All checks passed!; git diff --check exit0. Bao gồm fake full journey từ tracked start qua QR giả lập/admin-confirm/vendor giả đến một đơn giao, bấm đúp không mua lại, nguồn giữ nguyên và report thấy đúng món. Chưa có giao dịch production mới từ test.

Read-only preflight16:16:42VN: blocked_checks=[], source_customers=0, account ACTIVE, profile unlocked, giá34.000đ/tồn cache khớp, process mới đã nạp handler. Source mapping thuộc bài riêng / An Linh, không tăng replyA/B. Dashboard đang chạy cần reload riêng để thấy mapping mới; CLI dùng code mới ngay.

Quota16/24h áp dụng replies trong growth_posts. Đợt thử là một original post được chủ bot duyệt trực tiếp; không gửi thêm reply, không bật automatic own_posts, không đổi limit. Review queue27rows là khuyến nghị từng ID trong queue-review.json; không đọc bài gốc nên không tự reject hay approve chỉ dựa nội dung reply.

## Kết quả phát hành thực tế

Bài thật: https://www.threads.com/@anlinh_08_10/post/Df4LF2IFIlg

- Tài khoản An Linh, xác minh lại danh tính trực tiếp trong phiên trước khi tạo bài. Nội dung273ký tự, đúng unique source và giá34.000đ.
- Lượt đầu16:19VN dừng trước create_post do so @handle với bare handle; sửa chuẩn hóa, giữ proof trial-publication-attempt-1.json. Chỉ retry vì chứng minh chưa gọi create_post.
- Lượt16:21VN gọi create_post đúng một lần; adapter chưa tìm thấy permalink nên lưu unknown và không đăng lại. Verify chỉ đọc bắt đầu16:24:20VN tìm đúng bài trên profile, khớp toàn bộ text/giá/source, đã ghi posted. Không có retry xuất bản; số create_post thực tế1.
- trial-publication.json giữ initial_publish_error để phân biệt lỗi xác minh ban đầu với outcome posted; trial-verification.json là bằng chứng đọc lại. own_posts có đúng1 trial record trạng thái posted, URL khớp. Profile đã đóng/unlocked sau verify.
- Snapshot16:26:39VN: source riêng0 khách mới,0 QR/đơn/doanh thu, chưa có khách đủ24h; chưa kết luận hiệu quả. Không có dữ liệu impression/click trước Telegram Start; khách cũ không được gán lại.
- Theo dõi lại không gửi tin: PYTHONPATH=. .venv/bin/python reports/capcut-20261118/measure_trial.py. Mốc since là lúc bắt đầu attempt16:21:32VN, không khẳng định chính xác giây bài lên.

~~~text
final source measurement errors=[]; customers=0; mature_24h=0; conversion_24h_pct=null
Ruff (all changed backend/test and campaign scripts): All checks passed!
git diff --check: exit0
store-bot: MainPID3966961, NRestarts0, ExecMainStatus0, active/running
profile_locked=false
trial_records=[[posted,https://www.threads.com/@anlinh_08_10/post/Df4LF2IFIlg]]
~~~

Đã hoàn tất triển khai và phát hành đợt thử. Chưa commit/push. Chưa có kết quả tăng trưởng để kết luận; chờ đủ thời gian quan sát. Mapping Dashboard trong process cũ chưa reload; CLI đã nhận code mới. Anti/Claude review pending, chưa Done/archive.
