# ADR-014 — Ping "còn sống" ra healthchecks.io; sửa list model Gemini đã shut down

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-07
  ("oke triển khai theo thứ tự từng mục nhé", sau khảo sát `docs/research/2026-09-07-tich-hop-mien-phi.md`)
- **Liên quan**: ADR-012 (mẫu SettingSpec trong trang settings), ADR-013, PLAN-057 (backup)

## Bối cảnh

Ba lần "chết không ai biết": Postgres tự tắt 3 lần; Drive im lặng hỏng (backup báo
thành công nhưng bản ngoại vi không có); tài khoản Facebook chết 5 tuần mới biết.
Điểm chung: hệ chỉ biết **báo khi có lỗi**, không có ai báo khi **im lặng**.

Khảo sát 07/09: **healthchecks.io** free 20 check, kênh Telegram/ntfy/email; mô hình
"dead man's switch" — worker ping `hc-ping.com/<uuid>` đều đặn, quá hạn thì dịch vụ
báo. Không cần server, không cần mở port.

Đồng thời `app/core/ai/native_fallback.py:22-35` còn liệt kê `gemini-2.0-flash` /
`gemini-2.0-flash-lite` — trang models Google ghi **đã shut down**. Chuỗi fallback
gọi vào model chết trước khi tới model sống.

## Quyết định

1. Thêm module `app/core/observability/heartbeat.py`: `ping(url_key, kind="")` —
   đọc URL từ runtime settings, **không có URL thì im lặng bỏ qua**, có thì
   `GET` với timeout ≤5s, mọi lỗi mạng chỉ ghi log warning. **Ping thất bại không
   bao giờ làm việc chính thất bại.**
2. Ba điểm ping: cuối `manage.py db backup` (thành công → `/`, thất bại → `/fail`),
   cuối mỗi vòng `maintenance`, cuối mỗi vòng `fb_publisher` (login/account INVALID →
   `/fail`). Ba `SettingSpec` trong trang `/app/settings`, nhóm "Giam sat" — Owner dán
   URL, không sửa code.
3. Sửa list model Gemini trong `native_fallback.py`: bỏ 2.0, ưu tiên `gemini-3.5-flash`
   → `gemini-3.5-flash-lite` → `gemini-2.5-flash`. Không đổi logic fallback.
4. Thêm lệnh `manage.py ai check`: gọi 1 request nhỏ tới provider đang cấu hình
   (Gemini hoặc OpenAI-compatible qua `OPENROUTER_*`), in kết quả, thoát mã 1 nếu 401.
   Để Owner kiểm key trước khi bật stack.

## Phạm vi

| Việc | File |
|---|---|
| Module ping | `app/core/observability/heartbeat.py` (mới) + test |
| 3 SettingSpec | `app/core/settings.py` |
| Gọi ping | `manage.py` (db backup), `app/features/system_panel/workers/maintenance.py`, `app/features/facebook/workers/publisher.py` — mỗi chỗ ≤3 dòng |
| List model | `app/core/ai/native_fallback.py`, `app/core/ai/pipeline.py` (`default_model`), ví dụ trong `settings.py` — chỉ hằng số/chuỗi |
| Lệnh kiểm key | `manage.py` (`ai check`) |
| Mẫu `.env` | `.env.example` |

## Ngoài phạm vi

- Không tự tạo check trên healthchecks.io (cần tài khoản Owner).
- Không đổi logic AI pipeline, không thêm provider mới — Groq cắm qua `OPENROUTER_BASE_URL`
  sẵn có.
- Không ping từ `ai_generator` (chưa cần; thêm sau nếu Owner muốn).

## Hết hiệu lực

Sau khi Owner dán 3 URL vào settings và thấy check "up" trên healthchecks.io.
