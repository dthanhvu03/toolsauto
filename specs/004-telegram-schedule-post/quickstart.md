# Quickstart: Lên lịch đăng bài từ Telegram

## Điều kiện

- Nhánh `004-telegram-schedule-post`.
- Môi trường chạy test của repo. Ca máy dùng cơ sở dữ liệu nhớ tạm và nơi đăng giả, không gọi mạng.

## Ca máy

Từ gốc repo:

```bash
./venv/bin/python -m pytest tests/test_telegram_schedule.py tests/test_buffer_queue.py -q --tb=short
```

Kỳ vọng:

- Giờ hợp lệ tạo một lịch và câu xác nhận có tên kênh cùng giờ Việt Nam. Bài không bị đăng ngay.
- Cùng video cùng kênh, lần chọn giờ sau sửa lịch cũ, không thêm job và không thêm bài.
- Giờ đã qua, giờ không đọc được, sớm hơn 10 phút, xa hơn 30 ngày: không tạo lịch.
- Thiếu lời bài hoặc kênh lạ: không tạo lịch.
- Hôm nay hoặc tuần hết suất: không tạo lịch mới.
- Hủy bài chưa đăng thì bài không còn lịch. Bài đã đăng thì hủy và đổi giờ đều bị từ chối.
- Xếp hàng không chọn giờ vẫn không gửi mốc giờ. Đăng ngay vẫn không hỏi giờ.
- Ca xếp hàng cũ trong `tests/test_buffer_queue.py` vẫn pass.

## Ca trên máy chủ kênh

1. Mở một video sẵn sàng đã có lời bài. Bấm hẹn giờ, chọn kênh, chọn sáng mai 08:00. Chat nói đúng kênh và 08:00 ngày mai. Bài chưa lên kênh.
2. Gõ giờ khác theo mẫu trong chat. Chat đổi thành giờ mới, vẫn một bài.
3. Gõ một giờ hôm qua. Chat từ chối và bài vẫn giữ giờ đang hẹn.
4. Hủy lịch. Lệnh hạn đăng không còn bài đó.
5. Xếp một video khác vào kênh mà không hẹn giờ. Bài vào hàng chờ, chat không bắt chọn giờ.
