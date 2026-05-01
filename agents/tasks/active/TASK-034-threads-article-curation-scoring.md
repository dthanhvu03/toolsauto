# TASK-034: Threads Article Curation Scoring (Phase 1)

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-034 |
| **Status** | Pending Anti Approval |
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
- [ ] `alembic upgrade head` succeed local, single head.
- [ ] `pytest tests/test_article_scorer.py -q` ≥9 PASS.
- [ ] `pytest tests/test_threads_world_news.py -q` PASS (no regression) + có thêm test selection theo score.
- [ ] `from app.main import app` OK ≥207 routes.
- [ ] Smoke runtime: 3 article seed (score 80/50/20) → `process_news_to_threads()` chọn article 80.
- [ ] `THREADS_SOURCE_WEIGHTS` JSON map respected (test với `{"VnExpress": 1.5, "24h": 0.5}`).
- [ ] Diff scope ≤ 6 file.
- [ ] Anh Vu sau đó pull VPS + `alembic upgrade head` + `pm2 restart Threads_Publisher` → pipeline chạy 1 chu kỳ → DB confirm có `engagement_score`.

---

## Execution Notes
*(Claude Code điền vào trong khi làm sau khi anh Vu duyệt)*

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-05-01 | Pending Anti Approval | Task + PLAN-034 được tạo bởi Claude Code theo yêu cầu của anh Vu. Anh Vu sẽ duyệt khi quay lại; sau đó Claude Code tự execute + tự test. |
