# Chuyên viên số liệu — đợt thử CapCut

Vai trò phân tích của agent AI trong nhóm, chỉ đọc dữ liệu và chuẩn bị quyết định. Không thay vận hành, không tự phát hành nội dung. Phạm vi PLAN-173 đã đọc cùng PLAN-172, ADR-067 và current-status trước khi làm.

## Kết quả hiện tại

Đo campaign lúc **17:17:40 ngày 18/11/2026, giờ Việt Nam**; catalog/SQL đối chiếu lúc **17:19:59**. Bài được xác minh tại https://www.threads.com/@anlinh_08_10/post/Df4LF2IFIlg ; source riêng threads_ai_cc18_anlinh_p1. Cửa sổ đo bắt đầu 16:21:32, là lúc bắt đầu attempt, không phải bằng chứng giây xuất bản chính xác.

| Chỉ số | Mốc 16:26 | Mới 17:17 | Thay đổi |
|---|---:|---:|---:|
| Khách mới có source trial | 0 | 0 | 0 |
| Khách ghi nhận xem CapCut | 0 | 0 | 0 |
| Khách tạo QR cho CapCut | 0 | 0 | 0 |
| Khách có đơn CapCut đã giao | 0 | 0 | 0 |
| Doanh thu CapCut sau hoàn | 0đ | 0đ | 0đ |
| Khách đủ 24h / có đơn trong 24h | 0 / 0 | 0 / 0 | — |
| Tỷ lệ chuyển đổi 24h | chưa có mẫu số | null | không ghi 0% |

SQL độc lập đếm **exact source = 0**, đếm prefix = 0, số nhãn nguồn khác có cùng prefix = 0; khớp report. Đây là kiểm tra cần thiết vì công cụ hiện lọc startswith(source), chưa phải điều kiện source bằng tuyệt đối cho mọi tình huống tương lai. Nếu tái dùng link cho draft khác, không phân biệt được bài nào đem khách đến.

Chưa có dữ liệu để xác định chất lượng nội dung hoặc tỷ lệ xem → Start. Bot chỉ ghi first-touch của khách mới; người đã vào bot từ trước không được gán lại. Không có impression hoặc lượt bấm link trước Start. Thiếu marker xem món không đủ chứng minh khách bỏ màn; QR/nạp tiền cũng khác đơn giao. Khoảng 56 phút quan sát sau attempt không phải một kỳ 24 giờ.

## Tiền trên một đơn vị

Catalog #2 lúc đối chiếu: **Capcut Pro 30D BHF acc cấp**, active/upstream available; cache tồn **22**, sync **17:19:12 VN**. Cache tồn không chứng minh có đơn mới hoặc số món bán từ bài này; cần kiểm lại trước lời chào bán tiếp theo.

| Khoản | Giá trị hiện ghi |
|---|---:|
| Giá bán / đơn vị | 34.000đ |
| Giá vốn ghi nhận / đơn vị | 31.360đ |
| Chênh lệch trước chi phí khác | **2.640đ** |
| Chênh lệch / giá bán | **7,76%** |
| Thiếu giá vốn | Không, ở snapshot catalog này |
| Lãi ròng / tiền có thể rút | **Chưa xác định** |

Với giả định một khách mua một đơn vị đủ giá, không hoàn tiền, không có mua lại: trần chi phí thu hút khách hòa vốn **trước mọi chi phí khác** là **2.640đ/khách mua thành công**. Đây chỉ là giới hạn số học từ giá và vốn, không phải ngân sách quảng cáo được duyệt. Chi phí hỗ trợ, hạ tầng, thanh toán, hoàn/lỗi và công sức chưa được phân bổ, nên trần thực tế phải thấp hơn nếu các chi phí đó dương. Không dùng 2.640đ như lãi ròng hoặc tiền mặt thực nhận; khi có đơn cần dùng vốn/giá thực tế của đơn, không thay bằng catalog hiện tại.

Không có dữ liệu mua lại để tính LTV. Không giả định thêm doanh thu tương lai để biện minh chi phí thu hút khách.

## Ba quy tắc quyết định

1. **Mẫu số trước, tỷ lệ sau.** Chưa có khách đủ 24h thì giữ null và báo số tuyệt đối. Lần đánh giá sau khoảng 16:22 ngày 19/11 là mốc 24h của bài; từng khách chỉ vào mẫu số khi chính họ đã đủ 24h từ lúc vào bot. Có 0 khách sau mốc đó vẫn chưa phân biệt được thiếu tiếp cận, link ít được bấm hay nội dung chưa hợp.
2. **Theo chỗ có bằng chứng để chọn việc.** Nếu source bắt đầu có khách nhưng chưa có đơn, xem QR đã tạo, trạng thái thanh toán và đơn giao/hoàn trước khi đề xuất sửa luồng. Nếu vẫn 0 khách, ưu tiên xin/đọc số tiếp cận và tương tác thật của bài nếu có quyền, rồi mới chọn thử nội dung. Không coi số 0 hoặc thiếu marker là bằng chứng nguyên nhân; chưa tự chạy thêm thử nghiệm.
3. **Chỉ mở rộng khi có đơn và phần đóng góp đủ bù chi phí.** Khi có đơn, cộng doanh thu sau hoàn, trừ vốn thực tế đã ghi và chi phí liên quan đã đo. Nếu vốn thiếu thì ghi chưa đủ dữ liệu, không thay bằng 0. Nếu chi phí thu hút một khách mua đã vượt 2.640đ trong giả định một đơn vị và chưa chứng minh đóng góp mua lại, riêng giao dịch đầu đã không đủ bù chi phí khác: báo chủ bot xem lại economics; không tự tăng ngân sách hay giảm giá.

## Proof đã chạy

Từ /home/vu/toolsauto:

~~~text
PYTHONPATH=. .venv/bin/python reports/capcut-20261118/measure_trial.py
observed_at=2026-11-18T10:17:40.243550+00:00
errors=[]
cohort.customers=0
selected_product.stages={product:0,confirm:0,qr:0,paid:0,order:0}
selected_product.delivered_orders=0
selected_product.revenue_after_refunds=0
selected_product.mature_24h=0
selected_product.converted_24h=0
selected_product.conversion_24h_pct=null
exit 0

Independent SQLite mode=ro; BEGIN; env used only for DB path/admin exclusions:
observed_at_vn=2026-11-18T17:19:59.513997+07:00
exact_source_customers=0
prefix_customers=0
prefix_other_labels=0
independent_sql_matches=true
price=34000; upstream_cost=31360; upstream_stock=22
unit_spread_before_other_costs=2640
exit 0
~~~

SQL cohort dùng users JOIN state theo src:, cửa sổ julianday(created_at) >= since và < until, loại admin bằng tham số; đối chiếu s.value = source với substr(s.value,1,length(source)) = source. Chỉ count, không xuất ID/tên khách. Query catalog chỉ whitelist id/name/price/upstream_cost/upstream_stock/upstream_available/active/synced_at. Mọi kết nối SQLite mode=ro + BEGIN; không gửi tin hoặc gọi vendor/API/AI/browser. Không viết script hay sửa code production.

Artifact số tổng hợp: measurement-snapshot.json trong cùng thư mục, có thời gian và giới hạn diễn giải. Existing trial-measurement.json được cập nhật bởi công cụ đo đã được ủy quyền; hai đầu ra sở hữu riêng của agent là tài liệu này và measurement-snapshot.json.
