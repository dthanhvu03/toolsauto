# CapCut — kiểm tra chiến dịch 18/11/2026

Phần đầu dưới đây là snapshot chỉ đọc lúc14:30–14:36VN. Sau đó chủ bot đã duyệt và Codex triển khai link product+source, restart riêng store-bot và đăng đúng một bài thử An Linh. Kết quả mới ở TRIAL.md / trial-publication.json / trial-verification.json. Chưa kết luận tăng user/doanh thu.

## Kết quả thực tế

Snapshot khách hàng lúc **14:36:02 VN 18/11** (07:36:02 UTC). Mốc quan sát **09:01:59 VN** là thời gian commit 649d42e, không phải bằng chứng worker bắt đầu dùng toàn bộ code mới hoặc nguồn của từng khách. Đã loại tài khoản admin và chỉ lấy khách mới có nguồn bắt đầu bằng threads_ai_.

| Cửa sổ | Khách mới | Ghi nhận xem một món | QR / khách đã có đơn giao | Doanh thu đơn đã giao sau hoàn |
|---|---:|---:|---:|---:|
| Sau mốc commit đến 14:36 | 1 | 0 | 0 / 0 | 0đ |
| 7 ngày trước mốc commit | 91 | 14 | 4 / 3 | 180.200đ |

- Riêng CapCut sản phẩm #2: khách mới sau mốc có 0 lượt ghi nhận xem món, 0 QR, 0 đơn; trước mốc 7 ngày có 1 khách ghi nhận xem món, 0 đơn trong cohort này.
- Khách duy nhất sau mốc chưa đủ 24 giờ. Mẫu số chuyển đổi 24 giờ bằng 0, tỷ lệ là chưa đủ dữ liệu, không ghi 0%.
- Hai cửa sổ khác độ dài, không dùng để tính tăng/giảm do chiến dịch. First-touch dùng mã chung giữa nhiều bài; không thể gán khách này cho bài CapCut cụ thể.
- Step product/confirm chỉ giữ lần đầu và được bổ sung từ 16/11. Thiếu marker không chứng minh khách chưa từng xem món hoặc rời ở màn nào. QR là nhánh tùy chọn; nạp tiền thành công khác với giao đơn thành công.
- Đối chiếu SQL độc lập khớp **1 khách**. JSON chỉ có số tổng hợp và thông tin catalog, không xuất ID/tên khách, tài khoản đăng nhập hay dữ liệu đơn hàng riêng lẻ.

## Hàng chờ và worker

Snapshot lúc **14:30:28 VN** trong runtime-audit.json:

- Store có **25 reply approved**; **22 tạo trước mốc commit**; **4 có chữ CapCut**. Có **10 reply nhắc sản phẩm khác mà không nhắc CapCut**. Phân loại nội dung dùng từ khóa, không thay thế duyệt từng reply và không coi mọi reply thiếu từ CapCut là sai.
- Store có 8 pending, 1 có chữ CapCut. Sau mốc commit có 2 reply Store đã đăng từ anlinh, 1 có chữ CapCut. Đây là quan sát nội dung, chưa có attribution khách/đơn cho các reply này.
- Threads_Growth online, PID 3403840, restarts 23, khởi động 09:00:32 VN, trước commit khoảng 87 giây. Runtime override keywords/angle/hook đã đọc khớp giá trị CapCut trong code hiện tại; thời điểm process khởi động không đủ để khẳng định toàn bộ module tĩnh đã được nạp lại.
- Hook B hiện có lối kể đã mua và so sánh rẻ hơn gói chính hãng. Chưa có bằng chứng cho các lời này; các bản nháp mới tránh dùng chúng. Không thay cấu hình đang chạy trong lượt chỉ đọc.
- worker.py hiện chỉ tạo own-post cho role phục vụ Cashbot; chưa có nhánh tự đăng own-post Store trong đường này. Bài deal đã đăng sau mốc không phải bằng chứng bài CapCut đã được đăng.

## Sản phẩm và đường vào

Catalog lúc **14:35:50 VN**: #2 **Capcut Pro 30D BHF acc cấp**, giá **34.000đ**, upstream available, tồn cache 25. Giá vốn đang ghi **31.360đ**, chênh lệch **2.640đ/đơn vị trước chi phí**; không phải lãi ròng hoặc tiền đã thực nhận. Giá/tồn cần kiểm tra lại trước khi phát hành nội dung.

Catalog mô tả: tối đa 2 thiết bị; điện thoại đăng nhập email/mật khẩu; máy tính đăng nhập trên điện thoại rồi quét QR. Không suy diễn chữ BHF thành cam kết bảo hành cụ thể, không công bố thông tin tài khoản cung cấp.

Link có sẵn **https://t.me/aipass_shop_bot?start=buy_2** mở đúng món khi vào bot bằng Start; không tự mua/tạo QR. Theo store_bot/bot.py:188–195, nguồn first-touch cho nhánh buy_ là kenh. Link threads_ai_price giữ được nguồn Threads nhưng mở catalog chung. Ghép thêm hậu tố vào buy_2 không được nhánh hiện tại hỗ trợ. Vì vậy các bài nháp dùng link vào đúng món nhưng **không đo riêng chiến dịch/bài qua nguồn này**. Không có báo cáo tăng trưởng giả từ link đó.

## Nội dung chuẩn bị

Xem CONTENT.md: 3 bài riêng và 2 reply mẫu, ghi rõ bản nháp chưa đăng. Nói từ phía shop, dùng thông tin catalog, không giả trải nghiệm người mua, số khách, ưu đãi, bảo hành hay thời gian giao được bảo đảm.

## Quyết định thực tế nên làm tiếp

1. Duyệt lại hàng chờ Store với chủ PLAN-172 trước khi tiếp tục dùng suất đăng: 22 reply cũ có thể khiến chiến dịch vẫn phân tán. Không tự xóa/reject hàng chờ trong lượt này.
2. Chọn một nội dung CapCut đã xem được trong CONTENT.md và tài khoản/kênh phát hành. Muốn đăng ra ngoài cần xác định rõ nội dung và tài khoản; chưa có lượt gửi mới từ công việc này.
3. Nếu muốn vừa vào đúng món vừa đo riêng nguồn, cần một thay đổi nhỏ được thống nhất với chủ luồng Store/PLAN-172: payload hợp lệ kèm mã nguồn, vẫn giữ các link cũ. Đây là scope tiếp theo, chưa code trong lượt chỉ đọc.
4. Sau phát hành, đọc lại cùng cửa sổ nguồn và tách món CapCut khỏi tổng Store. Chỉ tính chuyển đổi 24h khi đủ thời gian quan sát; số khách/đơn thực tế quyết định có mở rộng chiến dịch hay không.

## Lệnh và proof

Chạy trong /home/vu/toolsauto, dùng môi trường dự án. snapshot.py đọc STORE_ADMIN_IDS và STORE_DB_PATH từ môi trường/.env nhưng chỉ xuất số tài khoản đã lọc. audit_runtime.py dùng transaction PostgreSQL chỉ đọc, SQLite mode=ro và chỉ lọc thông tin process cần thiết; không gọi vendor, AI hoặc gửi tin.

~~~text
PYTHONPATH=. .venv/bin/python reports/capcut-20261118/snapshot.py
observed_at=2026-11-18T07:36:02.301588+00:00
independent_sql_matches=true
cohort.customers=1; not_yet_24h=1
selected_product.stages={product:0,confirm:0,qr:0,paid:0,order:0}
product_economics={price:34000,recorded_unit_cost:31360,gross_spread_before_expenses:2640,cached_stock:25}
exit 0

.venv/bin/python -m pytest -q tests/test_store_campaign.py tests/test_growth_funnel.py tests/test_growth_report.py
.................                                                        [100%]
17 passed in 3.10s

.venv/bin/python -m ruff check cashback_bot/store_campaign.py tests/test_store_campaign.py reports/capcut-20261118/audit_runtime.py reports/capcut-20261118/snapshot.py
All checks passed!

git diff --check
(no output; exit 0)
~~~

Kiểm tra nội dung cuối lượt: content_exists=True; draft_count=5; draft_characters=[251,296,292,189,212], tất cả <=470; exit0. git diff --check cuối lượt exit0.

CLI bổ sung: .venv/bin/python -m cashback_bot.store_campaign --since 2026-11-18T02:01:59Z --product-id 2 --source-prefix threads_ai_ --json. CLI không tự loại admin; để có kết quả kinh doanh đã lọc, dùng snapshot.py hoặc truyền --exclude-user-id cho từng admin. Không đưa ID thật vào tài liệu/chia sẻ output lệnh.

Test dùng SQLite tạm: ranh giới offset/cửa sổ, source prefix literal, loại admin, refund/failed, QR khác đơn, exact 24h, khách chưa đủ 24h, DB thiếu không bị tạo, kết nối chặn ghi, JSON không lộ khách. Không mở browser mua hàng, không tạo QR, không sửa DB/queue/config, không restart/commit/push.

**Execution Done. Cần Claude Code verify + handoff.** Anti sign-off và Claude handoff vẫn pending; không archive PLAN/TASK.

## Cập nhật đợt thử đã phát hành

TRIAL.md ghi scope mới chủ bot duyệt, link buy_2_threads_ai_cc18_anlinh_p1,243tests và restart16:11VN. Bài thật đã xác minh đầy đủ nội dung: https://www.threads.com/@anlinh_08_10/post/Df4LF2IFIlg . Chỉ1lần create_post, không gửi reply/DM/broadcast, không đổi quota/roles. Việc adapter ban đầu chưa tìm thấy link được xử lý bằng đọc lại profile, không đăng lại. Snapshot16:26VN source riêng0khách/đơn, chưa đủ24h. Chưa commit/push; review/handoff pending. Các câu “chưa đăng” trong snapshot/content cũ chỉ áp dụng lúc chuẩn bị; manifest và TRIAL.md là trạng thái phát hành hiện tại.
