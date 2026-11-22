# Chuyên viên chuyển đổi — CapCut

Ngày rà soát: 18/11/2026, giờ Việt Nam. Vai trò AI phân tích chuyển đổi; đầu ra là tài liệu, không phải chứng chỉ chuyên môn hoặc thay đổi đã triển khai. Đã đọc current-status, toàn bộ PLAN-173/172 và ADR-067; phạm vi là specialist team được chủ bot yêu cầu. Chỉ ghi file này, không sửa code, DB, câu chữ đang chạy, lịch, queue, giá hoặc đăng/gửi thêm.

## Kết luận để hành động

Ưu tiên làm rõ điều kiện bảo hành và kỳ vọng nhận hàng trước khi thử tăng lưu lượng. Link đúng món có nguồn và QR đúng số tiền đã có; không cần xây lại chúng. Có ba điểm dưới đây đáng xem xét, nhưng chưa có bằng chứng khách bỏ mua vì các điểm này. Snapshot artifact lúc17:17:40VN có0 khách mới theo source thử,0 khách đủ24h; tỷ lệ24h là null, không phải0%.

## Đường mua hiện có

| Bước | Hành vi đọc được từ code | Bằng chứng |
|---|---|---|
| Vào từ bài | buy_2_threads_ai_cc18_anlinh_p1 mở #2, ghi nguồn cho khách mới; chỉ xem, chưa mua | store_bot/bot.py:187–205; trial-manifest.json:8–10 |
| Xem món | Hiện tên/mô tả/giá/bảo hành/tồn/số dư, nút số lượng; hết bán hoặc shop nghỉ có nhánh riêng | store_bot/bot.py:464–485; messages.py:211–229 |
| Chọn số lượng | Tính thiếu bao nhiêu theo số dư; đủ ví xác nhận mua, thiếu ví có QR phần thiếu nếu có ngân hàng | store_bot/bot.py:488–510; messages.py:237–254 |
| Thanh toán | QR hiện món/số lượng/số tiền/nội dung/hạn mã; tiền được ghi nhận sẽ tự mua món có intent | messages.py:372–394; bot.py:1086–1095 |
| Giao | Đơn pending/thiếu vốn có thông báo riêng, replay không gửi lại; đơn xong gửi hàng và lưu trong Đơn hàng | bot.py:543–562; messages.py:263–295 |

Nguồn là first-touch: người từng vào không được gán lại. Step product/confirm chỉ giữ lần đầu; thiếu marker không chứng minh khách chưa xem món. Nạp thành công và giao đơn là hai sự kiện riêng. Không suy ra strict funnel từ các bước độc lập.

## Ba phát hiện theo thứ tự ưu tiên

### 1. Điều kiện bảo hành chưa đủ cụ thể để khách tự hiểu

**Fact:** tên món #2 chứa BHF. messages.py:188 diễn giải BHF thành “suốt thời hạn gói (điều kiện xem mô tả)”; product_detail:216–218 và confirm_buy:246–253 hiển thị dòng này. Catalog trong trial-measurement.json:14–16 chỉ có chữ BHF, cách đăng nhập, tối đa2 thiết bị và ID tiện bảo hành; chưa nêu trường hợp được xử lý, loại trừ, thời gian phản hồi hoặc cách gửi yêu cầu. Dựng màn hình bằng hàm messages.product_detail trên bản snapshot thực sự xuất dòng bảo hành nói trên.

**Chưa biết:** BHF có phải điều kiện nguồn đã xác minh ở nơi khác hay không. Đây không phải kết luận rằng lời bảo hành sai. Chưa có quan sát khách để kết luận đây là nguyên nhân không mua.

**Việc đề xuất:** chủ vận hành xác nhận bằng văn bản điều kiện của đúng #2, rồi đưa nội dung rõ vào phần mô tả dùng trước bước trả tiền. Khi chưa xác nhận, bản marketing không thêm cam kết “1 đổi1”, “mọi lỗi” hay thời gian xử lý cụ thể. Không tự gọi vendor hoặc đổi catalog trong lượt này.

### 2. Lời hứa nhận ngay cần khớp nhánh chờ hàng thực tế

**Fact:** shop_list tại messages.py:181 và welcome:1228 dùng lời nhận hàng ngay sau QR; topup_instructions:376 nói khoảng1 phút khi auto. Đồng thời bot.py:543–547 có nhánh đã nhận đơn nhưng chờ vốn nhập hàng, messages.py:289–294 nói huỷ thì tiền về ví. Product/confirm đã có cảnh báo restocking nếu điều kiện phát hiện được (bot.py:485,510,575–579); vì vậy không phải hệ thống hoàn toàn thiếu cảnh báo.

**Giả thuyết:** nếu nhìn câu nhanh ở trên rồi gặp đơn chờ, khách có thể thấy kỳ vọng không khớp. Chưa đọc thời gian giao đơn thật của cohort, chưa có bằng chứng khách phàn nàn.

**Việc đề xuất:** rà một bộ cách nói nhất quán: khi tiền được xác nhận, bot xử lý đơn tự động; trạng thái hiện tại cho biết có cần đợi nhập hàng. Nêu rõ huỷ đơn chờ hoàn về ví bot, còn hoàn ngân hàng đi qua hỗ trợ, không hứa hoàn ngân hàng tức thì. Chỉ đổi sau khi chủ luồng xét cùng PLAN-172; không lấy thời gian test giả làm SLA giao thật.

### 3. Hướng dẫn chào mừng chưa theo ngữ cảnh link đã mở đúng món

**Fact:** bot.py:203–205 gửi welcome cho khách chưa có menu rồi mở món trực tiếp. welcome ở messages.py:1231–1235 vẫn bảo bấm “Mua sản phẩm”, chọn sản phẩm rồi chọn số lượng. Trong thực tế link trial đã mở đúng món, bước tiếp theo chỉ là đọc thông tin rồi chọn số lượng. Đây là hai tin theo cùng một lệnh start, không phải khách buộc phải đi lại qua catalog.

**Giả thuyết:** chỉ dẫn chung có thể làm khách bấm quay ra catalog hoặc không biết thao tác ở tin nào. Chưa có session recording hoặc câu hỏi khách xác nhận điều đó.

**Việc đề xuất:** thử lời dẫn theo ngữ cảnh “Bạn đang xem CapCut; đọc thông tin rồi chọn1 tài khoản bên dưới”, giữ menu cũ và màn chi tiết. Không gộp bỏ bước xác nhận mua hoặc tự tạo QR từ link.

## Những thứ đã có, không cần đề xuất xây lại

- Link product+source đúng món, tương thích link cũ và first-touch (bot.py:187–205, db.py:409–413).
- QR cho đúng phần thiếu, tự mua sau ghi nhận thanh toán; không bắt nạp ví trước cho luồng mua trực tiếp (bot.py:503–507,1086–1095).
- Nút hỗ trợ và nhờ admin nhắn lại (bot.py:433–451); thông báo shop nghỉ/hết bán/chờ nhập hàng (464–474,543–547).
- Chống mua lặp và fake full journey đã có test: tests/test_store_bot.py:1617,1697; PLAN-173 ghi243test pass. Lượt này không chạy lại test không cần thiết và không mua production.
- Đã có bài thật, nguồn riêng và đo chỉ đọc; không đăng lại chỉ vì0 khách trong vài chục phút.

## Ba câu khách cần được trả lời trước khi mua

1. “Tôi nhận tài khoản mới cấp hay nâng cấp tài khoản đang dùng;30 ngày tính từ đâu; tối đa2 thiết bị được hiểu và thay thiết bị thế nào?” Phần nhận acc cấp và tối đa2 thiết bị có catalog; mốc tính hạn/quy tắc đổi thiết bị chưa thấy trong snapshot, phải xác nhận.
2. “Bảo hành xử lý lỗi gì, trường hợp nào không áp dụng và tôi gửi thông tin gì để được hỗ trợ?” Catalog hiện nhắc ID tiện bảo hành, chưa đủ điều kiện cụ thể; không tự điền câu trả lời.
3. “Sau chuyển khoản tôi xem trạng thái ở đâu; nếu chờ hàng hoặc chuyển muộn thì tiền được xử lý thế nào?” Giải thích bằng luồng đang có và phân biệt tiền về ví với hoàn ngân hàng; không đưa cam kết thời gian chưa đo.

## Hai thử nghiệm hữu hạn — CHƯA THỰC HIỆN

| Đề xuất | Phạm vi cần duyệt trước | Cách đo và quyết định | Dừng khi |
|---|---|---|---|
| FAQ trước trả tiền | Sau khi xác nhận điều kiện #2, thử một nội dung mới chỉ bổ sung FAQ về acc cấp/2 thiết bị/nhận hàng; giữ giá và luồng. Có nguồn riêng được đăng ký trước; không dùng chung source bài đã chạy để gọi là A/B | Chỉ số chính: khách mới có đơn giao trong24h / khách mới đủ24h. Ghi thêm số câu hỏi hỗ trợ, đơn chờ/hoàn. Đọc sau tối đa72h; nếu dưới10 khách đủ24h thì ghi chưa đủ mẫu, không gọi thắng/thua.10 chỉ là ngưỡng đọc thử, không bảo đảm ý nghĩa thống kê | Bất kỳ điều kiện FAQ chưa xác minh, thông tin giá sai, lỗi link/thanh toán hoặc khiếu nại về câu hứa. Không đổi thêm biến giữa đợt |
| Kiểm tra hướng dẫn vào món | Bản demo dùng DB tạm, Telegram/QR/vendor giả; so hướng dẫn chung với câu dẫn đúng món. Mời3–5 người tự nguyện thao tác, chưa tự liên hệ ai | Quan sát có tìm được bước chọn1 tài khoản mà không quay lại catalog; thời gian và câu hỏi nhầm. Mục tiêu4/5 hoàn thành không cần nhắc; nếu chỉ3 người thì báo số tuyệt đối, không suy thành uplift mua hàng. Luồng demo chỉ dùng để tìm chỗ khó hiểu | Người thử hiểu nhầm acc cấp/thời hạn/bảo hành, cần dùng tiền/QR thật, hoặc bấm nhầm tạo giao dịch. Kết thúc sau5 phiên hoặc1 buổi; không thay UI production trong thử |

Hai đề xuất cần chủ vận hành xem cùng PLAN-172, không phải PLAN mới tự giao hay ủy quyền đăng. Giữ chiến dịch đã phát hành nguyên trạng để theo dõi; không mua traffic hoặc giảm giá theo các giả thuyết trên.

## Proof của lượt rà soát

Đã đọc bằng nl -ba đúng file/line nêu trên. Lệnh dựng màn hình từ snapshot, không mở DB khách hoặc gọi mạng:

~~~text
.venv/bin/python -c "import json; from pathlib import Path; from types import SimpleNamespace; from store_bot import messages; p=json.loads(Path('reports/capcut-20261118/trial-measurement.json').read_text())['report']['product']; product=SimpleNamespace(name=p['name'],description=p['description'],price=p['price'],stock=p['upstream_stock']); print(messages.product_detail(product,0)); print(messages.welcome('AI Pass Store',True))"
exit0
rendered product: Giá34.000đ; Bảo hành suốt thời hạn gói (điều kiện xem mô tả); tối đa2 thiết bị; số dư0đ
rendered welcome: 1.Bấm Mua sản phẩm;2.Chọn sản phẩm/số lượng;3.QR;4.Tiền vào tự gửi hàng ngay
~~~

Proof này xác nhận cách render với catalog snapshot, không xác nhận khách đã thấy màn đó hoặc đã mua. Snapshot đọc lúc17:17:40VN18/11 có0khách/mature24h0; kết quả agent số liệu có thể cập nhật sau. Không xuất ID/tên khách hoặc tài khoản đăng nhập sản phẩm.
