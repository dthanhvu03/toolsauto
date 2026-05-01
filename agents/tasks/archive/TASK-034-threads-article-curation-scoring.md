# TASK-034: Threads Article Curation Scoring (Phase 1)

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-034 |
| **Status** | Done (code + local verify); VPS deploy pending |
| **Priority** | P2 |
| **Owner** | anh Vu |
| **Executor** | Claude Code (anh Vu chấp thuận tự execute + tự test) |
| **Related Plan** | PLAN-034 |
| **Created** | 2026-05-01 |
| **Updated** | 2026-05-01 |

---

## Objective
Thay layer chọn article của pipeline Threads news từ "bài mới nhất" → "bài đáng đăng nhất" qua `engagement_score` tổng hợp 4 signal (recency, source weight, hot marker title, topic competition). Mục tiêu: nâng chất lượng bài đăng mà không cần thay prompt hay AI model.

---

## Scope
- Thêm column `NewsArticle.engagement_score` + migration alembic.
- Tạo `app/services/content/article_scorer.py` với hàm pure `compute_score(...)`.
- Wire scoring vào `news_scraper.py` (compute on insert).
- Đổi `order_by` trong `threads_news.py` để select theo score.
- Unit test ≥9 cases cho scorer; integration test cho selection.
- RuntimeSetting `THREADS_SOURCE_WEIGHTS` JSON.

## Out of Scope
- Backfill score cho article cũ.
- Engagement scraping post-publish (Phase 2).
- Google Trends / external API.
- Voice persona rotation.
- Touch worker / dispatcher / DB schema khác (chỉ thêm column vào `news_articles`).

---

## Blockers
- Cần anh Vu duyệt PLAN-034 (Anti Sign-off Gate) trước khi execute.

---

## Acceptance Criteria
- [x] `alembic upgrade head` succeed local, single head (`a8e7f6d5c4b3`).
- [x] `pytest tests/test_article_scorer.py -q` 10/10 PASS in 0.05s.
- [x] `pytest tests/test_threads_world_news.py -q` 14/14 PASS (12 cũ + 2 mới: selection theo score, scraper populate score).
- [x] `from app.main import app` OK 207 routes.
- [x] Smoke runtime: 3 article (score 20/50/85) → integration test confirm chọn article score 85.
- [x] `THREADS_SOURCE_WEIGHTS` JSON map respected — smoke với `{"VnExpress":1.3,"Tuổi Trẻ":1.2,"24h":0.7}` ra ranking chính xác (VnExpress NÓNG 82 > Tuổi Trẻ sốc 77 > 24h tin thường 24).
- [x] Diff scope: 7 file (model + migration + scorer + scraper + threads_news + 2 test files) — vượt 1 file so PLAN nhưng vẫn minimal.
- [ ] Anh Vu sau đó pull VPS + `alembic upgrade head` + `pm2 restart Threads_Publisher` → pipeline chạy 1 chu kỳ → DB confirm có `engagement_score`.

---

## Execution Notes
- 7 bước thực thi đầy đủ — chi tiết ghi trong `PLAN-034.Execution Notes`.
- Files touched (7):
  - `app/database/models/threads.py` (+1 column, +1 import)
  - `alembic/versions/a8e7f6d5c4b3_add_news_engagement_score.py` (new, 95 lines)
  - `app/services/content/article_scorer.py` (new, 95 lines)
  - `app/services/content/news_scraper.py` (+ scoring batch + import)
  - `app/services/content/threads_news.py` (+1 line: order_by change)
  - `tests/test_article_scorer.py` (new, 10 cases)
  - `tests/test_threads_world_news.py` (+2 cases)

---

## Verification Proof
- `venv/bin/alembic upgrade head` → `9f1c2d3e4a5b → a8e7f6d5c4b3`. `alembic heads` = `a8e7f6d5c4b3 (head)` single head.
- `venv/bin/python -m pytest tests/test_article_scorer.py tests/test_threads_world_news.py -v` → `24 passed in 1.65s`.
- `venv/bin/python -m py_compile` cho 5 file mới/sửa → all OK.
- `from app.main import app` → `APP_IMPORT_OK 207`.
- Smoke runtime với 3 article realistic (24h kinh tế / VnExpress NÓNG US politics / Tuổi Trẻ sốc US politics, weights `{"VnExpress":1.3,"Tuổi Trẻ":1.2,"24h":0.7}`):
  - 23.84  24h          Tin thường về kinh tế
  - 82.05  VnExpress    NÓNG: chấn động chính trường Mỹ
  - 76.94  Tuổi Trẻ     Bầu cử Mỹ: kết quả sốc
- 18 test failure khác trong full suite (`test_post_page`, `test_switch`, `test_platform_workflow_runtime`) là pre-existing FacebookAdapter/Playwright errors, không liên quan PLAN-034.

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-05-01 | Done (local) | 7 bước thực thi xong; 24/24 test PASS; alembic head clean; smoke runtime confirm logic. Pending VPS deploy + 1 chu kỳ live verify. |
| 2026-05-01 | In Progress | Anh Vu duyệt PLAN, Claude Code bắt đầu execute. |
| 2026-05-01 | Pending Anti Approval | Task + PLAN-034 được tạo bởi Claude Code theo yêu cầu của anh Vu. |
