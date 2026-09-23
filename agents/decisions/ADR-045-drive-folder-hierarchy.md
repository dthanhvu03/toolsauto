# ADR-045 — Phân cấp thư mục Drive (COO / CTO / CFO)

- **Ngày**: 2026-09-12
- **Trạng thái**: **ĐÃ ÁP DỤNG** (code `offsite.SUBDIRS` + dời bản đang có)
- **Liên quan**: ADR-012, ADR-023, ADR-030, ADR-042, ADR-043

## Bối cảnh

Sau khi sửa path Drive Windows, Owner yêu cầu **phân cấp thư mục** — không để mọi thứ
phẳng trong `videos/YYYY-MM/`. Cần nhìn bằng ba vai:

| Vai | Câu hỏi |
|-----|---------|
| **COO** | Hôm nay đăng cái nào? Cái nào đã xong? Bản gốc xem chơi để đâu? |
| **CTO** | Path ổn định, `find`/`move` không gãy, ID trong tên (ADR-030), tháng + Đã đăng (ADR-042) |
| **CFO** | Một bản chép hữu ích, không nhân đôi vô tội vạ; dễ dọn theo tuổi / trạng thái |

## Quyết định

```
tools_auto_media/
  backups/                      # CFO: khôi phục DB/config — không lẫn video
  videos/
    01_san-sang/YYYY-MM/        # COO: sẵn đăng tay (bản _reup mới chép)
      Đã đăng/                  # COO/ADR-042: đã bấm ✅ — vẫn trong tháng đó
    03_goc-tai-ve/YYYY-MM/      # COO/ADR-043: tải xem, không reup
```

1. **Số thứ tự đầu tên thư mục** (`01_`, `03_`) — Drive sắp xếp đúng quy trình vận hành.
2. **Không tách `02_da-dang` top-level** — giữ ADR-042: `…/YYYY-MM/Đã đăng/` để một năm sau
   không mở một thùng 300 file.
3. **Chừa số `02_`** cho niche/page sau này nếu Owner cần (vd `02_theo-page/`) — không làm sớm.
4. **Local `storage/media/reup` vẫn là bản làm việc** (📱, Gửi lại, Xử lý lại). Drive = bản
   ngoại vi; không đổi nguyên tắc ADR-012 “sao chép, không di chuyển” trong ADR này.

## Hệ quả kỹ thuật

- `SUBDIRS["video"]` = `videos/01_san-sang`
- `SUBDIRS["download"]` = `videos/03_goc-tai-ve`
- `find_video_copies` / `move_video_copies` vẫn `rglob` dưới `videos/01_san-sang` — OK
- Bản cũ `videos/YYYY-MM/` dời một lần sang `videos/01_san-sang/YYYY-MM/`

## Không làm trong ADR này

- Xóa `_reup` local sau khi có Drive (gãy 📱) — PLAN riêng nếu Owner muốn
- Drive API / link `drive.google.com`
- Phân theo Page Facebook (chờ Owner chốt naming page)
