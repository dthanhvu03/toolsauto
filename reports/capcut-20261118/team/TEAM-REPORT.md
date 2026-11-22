# Nhóm cộng tác CapCut — 18/11/2026

Chủ bot yêu cầu vài agent đóng vai cộng tác viên và chuyên viên để làm việc. Đã giao ba nhánh song song, mỗi agent có file đầu ra riêng; Codex chính rà chứng cứ, tổng hợp và chịu trách nhiệm báo cáo. Đây là các vai trò AI hỗ trợ công việc, không phải nhân viên thật hoặc lời cam kết làm việc liên tục ngoài phiên. Lịch theo dõi nguồn đã được đặt riêng mỗi2giờ.

| Vai trò | Việc đã giao | Đầu ra |
|---|---|---|
| CTV nội dung |3bài theo nhu cầu,2reply, điều cần xác minh trước phát hành | CONTENT-CONTRIBUTOR.md |
| Chuyên viên chuyển đổi | Rà đường từlinkđếnđơngiao, tìm3điểm cần làm rõ với dòng code, chuẩn bị2thửnghiệm có cách đo | CONVERSION-SPECIALIST.md |
| Chuyên viên số liệu | Đo nguồn trial, SQLđộc lập, giá/vốn và giới hạn diễn giải | MEASUREMENT-SPECIALIST.md + measurement-snapshot.json |

## Kết quả đã kiểm

- Nội dung:3bài+2reply, lần lượt253/300/252/190/207ký tự, tất cả<=470. Chưa đăng/gửi. Dùng lại link trial sẽ trộn attribution với bài đãđăng; muốn dùng nội dung mới để so sánh riêng cần source riêng được bot/report hỗ trợ. Không phát hành thêm các draft chỉ vì đã viết xong.
- Số liệu17:17VN: source threads_ai_cc18_anlinh_p1 có0khách mới/QR/đơn,0đ; chưa có mẫu số24h, tỷ lệnull. SQLđộc lập17:19VN: exactsource=prefix=report0. Chưa có impression/click trướcStart nên chưa xác định thiếu tiếp cận hay nội dung.
- Catalog17:19VN:34.000đ bán/31.360đ vốn ghi, spread2.640đ trước chi phí; lãi ròng chưa xác định. Cache tồn22 không phải số đơn từcampaign.

## Chuyên viên chuyển đổi đã tìm thấy

- BHF đang được UI diễn giải là “suốt thời hạn gói, điều kiện xem mô tả”, nhưng snapshot mô tả chưa có điều kiện xử lý cụ thể. Cần xác nhận điều kiện, chưa kết luận bảo hành sai. Evidence: store_bot/messages.py:188 và phần product_detail.
- Các câu QR→gửi ngay cần được rà cùng nhánh chờ nhập hàng và hoàn về ví bot. Hệ thống đã có cảnh báo riêng; chưa có chứng cứ khách bỏ mua vì điểm này.
- Welcome vẫn hướng dẫn bấm danh sách/chọn món khi link đã mở đúng CapCut; đây là cơ hội thử câu dẫn theo ngữ cảnh, không phải lỗi bắt khách đi lại.

Ba câu hỏi trước mua và hai thử nghiệm có chỉ số/điều kiện dừng nằm trong CONVERSION-SPECIALIST.md, đều chưa thực hiện.

## Ưu tiên điều phối

1. Làm rõ điều kiện hỗ trợ/bảo hành và trạng thái giao hàng trước khi mở rộng lời quảng bá. BHF hiện là ký hiệu catalog, không tự đặt điều kiện; đối chiếu message đanghiện và thông tin nhàcungcấpthực tế trước scope sửa. Không gọi vendor trong lượt này.
2. Giữ một bài thử hiện tại làm mốc; theo dõi khách/đơn bằngmeasure_trial.py. Với0khách và chưa có số tiếp cận, không kết luận luồng mua haycopy là nguyênnhân.
3. Chuẩn bị thử riêng thông điệp khi đủ dữ liệu; chỉ đăng nội dung mới khi có phạm vi phát hành cụ thể. Giữ quota/giá/flow hiện tại; không tự gửi tin hoặc tăng quảng cáo.

Các đề xuất trong tài liệu nhóm là đầu ra để review, chưa phải thay đổi code hoặc quyết định phát hành. Lượt này chỉ cập nhật tài liệu và chạy báo cáo chỉđọc; không sửa backend/template/DB, không gửi thêm và không commit/push.

## Proof hoàn tất lượt nhóm

5/5 artifacts tồn tại và không rỗng; measurement-snapshot.json parsePASS, independent_SQLmatchesPASS. Root đếm5draft:253/300/252/190/207ký tự, đều<=470. git diff --check exit0. Source/test diff giữ nguyên như đầu lượt: config+7,bot+14/-4,test_store+111,test_threads+31; không triển khai thêm code.

**Execution Done. Cần Claude Code verify + handoff.** Hoàn thành lượt công việc của ba vai trò; lịch đo2giờ đã có vẫn tiếp tục theo ủy quyền, không hứa agent chạy liên tục khi không được gọi.
