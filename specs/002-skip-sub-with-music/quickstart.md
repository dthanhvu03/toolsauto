# Quickstart: Bỏ phụ đề khi video đã có nhạc

## Điều kiện

- Nhánh `002-skip-sub-with-music`.
- Môi trường chạy test của repo. Ca máy không cần video thật và không cần bộ nhận lời nói.

## Ca máy

Từ gốc repo:

```bash
./venv/bin/python -m pytest tests/test_subtitle_layer.py -q --tb=short
```

Kỳ vọng sau khi có ca lọc:

- Một đoạn điểm không-phải-lời-nói 0,6 bị bỏ.
- Một đoạn tỷ lệ lặp chữ 2,5 bị bỏ.
- Một đoạn lời nói điểm 0,2 được giữ dù cạnh nó có đoạn nhạc điểm 0,9.
- Một đoạn không có hai điểm số được giữ.
- Hết đoạn thì không tạo file hình có phụ đề.
- Ca dựng kiểu chữ cũ vẫn xanh.

## Ca trên máy chủ kênh

1. Xử lý một video chỉ có nhạc. Video nhận được không có chữ trên hình.
2. Xử lý một video có người nói thành câu, có nhạc nền nhỏ. Video nhận được có phụ đề cho câu nói.
3. So phần chữ đăng bài của video nhạc với một video cùng loại trước quy tắc này. Phần chữ đăng bài không bị xóa vì video có nhạc.
4. Mở một video đã xử lý xong từ trước. File đó không bị làm lại chỉ vì quy tắc này.
