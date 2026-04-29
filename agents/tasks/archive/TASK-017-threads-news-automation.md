# TASK-017: Threads News Automation Integration

## Status
- **Status:** In Progress (Near Complete)
- **Priority:** High
- **Owner:** Antigravity (AI Agent)
- **Created:** 2026-04-25
- **Last Updated:** 2026-04-26

## Context
Tích hợp kênh Threads vào hệ thống Auto Publisher. Mục tiêu là tự động lấy tin tức từ RSS/Web, dùng AI viết lại và đăng tự động. Hỗ trợ tùy chỉnh toàn bộ qua Settings UI.

## Requirements
1. **News Scraper**: Lấy tin từ VnExpress, Tuổi Trẻ RSS.
2. **AI Style**: Viết theo prompt tùy chỉnh từ Settings (trước đây hardcode style us28qt).
3. **Approval Flow**: Hỗ trợ 2 chế độ: Duyệt tay (DRAFT) và Tự động (PENDING).
4. **Control Toggle**: Có nút bật/tắt chế độ tự động + tùy chỉnh cooldown, prompt, char limits.
5. **GenericAdapter Integration**: Sử dụng GenericAdapter để đăng bài lên Threads.
6. **Dynamic Account Selection**: Tự động tìm tài khoản Threads đang kết nối, không hardcode.

## Todo List
- [x] **Database Setup**
    - [x] Thêm bảng `news_articles` vào `app/database/models.py`.
    - [x] Thêm setting `THREADS_AUTO_MODE` vào `RuntimeSetting`.
- [x] **News Ingestion**
    - [x] Tạo `app/services/news_scraper.py` để lấy tin RSS.
    - [x] Worker riêng `workers/threads_news_worker.py` scrape định kỳ (chu kỳ tùy chỉnh qua Settings).
- [x] **AI Orchestration**
    - [x] Define prompt (giờ tùy chỉnh qua Settings `THREADS_AI_PROMPT`).
    - [x] Fix AI pipeline Pydantic schema cho null values (`ai_pipeline.py`).
    - [x] Fix content_orchestrator JSON validation cho null optional fields.
    - [x] Fix ai_generator.py null safety khi xử lý hashtags/keywords.
- [x] **Threads UI Configuration**
    - [x] Seed `platform_configs` cho Threads.
    - [x] Seed `workflow_definitions` cho Threads:POST.
    - [x] Seed `platform_selectors` cho các nút bấm trên Threads.
- [x] **Automation Logic**
    - [x] Tạo `app/services/threads_news.py` cho core logic.
    - [x] Fix cooldown query: chỉ đếm `job_type="post"`, bỏ qua verify jobs.
    - [x] Fix account selection: dynamic `platform LIKE "%threads%"` thay vì hardcode `facebook_3`.
- [x] **Settings UI (Remove Hardcode)**
    - [x] `THREADS_AUTO_MODE` — bật/tắt auto
    - [x] `THREADS_POST_INTERVAL_MIN` — cooldown giữa 2 bài
    - [x] `THREADS_SCRAPE_CYCLE_MIN` — chu kỳ quét tin mới
    - [x] `THREADS_MAX_CHARS_PER_SEGMENT` — ký tự mỗi bài
    - [x] `THREADS_MAX_CAPTION_LENGTH` — ký tự tối đa caption
    - [x] `THREADS_AI_PROMPT` — prompt AI tùy chỉnh (hỗ trợ `{title}`, `{summary}`, `{source_name}`, `{max_chars}`)
- [/] **Verification**
    - [x] Test scrape -> AI write -> Draft job (Successfully tested with fallback).
    - [x] Test login Threads trên profile.
    - [x] Fix production bugs (null schema, cooldown, account selection).
    - [ ] Test đăng bài thật trên Threads (end-to-end production).

## Done (2026-04-26 Session)
- [x] Fixed AI Caption Pipeline: Pydantic schema + JSON validation cho null values.
- [x] Fixed Threads auto-posting: cooldown miscounting + hardcoded account.
- [x] Moved 6 hardcoded values to Settings UI (section "Threads Auto").
- [x] Updated `threads_news_worker.py` sleep cycle to read from Settings.
- [x] All changes committed and pushed to `develop` branch.

## Remaining
- [x] End-to-end production test: VPS deploy → scrape → AI generate → create job → publish to Threads.
- [x] Monitor `pm2 logs Threads_NewsWorker` after deploy for stability.

## Closure (2026-04-29)
- Status: **Done — fulfilled by later PLANs**.
- End-to-end production test was delivered by PLAN-029 + PLAN-030 + PLAN-031 (all archived). Live VPS proof: job `613` (account Nguyen Ngoc Vi, profile `facebook_2`) and job `790` (account `senhora_consumista`) — see `agents/handoffs/current-status.md`.
- Worker for Threads news scrape + publish has been running on VPS since commit `e96a51d`.
- Archived from `agents/tasks/` root → `agents/tasks/archive/`.
