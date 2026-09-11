# ADR-042 — "Đã đăng": một trạng thái, không phải một thư mục

- **Ngày**: 2026-09-11
- **Trạng thái**: **ĐÃ DUYỆT** — Owner hỏi *"anh đã đăng video đó rồi, thì trên tele bấm đã
  đăng để nó di chuyển thư mục khác không"*, nghe phân tích xong: *"oke em triển khai đi"*.
- **Liên quan**: ADR-018 (READY = đăng tay), ADR-024 (chống trùng), ADR-027 (tin video),
  ADR-030 (bản chép Drive theo tháng), ADR-037 (`/sansang`), ADR-041 (phần con)

## Bối cảnh

Material dừng ở `READY` rồi hết — Owner đăng xong, tool **không biết**. Hệ quả: `/sansang`
liệt kê mãi cả video đã đăng; phần 1/3 đăng rồi vẫn hiện cả ba; Drive lẫn đã-đăng / chưa-đăng;
và không có dữ liệu "tuần này đăng gì, ngày nào".

"Di chuyển thư mục" là **triệu chứng**. Dời file mà không ghi trạng thái thì DB vẫn nói READY,
`/sansang` vẫn hiện, đường dẫn trong tin cũ sai — thêm một nhãn nói dối.

## Quyết định

1. **`ViralStatus.POSTED` + `posted_at`** trên material. Đây là sự thật gốc; thư mục là hệ quả.
2. **Nút "✅ Đã đăng"** ngay trên tin video (ADR-027) và trong `/sansang`. Một cú bấm:
   trạng thái → `POSTED`; bản `_reup` cục bộ dời vào `<platform>/da-dang/`; bản Drive dời vào
   `videos/YYYY-MM/Đã đăng/` (**cùng tháng**, không gom một thư mục chung — một năm sau thư mục
   chung là 300 file không ai mở nổi). Tin trả lời ghi rõ file nằm đâu.
3. **Nút "↩️ Chưa đăng"** lùi lại — bấm nhầm là chuyện thường; không lùi được thì Owner ngại
   bấm, và nút không ai bấm là nút không tồn tại.
4. `/sansang` tự ẩn POSTED (lọc theo trạng thái sẵn có). Thêm **`/dadang`**: 10 video đăng gần
   nhất, kèm nút Chưa đăng.
5. **Chống trùng (ADR-024) phải soi cả `POSTED`.** `DEDUP_STATUSES` hiện là
   `(READY, DRAFTED, REUP)` — không thêm `POSTED` thì đúng thứ đã đăng lại lọt vào được. Đây là
   lý do quan trọng nhất để trạng thái này tồn tại.

## Cố ý KHÔNG làm

- **Không xoá file cục bộ** khi bấm Đã đăng: xoá là không lùi được. Đầy đĩa thì mở rộng cơ chế
  giữ-N-ngày sang `da-dang/` sau khi thấy số thật.
- **Không bắt dán link bài Facebook** ở bước này: thêm một bước gõ là Owner bỏ qua cả nút. Để
  sau: trả lời tin bằng link ⇒ tool tự gắn (`posted_url`) — lúc đó mới đo được lượt xem thật.
- Không tự chuyển trạng thái theo lịch hay theo Job — luồng Job đã có `DONE` riêng.

## Phạm vi

| Việc | File |
|---|---|
| Trạng thái + cột + migration | `constants.py`, `models/viral.py`, `alembic/versions/s6…_posted.py` |
| Dời bản Drive (tìm theo `<id> - …`) | `app/core/storage/offsite.py` |
| `mark_posted` / `unmark_posted` | `viral_intake/service.py` |
| Chống trùng soi POSTED | `viral_intake/dedup.py` |
| Nút trên tin video | `notifier/service.py` |
| Hook, `/dadang`, callback | `bootstrap_hooks.py`, `command_handler.py`, `event_router.py` |
| Web: badge, nút, bộ lọc | `viral_row.html`, `app_viral.html`, `viral_intake/router.py` |
| Test | `tests/test_mark_posted.py`, `tests/test_telegram_posted.py` |

## Proof

`tests/test_mark_posted.py` (17): SQLite + đĩa tạm + Drive giả — Đã đăng dời `_reup` vào
`da-dang/` và bản Drive vào `<tháng>/Đã đăng/`, **file gốc không đụng** (còn cắt lại được);
`find_reup_path` vẫn thấy file đã dời (nút Gửi lại / Tải file còn dùng); Drive tắt hay không
có bản chép vẫn ghi nhận POSTED; Chưa đăng về nguyên trạng; **bản copy của video POSTED bị
chống trùng bắt**. `tests/test_telegram_posted.py` (7): nút, lệnh, nút lùi trên tin trả lời.

Ba test cũ ở `test_notify_jobless.py` đổi kỳ vọng: tin chữ (không gửi được video) nay cũng đi
qua `send_with_buttons` để có nút Đã đăng — cố ý, không phải hồi quy.

**985 passed, 16 skipped, 0 failed** (trước: 961) · `ruff` sạch · `lint-imports` 2 hợp đồng
giữ · `alembic heads` = `s6a3b4c5d6e7`.

## Hết hiệu lực

Sau proof: bấm Đã đăng trên SQLite + đĩa tạm ⇒ trạng thái, file cục bộ, bản Drive đúng chỗ,
lùi lại về nguyên trạng; `find_reup_path` vẫn thấy file trong `da-dang/` (nút Gửi lại còn
dùng được); chống trùng bắt được bản copy của video POSTED; toàn suite xanh; `lint-imports`
giữ; `ruff` sạch.
