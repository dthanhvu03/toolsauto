# PLAN-177 — Lấy giá, hoa hồng và tạo link trực tiếp từ Shopee Affiliate

| Thông tin | Nội dung |
|---|---|
| Mã kế hoạch | PLAN-177 |
| Trạng thái | **VERIFY smoke OK. Pilot P0/P1 đã lên kế hoạch: PLAN-180 / TASK-066 (draft, chờ Owner duyệt rồi mới bật).** |
| Người thực hiện | Codex điều phối các agent theo yêu cầu trực tiếp của anh ngày 19/11/2026. Phần giai đoạn 1 trước đó do Cursor làm. |
| Yêu cầu của anh | Ngày 18/11: không để Product Data lỗi làm chặn tạo link. Ngày 19/11: cho triển khai và giao agent làm lần lượt từng mục. |
| Liên quan | PLAN-174; `shopee_shortener.py`; `product_data.py`; `policy_snapshot.py`; `sale_relay.py`; ADR-067; yêu cầu chống SSRF trong `PROJECT.md` |
| Kiểm tra và bàn giao | Claude Code kiểm tra luồng khách; Antigravity (Anti) rà soát và ký duyệt theo quy trình. Anh quyết định khởi động lại bot và bật chính thức. |

## Đọc nhanh — Hiện mình ở đâu, tiếp theo làm gì?

**Mục tiêu:** khách gửi link Shopee → bot lấy được giá và hoa hồng → tính tiền hoàn theo chính sách đang dùng → trả link mua có mã theo dõi của khách.

**Nếu không lấy được hoa hồng:** thử nguồn Product Data dự phòng. Nếu cả hai nguồn đều lỗi nhưng đã xác định đúng sản phẩm, vẫn tạo link mua và ghi rõ chưa ước tính được tiền hoàn; không tự điền số 0 hay bịa tỷ lệ.

| Phần việc | Kết quả đã có | Còn thiếu |
|---|---|---|
| Tìm cách đọc dữ liệu Shopee | Đã lấy đúng 8 sản phẩm; có cả món có và không có hoa hồng XTRA. Giá và hoa hồng dùng để báo hoàn khớp Product Data trên 8 mẫu. | Đây là bằng chứng từ các mẫu thử, chưa chứng minh nguồn luôn hoạt động ổn định. |
| Viết cầu nối với phiên đăng nhập Affiliate | Đã có mã repo và giới hạn thời gian; 38 kiểm thử Node đạt. Cách chờ B đã lấy quote đúng ID và tạo shortlink thật trên một sản phẩm. | Cần Claude kiểm tra; một mẫu chưa chứng minh ổn định lâu dài. Legacy vẫn mặc định. |
| Viết bộ đọc giá và hoa hồng | Đã có, kiểm tra đúng mã shop/sản phẩm, tỷ lệ, mức trần và thời hạn; 98 bài kiểm thử riêng đạt. | Chưa có giờ Shopee cập nhật dữ liệu để xác minh độ mới của nguồn. |
| Ghép vào bot và thêm đường dự phòng | Đã có; 30 bài kiểm thử tích hợp riêng đạt. | Chưa đủ điều kiện bật nguồn Shopee mới cho khách. |
| Rà soát độc lập | Bộ Python cuối: 239 đạt, 1 lỗi đo thời gian. Chạy riêng đúng bài lỗi, giữ nguyên ngưỡng và mã: đạt. | Không được báo rằng cả bộ 240 bài đã cùng đạt trong một lượt. |

**Cập nhật mới nhất — 23:34 ngày 19/11:** sau A/B, đã sửa phần chờ trang theo B và smoke cầu nối repo thành công: chuẩn bị 14,238 giây, native quote đúng shop/item 1,347 giây, shortlink 0,193 giây. Đã phục hồi legacy, health 200 và shortlink thành công. Không bật native cho khách. Xem `reports/plan177/LIFECYCLE-B-NATIVE-SMOKE-20261119.md`. Các lỗi trước đó được giữ bên dưới theo lịch sử.

**Trình tự xử lý phần còn vướng:**

1. **Đã xử lý phần chờ portal theo bằng chứng A/B.** Bản repo đã chờ DOMContentLoaded/networkidle và nghỉ 2,5–4 giây, có cache cho đúng tài liệu và chặn điều hướng xen giữa. Lượt smoke một món đã đạt; không suy rằng mọi timeout cũ đều cùng nguyên nhân.
2. **Đã thử lại một lượt nhỏ và phục hồi.** Quote native đúng shop/item và shortlink qua repo đạt trên cùng phiên; legacy sau phục hồi cũng health/shortlink đạt. Giữ bằng chứng các lượt lỗi cũ và giới hạn một mẫu.
3. **Claude kiểm tra, Anti duyệt, anh cho bật thử.** Chỉ đổi nguồn mặc định và khởi động lại Cashbot khi đủ các điều kiện đã thống nhất. Theo dõi lỗi, thời gian trả lời và chênh lệch hoa hồng; có cờ quay lại nguồn cũ.

**Trạng thái được ghi nhận ở lần kiểm tra cuối:** cấu hình vẫn dùng Product Data và cầu nối cũ; không sửa `.env`, không khởi động lại Cashbot/Zalo, không commit/push. Chưa đánh dấu hoàn tất toàn kế hoạch.

### Một số từ kỹ thuật trong kế hoạch

- **Nguồn Shopee trực tiếp** (`native`): lấy dữ liệu trong trang Shopee Affiliate bằng phiên đăng nhập hiện có.
- **Cầu nối** (`bridge`): chương trình trên Windows giúp bot trong WSL gọi phiên Affiliate đó.
- **Product Data / PD**: nguồn dữ liệu AddLiveTag đang dùng, giữ lại làm dự phòng.
- **Thử nghiệm nhỏ / POC**: lấy một số mẫu để chứng minh cách làm; không đồng nghĩa đã chạy ổn cho mọi khách.
- **Kiểm tra thật / live**: gọi hệ thống bên ngoài bằng phiên thực, khác với dữ liệu giả trong kiểm thử.
- **Giới hạn thời gian / deadline**: thời điểm phải ngừng chờ và chuyển sang phương án an toàn.
- **Bản ghi chính sách / snapshot**: lưu nguồn và chính sách đã dùng lúc tạo link để sau này đối chiếu.
- **XTRA**: phần hoa hồng từ người bán. Hoa hồng dùng để tính tiền hoàn không phải toàn bộ số tiền khách sẽ nhận.

> Tên file, lệnh, tên biến, mã API và kết quả máy in ra được giữ nguyên để lập trình viên đối chiếu. Phần diễn giải viết bằng tiếng Việt. Các kết quả bên dưới là lịch sử đã ghi nhận ngày 19/11/2026, không phải lần kiểm tra trực tiếp mới.

## 1. Bối cảnh — Vấn đề cần giải quyết

- Ngày 18/11, khoảng 21:35 giờ Việt Nam: Product Data báo `Database connection failed`. Cashbot chặn tạo link vì luồng cũ bắt buộc lấy được báo giá trước khi tạo `an_redir` hoặc ký AffiPad.
- Lượt kiểm tra chỉ đọc cùng ngày ghi nhận: nhóm `data.*` lỗi; `conversions.php` và `shopee-link.php` hoạt động khi có URL. Lượt kiểm tra này không tự thay thế quyền gọi thật trong từng bước của kế hoạch.
- Hệ thống đã có những cách tạo link không cần Product Data: `build_an_redir`, `batchCustomLink` qua cầu nối, AffiPad và AMS.

## 2. Mục tiêu

1. Product Data lỗi vẫn tạo được link hợp lệ; **không bịa số hoàn**.
2. Sau khi đủ bằng chứng và được duyệt, ưu tiên lấy báo giá trực tiếp từ Shopee Affiliate.
3. Giữ Product Data làm dự phòng. Tắt nó trong một luồng báo giá không đồng nghĩa gỡ toàn bộ AddLiveTag hoặc khóa API.
4. Giữ `sub_id`, cách ký AffiPad, ví khách, đối soát và AMS; không đổi chính sách tiền.
5. Ghi đúng `quote_source` (nguồn báo giá) và `link_source` (nguồn tạo link).

## 3. Quy tắc kỹ thuật phải giữ

### 3.1 Phân biệt tạo link với báo tiền hoàn

| Dữ liệu | Cần để tạo link? | Cần để hiện tiền hoàn? |
|---|---|---|
| Mã shop, mã sản phẩm, `product_url` | Có | Có |
| Chỉ có giá sản phẩm | Không bắt buộc | **Chưa đủ**, không được tự suy ra hoa hồng |
| Hoa hồng hoặc tỷ lệ và thành phần đã xác minh | Không | **Bắt buộc** |
| Công thức tiền | Không áp dụng | Dùng lại `sure_commission_vnd` và `cashback_for` hiện tại |

**Cấm:** lấy `price × 2,5%` hoặc tỷ lệ cố định bất kỳ để bịa hoa hồng khi nguồn chưa cung cấp đủ dữ liệu. Không lưu `quote_*=0` như thể đã tính nếu thực tế chưa biết.

**Được khi thiếu hoa hồng:** tạo link, báo chưa ước tính, lưu `quote_*=NULL` và `quote_source=degraded_unquoted`. Nếu nguồn xác nhận hoa hồng thật bằng 0, phải phân biệt với trường hợp không có dữ liệu.

### 3.2 Thứ tự nguồn và cách tạo link

- **Khi đã bật nguồn mới:** Shopee trực tiếp → Product Data hợp lệ → link chưa có số hoàn.
- **Mặc định hiện tại:** `PRODUCT_QUOTE_PRIMARY=product_data`. Chỉ chọn `native` khi bật thử có chủ đích; không tự đổi mặc định.
- **Link mua:** tạo `an_redir`, thử rút gọn trong thời gian còn lại; có thể dùng `shopee-link.php` nếu cờ đã bật và đủ quyền; nếu không rút gọn được thì giữ link dài.
- Nếu chưa xác định được sản phẩm hợp lệ thì báo lỗi tạm thời, không tạo link trỏ sai món.

### 3.3 Mở link rút gọn an toàn — Tối đa 3 lần chuyển hướng

Giữ **tối đa 3 lần chuyển hướng**, đúng `PROJECT.md`. Không tự đổi thành 5. Muốn đổi phải có căn cứ và được Anti/anh duyệt riêng.

Mỗi chặng và URL cuối phải kiểm tra:

1. Giao thức chỉ `http` hoặc `https`; tách đúng tên miền, không có thông tin đăng nhập trong URL.
2. Tên miền thuộc danh sách cho phép. Link rút gọn chỉ là chặng trung gian; URL cuối phải lấy được shop/sản phẩm trên `shopee.vn` hoặc `www.shopee.vn` bằng đường dẫn `/product/`, `-i.` hoặc `/opaanlp/`.
3. Kiểm tra mọi IP từ DNS; chặn IP nội bộ, loopback, link-local, reserved, multicast và dạng IPv4 nằm trong IPv6. Đây là chống SSRF: tránh để link khách khiến máy gọi địa chỉ nội bộ.
4. Không đi tiếp khi URL hoặc IP vi phạm; tổng không quá 3 lần chuyển hướng.
5. Mỗi chặng chờ tối đa 3 giây, tổng phần mở link tối đa 8 giây và vẫn phải nằm trong ngân sách chung.

### 3.4 Giới hạn thời gian chung

- Dùng một mốc `time.monotonic()` cho chuỗi mở link, lấy báo giá, chờ khóa cầu nối, rút gọn, gọi dự phòng và ký AffiPad. Ngân sách cấu hình đang dùng là **20 giây**; chưa phải cam kết thời gian phản hồi tuyệt đối với khách.
- Mỗi bước chỉ dùng phần thời gian còn lại; không cộng các timeout riêng thành tổng dài hơn dự kiến.
- Khi hết thời gian, nếu đã biết sản phẩm và tạo được `sub_id` thì trả link `an_redir` dài; nếu chưa có báo giá thì để trống số hoàn. Nếu đã lấy được báo giá hợp lệ thì giữ số đã có và bỏ các bước gọi ngoài còn lại.
- Nếu chưa xác định được URL hợp lệ thì báo lỗi tạm thời.
- Kiểm thử phải chứng minh thời gian chờ khóa và gọi HTTP có bị ngắt; không chỉ đo timeout khai báo.
- **Giới hạn đã biết:** DNS/TLS đồng bộ của hệ điều hành, ghi SQLite và lúc tiến trình bị hệ điều hành tạm ngừng không bị hủy cứng. Vì vậy không được từ các bài kiểm thử này suy ra toàn bộ lượt xử lý luôn xong dưới 20 giây.
- Khởi tạo phiên browser là bước riêng trước khi cầu nối báo sẵn sàng: giới hạn chuẩn bị cuối là 45 giây; tiến trình có chặn an toàn lúc khởi động ở 55 giây. Giới hạn request tối đa vẫn 20 giây; client báo giá mặc định 8 giây.

### 3.5 Kết nối WSL ↔ Windows

| Thành phần | Quy định |
|---|---|
| Cầu nối | Chạy trên Windows, PM2 `shopee-mcp`, cổng `9224` |
| Bot trong WSL | Dùng `get_bridge_url()` và `get_bridge_host()`; ưu tiên `SHOPEE_BRIDGE_HOST` hoặc địa chỉ gateway từ `/proc/net/route` |
| Địa chỉ lắng nghe | Mặc định bản mới là `127.0.0.1`. Muốn cho WSL gọi phải cấu hình địa chỉ phù hợp và danh sách IP nguồn chính xác. Có thể dùng `0.0.0.0` có ràng buộc; không mở ra Internet. |
| Ranh giới truy cập | Kiểm tra IP nguồn, `Origin` và `Host`; không cho trình duyệt từ trang khác gọi tùy tiện; không cấp CORS `*` |
| Dữ liệu đăng nhập | Chỉ dùng trong bộ nhớ theo cơ chế đang có; không ghi log, xuất trả hoặc lưu mới cookie/CSRF/token |
| Khi bận/lỗi | Chờ trong thời gian còn lại, sau đó chuyển sang link dài hoặc nguồn dự phòng đã bật; lỗi liên tiếp thì tạm ngừng gọi |
| Bằng chứng cần có | WSL gọi được, quyền truy cập bị giới hạn, một lần lấy quote thật và tạo shortlink thật. `/health` trả 200 chỉ chứng minh chương trình trả lời, chưa chứng minh portal đang dùng được. |

Không giả định rằng bot WSL chỉ gọi được `127.0.0.1:9224`. Không đổi cấu hình tường lửa hoặc mở quyền mạng rộng hơn chỉ để vượt lỗi thử nghiệm.

### 3.6 Các dạng link khách được nhận

| Dạng | Tên miền / đường dẫn |
|---|---|
| Sản phẩm chuẩn | `shopee.vn` / `www.shopee.vn` + `/product/{shop}/{item}` |
| Link có tên sản phẩm | Có đoạn `-i.{shop}.{item}` |
| Link rút gọn | `s.shopee.vn/{code}` |
| Link rút gọn Việt Nam | `vn.shp.ee/{code}` |
| Link chuyển tiếp có URL gốc | `s.shopee.vn/an_redir?origin_link=`; lấy URL gốc ra để kiểm tra |
| URL sau chuyển hướng | `…/opaanlp/{shop}/{item}` |

Ngoài danh sách thì trả `invalid_link`. Cầu nối rút gọn còn phải giữ các link shop, voucher và chiến dịch đang được luồng cũ hỗ trợ; không vì thêm báo giá mà làm hỏng chúng.

### 3.7 Ghi đúng nguồn báo giá và nguồn tạo link

`policy_snapshot.QUOTE_SOURCE` trước đây mặc định cứng là `product_data`. Giai đoạn triển khai cho phép `record(..., quote_source=)` nhận:

- `product_data`: lấy báo giá từ Product Data.
- `native_shopee`: lấy trực tiếp từ Shopee Affiliate.
- `degraded_unquoted`: đã tạo link nhưng chưa có số hoàn.

`link_source` ghi `an_redir`, `bridge_short` hoặc `alt_shopee_link`. Dữ liệu native không có giờ cập nhật nguồn nên `product_last_update=NULL`; lưu `fetched_at` riêng cùng căn cứ giá thấp nhất và khoảng giá biến thể.

### 3.8 Giới hạn thay đổi đối với AddLiveTag

| Chức năng đang dùng | File | Trong giai đoạn 1–2 có gỡ không? |
|---|---|---|
| Báo giá Product Data | `product_data.py`; service/poller/Zalo gọi | Bỏ phụ thuộc bắt buộc, giữ làm dự phòng |
| Lịch sử giá / theo dõi giá | `price_watch.py` | Không |
| Tìm deal | `deals.py`, `MarketSearchClient` | Không |
| Đối chiếu đơn / chuyển đổi | `addlivetag_orders.py` | Không |
| Khóa bắt buộc lúc khởi động | `config.py`, `ADDLIVETAG_API_KEY` | Vẫn bắt buộc khi những chức năng ngoài phạm vi còn dùng |
| Link dự phòng `shopee-link.php` | `alt_shopee_link.py` | Đã có mã nhưng cờ mặc định tắt; gọi thật còn chờ Gate A |
| Chuyển tiếp voucher ra kênh | `voucher.py` | Không nằm trong phần gỡ Product Data |
| RioHub | Dùng khóa riêng | Không |

**Kế hoạch này chưa cho phép gỡ toàn bộ AddLiveTag.**

## 4. Quyền chạy thật và phối hợp

### 4.1 Claude Code / ADR-067

Claude Code phụ trách vận hành luồng khách của Cashbot. Phải phối hợp và được kiểm tra trước khi đưa thay đổi vào môi trường phục vụ khách. Anh thực hiện lệnh khởi động lại khi sẵn sàng; agent không tự khởi động lại Cashbot/Zalo.

### 4.2 Gate A — Quyền thử link dự phòng AddLiveTag

- Áp dụng riêng cho `shopee-link.php`, khác quyền thử Shopee Affiliate ở Gate B.
- Trước khi gọi thật hoặc dùng kết quả probe 18/11 làm bằng chứng nghiệm thu, phải ghi nhận anh cho phép riêng: `1.3-live-ok` hoặc `1.3-accept-probe-20261118`.
- Chưa có quyền này thì chỉ kiểm thử giả lập; không đánh dấu phần gọi thật đã đạt.
- Mọi tài liệu phải loại bỏ cookie, phiên đăng nhập, Authorization, CSRF, token và thông tin cá nhân.
- **Trạng thái: còn chờ; cờ ALT vẫn tắt.**

### 4.3 Gate B — Quyền thử Shopee Affiliate bằng phiên đăng nhập

- **Bước 0.0 đã được anh cho phép ngày 19/11:** «sao mình không làm gate B luôn».
- Gate A và Gate B không thay thế nhau.
- **Bước 0.1 đã có bằng chứng kỹ thuật:** `GET /api/v3/offer/product?item_id=...` trả giá và thành phần hoa hồng/mức trần. Có 8 sản phẩm khớp cả shop/item, gồm 7 XTRA và 1 không XTRA theo PD; đủ 6 mẫu gốc sau khi thử lại.
- Giá và `sure_commission` khớp PD trên 8 bản ghi thành công; **không phải 8/8 request luôn thành công**. Đợt đầu chỉ 6/12 lượt thành công.
- Bước 0.2 có bảng so sánh nhưng còn giới hạn dữ liệu PD lưu sẵn và độ mới nguồn. Bước chọn nguồn 0.3 đã được anh đồng ý triển khai theo hướng REST detail; duyệt Anti/Claude trước khi bật chính thức vẫn còn.
- Bằng chứng: `reports/plan177/PORTAL-DETAIL-POC-20261119.md` và JSON liên quan.

## 5. Các bước triển khai

### Giai đoạn 0 — Thử nghiệm nhỏ để xác minh dữ liệu

| Bước | Việc làm | Điều kiện / kết quả |
|---|---|---|
| 0.0 | Xin quyền thử portal thật | Anh đã cho phép; ghi ở mục 4.3 |
| 0.1 | Ít nhất 5 sản phẩm có cả XTRA và không XTRA; lấy giá và hoa hồng | Đã có 8 mẫu đúng ID; báo cáo và JSON đã loại thông tin đăng nhập |
| 0.2 | So sánh với Product Data lúc gọi được | Có bảng 8 mẫu; vẫn phải ghi rõ giờ lấy, giờ nguồn cập nhật và dữ liệu lưu sẵn |
| 0.3 | Chọn portal REST detail, GraphQL hay Open API | Hướng REST detail đã được anh đồng ý cho viết mã; duyệt cuối theo quy trình trước khi bật chính thức |

### Giai đoạn 1 — Product Data lỗi vẫn tạo được link

| Bước | Việc làm | Điều kiện đạt |
|---|---|---|
| 1.0 | Claude kiểm tra thiết kế luồng khách | Có kết quả kiểm tra/bàn giao |
| 1.1 | Mở link tối đa 3 lần chuyển hướng, kiểm tra SSRF từng chặng | Kiểm thử URL, DNS và IP |
| 1.2 | Khi Product Data lỗi, tạo link chưa có số hoàn; dùng mốc thời gian chung | Link và `sub_id` đúng; kiểm thử timeout |
| 1.3 | Thêm client `shopee-link` và cờ bật/tắt | Kiểm thử giả lập; phần thật chỉ sau Gate A |
| 1.4 | Thêm thông báo chưa ước tính được và cờ quay lại cách cũ | Kiểm thử thông báo |
| 1.5 | Ghi nguồn báo giá / tạo link vào snapshot | `record` nhận đúng nguồn |
| 1.6 | Kiểm tra WSL gọi Windows và ràng buộc truy cập | Có kết quả thực tế; không mặc định chỉ dùng localhost |

Mã giai đoạn 1 trước đây do Cursor triển khai trên nhánh `cursor/task-063-shopee-native-product-quote`. Kết quả riêng đã ghi nhận 164 bài kiểm thử đạt. Không từ đó kết luận giai đoạn 1 đã được Claude/Anti nghiệm thu hay đã chạy trong bot khách.

### Giai đoạn 2 — Thêm nguồn báo giá Shopee trực tiếp

Anh đã yêu cầu ngày 19/11: «oke vậy em cho agent triển khai từng mục giúp anh nhé». Codex giao agent làm **lần lượt**; chưa cho phép tự bật mặc định hoặc ký thay Claude/Anti.

| Bước | Việc đã làm / file | Bằng chứng và trạng thái |
|---|---|---|
| 2.1 Cầu nối | `scripts/shopee_bridge/` và lựa chọn khởi động trong `run_shopee_mcp.sh`. Báo giá, rút gọn và voucher dùng chung phiên/hàng chờ. Source do repo quản lý, không sửa thư mục npm. | 38 bài Node đạt; smoke theo B đúng một sản phẩm và shortlink đạt. Đã phục hồi bản cũ làm mặc định. |
| 2.2 Client và bộ đọc dữ liệu | `cashback_bot/native_shopee_quote.py`, `tests/test_native_shopee_quote.py`, `tests/fixtures/native_shopee_quote_poc.json` | 98 bài riêng đạt; dùng Decimal/số nguyên, đúng ID/kênh/split/cap/thời hạn; 8 mẫu thật; không bịa giờ cập nhật nguồn. |
| 2.3 Ghép thứ tự nguồn | `config.py`, `service.py`, `product_data.py`, `affipad.py`, `alt_shopee_link.py`, `shopee_shortener.py` và helper `deadline_http.py` | 30 bài riêng đạt. Mặc định PD; khi bật thì native → PD → link chưa có số. Giữ công thức tiền, snapshot, `sub_id` và ký Meta. Không cần sửa khởi tạo riêng cho Telegram/Zalo. |
| 2.4 Rà soát và chạy thật | Kiểm thử, review độc lập và smoke có giới hạn theo Gate B trong `reports/plan177/` | Bridge 38/38 đạt; native quote + shortlink thật đã đạt một món theo B. Python full lịch sử vẫn 239 đạt/1 lỗi timing, ca riêng đạt. Chưa đủ điều kiện tự bật cho khách. |

Phạm vi helper HTTP đã được ghi nhận trong bước 2.3: mỗi lượt có kết nối và deadline riêng, ngắt socket khi quá giờ, giới hạn response, không tự đi theo redirect; không đổi timeout của client đang được dùng chung. Cách gọi không truyền deadline của các chức năng cũ vẫn được giữ. Các bài kiểm thử có sửa hẹp để thích nghi chữ ký hàm và đo đúng phạm vi.

`poller.py` / `zalo_bot.py` chỉ nằm trong danh sách dự kiến nếu cần truyền client; triển khai thực tế không cần sửa chúng cho bước này. Không đổi HTML/CSS/UX, cấu trúc DB hay công thức tiền. Không gọi thật Gate A.

### Giai đoạn 3 — Đo kết quả và cân nhắc giảm AddLiveTag

Chưa triển khai giai đoạn này. Anh cần chốt các ngưỡng đạt/trượt trước khi được đánh dấu xong:

| Nội dung cần anh chốt | Ghi chú |
|---|---|
| Cửa sổ đo, ví dụ 7 ngày | Anh chọn |
| Tỷ lệ tạo link thành công tối thiểu | 95% mới là số đề xuất trước đó, chưa được anh duyệt |
| Thời gian trả lời p95 | 20 giây là ứng viên, chưa là cam kết đã ký |
| Chênh lệch hoa hồng cho phép so với đơn thật | Chốt sau đủ thử nghiệm |
| Khi nào được bỏ yêu cầu `ADDLIVETAG_API_KEY` | Chỉ khi kiểm kê mục 3.8 không còn chức năng bắt buộc |
| Khi nào đổi mặc định sang `PRODUCT_QUOTE_PRIMARY=native` | Cần điều kiện, ngày áp dụng và Claude kiểm tra |

Cần đo nguồn báo giá/tạo link, tỷ lệ tạo link, p95/p99 thời gian chờ, lỗi mở link/cầu nối và số thẻ báo số không có căn cứ (phải bằng 0).

Không đạt thì quay lại nguồn an toàn, giữ client PD và ghi bằng chứng; không xóa nguồn dự phòng hoặc đánh dấu giai đoạn 3 xong.

## 6. Phạm vi không thay đổi

- Không tự bỏ khóa AddLiveTag khi theo dõi giá, deal hoặc đối chiếu đơn vẫn cần.
- Không đổi ví, thanh toán, đối soát, AMS, TikTok hoặc công thức chia tiền.
- Không bịa hoàn; không làm mất chữ ký Meta hay mã theo dõi khách.
- Không mở cầu nối ra Internet; không gọi thật khi thiếu quyền của gate tương ứng.
- Không khởi động lại Cashbot/Zalo, commit hoặc push nếu anh chưa yêu cầu theo quy trình.
- Giữ nguyên các file đang có thay đổi từ công việc khác.

## 7. Rủi ro đã biết

Báo hoàn cao hơn căn cứ; link khiến máy gọi địa chỉ không an toàn; chờ lâu làm tắc bot; dùng sai kênh hoa hồng; nhầm giờ lấy dữ liệu với giờ nguồn cập nhật; làm đè thay đổi của Claude; nhầm bỏ PD trong báo giá với bỏ toàn AddLiveTag; dùng test giả thay bằng chứng thật.

Rủi ro vận hành đã có trong lịch sử: điều hướng và shortlink từng timeout. Lượt theo B lúc 23:34 đã đạt trên một sản phẩm và phục hồi legacy thành công; chưa suy rộng thành cam kết độ ổn định hoặc kết luận nguyên nhân mọi timeout cũ.

## 8. Điều kiện nghiệm thu — Đồng bộ TASK-063

### Giai đoạn 1

- [ ] PD lỗi, link thuộc danh sách cho phép vẫn tạo `created` và giữ đúng `sub_id`.
- [ ] Khi chưa biết hoa hồng, số tiền để `NULL` và nguồn `degraded_unquoted`.
- [ ] Mở link không quá 3 lần chuyển hướng; kiểm tra DNS/IP/tên miền từng chặng.
- [ ] Giới hạn thời gian cho chuỗi gọi ngoài và chờ khóa được kiểm chứng; hành vi hết giờ đúng mục 3.4. Ghi riêng giới hạn DNS/TLS/SQLite/lập lịch.
- [ ] Có bằng chứng kết nối WSL → Windows và giới hạn truy cập.
- [ ] Link ALT: test giả đạt; kết quả gọi thật chỉ được chấp nhận sau Gate A.
- [ ] Có kiểm tra Claude 1.0 và cờ quay lại cách cũ.

### Giai đoạn 2

- [ ] Gate B có quyền, ít nhất 5 sản phẩm có/không XTRA; giá/hoa hồng và độ mới được giải thích, dữ liệu đăng nhập đã loại bỏ.
- [ ] Chỉ báo số khi đủ thành phần để tính `sure_commission`; lỗi thì dùng PD hoặc để trống số.
- [ ] Có ít nhất một sản phẩm anh chọn chạy thật thành công qua bản cầu nối mới; test giả không thay được.
- [ ] Claude kiểm tra bước 2.0 trước khi bật native mặc định.

### Giai đoạn 3

- [ ] Anh đã chốt ngưỡng đạt/trượt và cách bật/quay lại.
- [ ] Đo đủ thời gian đã chốt; ghi quyết định bằng bằng chứng.
- [ ] Không tuyên bố bỏ toàn bộ AddLiveTag nếu chưa được mở phạm vi và kiểm kê xong.

### Chung

- [ ] Các kiểm thử bắt buộc đạt hoặc lỗi còn lại được giải quyết; không DELETE/DROP DB thật.
- [ ] Kết quả giả lập và kết quả chạy thật được phân biệt rõ.

Các ô nghiệm thu tổng vẫn chưa được đánh dấu thay Claude/Anti. Việc đã viết code hoặc một bộ test riêng đạt không tự hoàn tất toàn tiêu chí.

## 9. Kiểm tra, quay lại và ước lượng

- Kiểm tra theo mục 8, không khởi động lại liên tục để thử may rủi.
- Cờ quay lại: `PRODUCT_QUOTE_ALLOW_DEGRADED`, `ALT_SHOPEE_LINK_FALLBACK`, `PRODUCT_QUOTE_PRIMARY`. Cầu nối mới chỉ chạy khi chọn `SHOPEE_BRIDGE_IMPLEMENTATION=repo`; quay lại `legacy` để dùng bản cũ.
- Chưa có thời gian sửa lỗi portal được kiểm chứng. Ước lượng 0,5–1 ngày giai đoạn 1 trước đây là dự kiến sau duyệt, không phải cam kết cho lỗi hiện tại.

## 10. Tham chiếu kiểm kê ngày 18/11

Nhóm `data.*` gồm dữ liệu sản phẩm, lịch sử và tìm kiếm từng lỗi cùng đợt; nhóm `api/v1` cho chuyển đổi/link còn trả lời. Không được suy từ một đợt kiểm tra ra trạng thái hiện tại của toàn bộ dịch vụ.

## Trạng thái duyệt và bàn giao

| Mục | Trạng thái |
|---|---|
| Anti / Cursor, vòng thiết kế 1–2 | Lịch sử: đã thêm P1/P2 vào bản nháp, chưa duyệt thực thi ở thời điểm đó |
| Anh giao giai đoạn 1 ngày 19/11 | Đã giao Cursor triển khai |
| Anh giao agent làm từng mục giai đoạn 2 | Đã giao Codex điều phối; không đồng nghĩa duyệt bật mặc định |
| Gate A | Còn chờ |
| Gate B thử nghiệm | Đã cho phép; có 8 mẫu kỹ thuật đúng ID |
| Claude kiểm tra giai đoạn 1 / 2 | Còn chờ |
| Anti rà soát và ký duyệt | Còn chờ |
| Ngưỡng đo giai đoạn 3 | Còn chờ anh chốt |
| Khởi động lại Cashbot/Zalo | Anh thực hiện khi sẵn sàng; agent chưa làm |
| Toàn PLAN/TASK | Chưa hoàn tất, chưa lưu trữ |

## Việc tiếp theo

1. Claude kiểm tra bản sửa lifecycle B, bằng chứng một native quote đúng ID và shortlink thật; đối chiếu phạm vi với handoff.
2. Giữ mặc định Product Data + legacy trong khi chờ review. Nếu cần bổ sung mẫu/độ ổn định, thực hiện theo phạm vi có giới hạn, không tự đổi PRIMARY hoặc tăng timeout.
3. Bổ sung kết quả vào PLAN/TASK/báo cáo; Claude kiểm tra và Anti duyệt theo quy trình.
4. Chỉ sau khi đủ điều kiện mới đưa lệnh cho anh bật thử/khởi động lại. Giai đoạn 3 còn chờ ngưỡng đo; Gate A vẫn riêng nếu bật ALT.

## Bằng chứng thực hiện — Thử nghiệm dữ liệu ngày 19/11/2026

- Mã portal chính thức cho thấy đường đọc chi tiết `/api/v3/offer/product?item_id`, không cần đoán tên để tìm trong danh sách.
- Có 8 sản phẩm khác nhau khớp shop/item: S1–S6 và 2 mẫu mới. Giá và hoa hồng dùng để báo hoàn đều khớp PD; 5 mẫu cho thấy lấy nguyên tổng tỷ lệ sẽ báo cao hơn chính sách hiện tại. Mẫu không XTRA: hoa hồng dùng để báo hoàn 3.461 VND, còn lấy nguyên tổng sẽ ra 9.693 VND.
- Dùng Decimal/số nguyên; giữ `SHOPEE_BASE_BPS=250` và `cashback_for`. Mức trần cờ báo ở portal/PD có thể khác nhau dù số dùng để báo hoàn khớp.
- Lệnh thật: `.venv/bin/python -m reports.plan177.compare_portal_detail --check` → `{"contract_checks":59,"failures":0,"unique_exact_items":8,"non_xtra":1,"default_as_total_overquotes":5}`. Ruff báo `All checks passed!`; Node `--check` kết thúc mã 0.
- **Giới hạn:** đợt đầu 6/12 lượt thành công; thử riêng S3/S4 sau đó thành công. PD cuối có `source=db`; giờ cập nhật 09:21–10:00Z, trong khi portal lấy lúc 09:56–10:08Z. Không tuyên bố hai nguồn được cập nhật đồng thời hoặc đã xác minh độ mới độc lập.
- Ở cuối lượt POC đó, health Windows/WSL đều 200 và shortlink thành công. Đây là kết quả cũ; những lượt triển khai sau có lỗi được ghi riêng bên dưới.
- SHA-256 file npm giữ nguyên: `9F8E47F0A9F02D198A0390E193A29B3937A92DF04E76937C5835B4BCAB8EECBC`. Browser đóng trong `finally`; không restart Cashbot, commit hoặc push.
- Bằng chứng: `PORTAL-DETAIL-POC-20261119.md`, `portal-detail-matched-20261119.jsonl`, `portal-detail-compare-20261119.json`, `portal-runtime-proof-20261119.json` trong `reports/plan177/`.

**Đã xong phần POC bổ sung; còn chờ Claude kiểm tra/bàn giao và các điều kiện đưa vào dùng thật.**

## Bằng chứng bước 2.1 — Cầu nối do repo quản lý

- Agent `bridge_implementation` viết `scripts/shopee_bridge/{index,server,browser,queue,quote}.mjs`, README và ba file test Node. `run_shopee_mcp.sh` chỉ thêm lựa chọn bản mới, mặc định vẫn cũ.
- Review phát hiện giới hạn URL sản phẩm làm mất tương thích link shop/voucher/chiến dịch; đã thêm regression giữ các dạng đang được hỗ trợ.
- Lượt đầu: agent 25 đạt/0 lỗi trong 682,9099 ms. Root tự chạy bản 24 test trước đó: 24 đạt/0 lỗi trong 2098,6564 ms. `bash -n` mã 0.
- Dữ liệu trả về phiên bản 1, nguồn `native_shopee`, ngữ cảnh `social_media_shop_existing`. Giá, tỷ lệ và cap dạng số nguyên tỷ lệ 100000; có ID yêu cầu/ID thực tế. Chỉ có giờ lấy dữ liệu, không tự tạo giờ nguồn cập nhật.
- Trong bước viết mã ban đầu không gọi thật, không sửa npm. Khi thử thật sau đó mới phát hiện lỗi khởi tạo/điều hướng; đã sửa theo chứng cứ: chuẩn bị portal trước khi mở listener, dùng lại tab, giữ thứ tự hàng chờ đến khi cleanup xong, thêm đo từng bước chỉ dùng tên giai đoạn và số mili giây.
- Bản cuối: chuẩn bị tối đa 45 giây, chặn khởi động ở 55 giây, request tối đa 20 giây. Node cuối độc lập: **32 đạt, 0 lỗi, 2274,9498 ms**. Bản agent trước đó cũng đạt 32/32 trong 1999,6213 ms. Kết quả chạy thật vẫn chưa đạt.

## Bằng chứng bước 2.2 — Client và bộ kiểm tra dữ liệu

- Agent `native_quote_client` thêm `native_shopee_quote.py`, `test_native_shopee_quote.py` và `tests/fixtures/native_shopee_quote_poc.json`.
- `NativeShopeeQuoteClient.fetch_quote(target, *, now, deadline)` trả `NativeProductQuote`, kế thừa công thức `sure_commission_vnd`. `last_update=None`, có `fetched_at` và thông tin khoảng giá/căn cứ lấy giá thấp nhất riêng.
- Kiểm tra đúng ID, thành phần hoa hồng/cap/kênh, phiên bản dữ liệu, tiền tệ/trạng thái, thời hạn, phân biệt thiếu với 0 và giới hạn số nguyên signed64 của SQLite.
- Mẫu không XTRA thật có ngày bắt đầu cũ và ngày kết thúc 0; chỉ chấp nhận khi seller bằng 0 và ngày bắt đầu không ở tương lai.
- Kết quả riêng cuối: **98 đạt trong 4,59 giây**. Lượt kết hợp trước ba test cuối: 202 đạt trong 22,52 giây. Root tự chạy parser + bot trước ba test cuối: 139 đạt trong 11,75 giây. Một lượt parser/Phase1/shortener khác: 109 đạt trong 5,11 giây.
- Có test HTTP cục bộ trả header/body chậm, chờ khóa, nghỉ gọi sau lỗi, hồi phục sau thời gian nghỉ, chặn redirect/response quá lớn và không lộ thông báo lỗi thô. Không gọi Shopee thật trong các test này.
- Ruff đạt; biên dịch và kiểm tra diff mã 0. Không đổi DB hay cấu hình môi trường.

## Ghi chú triển khai bước 2.3 — Dùng chung giới hạn HTTP

- `deadline_http.py` dùng lại cho PD, AffiPad, ALT tùy chọn và rút gọn link. Mỗi lượt có kết nối riêng, giới hạn response, không tự theo redirect, không đổi timeout dùng chung.
- Nhánh không truyền deadline của chức năng cũ giữ API trước đó. Giới hạn DNS/TLS đồng bộ chưa bị loại bỏ, phải ghi thật trong nghiệm thu.
- ALT giữ nguyên query/auth; cờ vẫn tắt. Hết thời gian thì không gọi ALT. Không dùng việc thêm timeout làm quyền gọi thật Gate A.

## Bằng chứng bước 2.3 — Thứ tự nguồn có cờ bật thử

- Agent `quote_ladder_integration` ghép native → PD hợp lệ → chưa có báo giá; PD mặc định. Kiểm tra lại shop/item khi dùng PD dự phòng. Nguồn native lưu đúng `quote_source` và `product_last_update=NULL`; ghi khoảng giá, căn cứ giá và giờ lấy trong note.
- Giữ `sure_commission_vnd` / `cashback_for`. Sửa hẹp lỗi AffiPad khi kết quả sai dạng hoặc link ký Meta thiếu `channel_type` để không crash.
- Kết quả riêng cuối: **30 đạt trong 14,67 giây**. Ruff 8 file phạm vi đạt; biên dịch và diff mã 0. Bộ cũ lúc đầu sau tích hợp: 112 đạt trong 16,11 giây.
- Một lượt kết hợp trước đó: 238 đạt/2 lỗi trong 163,72 giây khi tải WSL khoảng 14, CPU Windows 85,15%. Một test Phase1 cũ đo cả dựng DB; một test mới đo sau ghi SQLite. Không coi lượt lỗi này là kết quả xanh.
- Reviewer chỉ sửa phép đo test cho đúng hợp đồng: giữ kiểm tra ngắt nguồn ngoài và không gọi sau hết hạn; thời gian cả lượt gồm SQLite được ghi như số đo, không gán một bảo đảm chưa triển khai.

## Bằng chứng bước 2.4 — Chạy thật chưa đạt

### Lượt đầu — Đã giữ nguyên bằng chứng lỗi

- Health Windows/WSL 200, nhưng hai quote native timeout 8,041 / 8,055 giây; shortlink HTTP 504 sau 18,116 giây.
- Lưu `phase2-live-proof-attempt1.json`. Cầu nối thử đóng trong finally, bản cũ được phục hồi. Không dùng test giả thay kết quả này.

### Lượt cuối — Đã biết điểm dừng, chưa biết nguyên nhân gốc

- Mở context xong ở 8,753 giây; đồng bộ cookie xong 13,364 giây; tab sẵn ở 13,919 giây.
- Bắt đầu điều hướng portal ở 13,984 giây; bị ngắt ở 45,063 giây; cleanup xong ở 61,396 giây. Chưa mở listener sẵn sàng, chưa có quote thật thành công từ bản cuối.
- Bản cũ được phục hồi và health trả `status=ok`, phiên bản 0.3.0. Tuy nhiên rút gọn link bản cũ cũng timeout 35 giây; lần thử cuối khác timeout 20,794 giây với giới hạn client 20 giây.
- Chưa có căn cứ kết luận chắc do đăng nhập, mạng hay riêng cầu nối mới. Không tự vượt xác minh/CAPTCHA hoặc tăng thời gian chờ liên tục.
- Bằng chứng: `phase2-live-proof.json` và các file `attempt/stages` trong `reports/plan177/`. SHA npm không đổi; chưa bật native, chưa restart Cashbot/Zalo.

### Kiểm thử cuối và giới hạn kết luận

- Python đầy đủ cuối: **239 đạt, 1 lỗi trong 346,16 giây**. Lỗi duy nhất là AffiPad trả header chậm: kết quả trả lỗi an toàn nhưng thời gian 0,3581 giây vượt ngưỡng 0,28 giây của test với deadline 0,13 giây.
- Chạy riêng đúng bài đó, **không sửa mã hoặc ngưỡng**, đạt **1 bài trong 35,99 giây**. Không được gộp hai lượt thành tuyên bố cả bộ 240 đã đồng thời đạt.
- Một lượt review trước: 239 đạt/1 lỗi trong 251,65 giây do phép đo cả ghi DB; sau sửa phép đo đúng phạm vi, hai test liên quan đạt trong 25,18 giây. Lịch sử đều có trong báo cáo độc lập.
- Node cuối: **32/32 đạt trong 2274,9498 ms**. Ruff, biên dịch Python, cú pháp Node/bash và `git diff --check` đạt ở phạm vi thay đổi.
- PM2 ở lần ghi nhận cuối: `shopee-mcp` online PID 2627135, bản cũ; PID các ứng dụng PM2 khác khớp mốc so sánh. Đây là snapshot đã lưu, không phải khẳng định đã đo lại ở lượt sửa tài liệu.
- Báo cáo chính: `reports/plan177/PHASE2-IMPLEMENTATION-20261119.md`; review độc lập: `reports/plan177/phase2-independent-review.md`.

**Đã hoàn thành phần viết mã và kiểm tra không gọi dịch vụ thật. Phần chạy thật, độ mới dữ liệu, kiểm tra Claude và ký duyệt Anti vẫn còn chờ; toàn kế hoạch chưa xong.**

Dòng bàn giao theo quy ước dự án: **Execution Done. Cần Claude Code verify + handoff.** Dòng này chỉ áp dụng phần viết mã đã nêu, không có nghĩa được bật phục vụ khách hay đánh dấu toàn TASK hoàn tất.

## Tiếp tục bước 2.4 — Kiểm tra nguyên nhân kết nối portal

Anh yêu cầu làm bước tiếp theo. Mục chẩn đoán đã được làm xong trong cùng lượt, có kết quả và kiểm tra phục hồi trước khi chuyển việc.

- Mốc chỉ đọc ban đầu: portal HTTP 200 trong 0,783054 giây; cầu nối cũ health 200, shortlink HTTP 500 với lỗi page.evaluate TypeError Failed to fetch. Tải WSL 1,00 / 0,82 / 1,07. Hash npm giữ nguyên. Bằng chứng: reports/plan177/runtime-resume-baseline-20261119.json.
- Công cụ đọc UI báo lỗi nhận diện cửa sổ Chrome; chưa xem được màn hình để phân biệt đăng nhập/xác minh.
- Script nội bộ dùng đúng phiên Affiliate có sẵn, chỉ ghi các giai đoạn, HTTP, trạng thái tài liệu và mã lỗi đã lọc. Không xuất cookie, CSRF, token, tên sản phẩm hoặc payload thô.
- Lần đo thật lúc 22:45 ngày 19/11: tài liệu portal trả 200 tại 2,525 giây; browser nhận tài liệu tại 2,540 giây; trạng thái interactive. Lệnh đọc hoa hồng một sản phẩm POC bị HTTP 403, mã 90309999. Chưa có quote mới thành công.
- Đã dừng gọi thêm, đóng context tại 5,165 giây. Cầu nối cũ được phục hồi trong finally, health 200 trong 0,016894 giây, không còn process POC; hash npm không đổi. Không sửa mã phục vụ khách, .env hoặc DB; không restart Cashbot/Zalo, không bật native, commit/push.
- Lệnh kiểm tra cú pháp Node cho runtime-lifecycle-probe.mjs đạt, mã thoát 0; chạy thật mã thoát 0. Số liệu và cleanup lưu tại runtime-lifecycle-20261119.json.

**Chủ tài khoản:** đã kiểm tra UI Affiliate (~22:54 VN), xác nhận không cần logout/login; báo **«xong»**.

**Thử lại có giới hạn sau «xong» (~22:58 VN):** shortlink OK; portal detail `item_id=54321049804` → HTTP 200, `code=0`, `ids_exact=true` (shop `1175585681`); seller `0%` / shopee+default `7%`. Lỗi `403/90309999` của lượt 22:45 **không tái hiện**. Legacy bridge phục hồi, health 200, shortlink sau restore OK. Báo cáo: `reports/plan177/POST-XONG-RETRY-20261119.md`. **Chưa bật native cho khách.**

**A/B ~23:21 VN:** cùng item/profile — script GPT (`commit`+chờ ngắn) vẫn **403/verification_required**; script Cursor (`networkidle`+2,5–4s) **200/code0/ids_exact**. Báo cáo: `reports/plan177/AB-PROBE-COMPARE-20261119.md`. Hệ quả: bridge native phải chờ kiểu B trước REST detail.

**Bước sau (đã giao GPT):** smoke cầu nối repo + `NativeShopeeQuoteClient` + shortlink (opt-in), **áp lifecycle chờ kiểu B**, proof trong `reports/plan177/`, rồi restore legacy. Handoff: `.comms/handoffs/cursor-to-ag/TASK-plan177-repo-bridge-native-smoke.md`. Không tăng timeout hoặc đổi PRIMARY mặc định để che lỗi. Claude verify / Anti–Owner duyệt bật vẫn sau lượt này.

## Kết quả handoff smoke cầu nối repo — 19/11/2026

- Đã đọc và thực hiện `.comms/handoffs/cursor-to-ag/TASK-plan177-repo-bridge-native-smoke.md`, không sửa mã phục vụ khách.
- Lượt thật bắt đầu 23:11:35 giờ Việt Nam. Context xong 7,712 giây, tab sẵn 7,846 giây; điều hướng portal bắt đầu 7,854 giây nhưng hết hạn chuẩn bị tại 45,053 giây. Cleanup tác vụ xong 52,067 giây, toàn harness 52,898 giây; đã đóng thành công.
- **Kết quả chức năng: CHƯA ĐẠT.** Chưa mở listener sẵn sàng, chưa gọi NativeShopeeQuoteClient và chưa gọi shortlink repo. Không kết luận lỗi xác minh/403 vì chưa tới request quote. Không tăng timeout hoặc gọi lặp.
- Lệnh gộp đầu bị công cụ chặn trước thực thi; lệnh tối thiểu với interface nội bộ WSL được chấp nhận. Bản thử dùng địa chỉ 192.168.112.1, peer 192.168.112.133, không dùng mọi interface.
- **Phục hồi đã kiểm chứng:** pm2 start legacy mã 0; WSL health 200/status ok; một shortlink cũ HTTP 200/success=true/host s.shopee.vn, thời gian 15,62 giây. Legacy online PID 3147903; không còn process harness.
- Hash .env, launcher, config/service/native client và bridge browser/index/server khớp trước/sau. PRIMARY vẫn mặc định product_data, bridge vẫn mặc định legacy. Cashbot/Zalo giữ nguyên PID và giờ khởi động, các PID PM2 khác không đổi. Hash npm giữ nguyên. Không restart Cashbot/Zalo, bật native, sửa DB hoặc commit/push.
- Báo cáo: `reports/plan177/REPO-NATIVE-SMOKE-HANDOFF-20261119.md`; proof chính `repo-native-handoff-smoke-20261119.json`; baseline/after và legacy-restore JSON đi kèm. Reviewer độc lập xác nhận nhánh thất bại có phân loại và phục hồi đạt yêu cầu.
- Chỉ sửa thêm artifact harness để URL health lần sau trỏ đúng interface lắng nghe; không chạy lại. Bản harness đã thực thi và hash được giữ riêng để đối chiếu.
- **Handoff smoke này hoàn tất theo nhánh fail có proof; toàn PLAN/TASK vẫn chưa hoàn tất.** Việc tiếp theo: chẩn đoán lifecycle điều hướng của bản repo rồi sửa và chạy lại smoke; Claude kiểm tra, Anti/anh duyệt bật nguồn vẫn sau bước đạt thật.

## Bằng chứng bước 2.4 — Sửa cách chờ B và smoke đạt lúc 23:34 ngày 19/11

- Chỉ sửa mã `browser.mjs` và `browser.test.mjs`: DOMContentLoaded (điều hướng tối đa 25 giây) → networkidle tối đa 8 giây → nghỉ đủ 2,5–4 giây; tổng chuẩn bị vẫn 45 giây. Tài liệu đã ổn định được dùng lại, mất hiệu lực khi đổi page/context/điều hướng/lỗi/abort. Bộ đếm phiên điều hướng chặn race do reviewer phát hiện.
- Windows Node: 38 tests / 38 pass / 0 fail, 722.884 ms; WSL Node: 38 pass / 0 fail, 1523.470113 ms. Output thật trong `lifecycle-b-node-tests-20261119.tap`. Lượt test đầu lỗi dấu ngoặc ở ca mới đã sửa; không tính là PASS.
- Lượt thật: chuẩn bị ready 14,238 giây; networkidle 7,672 giây, nghỉ 3,396 giây. Health Windows và WSL đều 200/implementation toolsauto.
- NativeShopeeQuoteClient từ WSL: shop 1175585681/item 54321049804, ids_exact=true/source=native_shopee, 1,347 giây. Shortlink cùng backend: HTTP 200/success=true/host s.shopee.vn, 0,193 giây. Không còn 403 trong lượt này.
- Cleanup closed=true, harness 17,832 giây/mã 0. Restore legacy mã 0; WSL health 200/status ok và một shortlink cũ HTTP 200/success=true, 8,142 giây. Hash 9 file baseline, npm, PRIMARY và PID/thời điểm khởi động Cashbot/Zalo giữ nguyên trong lượt smoke; app PM2 khác không đổi.
- Báo cáo: `reports/plan177/LIFECYCLE-B-NATIVE-SMOKE-20261119.md`; JSON `lifecycle-b-native-smoke-20261119.json`, baseline/after/legacy-restore đi kèm. Giữ nguyên bằng chứng lỗi trước đó.
- Một sản phẩm thành công, không phải kiểm chứng mọi sản phẩm/độ ổn định dài hạn. Không gọi PD để đối chiếu lại trong lượt này; last_update vẫn NULL, fetched_at riêng. Không đổi .env/PRIMARY, restart Cashbot/Zalo, sửa DB hoặc commit/push.

**Execution Done (smoke lifecycle-B).** Owner giao Cursor verify thay Claude (~23:45 VN): **VERIFY APPROVED** — checklist 9/9 trong `reports/plan177/VERIFY-LIFECYCLE-B-20261119.md` (rerun Node 38/38; PRIMARY=`product_data`; 0 cookie leak; legacy health live 200). **Không** bật native / không đổi `.env` / không restart bot. Toàn PLAN/TASK chưa Done/archive; **Anti/anh quyết định pilot hoặc giữ PD**.
