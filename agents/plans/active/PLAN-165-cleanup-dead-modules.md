# PLAN-165 — Dọn rác đợt 1: module / thư mục không còn ai dùng

- Executor: Claude Code · Duyệt: chủ bot (08/11: «tìm và xử lý dọn rác bớt đi»).
- Nguyên tắc: chỉ xoá thứ đã kiểm không còn import / tiến trình nào dùng; phần trong git khôi phục được bằng `git revert`.

## Khảo sát (08/11)
| Mục | Còn ai dùng | Quyết định |
|---|---|---|
| `app/features/fb_pro_tasks` (676 dòng) | không | **xoá** |
| `app/features/insights` (1.022 dòng) | chỉ 1 test + `.importlinter` | **xoá** (sửa test + importlinter) |
| `app/features/accounts` (README + `__init__`) | chỉ `.importlinter` | **xoá** |
| `experiments/` (41 file, nghiên cứu Shopee API cũ) | chỉ báo cáo .md nhắc tên | **xoá** |
| `scratch/` (ngoài git, ignored), `__pycache__/` gốc | không | chờ chủ bot (xoá ngoài git bị chặn quyền — không khôi phục được) |
| `scripts/archive/` | **Maintenance chạy `scrape_insights.py` mỗi vòng**; panel có lệnh gọi | GIỮ |
| `facebook` / `instagram` / `tiktok` / `story` / `affiliates` / `jobs` | dính dispatcher, publisher_runtime, process_scan, local_supervisor, metrics_checker, main.py, ai_generator | GIỮ — cần PLAN refactor riêng (bước cuối PLAN-106) |
| `profiles/` 88 MB, `content/` 9,2 MB (gốc, ngoài git) | đường dẫn LEGACY trong config (không dùng khi có `storage/`) | chờ chủ bot (xoá là mất hẳn) |
| `docs/ specs/ design/ reports/ deploy/ chrome_extension/` | tài liệu / triển khai | GIỮ |

## Proof (08/11)
- `git rm -r` fb_pro_tasks, insights, accounts, experiments (khôi phục: `git revert` / `git checkout <commit> -- <path>`).
- `.importlinter` bỏ 2 dòng; `tests/test_memory_leak_prevention.py` bỏ import + 2 test của insights service.
- `import app.main` OK; lint-imports 2 BROKEN như HEAD (có sẵn); không còn chỗ nào import 3 module đã xoá.
- pytest 9 file: 330 passed, 1 failed = test_metrics_checker_scrape_views_cleanup_no_unbound_local (HEAD cũng hỏng).
- Phát hiện: Maintenance mỗi vòng chạy `scripts/archive/scrape_insights.py` (cào insights page FB bằng tài khoản FB đã bỏ)
  → đề xuất tắt (đợt sau, cần chủ bot duyệt).

## Đợt 1b (08/11, chủ bot duyệt «anh duyệt cho em nhé»)
- Nén `profiles/ content/ scratch/` → `storage/backups/cleanup-root-legacy-20261108.tar.gz` (60 MB, 1.017 mục, chmod 600) rồi xoá.
- Maintenance: bỏ gọi `_scrape_page_insights()` mỗi 12 giờ (giữ hàm). ruff sạch; test 32 passed + 1 hỏng sẵn.
- Lập PLAN-166 (gỡ chuỗi đăng trực tiếp cũ) — chưa thực thi.
