# PLAN-108: Dọn giao diện đăng bài, tổ chức lại theo module

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-108 |
| **Status** | Approved — anh giao 31/10 («dọn dẹp các ui ux hiện tại trên đăng bài… chỉ giữ lại và cải tiến những gì vẫn đang hoạt động») |
| **Executor** | Claude Code (ngoại lệ ADR-061: anh giao trực tiếp) |
| **Created by** | Claude Code |
| **Created** | 2026-10-31 |
| **Liên quan** | PLAN-106 (Studio). Kéo phần **giao diện** của P6 đợt 1 lên làm trước; engine FB / Threads / IG vẫn để P6. |

---

## Goal
Một giao diện duy nhất (SPA `/app`) chia theo module đúng với cách anh đang làm: **video → Buffer**. Xoá các trang của
nền tảng đã chết. Trang còn dùng thì bỏ phần thừa của FB và đưa về đúng module.

## Bằng chứng (31/10, chỉ đọc)
- **DB:** 14 ngày qua chỉ có job `buffer` (157 DONE, 33 FAILED). Không có job FB / Threads / IG nào. 6 tài khoản FB đều `INVALID`.
  `news_articles` (Threads) ngừng 22/10, `page_insights` ngừng 08/09, `affiliate_links` ngừng 04/2026, `threads_interactions` = 0,
  `discovered_channels` = 0, bảng `violation_logs` không tồn tại.
- **Log truy cập web** (từ 30/10): `/buffer-cluster` + API của nó (hơn 900 lượt), `/buffer-media` (Buffer lấy video), `/app/logs/tail`,
  `/api/admin/overview|jobs|syspanel`, `/cashback`, `/health`. Không có lượt nào vào trang FB / Threads / Insights.
- PM2 đang chạy: Maintenance, Web_Dashboard, 9Router_Gateway, DB_Backup. FB-Publisher / Threads-* / AI-Generator không chạy.

## Module mới (sidebar SPA)
| Module | Trang | Nguồn |
|---|---|---|
| Tổng quan | Tổng quan Buffer (viết lại) | `/api/admin/overview` (chỉ đọc DB, không gọi Buffer API) |
| Video | Kho video, Nguồn video | giữ (`viral`, `viral-sources`); trang Jinja `/app/viral` giữ vì còn chọn mốc / chia phần / caption cho luồng reup cũ |
| Buffer | Lịch đăng (job Buffer), Cụm Buffer (`/buffer-cluster`) | `jobs` bỏ form tạo job FB, mặc định lọc `buffer` |
| Nội dung & AI | AI, Từ khoá cấm | `ai-studio`; `compliance` chỉ còn từ khoá (đang được nhét vào prompt caption) |
| Hệ thống | Nhật ký, Cài đặt vận hành, Panel hệ thống, Database, Telegram | giữ |

Studio (PLAN-106 P4) sẽ vào module Video.

## Xoá
- **SPA**: `accounts`, `affiliates`, `tiktok-links`, `insights`, `fb-pro-tasks`, `threads` (+ route `jobs-threads`), `control-plane`,
  `platform-config`; tab vi phạm của `compliance`; form tạo job FB của `jobs`.
- **API admin** (`app/platform/admin_api`): `/accounts*`, `/affiliates*`, `/tiktok-links`, `/fb-pro-tasks*`, `/threads*`, `/jobs/manual`;
  phần FB của `/overview` (checkpoint, affiliate leak, danh sách account).
- **Router chỉ phục vụ giao diện**: `accounts.router`, `affiliates.router`, `threads.router`, `insights.router`, `fb_pro_tasks.router`,
  `facebook.pages_router`, `facebook.manual_job_router`, `system_panel.config_router` (platform-config).
- **Trang Jinja + route của chúng** trong `dashboard_shell`: accounts, pages, control-plane, tiktok-links, discovery panel; template /
  fragment chỉ các trang đó dùng.
- **Test** chỉ kiểm các route / trang bị xoá.

## Không đụng
- Service / worker / adapter FB, Threads, insights, strategic (P6 đợt 1, sau thí điểm Studio). Dữ liệu: không xoá dòng nào
  (31 material `BOOST_PENDING` để nguyên).
- Buffer (`buffer/*`, `/buffer-cluster`, `/buffer-media`), viral_intake, Telegram, cashback (`/cashback*`), `syspanel`, `database`, `login`, `health`.

## Validation
- `npx tsc --noEmit` + `npm run build` (bản build `app/static/admin` có trong git).
- `ruff`, `lint-imports`, cả bộ test cắt mạng; so hỏng với HEAD.
- `import app.main` + Maintenance không lỗi; liệt kê route còn lại.
- Trình duyệt: chưa chụp được (cần phiên đăng nhập) — ghi rõ.

## Rollback
File bị xoá đều có trong git → `git checkout HEAD -- <path>`.

---

## Execution Notes
- ✅ **31/10 — xong, chưa commit.** `git diff --stat` (app, frontend/src, tests): 129 file, +536 / −14.255 dòng.
  - **Backend:** gỡ 8 router (accounts, affiliates, threads, insights, fb_pro_tasks, facebook pages / manual_job,
    platform-config); `dashboard_shell` bỏ route accounts / pages / control-plane / tiktok-links / discovery /
    overview cũ / queue panel; `/app` chỉ phục vụ SPA (thiếu bản build → 503 + hướng dẫn); 25 template + 3 file JS
    chỉ các trang đó dùng; 2 hàm dựng trang mồ côi (`view_insights_dashboard`, `platform_config_page`).
  - **API admin:** bỏ `/accounts*`, `/affiliates*`, `/tiktok-links`, `/fb-pro-tasks*`, `/threads*`, `/jobs/manual`.
    `/overview` viết lại: theo kênh Buffer (đã hẹn, bài kế tiếp, kho chờ, lên 7 ngày), job Buffer 24h, video
    mới 7 ngày, lỗi gần nhất kèm tên kênh, ổ đĩa — chỉ đọc DB. `/jobs` thêm tên kênh + id video.
  - **SPA:** xoá 8 feature (49 file); sidebar 5 module (`app/nav.ts`); Tổng quan mới; Lịch đăng chỉ xem (job
    Buffer PENDING không có worker chạy → nút Retry / Chạy cũ sẽ treo job); Từ khoá cấm bỏ tab vi phạm
    (`violation_log` ngừng ghi từ 05/2026); bỏ `ClassicFrame`. Build lại `app/static/admin`.
  - **Jinja còn giữ** (`/app/viral`, `/app/viral/sources`, `/app/logs`, `/app/settings/classic`, `/syspanel`,
    `/database`, `/compliance/`, `/app/jobs`, `/cashback*`): sidebar `layouts/app.html` viết lại theo cùng 5
    module (dữ liệu hoá, 1 vòng lặp); sửa link chết + breadcrumb «Facebook» → «Video» / «Nội dung & AI».
  - `.importlinter`: bỏ dòng ignore trỏ tới `insights.router` đã xoá.
  - **Test:** bỏ 13 test chỉ kiểm route / form đã xoá; thêm `test_admin_overview_theo_kenh_buffer`.

**Verification Proof**:
```
$ npx tsc --noEmit && npm run build        → ok, app/static/admin build lại
$ ruff check <file đã sửa>                 → All checks passed!
$ lint-imports                             → 2 luật Studio KEPT; 2 luật cũ BROKEN y hệt HEAD
$ unshare -n python -c "import app.main"   → 195 route, không còn route nào của trang đã xoá;
                                              Maintenance + Telegram poller import ok
# /overview chạy thật trên Postgres (transaction READ ONLY): 4 kênh có hoạt động; Sống Nhẹ kho chờ 18;
# 35 bài đã hẹn; 24h: 10 DONE / 4 FAILED (Buffer «Scheduled posts limit reached 10/10»)
# Trình duyệt thật (Playwright, uvicorn tạm 127.0.0.1:8799, cookie ký bằng SECRET_KEY, không gọi Buffer):
#   /app 1440 px + 390 px, /app/go/jobs 1440 + 390, /app/go/compliance, /app/viral, /app/viral/sources,
#   /app/logs, /app/settings — không lỗi JS khi tải từng trang; sidebar Jinja sáng đúng 1 mục.
```
- **Còn lại / lưu ý:**
  - Web đang chạy (PM2 `Web_Dashboard`) phục vụ thẳng `app/static/admin` nên SPA mới **đã hiện**, nhưng API vẫn là
    process cũ tới khi restart. Trang Tổng quan báo «chạy pm2 restart Web_Dashboard» thay vì trắng trang.
  - Engine FB / Threads / insights / strategic + bảng dữ liệu vẫn nguyên (PLAN-106 P6). 31 material `BOOST_PENDING`
    không còn trang duyệt — để nguyên.
  - Báo cáo 30/10 ghi «Hoa Lệ Đây 179 READY chưa hẹn»; DB hiện chỉ còn 45 READY, tất cả của Sống Nhẹ (18 chưa lên Buffer).
  - Dashboard đang bị quét `.env` / `wp-config` / `.git` từ ngoài (log 30–31/10) — đều bị chặn đăng nhập, nên kiểm lại
    cấu hình public.

