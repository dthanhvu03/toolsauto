# PLAN-033: Threads World News Pipeline (Phase 1 - MVP)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-033 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Claude Code (theo yeu cau user) |
| **Related Task** | TASK-033 |
| **Related ADR** | None |
| **Created** | 2026-04-28 |
| **Updated** | 2026-04-28 |

---

## Goal
Mo rong pipeline tin tuc Threads de phuc vu noi dung tin the gioi nong hoi, khong trung chu de, co kha nang route theo category cho tung account.

Phase 1 chi xu ly pipeline RSS + topic dedup + age/category filter. Khong dung AI dich/nguon quoc te goc.

---

## Context
Hien tai:
- `news_scraper.py` chi co 4 RSS; phan the gioi rat mong.
- `process_news_to_threads()` chi pick `NewsArticle.status='NEW'` moi nhat theo `published_at desc`.
- Chua co filter tuoi tin, chua co route category theo account, chua co dedup chu de.

User yeu cau: account Threads chuyen dang tin the gioi, uu tien tin <= 6h, va tranh lap khi nhieu bao dua cung 1 su kien.

---

## Scope

### [MODIFY] `app/services/content/news_scraper.py`
- Mo rong `RSS_SOURCES` them 5 RSS the gioi tu bao VN khac.
- Khi tao `NewsArticle`, tinh va luu `topic_key`.

### [MODIFY] `app/database/models/threads.py`
- Them cot `topic_key = Column(String, nullable=True, index=True)` vao `NewsArticle`.

### [NEW HELPER] `app/services/content/topic_key.py`
- `compute_topic_key(title: str) -> str`
- Lowercase, bo dau, loai stop-word, lay 5-7 tu khoa dai nhat, sort + hash MD5, cat 16 ky tu dau.

### [MODIFY] `app/services/content/threads_news.py`
- Doc them:
  - `THREADS_MAX_ARTICLE_AGE_HOURS` (default 6)
  - `THREADS_TOPIC_DEDUP_HOURS` (default 24)
  - `THREADS_ACCOUNT_CATEGORY_MAP` (JSON `{"<account_id>": "World"}`)
- Filter article theo tuoi tin.
- Filter article theo category map cua account hien tai.
- Tranh tao Job moi neu trong cua so dedup da co job Threads cung `topic_key`.

### [MIGRATION]
- Them cot `topic_key` vao `news_articles`.
- Backfill `topic_key` cho row cu.
- Seed setting mac dinh neu chua ton tai:
  - `THREADS_MAX_ARTICLE_AGE_HOURS=6`
  - `THREADS_TOPIC_DEDUP_HOURS=24`
  - `THREADS_ACCOUNT_CATEGORY_MAP={}`

---

## Out of Scope
- RSS quoc te goc + AI dich/Viet hoa.
- Trending HOT detection.
- UI dashboard cho category map.

---

## Proposed Approach
1. Schema: model + migration + backfill + seed setting.
2. Helper: `compute_topic_key()` + unit test.
3. Scraper: mo rong RSS, luu `topic_key`, verify `scrape_all()`.
4. Threads news: age filter + category map + topic dedup.
5. Verify: pytest, py_compile, app import smoke, migration smoke.

---

## Risks
| Risk | Muc do | Xu ly |
|---|---|---|
| RSS moi fail/format khac | Low | `fetch_rss` da co try/except; chi log loi feed |
| topic_key qua strict | Medium | heuristic 5-7 keyword, co the noi long o Phase 2 |
| topic_key qua long | Medium | chap nhan false positive nho o Phase 1 |
| Backfill row cu cham | Low | chunk 500 row |
| Migration tren VPS | High | can user approve truoc khi chay tren VPS |

---

## Validation Plan
- [x] Migration smoke isolated: up + down cho revision `9f1c2d3e4a5b`.
- [x] `compute_topic_key()` unit test PASS (8 case pair + cac case service/scraper).
- [x] `scraper.scrape_all()` duoc goi 1 lan trong test co lap, insert 9 article va luu `topic_key`.
- [x] `process_news_to_threads()` bo qua article > 6h.
- [x] `process_news_to_threads()` skip duplicate topic trong cua so dedup.
- [x] `process_news_to_threads()` route category theo account map.
- [x] `PY_COMPILE_OK`.
- [x] `APP_IMPORT_OK 207`.
- [ ] VPS proof: worker scrape + post that su, `post_url` dung handle account World.

---

## Rollback Plan
1. `ALTER TABLE news_articles DROP COLUMN topic_key;`
2. Revert `news_scraper.py`, `threads_news.py`, `threads.py`, `topic_key.py`, migration, va test.
3. Xoa setting seed neu can.

---

## Execution Notes
### Step 1 - Schema
- Added `NewsArticle.topic_key` in `app/database/models/threads.py`.
- Added migration `9f1c2d3e4a5b_add_news_article_topic_key.py`:
  - add nullable/indexed `topic_key`
  - backfill `news_articles.topic_key` in chunks of 500
  - seed `THREADS_MAX_ARTICLE_AGE_HOURS=6`, `THREADS_TOPIC_DEDUP_HOURS=24`, `THREADS_ACCOUNT_CATEGORY_MAP={}`
- Proof:
  - `venv/bin/python -m py_compile ... && echo PY_COMPILE_OK`
    - `PY_COMPILE_OK`
  - isolated Alembic smoke on `/tmp/plan033_iso.db`
    - `Running stamp_revision  -> f2a3b4c5d6e8`
    - `Running upgrade f2a3b4c5d6e8 -> 9f1c2d3e4a5b, add topic_key to news_articles`
    - `ISO_MIG_TOPIC_KEY_PRESENT True`
    - `ISO_MIG_BACKFILL 8efa9e64eb963783`
    - `ISO_MIG_SEEDS [('THREADS_ACCOUNT_CATEGORY_MAP', '{}', 'text'), ('THREADS_MAX_ARTICLE_AGE_HOURS', '6', 'int'), ('THREADS_TOPIC_DEDUP_HOURS', '24', 'int')]`
    - `Running downgrade 9f1c2d3e4a5b -> f2a3b4c5d6e8, add topic_key to news_articles`
    - `ISO_MIG_TOPIC_KEY_REMOVED True`

### Step 2 - Helper
- Added `app/services/content/topic_key.py` with accent normalization, VN stop-word removal, longest-keyword ranking, and `md5[:16]` topic hashing.
- Proof:
  - `venv/bin/python -m pytest tests/test_threads_world_news.py -vv`
    - `collected 12 items`
    - `test_compute_topic_key_same_event_pairs_match[...] PASSED`
    - `test_compute_topic_key_different_event_pairs_diverge[...] PASSED`

### Step 3 - Scraper
- Expanded `RSS_SOURCES` from 4 to 9 feeds.
- `NewsScraper.scrape_all()` now stores `topic_key` on insert.
- Proof:
  - `venv/bin/python -m pytest tests/test_threads_world_news.py -vv`
    - `tests/test_threads_world_news.py::test_scrape_all_runs_once_and_saves_topic_key PASSED`

### Step 4 - Threads news
- `process_news_to_threads()` now:
  - reads `THREADS_MAX_ARTICLE_AGE_HOURS`, `THREADS_TOPIC_DEDUP_HOURS`, `THREADS_ACCOUNT_CATEGORY_MAP`
  - filters candidates by age
  - applies per-account category routing
  - skips duplicate topics using recent Threads jobs + `topic_key`
- Added setting specs in `app/services/platform/settings.py`.
- Proof:
  - `venv/bin/python -m pytest tests/test_threads_world_news.py -vv`
    - `tests/test_threads_world_news.py::test_process_news_to_threads_skips_articles_older_than_max_age_hours PASSED`
    - `tests/test_threads_world_news.py::test_process_news_to_threads_marks_duplicate_topic_as_skipped PASSED`
    - `tests/test_threads_world_news.py::test_process_news_to_threads_applies_account_category_map PASSED`

### Step 5 - Verify
- Proof:
  - `venv/bin/python -m py_compile ... && echo PY_COMPILE_OK`
    - `PY_COMPILE_OK`
  - `venv/bin/python -m pytest tests/test_threads_world_news.py -q`
    - `............                                                             [100%]`
    - `12 passed in 1.05s`
  - `venv/bin/python -c "from app.main import app; print('APP_IMPORT_OK', len(app.routes))"`
    - `APP_IMPORT_OK 207`
- Live VPS publish proof is still pending.
- Execution Done. Can Claude Code verify + handoff.

---

## Anti Sign-off Gate
User chi dinh bo qua Anti gate cho PLAN nay; Codex va Claude Code tu execute/verify.

### Acceptance Criteria Check
| # | Criterion | Proof co khong? | Pass? |
|---|---|---|---|
| 1 | 9 RSS scrape thanh cong, luu topic_key | `test_scrape_all_runs_once_and_saves_topic_key PASSED` | ✅ local |
| 2 | 2 article cung topic_key -> 1 job duy nhat | `test_process_news_to_threads_marks_duplicate_topic_as_skipped PASSED` | ✅ local |
| 3 | Article > 6h khong bi pick | `test_process_news_to_threads_skips_articles_older_than_max_age_hours PASSED` | ✅ local |
| 4 | Account co category map -> chi pick match category | `test_process_news_to_threads_applies_account_category_map PASSED` | ✅ local |
| 5 | Live VPS: 1 publish the gioi, post_url dung handle | Chua chay worker/publish tren VPS | ⏳ pending |

### Verdict
> Local execute + isolated verify done. Live VPS publish proof still pending before full sign-off.
