# Current Status

## ⚠️ CẢNH BÁO BẢO MẬT (2026-08-11) — chờ Owner xử lý

`scratch/threads_cookies.json` chứa **cookie phiên thật** (FB `xs`/`c_user`,
IG `sessionid`, TikTok `msToken`) bị commit ở `a723c0f` ngày 2026-04-25 trên repo
**PUBLIC** `github.com/dthanhvu03/toolsauto` → phơi công khai ~3,5 tháng.

Đã xử (PLAN-051 §D): `filter-branch` purge cả 13 branch + force-push + gc.
**Nhưng object mồ côi vẫn tải được công khai theo SHA** (`gh api ...?ref=a723c0f`
→ 6908 bytes) cho tới khi GitHub tự GC.

Owner vẫn phải làm: (1) **đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok** —
việc duy nhất thực sự vô hiệu hoá cookie đã rò; (2) quyết private repo và/hoặc
ticket GitHub Support. Ai đã clone phải clone lại (mọi SHA đã đổi).

## System State (2026-08-11)

- **Máy không chạy được stack**: interpreter `pythoncore-3.14-64` biến mất,
  `venv\Scripts\python.exe` là stub trỏ vào đường dẫn đã mất → không chạy được
  `pytest` lẫn worker. Registry HKCU vẫn trỏ path cũ.
- Container `toolsauto_postgres` tắt 10 ngày, đã `docker start` lại để audit.
- **CI đỏ từ 2026-07-29**, 5 commit cuối trên `main` chưa từng deploy:
  workflow đặt Python 3.10 nhưng requirements ghim numpy 2.4.2 (cần ≥3.11).
- Hàng đợi tắc: 7 job DRAFT `[AI_GENERATE]` + 2 PENDING, tất cả `is_approved=false`;
  job #2 trỏ media đã bị xoá. `viral_materials` 11/11 kẹt DRAFTED.

## Done 2026-08-11 — audit tính năng + dọn nợ kỹ thuật (PLAN-051)

| Việc | Proof |
|---|---|
| Audit toàn bộ tính năng bằng DB thật + CI thật (không chỉ đọc doc) | Bảng row-count 26 bảng; `gh run list` 5 lần failure |
| Gỡ cookie phiên khỏi git index + `.gitignore` chặn `*cookies*.json` | `git ls-files \| xargs grep` secret pattern → rỗng |
| Xoá 731 dòng code chết (3 template, `gemini_api.py`, 2 shim) | grep 0 tham chiếu; ADR-006 §7 ghi closure |
| Sửa docstring `native_fallback.py` chỉ sai chỗ vision | vision nằm ở `call_native_gemini_vision` từ TASK-025 |
| ADR-009: `GenericAdapter` là code không thể chạm tới | `dispatcher.py:88` luôn ghi đè Registry cho cả 4 platform |

Diff đang chờ Owner review, **chưa commit**: 9 file, −750 dòng.

## Next Action (2026-08-11)

1. **Owner:** đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (vô hiệu cookie đã rò)
2. **Owner:** quyết repo private và/hoặc purge lịch sử git (thao tác phá huỷ)
3. Cài lại Python 3.14 + dựng venv → mở lại pytest
4. Bump `python-version` trong `deploy.yml` + xử `test_threads_world_news.py` → mở lại CI
5. Owner chốt ADR-009 trước khi động vào `GenericAdapter`

## System State (2026-07-31)

- PLAN-048 stack (supervisor + smart gate + orphan purge) đã qua vòng review/hardening
- **PLAN-049**: Facebook đăng được **bài feed** (chữ thuần / chữ + ảnh), không còn chỉ Reels
- FB **POST = Reels** vẫn chỉ video; **FEED** nhận ảnh/video/không media — hai loại tách bạch
- Job #6 (PNG vào Reels) bị chặn trước khi mở browser, tính là VALIDATION (không phạt account)
- Stack đang **TẮT**. Test suite: **161 passed**

## Done This Session — phần 2: luồng bài feed (PLAN-049)

| Việc | Proof |
|---|---|
| `JobType.FEED` + `assert_feed_media()` + rẽ nhánh dispatcher | `tests/test_facebook_feed_post.py` (17 pass) |
| `FacebookFeedComposer` — mở composer, gõ chữ, đính ảnh, Tiếp → Đăng | Đăng thật lên Page `kids0810`, owner đã xác nhận thấy bài |
| Form job thủ công chọn Reels / Bài feed, `accept` đổi theo | `test_media_ui_consistency` cập nhật theo chính sách mới |
| 2 lỗi chỉ lộ khi chạy live | Bước "Tiếp" của Page; `pre_post_delay()` thiếu tham số `page` |

Còn nợ: `post_url` của bài feed (Facebook Page không phơi permalink ra DOM). Chi tiết + hướng vá ghi trong PLAN-049.

## Done This Session (audit + fix 12 findings)

| Vùng | Thay đổi | Proof |
|---|---|---|
| Nhận diện process | `app/core/process_scan.py` mới — match cả `-m app.x.y` lẫn `app/x/y.py` (PM2), ancestry chống PID reuse, hydrate lazy | `tests/test_process_scan.py` (20 pass) |
| Orphan purge | Chỉ kill browser root có `--user-data-dir` nằm trong profile root chuẩn, không có ancestor worker sống, đã chạy > 120s | `tests/test_orphan_browser_purge.py` (13 pass) |
| Supervisor | State/lock tuyệt đối trong `storage/db/config/`, lock `O_CREAT|O_EXCL` + thu hồi stale, stop bằng CTRL_BREAK | `tests/test_local_supervisor.py` (10 pass) |
| Media gate | Một nguồn sự thật cho extension, caption-only manual job vẫn tạo được, upload bị từ chối không để lại file | `tests/test_facebook_media_gate.py` (14 pass) |
| Circuit breaker | `error_type=VALIDATION` không tăng `consecutive_fatal_failures` | như trên |
| Heartbeat | Mọi early return của publisher đều stop heartbeat (finally) | `tests/test_publisher_heartbeat.py` (3 pass) |
| ffmpeg | `app/core/media/ffmpeg_path.py` mới; thumbnail/DRM/orchestrator/reup đều resolve binary | `tests/test_ffmpeg_resolution.py` (10 pass) |
| UI | Form create/manual: video-only cả label, drag-drop lẫn `accept` | `tests/test_media_ui_consistency.py` (4 pass) |
| Hiệu năng | Quét process 8.3s → 0.02s (capture) + cache 30s cho đếm browser | đo trực tiếp trên máy (513 process) |

## Hardening vòng 2 (sau review)

| Rủi ro | Xử lý |
|---|---|
| Lệnh chỉ *nhắc tới* đường dẫn worker (`git diff`, `compileall`, editor) bị nhận là worker → supervisor không spawn | Parse argv thật (`-m` / positional script), argv[0] **và** tên process phải là interpreter |
| Browser mất ancestry khi job còn RUNNING → bị coi là orphan | Purge nhận `db`: profile của account có job RUNNING không bao giờ bị đụng; DB lỗi → tắt purge |
| PID reuse giữ lock | Lock ghi thêm `create_time`, lệch > 1s ⇒ stale |
| CTRL_BREAK khi không có process group riêng | Chỉ gửi khi `own_process_group=True`, còn lại dùng terminate |
| `count_chrome_processes` đổi contract | `ChromeProcessCounts` (NamedTuple): có tên field, vẫn unpack như tuple |
| Cache đếm browser bị đọc/ghi đa luồng | Bọc `threading.Lock` |

Full suite: `pytest tests -q --ignore=tests/test_threads_world_news.py` → **142 passed**.

Smoke process thật (Chromium thật, không đụng job production):
- Worker kiểu PM2 (script path) + Chromium của nó → **không** bị purge; orphan thật → bị kill (1/1)
- Topology Playwright thật `chrome ← node ← python worker` → attribution `worker`, an toàn
- Ancestry bị phá + job RUNNING trong DB thật → **không** bị kill; sau khi job DONE → mới purge được
- Lock: supervisor thứ 2 bị chặn bởi supervisor đang chạy thật (pid 33416)

## Unfinished + Blockers

- `tests/test_threads_world_news.py` hỏng từ trước — **đã chứng minh trên `origin/main`** (worktree sạch, cùng interpreter): cùng lỗi `ModuleNotFoundError: app.services`. Module bị xoá ở commit `fd87077` (refactor P028). Baseline không tính file này: 51 passed. Sửa cần dựng lại test theo module mới → tách task riêng.
- ~~Máy đang chạy 2 supervisor + 2 publisher...~~ **Đính chính:** đây KHÔNG phải trùng lặp. `venv\Scripts\python.exe` trong layout PyManager là **stub 3MB** re-exec interpreter thật (`AppData\Local\Python\pythoncore-3.14-64\python.exe`) làm process con **cùng cmdline** → mỗi worker hiện ra 2 pid. Đã sửa `ProcessSnapshot.find_pids` gộp chuỗi cha–con thành 1 instance (giữ nguyên 2 worker anh em thật, ví dụ FB_Publisher_1/2 của PM2).

## Next Action

- Restart `.\start.ps1 -Stack` và xác nhận log `[STACK] ensure web=... fb_publisher=... chrome_ta=`
- Hủy Job #6 hoặc thay media bằng .mp4
