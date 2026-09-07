# ADR-013 — Stack local phải chạy `ai_generator`

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-07
  ("bạn triển khai vá theo thứ tự đi") sau báo cáo luồng code cùng ngày
- **Liên quan**: PLAN-048 (local supervisor), ADR-010 (ngoại lệ backend cho Claude Code)

## Bối cảnh

Dự án đã ngừng VPS, chạy hoàn toàn ở máy local Windows bằng
`start.ps1 -Stack` → `manage.py stack` → `local_supervisor.run_stack`.

`local_supervisor.build_apps()` dựng **3** tiến trình: `web`, `maintenance`,
`fb_publisher`. `ecosystem.config.js` (PM2, chỉ trên VPS) dựng **11**, trong đó có
`AI_Generator` chạy `app/features/viral_intake/workers/ai_generator.py`.

Worker này là mắt xích giữa xưởng nội dung và hàng đợi đăng:

```
material NEW → (maintenance) tải + ffmpeg → Job AWAITING_STYLE
            → (ai_generator) sinh caption → Job DRAFT → Owner duyệt → PENDING
```

Không có nó, mọi job từ xưởng kẹt `AWAITING_STYLE` vĩnh viễn. Fallback
`_auto_style_default` (30 phút) cũng nằm trong chính worker đó nên không có lối
thoát nào khác.

**Kiểm DB 2026-09-07**: 0 job `AWAITING_STYLE`, 7 `DRAFT`, 11 material `DRAFTED`
— đều từ 31/07/2026 khi VPS còn chạy. Tức lỗ hổng **chưa gây hậu quả** vì xưởng
chưa nhận material mới kể từ khi chuyển về local; nhưng lần dùng tiếp theo sẽ kẹt.

## Quyết định

Thêm `ai_generator` vào `build_apps()` của stack local. **Chỉ một tiến trình**
(PM2 chạy hai, nhưng local một máy một người dùng).

## Phạm vi

| Việc | File |
|---|---|
| Thêm `AppSpec` cho `ai_generator` | `app/platform/local_supervisor.py` |
| Test khẳng định stack có `ai_generator` | `tests/test_local_supervisor.py` |
| Chuỗi mô tả thành phần stack | `start.ps1`, `manage.py` (chỉ chuỗi/docstring) |
| Bắt `SIGBREAK` trong `register_signals()` (bổ sung khi làm) | `app/features/viral_intake/workers/ai_generator.py` |

**Vì sao bổ sung `ai_generator.py` vào phạm vi:** supervisor dừng tiến trình con
trên Windows bằng `CTRL_BREAK_EVENT`. `publisher.py` và `maintenance.py` đều bắt
`SIGBREAK`; `ai_generator.py` thì không vì trước giờ chưa từng chạy dưới supervisor.
Đưa nó vào stack mà thiếu handler này là Ctrl+C giết nó giữa lúc gọi Gemini — job
kẹt `AI_PROCESSING` tới lần khởi động sau. Ba dòng, chép nguyên từ `maintenance.py`.

## Ngoài phạm vi

- **Không** thêm `Threads_*` (0 account Threads), `9Router_Gateway`, `DB_Backup`
  (local dùng Task Scheduler — `scripts/register_backup_task.ps1`).
- Không sửa logic `ai_generator.py` ngoài `register_signals()`; không sửa `process_scan.py` (đã liệt kê module này
  ở dòng 40 nên orphan purge nhận diện đúng).

## Hết hiệu lực

Sau khi `build_apps()` trả về `ai_generator`, test xanh, và một lần bật
`start.ps1 -Stack` thấy tiến trình này trong `supervisor_tick` statuses.
