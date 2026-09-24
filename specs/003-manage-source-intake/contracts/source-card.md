# Contract: Thẻ nguồn và lần quét

Bề mặt là danh sách nguồn chủ kênh đang mở trong chat, cùng kết quả một lần quét. Không thêm lệnh mới.

## Thẻ một nguồn

Mỗi nguồn một tin:

- Tên nguồn và đang bật hay tắt.
- Ngưỡng đang dùng: hai số riêng nếu có, nếu không thì nói đang dùng mức chung.
- Số video mới còn chờ của đúng nguồn đó. Video không gắn nguồn không tính.
- Kết quả lần quét gần nhất: lúc quét, số video mới thêm được, hoặc lỗi nếu lần đó hỏng.

Nút quét và nút bật hoặc tắt giữ chỗ như hiện tại.

## Đặt số riêng

Cùng lệnh mở danh sách nguồn:

- Kèm mã nguồn và hai số nguyên: lưu mức xem tối thiểu và số video tối đa cho nguồn đó. Nguồn khác và mức chung không đổi. Trang đích của nguồn không đổi.
- Kèm mã nguồn và lời xóa số riêng: hai số riêng trở về trống, lần quét sau dùng mức chung.
- Số không phải số nguyên, mức xem âm, hoặc số video tối đa nhỏ hơn 1: không lưu, trả một câu vì sao.

## Lần quét

- Nguồn tắt: không đọc kênh, không thêm video, câu trả lời nói nguồn đang tắt. Số video đang chờ không giảm.
- Nguồn bật: chỉ thêm video đạt mức xem đang có hiệu lực, và dừng khi đủ số video tối đa đang có hiệu lực. Video thêm mới gắn về nguồn vừa quét.
- Video đã chờ, đang xử lý, hoặc đã sẵn sàng không bị xóa.
