# Quickstart: Quản lý nguồn khi video đổ về nhiều

## Điều kiện

- Nhánh `003-manage-source-intake`.
- Môi trường chạy test của repo. Ca máy dùng cơ sở dữ liệu nhớ tạm, không gọi mạng.

## Ca máy

Từ gốc repo, chạy các ca nguồn đang có cộng ca mới của feature này:

```bash
./venv/bin/python -m pytest tests/test_viral_sources.py -q --tb=short
```

Kỳ vọng:

- Hai nguồn, video chờ gắn nguồn A không bị đếm vào nguồn B. Video không gắn nguồn không bị đếm.
- Quét nguồn đang tắt không thêm video và không đọc kênh.
- Mười video đủ mức xem, số tối đa riêng là 3, chỉ thêm 3 video và cả ba gắn đúng nguồn.
- Đặt số riêng của nguồn A không đổi nguồn B và không đổi mức chung.
- Số video tối đa nhỏ hơn 1 không được lưu.
- Tắt nguồn hoặc đổi ngưỡng không xóa video đã có.

## Ca trên máy chủ kênh

1. Gõ lại lệnh danh sách nguồn. Mỗi nguồn hiện số video còn chờ và ngưỡng đang dùng.
2. Tắt một nguồn đang có video chờ, rồi bấm quét nguồn đó. Câu trả lời nói nguồn đang tắt. Số video chờ không giảm.
3. Đặt riêng một nguồn ở mức xem thấp và tối đa 3 video, rồi quét. Lần đó thêm không quá 3 video.
4. Xóa số riêng của nguồn đó. Lần quét sau dùng lại mức chung.
