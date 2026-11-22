# PLAN-177 — Kết quả chẩn đoán tiếp bước 2.4 ngày 19/11/2026

## Kết luận và việc cần làm

Đã hoàn thành một mục chẩn đoán có giới hạn, không chuyển sang mục sửa mã hay bật nguồn mới. Lượt mới chứng minh browser mở được trang Affiliate, nhưng API hoa hồng từ chối request bằng HTTP 403 và mã 90309999. Cần chủ tài khoản kiểm tra phiên Shopee Affiliate dùng cho bot và hoàn tất yêu cầu đăng nhập/xác minh nếu Shopee đưa ra. Chưa có bằng chứng phân biệt hết phiên, xác minh bảo mật hay lý do từ chối khác; không tự gán nguyên nhân.

Không gọi tiếp API hoa hồng, không đổi dấu vân tay trình duyệt, không vượt CAPTCHA và không tăng timeout để thử vượt chặn.

## Bằng chứng thực tế

Thời điểm script:2026-11-19T15:45:34.594Z, tương đương22:45:34 ngày 19/11 giờ Việt Nam.

| Phép đo | Kết quả |
|---|---|
| Windows HEAD tới trang Affiliate | HTTP 200, tổng0,783054s |
| Cầu nối cũ trước phép đo | health200; shortlinkHTTP500 với page.evaluate TypeError Failed to fetch |
| Tải WSL | load average1,00/0,82/1,07 |
| Khởi tạo context browser | xong1930ms |
| Đồng bộ cookie có sẵn trong bộ nhớ | xong2016ms; không lưu mới hoặc xuất giá trị |
| Bắt đầu điều hướng trang Affiliate |2031ms |
| Tài liệu chính trả lời | HTTP 200 ở2525ms |
| Browser xác nhận đã chuyển đến trang |2540ms, đúng originAffiliate và đườngoffer |
| Trạng thái tài liệu | interactive, cóbody; không thấy chuyển sang đườngauth/verify trong phép kiểmtra đườngdẫn |
| Một request lấy chi tiết sản phẩm POC | HTTP 403, mã 90309999; script ghi nhãn verification_required và không xuất raw body |
| DOMContentLoaded |3740ms |
| Đóng context | xong5165ms; closed=true |
| Sau khôi phục cầu nối cũ | health200 trong0,016894s; không còn processscriptchẩnđoán |

Đây không phải quote thành công. Chưa lấy được giá/hoa hồng từ request mới, chưa chứng minh native sẵn sàng.

Script dùng waitUntil=commit để đo thời điểm tài liệu được browser nhận; vẫn ghi riêng sự kiện DOMContentLoaded. Cách này chỉ nằm trong script chẩn đoán, không thay lifecycle chuẩn bị của cầu nối phục vụ khách. Kết quả cho thấy lỗi chờ45s cũ không tái hiện ở lần tải máy thấp này; không từ đó kết luận timeout cũ chỉ do tải máy.

## Môi trường và ranh giới giữ nguyên

- Chỉ dừng/bật riêng PM2 shopee-mcp để mượn đúng profile, đóngcontext trong finally và phục hồi legacy trong finally.
- Không sửa .env, npm, codeproduction hoặc DB khách; không restart Cashbot/Zalo, không commit/push.
- Hash npm giữ nguyên 9F8E47F0A9F02D198A0390E193A29B3937A92DF04E76937C5835B4BCAB8EECBC.
- Công cụ đọc UI Windows không truy cập được cửa sổ do lỗi nhận diện Chrome; đây là lỗi công cụ, không là bằng chứng portal có hay không có màn hình xác minh.
- Không có cookie/CSRF/token/tên sản phẩm/rawpayload trong kết quả xuất.

## Lệnh và artifact

- Node --check reports/plan177/runtime-lifecycle-probe.mjs: exit0.
- Đã chạy WindowsNode với SHOPEE_PROFILE_DIR đúng profile có sẵn và SHOPEE_DOMAIN=shopee.vn; script kết thúc exit 0; shell ghi legacy_bridge_restored.
- Báo cáo máy: runtime-resume-baseline-20261119.json và runtime-lifecycle-20261119.json.
- Script tái hiện: runtime-lifecycle-probe.mjs. Chỉ chạy khi legacy đã dừng, có quyềnGate B và sau khi chủ tài khoản xử lý phiên; không chạy lặp để vượt 403.

## Điều kiện chuyển mục

1. Chủ tài khoản xác nhận đã kiểm tra đăng nhập/xác minh trong đúng phiênShopeeAffiliate dành cho bot.
2. Chạy lại mộtrequest có giới hạn; nếu 403 còn thì dừng, ghi nguyên trạng và phân loại bằng bằng chứng bổ sung, không néchặn.
3. Khi request trảcode0 và đúng shop/item, thử client/cầu nối mới cùng shortlink theoPLAN; có bằng chứng rồi mới nhậnmục sửa tiếp nếu cần.
4. Claude/Anti/anh duyệt bật chính thức vẫn giữ nguyên.

Mục chẩn đoán này đã có điểm kiểm tra và cleanup được đọc lại. Phần chạy thật của TASK-063 còn chờ chủ tài khoản; không đánh dấu toàn TASK xong.

## Cập nhật sau Owner «xong» (~22:58 VN)

Owner xác nhận UI vẫn đăng nhập, không logout/login. Thử lại một request: detail `item_id=54321049804` → HTTP 200 / code 0 / ids_exact; shortlink OK trước và sau restore bridge. Chi tiết: [POST-XONG-RETRY-20261119.md](POST-XONG-RETRY-20261119.md). Native vẫn chưa bật cho khách.
