# PLAN-175 — Tái cấu trúc giao diện toàn hệ thống, ưu tiên điện thoại

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-175 |
| **Status** | Execution Verified (mobile foundation pass) — review / real-device acceptance pending |
| **Executor** | Codex — ngoại lệ trực tiếp cho chương trình UI/UX |
| **Created by** | Codex, theo ủy quyền của chủ bot |
| **Related Task** | TASK-061 |
| **Related ADR** | ADR-061, ADR-067 |
| **Created** | 2026-11-17 |
| **Updated** | 2026-11-17 |

## Goal
Rà soát và cải tiến toàn bộ bề mặt UI/UX của ToolsAuto theo điện thoại trước, giữ nguyên API và nghiệp vụ trừ khi có PLAN riêng. Chia execution thành các đợt nhỏ có thể build, xem trực quan và kiểm chứng độc lập.

## Context
- Chủ bot dùng điện thoại thường xuyên hơn web desktop và giao toàn quyền triển khai ngày 2026-11-17.
- PLAN-108 đã tái tổ chức dashboard thành SPA/module nhưng là kế hoạch cũ; shell hiện có bottom nav, sidebar trượt, còn Tổng quan và Lịch đăng dùng bảng ngang trên mobile.
- Bề mặt giao diện gồm admin SPA + Jinja, Xe Tết `/control` + overlay, và menu/nội dung tương tác Cashbot/Store trên Telegram/Zalo.
- Working tree ban đầu có hai bản vá test không liên quan: `tests/test_store_bot.py`, `tests/test_ytdlp.py`; phải giữ nguyên.

## Program Phases
1. Dashboard SPA: shell điều hướng một tay, Tổng quan, Lịch đăng và các luồng vận hành hay dùng.
2. Video workflow: Studio, Kho video, Nguồn video và editor.
3. Vận hành và tăng trưởng: Threads, khách các bot, Settings, system panel, logs, database.
4. Xe Tết: bảng điều khiển điện thoại, thao tác live và màn hình overlay.
5. Cashback/Store: admin, menu, tin nhắn và luồng khách trên Telegram/Zalo.
6. Các trang Jinja còn giữ, kiểm tra responsive/toàn cục và hồi quy.

Mỗi phase được kiểm chứng trước khi mở rộng phase tiếp theo. Các scope bên dưới ghi từng đợt đã thực hiện; owner authorization áp dụng toàn chương trình. Chưa nghiệm thu cuối trên điện thoại thật.

## Scope — Phase 1, bước A
- `frontend/src/layouts/AppShell.tsx`: mobile navigation một tay, trạng thái active chính xác, safe-area và hit target.
- `frontend/src/features/overview/pages/OverviewPage.tsx`: thứ tự ưu tiên và spacing trên mobile.
- `frontend/src/features/overview/components/ChannelTable.tsx`: card/list cho mobile, bảng desktop giữ nguyên.
- `frontend/src/features/jobs/components/JobsTable.tsx`: job card trên mobile, bảng desktop giữ nguyên.
- `frontend/src/features/jobs/components/JobsFilters.tsx`: controls xếp dọc/đủ rộng trên mobile.
- Cập nhật PLAN/TASK với proof thực tế; không sửa template Jinja/backend trong bước này.

## Out of Scope — toàn chương trình
- Đổi API, truy vấn, dữ liệu, trạng thái job hoặc hành vi Buffer.
- Đổi nghiệp vụ Store/Cashbot, lời hứa thương mại, callback bot hoặc luồng tiền.
- Sửa hai test patches có sẵn; reset nhánh hoặc gộp thay đổi ngoài UI.
- Commit/push trước khi được yêu cầu riêng. Chủ bot đã ủy quyền deploy static và sau đó commit/push lên nhánh hiện tại.

## Approach
1. Đọc luồng và component hiện tại; chốt các mục tiêu mobile: menu luôn tới được, trạng thái hiện hành nhận ra được, nội dung quan trọng không cần kéo ngang.
2. Cải tiến shell và mobile card views bằng cùng dữ liệu/logic hiện có; desktop table giữ nguyên.
3. Build frontend; chạy kiểm tra tương tác ở 390px, tablet 768px và desktop 1440px, xác nhận không tràn ngang/che bottom nav và menu đóng sau điều hướng.
4. Ghi proof, cập nhật danh sách phase và điểm còn lại trước khi chuyển sang phase khác.

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Bottom nav che nội dung cuối | Trung bình | safe-area + padding đáy; xác minh viewport điện thoại |
| Bản mobile và desktop hiển thị dữ liệu khác nhau | Trung bình | cùng nguồn dữ liệu; chỉ khác presentation |
| Nhiều mục cạnh tranh bottom nav | Trung bình | đưa thao tác phụ vào menu, giữ 3 đích chính + menu |
| SPA proxy cần backend đăng nhập | Thấp | kiểm UI bằng Vite và mock API tại browser; không gọi dịch vụ ngoài |

## Validation Plan
- [x] `npm run build -- --outDir /tmp/toolsauto-ui175-dist` trong `frontend/`.
- [x] Playwright fixture tại 320×740, 390×844, 768×1024 và 1440×900.
- [x] Không document overflow trong 112 lượt route/viewport; drawer, pagination, toast/nav, callback được kiểm riêng.
- [x] `git diff --check` exit 0; hai test patches giữ nguyên.
- [ ] Điện thoại thật + authenticated runtime acceptance / Claude verify + handoff.

## Rollback Plan
Khôi phục riêng component của Phase 1 từ diff PLAN-175; không reset toàn nhánh và không đụng hai test patches có sẵn.

## Execution Notes
- [x] Phase 1A: dashboard mobile shell, Tổng quan và Lịch đăng. Build độc lập `/tmp/toolsauto-ui175-dist` (không ghi vào static đang chạy).
- Browser fixture: 320×740, 390×844, 768×1024, 1440×900; 8 lượt route không tràn document; menu đóng bằng Escape/điều hướng/resize; query tìm kiếm giữ nguyên; rỗng/HTTP 503 hiển thị được; pagination phía trên bottom nav khi cuộn cuối; `page_errors=[]`, `external_requests=0`.
- Lệnh: `.venv/bin/python /tmp/toolsauto-ui175-check.py`; output JSON lưu cùng ảnh trong `reports/ui175/phase1/`.

## Scope — Phase 2, video và controls dùng chung
- StudioBoardPage, UploadBox, TechniquePicker, ProjectCard: một cột trên điện thoại, nhãn và trường không tràn, vùng bấm 44px.
- ViralTable, ViralSourcesTable: mobile cards với cùng callback, busy state và xác nhận xóa; desktop giữ bảng.
- Shared controls, SearchField, Pagination: input 16px trên mobile và vùng bấm 44px; không đổi callback/API.
- Toast: nổi trên mobile navigation, hỗ trợ thông báo qua live region.
- Chỉ presentation; không upload/duyệt/quét/xóa dữ liệu thật trong verification.
- Ngoại lệ phát hiện khi browser verify: `useViralSources` lấy mutation.variables kể cả khi đã hoàn tất, khóa nguồn vĩnh viễn. Bổ sung sửa busyId chỉ khi `isPending`, bao gồm page mutation; không đổi API/nghiệp vụ.
- Verify: build độc lập, fixture browser cho Studio/kho/nguồn tại 320/390/768/1440; kiểm callback với request mock và xác nhận xóa.

## Anti Sign-off Gate
Reviewed by: Pending — execution do chủ bot ủy quyền trực tiếp; không tự giả danh Antigravity. Chưa archive.

## Phase 2 proof / Phase 3 scope
- Phase 2 build: TypeScript + Vite PASS, 1,870 modules, JS 585.21 kB (cảnh báo chunk >500 kB còn tồn tại).
- `.venv/bin/python /tmp/toolsauto-ui175-phase2.py`: 12 route×viewport PASS, `page_errors=[]`, `unknown_requests=[]`; mock approve/process/scan/page đúng URL/payload; hủy xóa không gửi request; toast trên nav; rỗng không tràn.
- Phase 3: SettingsPage/UnsavedBar (thanh thay đổi trên nav + chọn section mobile), app.css (font input/vùng bấm/focus mobile), Threads ControlBar (bỏ min-width cứng), BotUsersPage (legend xuống dòng), DatabasePage (chọn bảng bằng nút, danh sách mobile và SQL input dễ đọc). System panel có sẵn card mobile; kiểm lại qua fixture. Logs dùng Jinja, gộp validation với Phase 6.
- Không thay logic save/reset/SQL/mutation. Chỉ kiểm dữ liệu mock; không chạy SQL hoặc bật/tắt tiến trình thật.
- Browser stress 320px xác nhận key cấu hình dài tràn; thêm SettingsFieldMetaLine/FieldLabel vào scope Phase 3 để wrap nhãn và key.

## Handoff Note
Mobile foundation pass đã execute và verify. Chưa đánh dấu toàn chương trình Done hoặc archive; cần Claude Code verify + handoff, sau đó nghiệm thu điện thoại thật/runtime.

## Phase 3 proof / Phase 4 scope
- Build TypeScript/Vite PASS; `.venv/bin/python /tmp/toolsauto-ui175-phase3.py`: 20 route×viewport PASS, không tràn ngang, `page_errors=[]`, `unknown_requests=[]`.
- Chọn nhóm settings cuộn đúng; thanh chưa lưu trên bottom nav; Save section gửi đúng PATCH/payload mock; preview DB hoạt động, không chạy SQL.
- Phase 4 chỉ sửa `xe_tet/server/control.html`: viewport-fit, safe-area top/bottom, vùng bấm 44px, chống tràn tên/số dài, người xem hiển thị một cột ở màn hẹp.
- Overlay là đầu ra live 9:16, giữ nguyên bố cục và logic; build overlay ra `/tmp` để xác minh. Không dùng e2e cũ có lệnh reset game/live; browser mock toàn bộ API control.

## Phase 4 proof / Phase 5–6 scope
- `.venv/bin/python /tmp/toolsauto-ui175-phase4.py`: 320/390/768/1440, mở toàn bộ nhóm settings: không tràn ngang, 6 dock buttons ≥44px, `page_errors=[]`; pause gửi đúng mock `{action:pause,paused:true}`. Không gọi máy chủ live.
- Phase 5–6: layouts/app_light.html và layouts/app.html đồng bộ bottom nav 5 mục với SPA, drawer focus/Escape/scroll lock/resize; thêm 2 shared fragments mobile styles + navigation script.
- Cashback `cashback_users.html`: thẻ khách trên mobile cùng dữ liệu financial hiện có, desktop bảng giữ nguyên; cashback_style: tab đủ vùng bấm, số/nhãn dài wrap.
- Logs: tablist cuộn trong khung, không đẩy document; controls dùng shared mobile styles.
- Bot Telegram/Zalo: đọc menu/keyboard + test existing; không sửa lời hứa thương mại, callback, quyền, luồng tiền hay gửi tin. Telegram admin là màn nhúng, shared CSS cho form.
- Các trang còn lại: fixture smoke + overflow; chỉ sửa thêm khi có lỗi cụ thể và ghi scope trước. Matrix DB/financial nhiều cột giữ cuộn bên trong có chủ đích.
- LogsPage SPA vẫn là bảng 720px trên điện thoại: thêm thẻ sự kiện mobile để đọc đầy đủ message, giữ bảng desktop. Search box Cashback shared thêm min-width/wrap để nút Tìm không tràn ở 320px.
- Vòng rà soát cuối: StudioAssetsPage (card audio/video 1 cột mobile); SubtitleEditor/TextAudioPanel (field không bị bóp ở 320px); DoctypeListPage/RecordListPage (mobile list thay bảng ngang; bảng dữ liệu tùy biến trong builder vẫn cuộn trong khung). API và callback giữ nguyên.
- Phát hiện Git: mẫu `logs/` bỏ qua cả feature source `frontend/src/features/logs/` đang được App.tsx import. Thêm ngoại lệ đúng folder source vào `.gitignore` để 4 file API/hook/type/page hiện có đi theo bản vá; không bỏ ignore log runtime.

## Final verification proof — 2026-11-17
- Durable artifacts: `reports/ui175/README.md`, `summary.json`, 6 `proof.json`, 6 browser scripts, local phone screenshots.
- 112 route×viewport checks PASS, `page_errors=[]`. 60 lượt cuối bao gồm editor, assets/setup/TikTok/doc, AI, compliance, Telegram, DocType builder/list/form; API mock hoàn toàn.
- Frontend build PASS: 1,870 modules, JS 589.18 kB; overlay build PASS: 26 modules, JS 840.05 kB. Cả hai còn chunk warning; output chỉ ở `/tmp`.
- Related regression: `pytest -q tests/test_cashback_admin_ui_ux.py tests/test_cashback_zalo.py tests/test_store_bot.py` → **147 passed in 23.94s**.
- Parse tất cả Jinja → **57 templates PASS**. `git -c core.autocrlf=false diff --check` → exit 0.
- Bot menu review: Cashback home hiện 2 nút/hàng, hướng dẫn gom trong mục riêng; Store menu chính 1–2 nút/hàng và tôn trọng trạng thái bàn phím người dùng; Zalo có renderer riêng. Không thấy cần thay cấu trúc native ở pass này; giữ callback/logic và kiểm regression.
- Self-review theo review-agent: **No findings.** Không thay thế Anti/Claude sign-off. Giới hạn runtime và các acceptance chưa chứng minh ghi đầy đủ ở README proof.

Execution Done. Cần Claude Code verify + handoff.

## Follow-up scope — CEO overview and paginated customer lists
- Owner feedback: «danh sách không phân trang gì hết» and current overview is Buffer-only, insufficient for COO/CEO.
- Overview: combine Buffer operations with existing read-only bot growth summary and read-only process/service snapshot. Distinguish per-bot registrations from unique people; don't invent a merged money/revenue KPI.
- Bot user list: API page/per_page pagination (25 default) with filters/search retained; report summaries and charts stay independent of the current page.
- Cashback customer list: server-rendered pagination, 50/page, preserve search/channel/segment/sort across page links.
- Audit other primary operational lists for existing pagination and avoid unbounded detail views in this scope. No changes to business/financial processing.
- Verification: pagination endpoint/filter tests, responsive mobile browser proof, backend read-only report and process source contracts; build and related tests.
- Coverage expansion before deployment: add `/api/admin/executive` for grouped Studio status/task counts, Threads reply counts (SQLite read-only, no runner startup) and separate Cashback/Store financial summaries. Reuse `insights.money` and Store `stats` through a read-only repository; preserve their period/financial definitions and exclude Store admins using configured IDs. Each source can fail independently, reported unavailable instead of zero. Scheduled DB backup stopped is expected, not an incident.

### Follow-up execution proof — 2026-11-17
- Proof and reproduction: `reports/ui175/followup/README.md`, `check.py`, `proof.json`, `live_check.py`, `live-proof.json`.
- Backend: 41 passed in 17.63s for bot users, Cashback insights, executive API and admin lists. After relative pagination links, Cashback 28 passed in 7.12s. Ruff PASS; diff check PASS.
- Frontend: TypeScript/Vite PASS, 1,871 modules, 7.36s; JS 597.64 kB with existing bundle warning. Fixture 320/390/768/1440 PASS; page 2/search reset and unavailable-source isolation PASS; page_errors=[].
- Read-only source tests reject SQLite DELETE, do not create missing DBs, exclude configured Store admins and isolate unavailable sources. Live authenticated reads returned 25 bot-user rows and 50 Cashback rows on page 1. Pagination slices full source aggregates; it is not SQL-level pagination.
- Jobs, warehouse, Logs, compliance keywords and DocType records already paginated. Missing customer lists now have 25/page (bot users) and 50/page (Cashback), filters retained. Cashback page links are query-relative for reverse-proxy safety. Scheduled backup stopped is excluded from online denominator.
- Owner's deployment authorization covers the dashboard increment. Backup 11 files at `/tmp/toolsauto-ceo-ui-backup-20261117-followup`; copied 9-file staging, retained old assets, atomically replaced index, verified temporary source absent/destination present and hashes matched.
- Restarted only Web_Dashboard to load API, restarts 4 -> 5; authenticated login and core GETs HTTP 200, executive errors=[] and all four sources available. Live overview + bot users across four widths: no overflow, page_errors=[], blocked_requests=[]. Authenticated tailnet login and executive GET both HTTP 200 with verified TLS.
- Xe Tết metrics, comparable-period growth trends, physical phone/iOS and independent sign-off remain pending. Do not mark whole-system CEO coverage complete.

Execution Done. Cần Claude Code verify + handoff.

## Deployment — owner authorized 2026-11-17
- Chủ bot yêu cầu trực tiếp: «em trien khai cho anh luon di».
- Runtime xác nhận: Web_Dashboard cwd `/home/vu/toolsauto`, HTTP 8000; frontend đọc `app/static/admin/index.html` mỗi request. Xe Tết control trả FileResponse trực tiếp; Jinja đọc template từ checkout.
- Scope: build staging mới, backup static hiện hành, copy asset mới trước và thay index atomically; giữ asset cũ cho tab đang mở. Không restart bot/worker, không chạy migration, không commit/push.
- Verify: authenticated GET của shell và Jinja, đối chiếu SHA-256 asset HTTP với staging; health và process vẫn hoạt động. Browser/runtime smoke chỉ đọc nếu dùng dữ liệu thật.
- Rollback: phục hồi index/manifest từ backup đã ghi trong deployment proof; asset cũ vẫn còn. Không reset toàn nhánh.
- Executed 14:53:19 UTC: staging build TypeScript/Vite PASS, 1,870 modules, built in 6.89s; 9 files backup verified, 9 staging files verified, asset cũ giữ nguyên. Backup `/tmp/toolsauto-ui175-backup-20261117T145319Z`.
- Live proof `reports/ui175/deployment.json`: login 200; GET `/app`, `/app/go/studio`, `/cashback/users`, `/app/logs`, `/health` đều 200; 7 asset HTTP SHA-256 khớp staging. SPA index SHA-256 `1d8fd449a1b43d719f6fcc7eba821fb5b45fa2e15ad08babf61fdeef98cfcd78`.
- Browser Chromium authenticated `/app` + `/api/admin/overview` dữ liệu thật read-only 200; 320/390/768/1440 không overflow, drawer/Escape PASS, page_errors=[], blocked_requests=[]. Không gọi API dịch vụ ngoài.
- HTTPS tailnet 8443 shell 200 + hash match + TLS certificate verified khi resolve hostname về `100.102.93.11`. Public DNS trỏ Funnel, probe public-DNS 8443 lỗi SSL EOF; 8443 hiện tailnet-only, điện thoại cần Tailscale. Cổng 443 phục vụ Store; giữ nguyên network config.
- PM2 Web_Dashboard online, restart count vẫn 4. Không restart/migrate/commit/push; Xe Tết control source đã có nhưng không thấy Xe Tết server đang listen, không tự bật game. Điện thoại thật và independent sign-off vẫn pending.

## Commit / push — owner authorized
- Chủ bot yêu cầu «em commit va pussh nha»; nhánh `feat/xe-tet`, remote `origin`. Fetch xác nhận HEAD và remote cùng mốc trước commit (`0 0`).
- Commit chỉ gồm UI source, bundle đang phục vụ và proof PLAN-175; không gộp hai bản vá test audit có sẵn.
- Staged diff check phát hiện whitespace trong 3 proof scripts mới; đã chuẩn hóa, không đổi logic. Bundle JS có 5 dòng chỉ có khoảng trắng bên trong CSS template string của dependency; giữ nguyên output Vite để khớp tên asset và SHA-256 đã deploy. Kiểm source/proof bằng `git diff --cached --check -- . ':!app/static/admin/assets/*'`.
