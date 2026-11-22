# PLAN-177 — Cầu nối repo đã qua smoke theo cách chờ B

Ngày 19/11/2026, lượt thật bắt đầu 23:34:04 giờ Việt Nam (2026-11-19T16:34:04.921Z).

## Kết quả

**ĐẠT trong phạm vi một sản phẩm được chọn:** cầu nối repo chuẩn bị portal, health Windows/WSL đúng bản toolsauto, NativeShopeeQuoteClient trả đúng shop/item, rồi tạo shortlink trên cùng backend. Đã đóng bản repo và phục hồi legacy; không bật nguồn mới cho khách.

| Kiểm tra thật | Kết quả |
|---|---|
| Chuẩn bị portal theo B | ready=true sau 14,238 giây; giới hạn vẫn 45 giây |
| Tải tài liệu | navigate_done tại 3,145 giây từ đầu chuẩn bị |
| Chờ mạng ổn định | 7,672 giây; network_idle_done tại 10,821 giây |
| Nghỉ sau khi mạng ổn định | 3,396 giây; settle_done tại 14,219 giây |
| Health repo từ Windows | HTTP 200, implementation=toolsauto, quote_schema=1 |
| Health repo từ WSL | HTTP 200, implementation=toolsauto |
| Native quote qua client Python trong WSL | shop 1175585681 / item 54321049804, ids_exact=true, source=native_shopee; 1,347 giây |
| Shortlink qua repo, cùng sản phẩm/backend | HTTP 200, success=true, host s.shopee.vn; 0,193 giây |
| Cleanup bản repo | closed=true; cả harness 17,832 giây; mã thoát 0 |
| Phục hồi legacy | pm2 start mã 0, online PID 3285822 |
| Health legacy sau phục hồi | HTTP 200/status=ok; không phải implementation toolsauto |
| Một shortlink legacy sau phục hồi | HTTP 200/success=true/host s.shopee.vn; 8,142 giây |

Quote mẫu: price_vnd=138475, sure_commission_vnd=3461, seller_commission_vnd=0, shopee_commission_vnd=9693, is_xtra=false. sure_commission là căn cứ hoa hồng theo công thức hiện hành, không phải tự khẳng định toàn bộ số tiền hoàn cho khách. last_update=NULL; fetched_at=2026-11-19T16:34:21.645Z. Lượt này không gọi Product Data để đối chiếu lại và không có thời gian Shopee cập nhật nguồn.

## Thay đổi trong mã

Chỉ hai file mã/kiểm thử: scripts/shopee_bridge/browser.mjs và browser.test.mjs.

- Giữ DOMContentLoaded; giới hạn điều hướng 25 giây, nằm trong ngân sách chuẩn bị 45 giây. Chờ networkidle tối đa 8 giây rồi nghỉ đủ 2,5–4 giây trước lần gọi REST đầu tiên, kể cả tab đã nằm ở portal.
- Dùng lại trạng thái đã ổn định cho đúng page/context. Đổi page, main-frame navigation, lỗi, abort hoặc close thì bỏ trạng thái này; các request đã ấm không phải chờ lại 8–12 giây trong ngân sách client 8 giây.
- Reviewer phát hiện điều hướng có thể xảy ra ngay trong lúc nghỉ. Đã thêm bộ đếm phiên điều hướng; nếu thay đổi trước khi xác nhận sẵn sàng thì dừng và cleanup, không tự gọi lại.
- Không đủ thời gian nghỉ thì trả timeout trước fetch; không rút khoảng nghỉ xuống vài trăm mili giây. Giữ xử lý 401/403/90309999 và hàng chờ/cleanup hiện có.
- Thêm các stage cố định để phân biệt điều hướng, chờ mạng và nghỉ. Không ghi URL động, thông báo lỗi thô hoặc dữ liệu đăng nhập.

Bản repo trước sửa đã dùng domcontentloaded, không phải commit như script A. Chênh lệch đã sửa là thời gian chờ networkidle, settle và việc áp dụng cho tab có sẵn. A/B giải thích khác biệt kết quả 403/200 trong các mẫu đã ghi; không đủ để khẳng định mọi timeout cũ đều cùng một nguyên nhân.

## Kiểm thử và rà độc lập

- Windows Node: node --test scripts/shopee_bridge/browser.test.mjs scripts/shopee_bridge/bridge.test.mjs scripts/shopee_bridge/quote.test.mjs → 38 tests, 38 pass, 0 fail, 722.884 ms. Output đầy đủ: lifecycle-b-node-tests-20261119.tap.
- WSL Node: cùng 38 tests → 38 pass, 0 fail, 1523.470113 ms.
- Reviewer lifecycle_b_review tái hiện race bằng browser giả, rồi xác nhận bản sửa từ chối cả điều hướng trong settle và validation: ready=false/fetch_count=0. Không còn phát hiện material trước smoke.
- Lượt chạy test đầu có một dấu ngoặc thừa trong ca kiểm thử mới; đã sửa trước các lượt 38/38 nêu trên. Không coi lượt lỗi là đạt.

## Ranh giới vận hành

- Không sửa .env/PRIMARY, client Python, launcher hoặc npm; không restart Cashbot/Zalo, không sửa DB, không commit/push. Trong thời gian smoke, hash tất cả 9 file baseline giữ nguyên, gồm cả hai file mã vừa sửa trước đó; PID và thời điểm khởi động Cashbot/Zalo cùng các app PM2 khác giữ nguyên.
- Mặc định vẫn product_data + legacy. Chỉ tiến trình smoke dùng bridge repo trên interface nội bộ 192.168.112.1, cho đúng peer Windows/WSL; không mở mọi interface hoặc đổi tường lửa.
- File PowerShell chưa ký bị hệ điều hành từ chối trước thực thi. Lệnh gộp có thao tác kill/xóa trực tiếp cũng bị công cụ từ chối trước thực thi. Đã dùng cách hẹp hơn được chấp nhận: stop/start riêng shopee-mcp, dùng cleanup sẵn có của launcher, harness chỉ kiểm tra bốn lock không tồn tại. Không đổi execution policy; không gọi lại để vượt 403.
- Không lưu mới cookie/CSRF/token, header hoặc response thô. Không đổi các artifact lỗi cũ; lượt B có tên riêng.

## Bằng chứng

- lifecycle-b-native-smoke-20261119.json: kết quả, stage, quote, shortlink và invariants.
- lifecycle-b-native-smoke-20261119.mjs: đúng harness đã chạy; SHA-256 trong baseline/proof.
- lifecycle-b-baseline-20261119.json và lifecycle-b-after-20261119.json: hash, cấu hình và tiến trình trước/sau.
- lifecycle-b-legacy-restore-20261119.json: health/shortlink legacy sau phục hồi.
- lifecycle-b-browser-before-20261119.mjs và lifecycle-b-browser-change-20261119.diff: bản mã trước sửa và phần thay đổi.
- AB-PROBE-COMPARE-20261119.md: bằng chứng A/B do Cursor cung cấp, không phải lượt chạy lại A trong phiên này.

## Bàn giao

**Execution Done. Cần Claude Code verify + handoff.** Riêng bước sửa lifecycle và smoke một sản phẩm theo handoff đã đạt. Toàn PLAN-177/TASK-063 chưa Done/archive; Claude kiểm tra, Anti/anh duyệt bật vẫn pending. Một mẫu thành công chưa chứng minh độ sẵn sàng lâu dài, freshness độc lập hoặc mọi sản phẩm; không tự đổi PRIMARY hay restart bot để bật nguồn.

Kiểm tra artifact cuối: git diff --check mã 0; sáu file mã/tài liệu mới được kiểm tra riêng bằng git diff --no-index --check, không có cảnh báo khoảng trắng (mã 1 của no-index biểu thị có nội dung khác /dev/null). Quét 10 artifact tại thời điểm rà dữ liệu không thấy giá trị cookie/CSRF/token từ tệp phiên hiện có (0 giá trị khớp). Reviewer xác nhận proof/hash độc lập; đây không phải lượt gọi live thứ hai.
