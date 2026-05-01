# PLAN-034: Threads Article Curation Scoring (Phase 1)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-034 |
| **Status** | Pending Anti Approval |
| **Executor** | Claude Code (anh Vu chấp thuận tự execute + tự test cho task này) |
| **Created by** | Claude Code (theo yêu cầu của anh Vu) |
| **Related Task** | TASK-034 |
| **Related ADR** | None |
| **Created** | 2026-05-01 |
| **Updated** | 2026-05-01 |

---

## Goal
Nâng chất lượng bài Threads bằng cách thay layer "đăng tin gì" — chuyển từ chọn theo `published_at desc` (bài mới nhất) sang chọn theo `engagement_score desc` (bài đáng đăng nhất). Layer prompt + voice giữ nguyên — Phase 2.

---

## Context
Pipeline hiện tại (`threads_news.py:186`) chọn article bằng `order_by(published_at desc, id desc).first()` → bài mới nhất, không phân biệt bài hot vs. bài thường. AI viết hay cách mấy cũng không kéo engagement nếu nguồn vào là bài tệ. Phase 1 giới thiệu scoring layer rẻ tiền (toán cục bộ, không gọi external API) để test giả thuyết "curation > generation" trước khi đầu tư Phase 2 (engagement feedback loop, Google Trends).

---

## Scope

### [NEW] `app/services/content/article_scorer.py`
- `compute_score(article, *, all_topic_counts: dict[str, int], source_weights: dict[str, float], now_ts: int) -> float`
- 4 signal thành phần, weighted sum, clamp về [0, 100]:
  1. **Recency** (40%): `exp(-age_hours / 6)` — bài 0h = 1.0, 6h = 0.37, 12h = 0.14.
  2. **Source weight** (20%): tra `source_weights` map; default 1.0; clamp [0.3, 1.5].
  3. **Title hot-marker bonus** (15%): regex `r'\b(nóng|đột ngột|lần đầu|kỷ lục|vừa|mới nhất|bất ngờ|chấn động|sốc)\b'` (case-insensitive, có dấu) — match = +1.0, không = 0.
  4. **Topic competition bonus** (25%): nếu `topic_key` có ≥2 article cùng được scrape gần đây (`all_topic_counts[topic_key] >= 2`) → +1.0, ≥3 → +1.5 (tin "nhiều nguồn cùng đưa" = hot).

### [MODIFY] `app/database/models/threads.py`
- Thêm `engagement_score = Column(Float, nullable=True, index=True)` vào `NewsArticle`.

### [NEW] `alembic/versions/{rev}_add_news_engagement_score.py`
- `down_revision = "9f1c2d3e4a5b"` (head hiện tại sau PLAN-033 Phase 1).
- Add column `engagement_score FLOAT NULL` + index `ix_news_articles_engagement_score`.
- Downgrade: drop index + column.

### [MODIFY] `app/services/content/news_scraper.py`
- Sau khi `db.add(article)` + commit (line 116-117), tính score qua `compute_score()` rồi `article.engagement_score = score; db.commit()`.
- Lấy `source_weights` từ RuntimeSetting `THREADS_SOURCE_WEIGHTS` (JSON, default `{}` → tất cả = 1.0).
- Tính `all_topic_counts` 1 lần đầu `scrape_all()` (query `topic_key, count(*)` trong 24h gần nhất).

### [MODIFY] `app/services/content/threads_news.py`
- Line 186: đổi `order_by(NewsArticle.published_at.desc(), NewsArticle.id.desc())` → `order_by(NewsArticle.engagement_score.desc().nullslast(), NewsArticle.published_at.desc(), NewsArticle.id.desc())`.
- Nullslast để article cũ chưa kịp score (legacy data) rơi xuống cuối.

### [NEW] `tests/test_article_scorer.py` (≥8 cases)
1. Recency: 0h vs. 6h vs. 24h → score giảm dần.
2. Source weight: VnExpress (1.0) > 24h (0.7) cho cùng article.
3. Hot marker: title chứa "nóng" → score cao hơn title trung tính.
4. Topic competition: topic_key xuất hiện 3 lần > 1 lần.
5. Source weight clamp: weight 5.0 → bị clamp về 1.5.
6. Source weight clamp: weight 0.0 → bị clamp về 0.3.
7. Hot marker case-insensitive + có dấu VN.
8. Score luôn nằm trong [0, 100].
9. (bonus) Tổ hợp 4 signal max ra giá trị reasonable (<= 100).

### [MODIFY] `tests/test_threads_world_news.py`
- Thêm 1 test: seed 3 article cùng category, khác score → `process_news_to_threads()` phải chọn article có score cao nhất, không phải mới nhất theo `published_at`.

---

## Out of Scope (Phase 2 — plan riêng)
- Engagement feedback loop (scrape like/reply count sau publish 24h).
- Google Trends VN integration.
- Voice persona rotation.
- AI model upgrade.
- Real-time scoring (push notification → score lại).
- Backfill score cho article cũ (chỉ score article mới scrape; cũ rơi xuống cuối qua `nullslast`).

---

## Proposed Approach

**Bước 1**: Thêm column + migration. Verify `alembic upgrade head` clean local.
**Bước 2**: Viết `article_scorer.py` + tests. Verify pytest pass.
**Bước 3**: Wire vào `news_scraper.py` (compute score on insert).
**Bước 4**: Đổi `order_by` trong `threads_news.py`.
**Bước 5**: Update `test_threads_world_news.py` cho selection mới.
**Bước 6**: Smoke test toàn pipeline local: `scraper.scrape_all()` → kiểm tra DB có `engagement_score` đầy → `process_news_to_threads()` chọn đúng.
**Bước 7**: Commit + push develop. VPS handoff cho anh Vu (alembic upgrade + restart).

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Score logic sai → chọn bài kém liên tục | Medium | Score formula đơn giản, dễ tune; có RuntimeSetting để chỉnh weight không cần redeploy. Monitor 1 tuần đầu. |
| Source weight default `{}` lệch lạc | Low | Default tất cả = 1.0 (neutral) — không thay đổi behavior nếu anh Vu không set. |
| Hot marker regex false positive (vd. "vừa qua" trong tin lịch sử) | Low | Bonus chỉ +1.0/15% trọng số → không dominate; có thể tune sau. |
| Migration thêm column gây slow trên table lớn | Very Low | `news_articles` table nhỏ (vài nghìn row). ALTER TABLE ADD COLUMN NULL = instant trên PostgreSQL. |
| Article legacy không có score rơi xuống cuối luôn → không bao giờ được đăng | Acceptable | Đúng intended behavior — bài >24h cũ không nên đăng (đã có `THREADS_MAX_ARTICLE_AGE_HOURS` filter chặn từ trước). |
| Score recompute sai do `all_topic_counts` query expensive | Low | Query 1 lần / chu kỳ scrape (15-30p/lần), index trên `topic_key` + `published_at` → cheap. |

---

## Validation Plan
- [ ] `alembic upgrade head` succeed local; `alembic heads` = 1 head duy nhất (migration mới).
- [ ] `pytest tests/test_article_scorer.py -q` ≥9 PASS.
- [ ] `pytest tests/test_threads_world_news.py -q` toàn bộ PASS (regression).
- [ ] `from app.main import app` → ≥207 routes.
- [ ] Smoke runtime: seed 3 article (score 80, 50, 20) → `process_news_to_threads()` → job được tạo cho article score 80.
- [ ] Commit message tuân `fix(...)` / `feat(...)` convention.
- [ ] Diff scope ≤ 6 file (model, migration, scorer, scraper, threads_news, 2 test files).

---

## Acceptance Criteria
1. Migration `add_news_engagement_score` lên head clean, alembic chain không multi-head.
2. `compute_score()` unit test ≥9 cases PASS, mỗi signal có ít nhất 1 test riêng.
3. `news_scraper.scrape_all()` populate `engagement_score` cho mọi article mới insert (verify DB).
4. `process_news_to_threads()` select article theo `engagement_score desc nulls last`, có integration test confirm.
5. `THREADS_SOURCE_WEIGHTS` RuntimeSetting JSON respected (test với map `{"VnExpress": 1.5, "24h": 0.5}`).
6. App import OK + tất cả test cũ PASS (no regression).

---

## Rollback Plan
1. `alembic downgrade -1` để bỏ column.
2. `git revert <commit-sha>` → reset code.
3. Pipeline về behavior cũ (chọn bài mới nhất).

---

## Execution Notes
*(Claude Code điền vào theo thứ tự từng bước khi anh Vu duyệt PLAN)*

---

## Anti Sign-off Gate ⛔
**Reviewed by**: Pending — chờ anh Vu duyệt PLAN trước khi Claude Code execute.

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Migration lên head clean | No | ⏳ |
| 2 | Scorer unit test ≥9 PASS | No | ⏳ |
| 3 | Scraper populate score | No | ⏳ |
| 4 | Selection theo score | No | ⏳ |
| 5 | Source weight RuntimeSetting | No | ⏳ |
| 6 | No regression existing tests | No | ⏳ |

### Verdict
> **PENDING APPROVAL** — chờ anh Vu duyệt scope + approach.
