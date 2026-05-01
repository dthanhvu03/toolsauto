# Current Status

## Recent Execution

- **[2026-05-01] 🐛 Fix Competitive Intelligence (Insights dashboard) — 3 endpoint crash 500 + 1 contract mismatch**
  - **Triệu chứng**: anh báo "check Competitive Intelligence trong insight". Inspect: 3 API endpoint trên `/insights/api/...` đều có bug.
  - **Bug 1** — Trending Topics không bao giờ hiện data:
    - Frontend `insights.html:1406-1410` đọc `json.data` + `json.reels_analyzed`.
    - Backend `insights_service.get_trending_topics()` trả `topics` + `total_captions_analyzed`.
    - → Mismatch tên field, frontend luôn render "Chưa có dữ liệu". Fix: rename keys backend cho khớp frontend (single consumer).
  - **Bug 2** — 3 endpoint crash 500 vì query column không tồn tại trong `competitor_reels`:
    - Schema thật chỉ có: `id, reel_url, scrape_date, page_url, views, likes, comments, shares, caption, recorded_at`.
    - Service queries `WHERE scraped_at >= :cutoff` — không có cột `scraped_at`. Fix: đổi → `recorded_at` (Unix TS).
    - `get_competitor_top` SELECT `page_name, platform, published_date` — không có cột nào trong các cột trên. Fix: derive `page_name` từ `page_url`, hardcode `platform="facebook"` (competitor_reels là FB-only by design), drop `published_date` (sort "date" giờ dựa `recorded_at`).
  - **Bug 3** — PostgreSQL strict GROUP BY: `page_url` không nằm trong GROUP BY → fix wrap `MAX(page_url)`.
  - **Verify** sau fix:
    - `trending-topics`: 10 topics, top: `xuhuong (36)`, `shopee (27)`, `https (25)`, `người (20)`, `nhà (20)` — 266 reels analyzed.
    - `market-benchmark`: `has_competitor_data=True`, `market.reel_count=289`, `market.avg_likes=57160.9`, `our.post_count=144`.
    - `competitor-top` sort=likes: top 3 reels có `likes=3.8M / 1.6M / 1.5M`.
  - **Bug còn lại — KHÔNG phải insight UI**: 293/293 row `competitor_reels` có `views=0` và `page_url=''` rỗng. Likes/comments/shares lưu đúng, nhưng views + page_url scraper bỏ qua. Hậu quả: Market Gap card hiện `0×` mãi (chia AVG(views) ours / AVG(views) market khi market = 0). Cần điều tra `app/services/scraper/` (suggested-reels GQL parser) — out of scope task UX này, mở task riêng nếu anh muốn.
  - **Files** (1): `app/services/dashboard/insights_service.py` — 3 SQL fix + key rename + GROUP BY fix.

- **[2026-05-01] UX fix — PENDING jobs hiển thị ETA tuyệt đối (đã tính cooldown) thay vì ô trống**
  - **Bug**: Anh Vu chụp screenshot dashboard PENDING jobs Threads chỉ thấy "Cooldown: 8m16s" mà không có thời điểm đăng cụ thể.
  - **Root cause**: 2 vấn đề tách biệt:
    1. `app/services/content/threads_news.py:307` tạo Job không set `schedule_ts` → cột Schedule render `None | format_time` = `"-"`.
    2. `app/templates/fragments/job_row.html:248-264` chỉ tính cooldown relative (`remaining = cooldown_seconds - elapsed`), không suy ra ETA tuyệt đối, cũng không xét `schedule_ts` riêng.
  - **Fix**:
    - `threads_news.py`: thêm `schedule_ts=now_ts` vào Job constructor — job eligible ngay khi tạo, cooldown mới là gate cuối.
    - `job_row.html` PENDING block: tính `eta = max(schedule_ts, account.last_post_ts + cooldown_seconds)` và hiển thị 2 dòng — countdown "Còn 8m19s" (orange) hoặc "Sẵn sàng" (emerald), kèm ETA tuyệt đối format `HH:MM:SS DD/MM/YYYY` (mono).
  - **Verify**:
    - `py_compile threads_news.py` PASS; `from app.main import app` → `APP_IMPORT_OK 207`.
    - `pytest tests/test_threads_world_news.py -q` → `14 passed in 1.79s`.
    - Jinja smoke 2 case: cooldown active → "Còn 8m19s" + ETA; ready → "Sẵn sàng" + ETA.
  - **Pending VPS**: pull develop → `pm2 restart Threads_Publisher` (mới chạy threads_news code mới) + restart web server (nếu PM2 process riêng) để render template mới. Job PENDING cũ trong DB vẫn `schedule_ts=NULL` → ETA chỉ hiện cooldown component cho tới khi tạo job mới.

- **[2026-05-01] PLAN-034 / TASK-034 — Threads article curation scoring (Phase 1) DONE local, VPS deploy pending ✅**
  - **Anh Vu duyệt PLAN** lúc anh quay lại; Claude Code execute autonomous.
  - **7 bước hoàn tất**:
    1. Column `NewsArticle.engagement_score` + migration `a8e7f6d5c4b3` (down_revision `9f1c2d3e4a5b`); seed RuntimeSetting `THREADS_SOURCE_WEIGHTS = {}`.
    2. `app/services/content/article_scorer.py` — pure function `compute_score()` 4 signal (recency 40% / source 20% / hot marker 15% / topic competition 25%), score round trong [0, 100].
    3. `tests/test_article_scorer.py` 10 cases — 10/10 PASS in 0.05s.
    4. `news_scraper.py:_rescore_recent_articles()` tính score batch sau insert (đọc weights từ RuntimeSetting, count topic_key trong 24h gần nhất).
    5. `threads_news.py:186` đổi `order_by` → `engagement_score.desc().nullslast()` ưu tiên.
    6. `tests/test_threads_world_news.py` thêm 2 case: selection theo score + scraper populate score → 14/14 PASS.
    7. Smoke realistic: 3 article giả lập (24h kinh tế / VnExpress NÓNG / Tuổi Trẻ sốc cùng topic), weights `{"VnExpress":1.3,"Tuổi Trẻ":1.2,"24h":0.7}` → score 23.84 / 82.05 / 76.94 — selection chính xác.
  - **Verify**: `alembic upgrade head` clean → head `a8e7f6d5c4b3`; `py_compile` 5 file PASS; `from app.main import app` → 207 routes; 24/24 test PASS. (18 fail khác trong suite là pre-existing FacebookAdapter/Playwright unrelated.)
  - **Files** (7): `app/database/models/threads.py`, `alembic/versions/a8e7f6d5c4b3_add_news_engagement_score.py`, `app/services/content/article_scorer.py`, `app/services/content/news_scraper.py`, `app/services/content/threads_news.py`, `tests/test_article_scorer.py`, `tests/test_threads_world_news.py`.
  - **Pending VPS**:
    1. Pull develop → `cd /root/toolsauto && git pull origin develop`.
    2. `venv/bin/alembic upgrade head` (sẽ chạy migration `a8e7f6d5c4b3`).
    3. Tuỳ chọn: set `THREADS_SOURCE_WEIGHTS` JSON qua RuntimeSetting nếu muốn weight cụ thể; default `{}` = neutral (mọi nguồn = 1.0).
    4. `pm2 restart Threads_Publisher` (restart, KHÔNG reload).
    5. Theo dõi 1 chu kỳ scrape kế tiếp: DB confirm `news_articles.engagement_score IS NOT NULL` cho article mới scrape.
    6. Sau 1-2 chu kỳ publish: confirm bài chọn đúng score cao nhất (xem log `Processing article '...'`).

- **[2026-05-01] 🐛 Fix Threads duplicate-publish bug (3-4 lần) — code DONE local, VPS deploy pending**
  - **Root cause**: Sau click Post thành công (post LIVE trên Threads), nếu adapter không capture được `post_url` → trả `ok=False, is_fatal=False` → worker `mark_failed_or_retry` → status PENDING + backoff → re-claim → **publish lại** trên Threads. `max_tries=3` → đăng tối đa 3 lần. Sau PLAN-032 (`_capture_post_reference` strict trả `(None,None)` khi không match own-handle) bug càng nặng vì mọi capture-miss đều thành retry.
  - **Fix A (root)** — convert capture-fail thành success-without-URL:
    - `app/adapters/threads/adapter.py:825-829` đổi `ok=False, is_fatal=False` → `ok=True, details={"post_url": None}`. Job mark DONE với `post_url=NULL` thay vì retry → publish lại.
    - `workers/threads_publisher.py:204-207` bỏ block ép `ok=False` khi thiếu `post_url`, chỉ log warning.
  - **Fix B (idempotency guard)** — pre-publish check trên retry:
    - Helper mới `_caption_signature(caption)`: lấy 60 ký tự đầu trước footer `(Nguồn: ...)`.
    - Helper mới `_check_already_published(caption)`: navigate own profile, scan 5 post link đầu, match signature trong `<article>` text.
    - `publish()` đầu hàm: nếu `job.tries > 0` và `_own_handle` available → probe profile; nếu thấy bài đã đăng → trả `ok=True, post_url=<existing>`, không click Post lần 2.
  - **Verify local**:
    - `venv/bin/python -m py_compile app/adapters/threads/adapter.py workers/threads_publisher.py` → `PY_COMPILE_OK`.
    - `from app.main import app` → `APP_IMPORT_OK 207`.
    - Helper smoke: `_caption_signature("NÓNG: Bộ Y tế ... (Nguồn: VnExpress) ...")` → `'NÓNG: Bộ Y tế cảnh báo dịch tay chân miệng\\n\\nBài viết đầy đủ'` (60 ký tự, không dính footer).
    - `git diff --stat`: `adapter.py +79/-3`, `threads_publisher.py +5/-3` → 2 file, đúng minimal-diff rule.
  - **Pending**:
    1. Anh Vu commit + push develop (suggested message: `fix(threads): prevent duplicate publish on capture-miss + add retry idempotency guard`).
    2. VPS pull + `pm2 restart Threads_Publisher` (restart, không reload — Python module cache).
    3. Bulk reset stuck jobs Threads bị duplicate trên VPS nếu còn:
       ```sql
       UPDATE jobs SET status='DONE', last_error='Marked DONE manually after dup-publish fix [2026-05-01]'
       WHERE platform='threads' AND status='FAILED'
         AND last_error LIKE '%post_url could not be captured%';
       ```
    4. Theo dõi 1-2 chu kỳ publish kế tiếp: confirm không còn duplicate; nếu `post_url=NULL` (capture trượt) thì đó là expected, post vẫn live trên Threads, không retry.

- **[2026-05-01] PLAN-032 / TASK-032 — VPS verified DONE, archived ✅**
  - Anh Vu confirm đã pull adapter diff lên VPS, `pm2 restart Threads_Publisher`, chạy 1 controlled publish account `facebook_2` (Nguyen Ngoc Vi) → `post_url` / `external_post_id` đúng own-handle. Bug bắt nhầm URL viral feed (job 613 cũ với `@campuchino.iu9x`) đã được fix trên production.
  - **Anti Sign-off**: APPROVED — 3/3 AC PASS. Acceptance criterion 1 và 3 chốt bằng VPS attestation từ anh Vu [2026-05-01].
  - **Archived**: PLAN-032 → `agents/plans/archive/`; TASK-032 → `agents/tasks/archive/`.
  - **System impact**: Threads pipeline trên VPS giờ vừa publish thành công (P029+P030+P031) vừa lưu `post_url` đúng chủ thể (P032). End-to-end production-ready.

- **[2026-04-29] Doc cleanup — TASK-015 → active/, TASK-017 → archive/, prompt rewrite committed**
  - **TASK-015** (`reverse-engineer-business-suite`) moved to `agents/tasks/active/` to match PLAN-015 location.
  - **TASK-017** (`threads-news-automation`) closed and moved to `agents/tasks/archive/` — its remaining "end-to-end VPS production test" item was delivered by PLAN-029/030/031 trilogy (job 613 + job 790 proofs).
  - **Prompt rewrite**: commit `19f8054 fix(threads-prompt): rewrite default prompt for hot world news` pushed to develop. Default prompt now enforces: scroll-stop hook (≤80 ký tự, 4 mẫu bắt buộc), 3-block structure (hook/body/CTA), forbids stale openers (NÓNG:, BREAKING:, …), trailing ellipsis, fabricated facts, hashtags. Emoji cap 2/post.
  - **Anh Vu deploy [2026-04-29]**: anh báo đã deploy lên VPS (pull develop + alembic upgrade head + paste prompt mới vào RuntimeSetting `THREADS_AI_PROMPT` + set `THREADS_ACCOUNT_CATEGORY_MAP` + `pm2 restart Threads_Publisher`). Live publish proof chưa thu thập trong session này.

- **[2026-04-29] PLAN-033 / TASK-033 - Threads World News Pipeline (Phase 1) — Codex execute DONE, Claude Code verified, VPS proof pending**
  - **Claude Code re-verify [2026-04-29]**:
    - Files đầy đủ: `app/services/content/topic_key.py`, `app/services/content/news_scraper.py`, `app/services/content/threads_news.py`, `app/database/models/threads.py`, `alembic/versions/9f1c2d3e4a5b_add_news_article_topic_key.py`, `tests/test_threads_world_news.py`.
    - `py_compile` cả 5 file Phase 1 → `PY_COMPILE_OK`.
    - `pytest tests/test_threads_world_news.py -q` → `12 passed in 1.25s`.
    - `from app.main import app` → `APP_IMPORT_OK 207`.
    - `RSS_SOURCES` count = 9 (VnExpress General/World/Current Affairs, Tuổi Trẻ General/World, Thanh Niên World, Dân Trí World, Vietnamnet World, 24h World) — đúng PLAN scope.
    - `news_scraper.py:111` lưu `topic_key=compute_topic_key(item["title"])` khi insert.
    - `threads_news.py` đọc 3 setting `THREADS_MAX_ARTICLE_AGE_HOURS / THREADS_TOPIC_DEDUP_HOURS / THREADS_ACCOUNT_CATEGORY_MAP`, có `_find_recent_topic_duplicate()` cho dedup, có age filter + category routing per-account.
    - Migration head clean: `alembic heads` → `9f1c2d3e4a5b (head)` (đã được fix multi-head trong commit `3e14d09`).
    - Git: PLAN-033 đã commit `c281a70`, follow-ups `3e14d09` (alembic heads chain), `b8596e1` (VN accents), `0ec2f60` (CI deploy trigger).
  - **Acceptance Criteria local**: 4/5 PASS (criterion 5 — VPS live publish — vẫn pending).
  - **Files**: [agents/plans/active/PLAN-033-threads-world-news.md](agents/plans/active/PLAN-033-threads-world-news.md), [agents/tasks/active/TASK-033-threads-world-news.md](agents/tasks/active/TASK-033-threads-world-news.md).
  - **Status**: Phase 1 code + verify done. Còn chờ anh Vu approve migration trên VPS + chạy live publish account World để chốt criterion 5.

- **[2026-04-28] PLAN-033 / TASK-033 - Threads World News Pipeline (Phase 1) — opened, Codex pending execute**
  - **User decision**: yêu cầu mở rộng pipeline cho mảng tin thế giới nóng hổi; chỉ định Claude Code + Codex tự execute, bỏ Anti sign-off gate cho PLAN này.
  - **Phase 1 scope** (PLAN-033):
    1. `news_scraper.py` — thêm 5 RSS thế giới VN (Tuổi Trẻ, Thanh Niên, Dân Trí, Vietnamnet, Zing/24h) → tổng 9 RSS.
    2. `NewsArticle.topic_key` (cột mới + migration + backfill) — hash từ keyword title sau khi loại stop-word VN.
    3. Helper `compute_topic_key(title)` + unit test (≥8 cases).
    4. `process_news_to_threads()` filter tuổi tin (`THREADS_MAX_ARTICLE_AGE_HOURS`, default 6).
    5. Topic dedup (`THREADS_TOPIC_DEDUP_HOURS`, default 24) — 2 article cùng topic_key → 1 job.
    6. Category routing per-account qua `THREADS_ACCOUNT_CATEGORY_MAP` (JSON RuntimeSetting).
  - **Phase 2 (out-of-scope, plan riêng sau)**: RSS quốc tế gốc + AI dịch, voice persona rotation, trending HOT detection.
  - **Files**: [agents/plans/active/PLAN-033-threads-world-news.md](agents/plans/active/PLAN-033-threads-world-news.md), [agents/tasks/active/TASK-033-threads-world-news.md](agents/tasks/active/TASK-033-threads-world-news.md).
  - **Status**: Codex execute backend; Claude Code verify UX/handoff sau khi Codex hoàn thành.

- **[2026-04-28] PLAN-032 / TASK-032 - Threads own-handle `post_url` capture implemented; VPS verify pending**
  - **Code change**: `app/adapters/threads/adapter.py` now stores `self._own_handle`, parses handle from both `threads.net` and `threads.com`, tries `_capture_own_latest_post()` first, filters fallback capture by own handle only, and clears `observed_urls` immediately before clicking Post so feed URLs collected earlier do not pollute the final capture.
  - **Static proof**:
    - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"` -> `PY_COMPILE_OK`
    - `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'\nfrom app.main import app\nprint('APP_IMPORT_OK %s' % len(app.routes))\nPY"` -> `APP_IMPORT_OK 207`
  - **Local runtime safety proof**:
    - `open_session('content/profiles/facebook_3')` -> `SESSION_OK=True`, `OWN_HANDLE=None`, `CURRENT_URL=https://www.threads.com/`
    - On that same live session: `CAPTURE_POST_REFERENCE=(None, None)` and `PROFILE_CAPTURE=(None, None)`
    - Meaning: if own handle cannot be discovered, the adapter now safe-fails instead of storing a random viral `post_url`.
  - **Local limitation**: all available local Threads profiles currently open `https://www.threads.com/` without a discoverable own handle, so the success path is not reproducible in this workspace.
  - **Claude Code re-verify [2026-04-28]**: diff = `1 file changed, 234 insertions(+), 3 deletions(-)` — scope đúng PLAN-032 (chỉ chạm `app/adapters/threads/adapter.py`, không đụng worker/dispatcher/DB). Re-run `venv/bin/python -m py_compile app/adapters/threads/adapter.py` → `PY_COMPILE_OK`; re-run `from app.main import app` → `APP_IMPORT_OK 207`. Logic check OK: `observed_urls.clear()` đặt ngay trước click Post (line 665), `_capture_own_latest_post()` chạy trước fallback (line 678+), `_capture_post_reference()` trả `None, None` khi không có URL match own-handle, `close_session()` reset `self._own_handle = None`.
  - **Status**: code + Claude Code verify done. VPS handoff still required for acceptance criteria 1 và 3.

- **[2026-04-28] 🐛 ThreadsAdapter capture nhầm `post_url` của người khác — đã mở TASK-032 (Planned)**
  - **Triệu chứng**: VPS job 613 (account Nguyen Ngoc Vi) đăng thành công, nhưng `post_url` trong DB là `https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x` — handle `campuchino.iu9x` KHÔNG phải Nguyen Ngoc Vi → đây là bài viral trên feed.
  - **Root cause** ([adapter.py:184-249](app/adapters/threads/adapter.py#L184-L249)):
    1. `capture_response`: scan mọi JSON response, match POST_PATH_RE → vào `observed_urls`.
    2. `_collect_urls_from_dom`: `querySelectorAll('a[href*="/post/"]')` toàn page (feed/comments/sidebar) + regex `page.content()` HTML.
    3. `_capture_post_reference`: trả `ordered_urls[0]` — không filter theo username chủ thể.
    → Sau click Post, Threads redirect về feed → bài viral render trước bài mình post → URL nhầm lên đầu.
  - **Fix recommended** (Codex thực thi qua TASK-032):
    1. `_discover_own_handle()` từ `a[href^="/@"]` ngay sau session init, lưu `self._own_handle`.
    2. `_capture_own_latest_post()`: navigate `https://www.threads.net/{own_handle}` → lấy `a[href*="/{own_handle}/post/"].first`.
    3. Fallback layer 2: filter `_capture_post_reference` theo `f"/{own_handle}/post/"` trong URL — nếu không match thì trả `None, None` (an toàn hơn false positive).
  - **Recovery DB sai**: SQL `UPDATE jobs SET post_url=NULL, external_post_id=NULL WHERE id=613;` (bài thật trên Threads vẫn còn, chỉ data trong DB nhầm).
  - **Status**: TASK-032 đã Planned. Chờ Codex thực thi.

- **[2026-04-28] 🎉 VPS PRODUCTION VERIFY: Threads end-to-end post thành công**
  - **Trigger**: Anh Vu pull `e96a51d` (merge P031) trên VPS + `pm2 restart Threads_Publisher` (restart, không reload — để Python re-import module).
  - **Live job 613**: Account `Nguyen Ngoc Vi`, profile `/root/toolsauto/content/profiles/facebook_2` → POST URL **`https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x`**, status DONE, cooldown 48s.
  - **Confirm fix path**: Compose ✓ → caption fill ✓ → attach button click ✓ (P030) → file input found via `_find_first_present` ✓ (P030) → upload ✓ → preview wait ✓ (P031) → Post button click trong dialog ✓ (P031) → URL captured ✓.
  - **Pipeline production-ready**. Worker tự động poll tiếp các Threads PENDING jobs trong queue.
  - **Lesson learned (ghi vào memory cho future deploy)**: PM2 với Python script PHẢI dùng `pm2 restart`, không phải `pm2 reload`. Reload không kill interpreter → module cache còn nguyên → fix không có hiệu lực.

- **[2026-04-28] PLAN-031 / TASK-031 - Threads Post button overlay — DONE & ARCHIVED ✅**
  - **Anti Sign-off**: APPROVED (4/4 AC PASS — overlay click fix, preview wait, fallback chain, no text-only regression).
  - **Claude Code re-verify**: PY_COMPILE_OK, APP_IMPORT_OK 207 routes, 26/26 tests PASS in 0.69s. DB job 790 confirm: `status=DONE, post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF, external_post_id=DXp-D0hjvPF, finished_at=1777339166, last_error=None`. Real post lên Threads thật ✓.
  - **Pending action for anh Vu**:
    1. Commit `M app/adapters/threads/adapter.py` — suggested: `fix(P031): scope Post button to dialog + media preview wait + 3-stage click fallback`.
    2. Push develop → VPS pull → `pm2 reload Threads_Publisher`.
    3. Bulk reset stuck FAILED jobs Threads trên VPS: `UPDATE jobs SET status='PENDING', tries=0, last_error=NULL, started_at=NULL, locked_at=NULL, last_heartbeat_at=NULL, schedule_ts=NULL WHERE platform='threads' AND status='FAILED';`
    4. Xoá post test "NÓNG: Bộ Y tế..." trên account `senhora_consumista` Threads.
  - **Archived**: PLAN-031 → `agents/plans/archive/`; TASK-031 → `agents/tasks/archive/`.

- **[2026-04-28] PLAN-031 / TASK-031 — original Codex handoff (superseded by archive entry above)**
  - **Status**: ✅ Anti Sign-off Completed. Ready for Archive.
  - **Code outcome**: `app/adapters/threads/adapter.py` now scopes `POST_BUTTON_SELECTORS` to `div[role="dialog"]`, waits for a visible media preview after `set_input_files(...)`, and uses a 3-stage click fallback for the final Post action: normal click -> `force=True` click -> JS `evaluate("el => el.click()")`.
  - **Static proof**: `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile app/adapters/threads/adapter.py && printf 'PY_COMPILE_OK\n'"` -> `PY_COMPILE_OK`.
  - **Runtime proof (local WSL)**:
    - `logs/app.log` lines 37-52 show `Job-790` moving through `[CLAIM]` -> `[PUBLISH]` -> `ThreadsAdapter: Publish completed for job 790 with post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF` -> `[DONE] Successfully published.`
    - DB row `jobs.id=790` now stores `status=DONE`, `tries=2`, `post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF`, `external_post_id=DXp-D0hjvPF`, `last_error=None`.
  - **Open proof gap**: No separate live text-only Threads publish is present in the current local DB (`TEXT_ONLY_JOB_NONE`), so the text-only non-regression criterion is not independently runtime-verified yet. The new preview wait stays inside `if media_path:` and does not execute for text-only jobs.

- **[2026-04-27] PLAN-030 / TASK-030 - Threads upload fix**
  - **Status**: Done and archived.
  - **Outcome**: Fixed hidden Threads media input handling by adding `ATTACH_SELECTORS` and `_find_first_present(...)`.
  - **Git**: committed and pushed on `develop` as `91a6778`.

- **[2026-04-27] PLAN-029 / TASK-029 - Threads publisher implementation**
  - **Status**: Done and archived.
  - **Outcome**: Threads adapter, isolated `Threads_Publisher` worker, dispatcher route, queue platform isolation, and PM2 entry were implemented. Follow-up runtime bugs were split into TASK-030 and TASK-031 instead of reopening PLAN-029.

## System State

- **Environment**: WSL Ubuntu / Python 3.10 / direct server workflow
- **Database**: PostgreSQL
- **Git branch**: `develop`
- **Threads pipeline**: News scrape -> AI gen -> `PENDING` Threads job -> `Threads_Publisher` -> Playwright publish -> DB update (`post_url`, `external_post_id`)
- **Latest local Threads publish proof**: Job `790` published successfully with `post_url=https://www.threads.net/@senhora_consumista/post/DXp-D0hjvPF`
- **Current Threads priority**: PLAN-032 closed [2026-05-01]. Còn lại PLAN-033 Phase 1 chờ VPS migration approve + live publish criterion 5.
- **Threads pipeline status**: ✅✅ End-to-end working **trên VPS production** (commit `e96a51d` merge P031). Live proof job 613 (account `Nguyen Ngoc Vi`, profile `facebook_2`) post thành công: `https://www.threads.net/@campuchino.iu9x/post/DXpDgbYj12x`, status DONE, cooldown 48s tới poll tiếp. Trilogy PLAN-029 + P030 + P031 hoàn tất production verification.
- **AI pipeline baseline**: prior service-layer tests remain at `18/18 PASS`

## Open Risks

- Threads dup-publish fix [2026-05-01] chưa có VPS proof — chờ pull + `pm2 restart` + 1-2 chu kỳ verify trước khi đóng risk.
- `_check_already_published` dựa vào `caption_signature` 60 ký tự đầu — nếu 2 article khác nhau có 60 ký tự đầu giống hệt (rất hiếm cho tin world news) sẽ false-positive skip publish; chấp nhận trade-off vì topic_dedup đã chặn ở layer trên.
- `post_url=NULL` cho job DONE: dashboard / NotifierService phải chấp nhận URL trống. Đã check `notify_job_done(job, post_url=post_url)` cho `post_url=None` — cần monitor 1 chu kỳ thật để confirm không crash.

- `PLAN-031` still lacks independent live proof for the text-only Threads publish branch.
- VPS/PM2 verification for the PLAN-031 overlay fix has not been repeated in this turn; current proof is local WSL log + DB evidence.
- The older VPS-side `AI_Generator` `SyntaxError: source code cannot contain null bytes` investigation remains unresolved in handoff history and is unrelated to PLAN-031.

## Next Action

0. **Threads dup-publish fix [2026-05-01]**: anh Vu commit + push develop → VPS pull → `pm2 restart Threads_Publisher` → bulk reset FAILED jobs có lỗi `post_url could not be captured` → theo dõi 1-2 chu kỳ publish, verify không còn dup.

1. **PLAN-033 Phase 1**: code + Claude Code verify DONE local (4/5 AC PASS). Còn lại:
   - Anh Vu approve migration `9f1c2d3e4a5b_add_news_article_topic_key.py` trước khi chạy trên VPS.
   - Pull lên VPS → `alembic upgrade head` → restart `Threads_Publisher` (`pm2 restart`, không reload).
   - Set `THREADS_ACCOUNT_CATEGORY_MAP` JSON cho account World qua RuntimeSetting.
   - Chạy 1 chu kỳ scrape + publish thật, verify `post_url` đúng handle World account → chốt criterion 5 + Anti Sign-off.
2. Revisit older `PLAN-031` text-only proof gap only if acceptance criterion is still required.
