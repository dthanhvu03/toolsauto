# Gemini caption audit summary (DB + files)

Generated: 2026-03-18

## 1) Kết quả quét DB (`jobs`)

Nguồn: `/home/vu/toolsauto/data/auto_publisher.db`

- **Tổng jobs**: 403
- **Suspect captions** (bị gắn cờ theo heuristic): **8**

### Breakdown theo status

- DONE: 209
- DRAFT: 81
- CANCELLED: 39
- FAILED: 39
- PENDING: 35

### Breakdown theo `last_error` (classifier)

- auth_cookie: 34
- infra_timeout: 12
- empty_result: 10
- content_policy: 1
- other: 23

### 8 job caption nghi lỗi (mẫu tiêu biểu)

Chi tiết đầy đủ: `logs/audit_bad_captions_20260318-101929.md` và `logs/audit_bad_captions_20260318-101929.json`.

- **Job #351 (DRAFT)**: `assistant_prose` (Gemini trả kiểu nói chuyện “Chào Vũ…”)
- **Job #243 (DONE)**: `options_vi` (nhiều câu có cụm “Lựa chọn…”)
- **Job #217 (DONE)**: `options_vi`
- **Job #198 (DONE)**: `options_vi`
- **Job #176 (DONE)**: `options_vi`
- **Job #204 (CANCELLED)**: `options_vi`
- **Job #132 (CANCELLED)**: `options_vi` + `last_error = AI Generation returned empty result`
- **Job #65 (DONE)**: `empty` (caption rỗng)

## 2) Quét files output

Trong `content/` hiện **không có file `.json/.txt/.srt/.vtt`** để đối chiếu caption đã serialize ra file.

- `content/**/*.json`: 0
- `content/**/*.txt`: 0

Hiện tại caption chủ yếu đang nằm trong **DB (`jobs.caption`)**.

## 3) Cookie expired (lỗi anh gửi screenshot)

Ảnh log anh gửi có dòng `Gemini cookies expired` → đây đúng nhóm **auth/cookie** theo policy hiện tại trong `workers/ai_generator.py`:

- **Auth/Cookie** ⇒ job bị **FAILED** + **Circuit breaker** tạm ngưng 30 phút (đòi login/cookie mới).

Tần suất trong PM2 log (AI worker):

- `/home/vu/.pm2/logs/AI-Generator-out.log`: **`cookies expired` xuất hiện 292 lần**

Điều này giải thích vì sao đôi lúc Gemini trả về lỗi/FAILED hàng loạt: cookie/session đang hết hạn hoặc chưa login ổn định.

