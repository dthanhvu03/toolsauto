# PLAN-177 — Bridge R&D tiếp theo: capture commission từ Affiliate portal

- Ngày: 2026-11-19 (VN)
- Phạm vi: R&D read-only với session bridge `shopee-mcp`; không thay luồng Cashbot, không bật quote cho khách, không lưu cookie/session/CSRF/raw response.
- Kết quả: **chưa lấy được giá/hoa hồng/XTRA từ native portal**.

## Điều đã xác minh

- Bridge `/health` trả HTTP 200 trước và sau thử nghiệm; cuối lượt PM2 `shopee-mcp` online.
- POC trước đó chứng minh `productOfferLinks` tạo short offer link 6/6, nhưng type chỉ trả link.
- `/api/capture_offer_gql` bắt được 6 request khi trang product offer chạy. Hai request product list là `/api/v3/offer/product/list`, nhưng route chỉ lưu 220 ký tự đầu response nên không tới phần field offer.
- `/api/hook_fetch_offer` chỉ thấy analytics `/g/collect`; route wrap `window.fetch`, không bắt request XHR product list.
- `/api/gql_guess` xác nhận `productOfferV2` không có trong portal schema. GraphQL gợi ý `GetProductOfferList`, nhưng phép gọi schema không có arguments trả `error parameter`; chưa biết input type/required args.
- `/api/open_product_offer`: Open API `productOfferV2` trả `Failed to fetch`; portal GraphQL trả HTTP 400, `productOfferV2` không có trên Query.

## Thử capture tạm và cleanup

- Đã thêm tạm route cục bộ để bắt response chỉ từ `/api/v3/offer/product/list`, parse in-memory và chỉ trả tên field + giá trị số phù hợp (`price`, `commission`, `rate`, `XTRA`). Không trả headers, cookie, CSRF, token, tên sản phẩm, ID hay raw body.
- Lần đầu route tạm không giới hạn peer trong khi listener bridge hiện có bind `0.0.0.0` và CORS `*`. Chỉ có request của agent từ WSL được chủ động gửi; **không có access log đủ để xác minh hay loại trừ truy cập khác** trong khoảng route hoạt động. Output route là danh sách field số đã lọc, không chứa credential/header/raw response. Route đã bị gỡ ngay sau capture.
- Lần kế tiếp giới hạn peer `192.168.112.133`; kết nối WSL bị HTTP 403 vì địa chỉ peer bridge nhìn thấy khác giá trị đó.
- Lần loopback `127.0.0.1` tới route capture trả HTTP 500 trước khi có data.
- Restore file npm-installed bridge từ backup tạm: SHA-256 trở lại `9F8E47F0A9F02D198A0390E193A29B3937A92DF04E76937C5835B4BCAB8EECBC`, khớp hash trước thử; Windows Node `--check` PASS. Backup tạm đã xóa. Restart chỉ `shopee-mcp`, không restart Cashback.
- Trạng thái cuối: `shopee-mcp` online, `/health` HTTP 200. Không có route capture tạm còn lại.

## Kết luận / việc tiếp theo

- Chưa có payload đủ dùng để map `sure_commission`; **không dùng giá/hoa hồng cũ từ DB làm quote native**.
- Capture trong bridge cần được thiết kế thành adapter repo-owned, có ranh giới truy cập local được kiểm chứng, timeout, và chỉ xuất allowlist field. Chẩn đoán route tạm hiện thất bại do browser/page capture hoặc topology peer; chưa xác định nguyên nhân HTTP 500.
- Phương án ít rủi ro hơn cho lần tiếp: bật Network/DevTools ngay trong cửa sổ Affiliate sẵn đăng nhập, hoặc xây repo-owned local bridge wrapper/source trước khi lặp lại capture. Không chia sẻ cookie/session; scrub body trước khi ghi báo cáo.
- Gate B vẫn **partial**; Phase 2 native quote chưa được chứng minh.
