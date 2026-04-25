# TASK-017: Threads News Automation Integration

## Status
- **Status:** In Progress
- **Priority:** High
- **Owner:** Antigravity (AI Agent)
- **Created:** 2026-04-25

## Context
Tích hợp kênh Threads (tài khoản Hoang Khoa) vào hệ thống Auto Publisher. Mục tiêu là tự động lấy tin tức từ RSS/Web, dùng AI viết lại theo style của kênh (tin nóng, tiêu đề viết hoa, emoji cờ) và đăng tự động hằng ngày.

## Requirements
1. **News Scraper**: Lấy tin từ VnExpress, Tuổi Trẻ RSS.
2. **AI Style**: Viết tiêu đề VIẾT HOA, dùng emoji cờ quốc gia (🇺🇸🇮🇷🇻🇳), ngắn gọn, tone drama.
3. **Approval Flow**: Hỗ trợ 2 chế độ: Duyệt tay (DRAFT) và Tự động (PENDING).
4. **Control Toggle**: Có nút bật/tắt chế độ tự động hằng ngày.
5. **GenericAdapter Integration**: Sử dụng GenericAdapter để đăng bài lên Threads.

## Todo List
- [x] **Database Setup**
    - [x] Thêm bảng `news_articles` vào `app/database/models.py`.
    - [x] Thêm setting `THREADS_AUTO_MODE` vào `RuntimeSetting`.
- [x] **News Ingestion**
    - [x] Tạo `app/services/news_scraper.py` để lấy tin RSS.
    - [ ] Tích hợp vào Maintenance worker để scrape định kỳ.
- [/] **AI Orchestration**
    - [x] Phân tích style `us28qt` và define prompt.
    - [ ] Cập nhật `app/services/content_orchestrator.py` với method chính thức.
    - [ ] Cập nhật `workers/ai_generator.py` để xử lý nguồn tin tức.
- [x] **Threads UI Configuration**
    - [x] Seed `platform_configs` cho Threads.
    - [x] Seed `workflow_definitions` cho Threads:POST.
    - [x] Seed `platform_selectors` cho các nút bấm trên Threads.
- [x] **Automation Logic**
    - [x] Tạo `app/services/threads_news.py` cho core logic.
    - [ ] Cập nhật `app/services/strategic.py` để trigger định kỳ.
- [/] **Verification**
    - [x] Test scrape -> AI write -> Draft job (Successfully tested with fallback).
    - [x] Test login Threads trên profile Hoang Khoa.
    - [ ] Test đăng bài thật (sau khi anh duyệt).

## Done
- [x] Phân tích nội dung profile Threads `us28qt`.
- [x] Đăng nhập thành công Threads trên profile Hoang Khoa (local).
- [x] Lên Implementation Plan và được anh duyệt.
- [x] Thiết kế UI Control Panel cho Threads News trong Overview.
- [x] Triển khai router `/threads` và API điều khiển.
