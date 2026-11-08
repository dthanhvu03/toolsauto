# PLAN-166 — Gỡ chuỗi đăng bài trực tiếp cũ (Facebook / IG / TikTok upload / Threads cũ)

- Executor: Claude Code (gỡ code) · Duyệt lập kế hoạch: chủ bot (08/11, sau PLAN-165). **Chưa thực thi** — chờ duyệt từng đợt.
- Bối cảnh: mọi bài đã đăng qua Buffer (PLAN-106/108). Giao diện các module cũ đã gỡ ở PLAN-108; các worker PM2 cũ
  (FB_Publisher_1/2, AI_Generator_1/2, Threads_AutoReply / NewsWorker / Publisher) dừng từ 20/10, không có trong `pm2 list`.
  6 tài khoản FB (id 15–20) INVALID, chủ bot đã bỏ.

## Phạm vi khảo sát (08/11)
| Module | Dòng | Ai còn dùng |
|---|---|---|
| `app/features/facebook` | 6.969 | `adapters/dispatcher.py`, `core/process_scan.py`, `platform/local_supervisor.py`, `core/observability/metrics_checker.py`, PM2 FB_Publisher |
| `app/features/instagram`, `tiktok` | 545 + 556 | `adapters/dispatcher.py` |
| `app/features/story` | 536 | `core/queue/publisher_runtime.py` |
| `app/features/affiliates` | 516 | `viral_intake/workers/ai_generator.py` (lookup_queue) |
| `app/features/jobs` | 219 | `app/main.py` (router) |
| `app/features/threads` (trừ `growth/`, `adapter.py`) | ~2.850 | PM2 Threads_AutoReply / NewsWorker / Publisher (đã dừng) |
| tests | 47 file | import các module trên |

**PHẢI GIỮ:** `app/features/threads/adapter.py` (ThreadsAdapter — kéo khách dùng), `app/adapters/contracts.py`
(Buffer dùng `PublishResult`), `core/queue/queue.py` phần recover job (Maintenance), viral_intake (nguồn video Buffer),
`facebook_scraper` ẩn danh/đăng nhập của viral_intake (quét reels nguồn).

## Các đợt (mỗi đợt 1 commit, chạy test trước/sau, dừng nếu đụng Buffer / Studio / kéo khách)
1. **PM2 + worker cũ:** bỏ 7 app khỏi `ecosystem.config.js` (FB_Publisher_1/2, AI_Generator_1/2, Threads_AutoReply,
   Threads_NewsWorker, Threads_Publisher); bỏ entry tương ứng trong `process_scan.py` / `local_supervisor.py`.
   Kiểm tra trước: AI_Generator còn việc gì cho Buffer không (caption viral hiện do Maintenance làm).
2. **Threads cũ:** gỡ `threads/workers/*`, `threads/service`, `threads/dashboard.py` (giữ `adapter.py`, `growth/`).
3. **IG / TikTok upload / Story:** gỡ khỏi `dispatcher.py`, `publisher_runtime.py`; gỡ module.
4. **Facebook:** gỡ `features/facebook` + `metrics_checker` phần FB + dispatcher FB; tách `MediaProcessor` nếu viral_intake còn dùng.
5. **affiliates / jobs:** gỡ lookup_queue khỏi ai_generator (nếu AI_Generator đã bỏ ở đợt 1 thì gỡ luôn), gỡ router jobs.
6. **Dọn còn lại:** tests của module đã gỡ, `.importlinter`, `scripts/archive` (khi không còn ai gọi), dữ liệu Postgres
   (bảng / account FB) — **không DROP / DELETE khi chưa có duyệt trực tiếp**.

## Kiểm tra mỗi đợt
- `import app.main`, `lint-imports` (không thêm BROKEN), pytest các bộ Buffer / Studio / viral / growth / storage / store-bot
  (không chạy 2 file gọi Buffer thật), khởi động thử Maintenance + Web_Dashboard trên bản sao (không restart prod khi chưa báo).

## Proof
### Đợt 1 (08/11) — xong
- `ecosystem.config.js`: bỏ 7 app (FB_Publisher_1/2, AI_Generator_1/2, Threads_AutoReply / NewsWorker / Publisher) → còn 9 app
  đang chạy. AI_Generator chỉ xử lý job nháp FB (DB: 429 job đều buffer) → bỏ an toàn.
- `process_scan.WORKER_MODULES`, `local_supervisor.build_apps`, `pm2_apps` (PM2_SAFE_NAMES + PM2_LOG_MAP, thêm DB_Backup log),
  `system_panel.get_logs` (dùng PM2_SAFE_NAMES), ô chọn tiến trình `app_logs.html` → đúng 9 app.
- Test: đổi worker mẫu sang maintenance / threads growth (logic không đổi); thêm khẳng định worker cũ đã bỏ.
  347 test vùng liên quan + 318 test Buffer/viral/growth/store/storage: qua hết trừ 1 hỏng sẵn (metrics_checker).
  `import app.main` OK; lint-imports như HEAD; ruff sạch file đổi.
- Không cần restart: các app bỏ vốn không chạy. (Nếu từng `pm2 save` có chúng: `pm2 delete <tên>` — hiện `pm2 list` không có.)
