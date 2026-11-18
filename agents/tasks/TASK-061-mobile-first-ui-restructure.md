# TASK-061 — Tái cấu trúc UI/UX toàn hệ thống, ưu tiên điện thoại

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-061 |
| **Status** | Execution Verified — pending review / real-device acceptance |
| **Priority** | P1 |
| **Owner** | Chủ bot (ủy quyền trực tiếp) |
| **Executor** | Codex — ngoại lệ trực tiếp 2026-11-17 |
| **Related Plan** | PLAN-175 |
| **Created** | 2026-11-17 |
| **Updated** | 2026-11-17 |

## Objective
Rà soát rồi cải tiến toàn bộ UI/UX ToolsAuto theo thứ tự phase, lấy điện thoại làm thiết bị chính và giữ nguyên nghiệp vụ/API.

## Scope
- Phase 1: dashboard SPA, mobile shell, Tổng quan, Lịch đăng.
- Các phase sau: Studio/video, vận hành/tăng trưởng, Xe Tết, Cashback/Store Telegram-Zalo, Jinja/global polish.
- Mỗi phase có validation riêng trước khi tiếp tục.

## Out of Scope
- Thay đổi core business logic, API hoặc schema nếu chưa có scope/PLAN tương ứng.
- Commit/push/restart production khi chưa được yêu cầu riêng. Chủ bot đã yêu cầu deploy static sau lượt verification.

## Blockers
- Không có; chủ bot đã giao toàn quyền 2026-11-17.

## Acceptance Criteria
- [x] Các phase được kiểm kê và triển khai mobile foundation lần lượt; scope/proof trong PLAN-175.
- [x] 112 lượt browser fixture tại 320/390/768/1440px: không document overflow, page_errors=[].
- [x] API/nghiệp vụ giữ nguyên; desktop build/browser fixture PASS; sửa riêng busy-state bug có proof.
- [x] Không làm mất hoặc sửa hai bản vá test có sẵn.
- [ ] Claude verify + handoff; nghiệm thu điện thoại thật với backend đăng nhập.

## Execution Notes
- [x] Đọc PLAN-108, PLAN-175 context, shell SPA và component Tổng quan/Lịch đăng.
- [x] Phase 1 dashboard; Phase 2 Studio/video; Phase 3 vận hành; Phase 4 control Xe Tết; Phase 5 Cashback/native menu review; Phase 6 Jinja/shared controls và regression.
- [x] Kiểm tra trực quan mobile/tablet/desktop, browser interactions và lưu proof.

## Follow-up — executive charts and product/money visibility (2026-11-18)
- [x] API supports read-only Store and Cashback summaries, trends, and money positions for 7/30 days.
- [x] Store rankings use delivered quantity, net-of-refund sales, recorded cost semantics, and configured admin exclusion.
- [x] Cashback balances and payout amounts come from `money_flow.snapshot`; Store and Cashback amounts remain separate.
- [x] Responsive overview proof at 320/390/768/1440px; backend/frontend regression tests pass.
- [x] Record proof and outstanding runtime acceptance in PLAN-175/current-status.

## Verification Proof
`reports/ui175/README.md` + `summary.json`: 112 route×viewport checks PASS; frontend và overlay build PASS; 147 related regression tests passed in 23.94s; 57 Jinja templates parse PASS; git diff --check exit 0. Browser API hoàn toàn mock, không chứng minh production runtime. Còn bundle-size warnings, physical-phone/authenticated acceptance và independent sign-off.

Execution Done. Cần Claude Code verify + handoff.

## Deployment proof — owner authorized
Đã deploy static ngày 17/11 lúc 14:53:19 UTC, không restart. `reports/ui175/deployment.json`: backup 9 files verified; login và 5 GET 200; 7 asset hash match; HTTPS tailnet 8443 shell 200/hash match/TLS verified; live read-only Tổng quan browser 4 widths PASS, page_errors=[]. PM2 Web_Dashboard online, restarts vẫn 4. Chưa commit/push. Điện thoại cần Tailscale để vào cổng 8443; nghiệm thu thiết bị thật và review độc lập còn pending.

## Status History

Follow-up 2026-11-17: owner requested customer pagination and CEO/COO scope beyond Buffer. Added bot/Cashback pagination and read-only executive summary; see PLAN-175 follow-up scope and `reports/ui175/followup/README.md`. 41 related tests passed; relative pagination link recheck 28 passed; frontend build and four-width fixture PASS. Deployed bundle and restarted only Web_Dashboard (4 -> 5); authenticated six GETs 200, four sources available, eight live viewport checks without overflow/JS errors. Pending Xe Tết metrics, physical phone and independent verification; not Done/archive.

| Date | Status | Note |
|---|---|---|
| 2026-11-17 | New | Chủ bot giao toàn quyền tái cấu trúc UI, nhấn mạnh sử dụng điện thoại |
| 2026-11-17 | Planned | PLAN-175 ghi roadmap theo phase; bước A bắt đầu ở dashboard SPA |
| 2026-11-17 | In Progress | Codex thực thi theo ngoại lệ trực tiếp của chủ bot |
| 2026-11-17 | Execution Verified | Mobile foundation pass qua 6 đợt; proof durable, chưa mark Done/archive hoặc deploy |


## Executive analytics proof — 2026-11-18
Read-only API and mobile charts/rankings/money positions implemented. Related tests 139 passed; final focused tests 3 passed; Ruff/diff check PASS. Frontend build PASS (1,871 modules, 606.98 kB JS); 8 period/viewport + 5 failure/empty/legacy checks PASS, no JS errors/unexpected requests. Full proof: reports/ui175/executive-analytics/README.md. No deploy/commit/push/restart; runtime and physical phone/Claude review pending.

Execution Done. Cần Claude Code verify + handoff.

Release authorization 2026-11-18: owner requested commit/push/restart. Static backup and 9 files verified; release and live proof follow in PLAN-175 and reports/ui175/executive-analytics/.

Release completed 2026-11-18: code/bundle 28f6b1f pushed; Web_Dashboard restarted 6 → 7 and online. Authenticated 7/30-day APIs HTTP 200; all chart totals match; 8 live viewport checks PASS, page_errors=[]; tailnet TLS/API PASS. Other PM2 processes unchanged; four bot systemd services active. See live-proof.json. Physical phone/iOS and formal Claude review pending.
