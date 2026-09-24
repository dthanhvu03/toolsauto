# Quickstart: Gộp bài trùng trong báo cáo chỉ số

## Điều kiện

- Nhánh `001-group-duplicate-posts`.
- Môi trường chạy test của repo, không cần kênh thật cho ca máy.

## Ca máy

Từ gốc repo:

```bash
./venv/bin/python -m pytest tests/test_buffer_api.py -q --tb=short
```

Kỳ vọng sau khi có ca gộp:

- Năm bản cùng chữ, cùng kênh, cùng ngày ra một nhóm, số bản là 5.
- Hai chữ khác nhau ra hai nhóm.
- Cùng chữ ở hai ngày ra hai nhóm.
- Tóm tắt ghi một nội dung và năm bản lịch sử, không ghi năm nội dung.
- Ca không gọi lệnh xóa bản.

## Ca trên máy chủ kênh

1. Gõ lại `/so`. Tin cũ không đổi.
2. Đọc tóm tắt Mê Câu Cá. Với năm bản cùng video trong ngày 23/09, câu phải là một nội dung và năm bản lịch sử.
3. Bấm Mê Câu Cá. Danh sách còn một khối cho video đó, có ghi năm bản.
4. Một nội dung chữ khác trên cùng kênh vẫn là một khối riêng.
5. Đếm bản trong lịch sử đăng của kênh. Số bản không giảm sau khi xem.

Nếu báo cáo đang cắt ở 50 bài mới nhất, chỉ xét các bản nằm trong tin đó.
