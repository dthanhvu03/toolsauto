# TASK-063 — Lấy báo giá và tạo link trực tiếp từ Shopee Affiliate

| Thông tin | Nội dung |
|---|---|
| Mã công việc | TASK-063 |
| Trạng thái | **VERIFY APPROVED (Cursor thay Claude): lifecycle-B + smoke 1 SP. Legacy OK. Chưa bật native; chờ Anti/anh quyết định pilot.** |
| Ưu tiên | Cao |
| Kế hoạch | [PLAN-177](../plans/active/PLAN-177-shopee-native-product-quote.md) |
| Người thực hiện | Codex điều phối agent làm tuần tự theo yêu cầu của anh ngày 19/11/2026; phần giai đoạn 1 trước đó do Cursor làm |
| Phối hợp | Claude Code kiểm tra luồng khách; Anti rà soát/ký duyệt; anh quyết định khởi động lại và bật chính thức |
| Liên quan | PLAN-174, ADR-067, `product_data.py`, `shopee_shortener.py`, `policy_snapshot.py`, `sale_relay.py` và quy tắc chống SSRF trong `PROJECT.md` |

## Tóm tắt để anh theo dõi

**Đã làm:** tìm được cách tra sản phẩm bằng mã; viết cầu nối Affiliate; viết bộ kiểm tra giá/hoa hồng; ghép vào bot theo thứ tự Shopee → Product Data → link chưa có số hoàn.

**Mới nhất 23:34 ngày 19/11:** sau sửa cách chờ B, cầu nối repo đã trả native quote đúng shop/item và tạo shortlink thành công. Bản cũ đã phục hồi; một mẫu chưa chứng minh ổn định dài hạn.

**Tiếp theo:** Anti/anh quyết định giữ PD hoặc pilot native (có đo + rollback). Verify: `reports/plan177/VERIFY-LIFECYCLE-B-20261119.md`. Mặc định vẫn Product Data + cầu nối cũ.

## Vấn đề và mục tiêu

Product Data lỗi từng khiến Cashbot chặn tạo link. Cần bỏ phụ thuộc bắt buộc đó nhưng không bịa số hoàn, không đổi chính sách tiền và không gỡ các chức năng AddLiveTag khác còn dùng.

- Khi đủ dữ liệu: dùng lại `sure_commission_vnd` và `cashback_for` để tính tiền hoàn.
- Khi thiếu dữ liệu nhưng đã biết đúng sản phẩm: tạo link, để số tiền `NULL` và ghi nguồn `degraded_unquoted`.
- Giữ đúng `sub_id`, chữ ký Meta/AffiPad, nguồn báo giá và chính sách lưu lúc tạo link.

## Quy tắc kỹ thuật chính

| Nội dung | Quy tắc |
|---|---|
| Link rút gọn | Tối đa 3 lần chuyển hướng; kiểm tra tên miền/DNS/IP từng chặng, chặn địa chỉ không an toàn |
| Thời gian chờ | Một mốc `time.monotonic()` dùng chung cho chuỗi gọi ngoài và chờ khóa; ngân sách đang cấu hình 20 giây |
| Giới hạn phải nói rõ | DNS/TLS đồng bộ, SQLite và lúc hệ điều hành tạm ngừng tiến trình không bị hủy cứng; không hứa toàn lượt luôn dưới 20 giây |
| Kết nối | Bot WSL gọi cầu nối Windows qua `get_bridge_host()` / `SHOPEE_BRIDGE_HOST`; không mở cổng ra Internet |
| Nguồn mới | `PRODUCT_QUOTE_PRIMARY=native` chỉ bật có chủ đích; mặc định `product_data` |
| Thời gian dữ liệu native | `fetched_at` là giờ lấy; không giả thành giờ nguồn cập nhật; `product_last_update=NULL` |
| Khóa AddLiveTag | Vẫn bắt buộc khi lịch sử giá/deal/đối chiếu đơn còn dùng |
| Gate A | Quyền riêng trước khi gọi thật `shopee-link.php`; hiện còn chờ, cờ tắt |
| Gate B | Anh đã cho thử Affiliate; POC có 8 sản phẩm khớp shop/item, gồm có và không XTRA; không thay thế điều kiện chạy thật qua cầu nối cuối |
| Dữ liệu giả | Dùng kiểm tra logic, không thay bằng chứng gọi hệ thống thật |

## Các bước và kết quả

| Bước | Phạm vi | Kết quả đã ghi nhận |
|---|---|---|
| 0.1–0.2 | Thử đọc dữ liệu và so với PD | 8 sản phẩm đúng ID, giá và hoa hồng dùng báo hoàn khớp PD; 59 kiểm tra đạt. Đợt đầu 6/12 request thành công, không kết luận luôn ổn định. PD có dữ liệu lưu sẵn, độ mới nguồn còn giới hạn. |
| 2.1 | Cầu nối do repo quản lý | Đã viết `scripts/shopee_bridge/`; lựa chọn khởi động bản mới trong `run_shopee_mcp.sh`; 38 test Node đạt; smoke theo B trên một món đã đạt quote + shortlink. Chuẩn bị portal riêng 45 giây, chặn khởi động ở 55 giây; request tối đa 20 giây. |
| 2.2 | Client và bộ kiểm tra dữ liệu | `native_shopee_quote.py`; 98 test riêng đạt; kiểm tra ID/split/cap/kênh/thời hạn; giữ công thức hiện tại. |
| 2.3 | Thứ tự nguồn và cờ bật thử | 30 test riêng đạt; nguồn lỗi thì dùng dự phòng; hết giờ vẫn có link dài chưa số khi biết sản phẩm. |
| 2.4 | Rà soát và thử thật | Python cuối 239 đạt/1 lỗi timing; chạy riêng bài lỗi giữ nguyên ngưỡng đã đạt. Node mới 38/38 đạt; smoke repo theo B đúng một món đã đạt. Claude/Anti/anh duyệt bật vẫn pending. |

## Điều kiện nghiệm thu — Đồng bộ PLAN-177 mục 8

### Giai đoạn 1

- [ ] PD lỗi, link hợp lệ vẫn tạo được và giữ đúng `sub_id`.
- [ ] Không bịa tiền: chưa biết thì `quote_*=NULL` và `quote_source=degraded_unquoted`.
- [ ] Mở link không quá 3 lần chuyển hướng, kiểm tra SSRF từng chặng.
- [ ] Có kiểm chứng deadline của gọi ngoài/chờ khóa và ghi rõ giới hạn đã biết.
- [ ] WSL gọi được Windows; truy cập bị giới hạn.
- [ ] ALT có test giả; phần gọi thật chỉ được tính sau Gate A.
- [ ] Claude kiểm tra thiết kế giai đoạn 1 và cách quay lại.

### Giai đoạn 2

- [ ] Đủ quyền Gate B và ít nhất 5 sản phẩm có/không XTRA; giải thích độ mới/chênh lệch; loại thông tin đăng nhập khỏi bằng chứng.
- [ ] Chỉ hiện số khi đủ dữ liệu tính `sure_commission`; lỗi dùng PD hoặc để trống số.
- [ ] Ít nhất một món anh chọn chạy thật thành công qua cầu nối mới; không thay bằng test giả.
- [ ] Claude kiểm tra trước khi bật native mặc định.

### Giai đoạn 3

- [ ] Anh chốt ngưỡng đo đạt/trượt, điều kiện bật/quay lại.
- [ ] Đo đủ thời gian và ghi kết quả thật.
- [ ] Không tuyên bố bỏ hết AddLiveTag khi chưa được duyệt phạm vi và kiểm kê xong.

### Chung

- [ ] Các test bắt buộc đạt hoặc lỗi được giải quyết; không DELETE/DROP DB thật.
- [ ] Không gộp test giả thành bằng chứng chạy thật.

Các ô tổng vẫn chờ nghiệm thu; không tự đánh dấu thay Claude/Anti.

## Phạm vi không làm

Không đổi ví/đối soát/AMS/TikTok hoặc công thức tiền; không sửa UX/HTML/CSS; không gỡ khóa AddLiveTag; không làm mất chữ ký Meta; không mở cầu nối Internet; không gọi Gate A khi chưa có quyền; không khởi động lại Cashbot/Zalo, commit/push hay lưu trữ TASK nếu chưa đủ điều kiện.

## Phụ thuộc và người quyết định

1. Anh đã giao viết mã và agent làm tuần tự; không cần xin lại quyền cho đúng phần này.
2. Claude kiểm tra luồng khách theo ADR-067, Anti rà soát/ký duyệt theo quy trình.
3. Gate A vẫn riêng; Gate B chỉ cho thử Affiliate trong phạm vi đã ghi.
4. Anh chốt ngưỡng giai đoạn 3 và khi nào khởi động lại/bật phục vụ khách.

## Bằng chứng và lỗi còn lại ngày 19/11/2026

- POC: `reports/plan177/PORTAL-DETAIL-POC-20261119.md`, `portal-detail-compare-20261119.json`, `portal-runtime-proof-20261119.json`. Kết quả health/shortlink đạt ở cuối lượt POC là lịch sử; các lượt sau có lỗi riêng.
- Viết mã: `reports/plan177/PHASE2-IMPLEMENTATION-20261119.md`. Rà soát độc lập: `phase2-independent-review.md`.
- Python full cuối: **239 đạt/1 lỗi, 346,16 giây**. Ca AffiPad header chậm trả lỗi an toàn nhưng mất 0,3581 giây, vượt ngưỡng 0,28 giây cho deadline 0,13 giây. Chạy riêng nguyên ca, không đổi mã/ngưỡng: **1 đạt trong 35,99 giây**. Không báo cả bộ 240 đã xanh cùng lượt.
- Node cuối: **32/32 đạt, 2274,9498 ms**; Ruff, compile, cú pháp bash/Node và diff check đạt.
- Lượt thật cuối: tab sẵn 13,919 giây; điều hướng bắt đầu 13,984 giây, timeout 45,063 giây; cleanup xong 61,396 giây. Chưa có quote thật từ bản cầu nối cuối.
- Bản cũ đã phục hồi, health 200 nhưng shortlink cũng timeout 35 giây và một lần nữa timeout 20,794 giây với giới hạn client 20 giây. Xem `phase2-live-proof.json`; chưa khẳng định nguyên nhân auth/mạng/bản mới.
- Không sửa `.env`, không bật native, không sửa npm, không khởi động lại Cashbot/Zalo, không commit/push. Toàn TASK chưa hoàn tất, chưa lưu trữ.

**Đã hoàn thành phần viết mã và kiểm tra không gọi dịch vụ thật; còn chờ xử lý kết nối portal, bằng chứng thật và duyệt triển khai.**

Dòng bàn giao theo quy ước: **Execution Done. Cần Claude Code verify + handoff.** Chỉ áp dụng phần viết mã, không xác nhận toàn TASK đã xong.

## Cập nhật chẩn đoán thật tiếp theo ngày 19/11/2026

Mở portal đã thành công khoảng 2,54 giây khi tải máy thấp. Request lấy một món POC trả HTTP 403/mã 90309999; đã dừng gọi tiếp. Context đóng tại 5,165 giây, legacy phục hồi health 200 và không còn process script.

Cần chủ tài khoản kiểm tra đăng nhập/xác minh trong đúng phiên Affiliate. Chưa kết luận hết phiên hay loại xác minh. Sau khi xử lý phiên mới thử một request có giới hạn, không né chặn.

Bằng chứng: reports/plan177/RUNTIME-DIAGNOSTIC-20261119.md và runtime-lifecycle-20261119.json. Không sửa mã production/cấu hình/DB, không restart Cashbot/Zalo. Mục chẩn đoán đã có điểm kiểm tra; bước chạy thật 2.4/TASK chưa xong.

## Handoff smoke repo đã thực hiện ngày 19/11/2026

Prepare portal hết hạn tại 45,053 giây, cleanup xong 52,067 giây. Chưa gọi native quote/shortlink repo; không báo thành công thay cho kết quả này. Bản cũ đã phục hồi: health WSL 200 và shortlink HTTP 200/success=true. .env/PRIMARY/mã nguồn và PID/giờ khởi động Cashbot/Zalo giữ nguyên.

Bằng chứng: reports/plan177/REPO-NATIVE-SMOKE-HANDOFF-20261119.md + repo-native-handoff-smoke-20261119.json. Handoff riêng có thể đóng theo nhánh fail được phân loại và phục hồi; toàn TASK-063 chưa Done/archive. Tiếp theo chẩn đoán điều hướng repo, sửa và smoke lại; Claude/Anti/anh duyệt bật sau khi đạt.

## Sửa cách chờ B và smoke đạt — 23:34 ngày 19/11/2026

- Hai file mã/kiểm thử: browser.mjs + browser.test.mjs. Chờ DOMContentLoaded/networkidle rồi nghỉ đủ 2,5–4 giây; cache cho đúng tài liệu và chặn điều hướng xen giữa; giữ ngân sách chuẩn bị 45 giây, client 8 giây.
- Windows Node 38/38 đạt (722.884 ms), WSL Node 38/38 đạt (1523.470113 ms). Reviewer độc lập xác nhận đã chặn race, không còn lỗi material trước smoke.
- Repo chuẩn bị 14,238 giây; health Windows/WSL HTTP 200/implementation toolsauto. Native quote đúng shop 1175585681/item 54321049804 trong 1,347 giây; shortlink HTTP 200/success=true trong 0,193 giây.
- Đã đóng repo và restore legacy: health WSL 200, shortlink HTTP 200/success=true/host s.shopee.vn trong 8,142 giây. Config/PRIMARY/npm và PID/giờ khởi động Cashbot/Zalo cùng các app PM2 khác không đổi; không bật nguồn, restart bot, sửa DB, commit/push.
- Proof: reports/plan177/LIFECYCLE-B-NATIVE-SMOKE-20261119.md và lifecycle-b-native-smoke-20261119.json (cùng baseline/after/legacy-restore/TAP). Một mẫu thật, chưa chứng minh freshness độc lập hoặc độ ổn định dài hạn; Python full lịch sử 239/1 không đổi thành 240 xanh.

**Execution Done. Cần Claude Code verify + handoff.** Riêng phần sửa và smoke này đạt; toàn TASK chưa Done/archive, vẫn chờ Claude/Anti/anh duyệt bật.
