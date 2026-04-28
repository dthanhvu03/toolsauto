# TASK-033: Threads World News Pipeline - Phase 1

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-033 |
| **Status** | In Progress |
| **Priority** | P1 |
| **Owner** | Claude Code (UX/handoff) + Codex (backend execute) |
| **Executor** | Codex |
| **Related Plan** | PLAN-033 |
| **Created** | 2026-04-28 |
| **Updated** | 2026-04-28 |

---

## Objective
Dua tin tuc the gioi (qua bao VN) vao pipeline Threads voi 3 co che chong nhieu:
- filter tuoi tin
- dedup theo chu de
- route category theo account

---

## Scope
Theo PLAN-033 - Phase 1:
1. Mo rong `RSS_SOURCES` them 5 RSS the gioi VN.
2. Them cot `topic_key` vao `NewsArticle` + migration + backfill.
3. Implement `compute_topic_key(title)` + unit test.
4. Filter tuoi tin (`THREADS_MAX_ARTICLE_AGE_HOURS`, default 6).
5. Topic dedup (`THREADS_TOPIC_DEDUP_HOURS`, default 24).
6. Category routing per-account qua `THREADS_ACCOUNT_CATEGORY_MAP`.

## Out of Scope
- RSS quoc te goc + AI dich (Phase 2).
- Voice persona rotation, trending HOT (Phase 2).
- UI dashboard cho category map.

---

## Blockers
- None for local execute.
- Live VPS migration/publish still requires user approval + environment run.

---

## Acceptance Criteria
- [x] 9 RSS (4 cu + 5 moi) scrape khong loi; moi `NewsArticle` moi co `topic_key`.
- [x] Helper `compute_topic_key()`: >=4 cap title cung su kien ra cung key, >=4 cap khac su kien ra key khac.
- [x] `process_news_to_threads()` bo qua article >`THREADS_MAX_ARTICLE_AGE_HOURS` tuoi.
- [x] Khi 2 article cung `topic_key` xuat hien trong cua so dedup, chi 1 Job duoc tao; article con lai co `status='SKIPPED'`.
- [x] Khi `THREADS_ACCOUNT_CATEGORY_MAP` co entry cho account dang xu ly, chi article match category moi duoc pick.
- [x] `PY_COMPILE_OK` + `APP_IMPORT_OK 207` khong giam.
- [ ] Live VPS 1 nhip: 1 job the gioi duoc publish; `post_url` chua handle dung cua account World.

---

## Execution Notes
### Step 1 - Schema + migration
- Added `topic_key` field to `NewsArticle`.
- Added migration `9f1c2d3e4a5b_add_news_article_topic_key.py` with backfill + setting seed.
- Proof:
  - `PY_COMPILE_OK`
  - `ISO_MIG_TOPIC_KEY_PRESENT True`
  - `ISO_MIG_BACKFILL 8efa9e64eb963783`
  - `ISO_MIG_SEEDS [('THREADS_ACCOUNT_CATEGORY_MAP', '{}', 'text'), ('THREADS_MAX_ARTICLE_AGE_HOURS', '6', 'int'), ('THREADS_TOPIC_DEDUP_HOURS', '24', 'int')]`
  - `ISO_MIG_TOPIC_KEY_REMOVED True`

### Step 2 - Helper
- Added `app/services/content/topic_key.py`.
- Proof:
  - `test_compute_topic_key_same_event_pairs_match[...] PASSED`
  - `test_compute_topic_key_different_event_pairs_diverge[...] PASSED`

### Step 3 - Scraper
- Expanded `RSS_SOURCES` to 9 feeds and save `topic_key` on insert.
- Proof:
  - `tests/test_threads_world_news.py::test_scrape_all_runs_once_and_saves_topic_key PASSED`

### Step 4 - Threads news
- Added age filter, topic dedup, and account category routing.
- Added runtime setting specs:
  - `THREADS_MAX_ARTICLE_AGE_HOURS`
  - `THREADS_TOPIC_DEDUP_HOURS`
  - `THREADS_ACCOUNT_CATEGORY_MAP`
- Proof:
  - `tests/test_threads_world_news.py::test_process_news_to_threads_skips_articles_older_than_max_age_hours PASSED`
  - `tests/test_threads_world_news.py::test_process_news_to_threads_marks_duplicate_topic_as_skipped PASSED`
  - `tests/test_threads_world_news.py::test_process_news_to_threads_applies_account_category_map PASSED`

### Step 5 - Verify
- Proof:
  - `venv/bin/python -m pytest tests/test_threads_world_news.py -q`
    - `12 passed in 1.05s`
  - `venv/bin/python -c "from app.main import app; print('APP_IMPORT_OK', len(app.routes))"`
    - `APP_IMPORT_OK 207`
- Live VPS proof pending.
- Execution Done. Can Claude Code verify + handoff.

---

## Verification Proof
- `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m py_compile ... && echo PY_COMPILE_OK"`
  - `PY_COMPILE_OK`
- `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -m pytest tests/test_threads_world_news.py -vv"`
  - `collected 12 items`
  - `12 passed in 1.02s`
- `wsl.exe bash -lc "cd /home/vu/toolsauto && venv/bin/python -c 'from app.main import app; print(...)'"`
  - `APP_IMPORT_OK 207`

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-28 | New | User chi dinh Claude Code + Codex execute (bo Anti gate cho PLAN nay) |
| 2026-04-28 | In Progress | Codex da xong local execute + isolated verify; cho Claude Code verify/handoff va VPS proof |
