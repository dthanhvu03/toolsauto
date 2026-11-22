# PLAN-177 — Smoke cầu nối repo theo handoff ngày 19/11/2026

## Kết quả

**Đã thực hiện xong lượt smoke và phục hồi bản cũ. Kết quả chức năng: CHƯA ĐẠT.** Cầu nối repo không chuẩn bị xong portal trong giới hạn 45 giây. Vì vậy chưa gọi NativeShopeeQuoteClient hoặc shortlink của cầu nối repo; không được ghi rằng native đã thành công.

**Bản cũ đã phục hồi:** health từ WSL trả 200; shortlink cũ HTTP 200, success=true, host=s.shopee.vn. Cấu hình nguồn khách, .env và Cashbot/Zalo giữ nguyên.

Handoff: .comms/handoffs/cursor-to-ag/TASK-plan177-repo-bridge-native-smoke.md. GateB có hiệu lực cho lượt thử này; GateA và duyệt bật nguồn khách không thay đổi.

## Bằng chứng chính

Thời điểm bắt đầu: 2026-11-19T16:11:35.021Z, tức 23:11:35 giờ Việt Nam ngày 19/11.

| Bước | Kết quả thật |
|---|---|
| Khởi tạo browser context | Xong 7,712 giây |
| Đồng bộ cookie có sẵn trong bộ nhớ | Xong 7,832 giây; không xuất giá trị |
| Nhận tab trong profile | Xong 7,846 giây |
| Bắt đầu điều hướng Affiliate |7,854 giây |
| Hết ngân sách chuẩn bị |45,053 giây; timeout |
| Thu hồi tác vụ / context |52,067 giây; cleanup.closed=true; cả harness 52,898 giây |
| Health cầu nối repo | Chưa tới bước mở listener; không có bằng chứng health repo thành công |
| Native quote | Không gọi vì prepare chưa sẵn sàng |
| Shortlink repo | Không gọi vì prepare chưa sẵn sàng |
| Khôi phục PM2 legacy | pm2 start mã thoát 0; online PID 3147903 |
| Health legacy từ WSL | HTTP 200/statusok; response không có implementation=toolsauto |
| Một shortlink legacy sau phục hồi | HTTP 200/success=true/host s.shopee.vn;15,62 giây |

Lượt này không gặp lại 403/90309999 ở request quote vì request quote chưa được gọi. Không dùng việc không gặp 403 để kết luận đã chứng minh phiên đăng nhập trên cầu nối repo.

Nguyên nhân gốc của việc điều hướng không hoàn tất vẫn chưa xác định từ dữ liệu hiện có. Chưa sửa lifecycle của bridge, không tăng timeout để che lỗi và không gọi lặp.

## Ranh giới và phục hồi

- Lệnh gộp ban đầu bị công cụ kiểm duyệt từ chối trước thực thi, không cung cấp lý do chi tiết. Lượt được chấp nhận sau đó thu hẹp địa chỉ lắng nghe về mạng WSL 192.168.112.1 thay vì mọi interface; chỉ cho peer WSL 192.168.112.133. Bản repo chưa tới bước listen do prepare thất bại.
- Chỉ dừng/bật PM2 shopee-mcp. Browser/repo được đóng trong finally; shell ngoài luôn pm2 start legacy.
- Không còn process harness. Hash npm giữ nguyên 9F8E47F0A9F02D198A0390E193A29B3937A92DF04E76937C5835B4BCAB8EECBC.
- Hash .env, launcher, config, service, nativeclient và bridgebrowser/index/server trước/sau đều khớp. Không sửa mã production.
- PRODUCT_QUOTE_PRIMARY chưa set; mặc định product_data. SHOPEE_BRIDGE_IMPLEMENTATION chưa set; mặc định legacy.
- Cashbot PID 1456507 và Zalo PID 1456511 cùng mốc khởi động giữ nguyên, đều active. Các PID ứng dụng PM2 khác cũng giữ nguyên.
- Không bật nguồn cho khách, không restart Cashbot/Zalo, không sửa DB hoặc commit/push.

## Lệnh và artifact

- Node --check reports/plan177/repo-native-handoff-smoke.mjs: exit0.
- WindowsNode chạy harness trong try/finally; repo_smoke_exit=0 nghĩa là script đã ghi kết quả và dọn dẹp, **không** có nghĩa smoke chức năng đạt. Trường result là failed_before_required_completion, error=timeout.
- Khôi phục: legacy_restore_pm2_exit=0; WSL get_bridge_url()+/health HTTP 200; một request shortlink legacy thành công.
- repo-native-handoff-smoke-20261119.json: kết quả và các giai đoạn của lượt smoke.
- repo-smoke-handoff-baseline-20261119.json / repo-smoke-handoff-after-20261119.json: hash, PRIMARY, PID/thời gian khởi động trước/sau.
- repo-smoke-legacy-restore-20261119.json: kết quả shortlink legacy sau phục hồi.
- repo-native-handoff-smoke-executed.mjs: đúng mã harness đã chạy, SHA ghi trong proof; bản sao được kiểm hash.
- repo-native-handoff-smoke.mjs: harness dùng cho lần sau. Sau lượt này chỉ sửa URL health/shortlink của harness để trỏ đúng interface cục bộ nếu prepare thành công; chưa chạy lại, không thay mã production.

Các artifact chỉ lưu dữ liệu đã lọc; không cookie/CSRF/token/tên sản phẩm đầy đủ/raw body.

## Điều kiện hoàn thành handoff lượt này

- [x] Có JSON và báo cáo tiếng Việt.
- [x] Smoke thất bại có phân loại, không báo native/shortlink repo đã chạy khi chưa chạy.
- [x] Legacy health 200 và một shortlink sau phục hồi thành công.
- [x] PLAN/TASK/status được cập nhật, nguồn khách không đổi.

**Việc tiếp theo:** kiểm tra cụ thể lifecycle điều hướng portal của bản repo so với POC/legacy trước khi sửa mã; giữ thời gian chờ có giới hạn. Sau sửa phải smoke lại repo health + native quote đúng shop/item + shortlink trên cùng phiên và restore legacy. Claude kiểm tra, Anti/anh duyệt bật chỉ sau khi đủ bằng chứng.

Chỉ hoàn tất handoff smoke này theo nhánh thất bại có proof; **không** đánh dấu toàn TASK-063 hoặc PLAN-177 hoàn tất/lưu trữ.

Kiểm tra artifact cuối: `git diff --check` mã thoát 0; quét 7 artifact mới không thấy giá trị cookie/CSRF/token từ tệp phiên hiện có (0 giá trị khớp).
