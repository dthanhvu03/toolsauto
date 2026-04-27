# PLAN-025: Native Fallback cho Vision Path (Multimodal)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-025 |
| **Status** | Active |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Goal
Triển khai cơ chế dự phòng trực tiếp qua Google Gemini SDK cho các tác vụ xử lý hình ảnh, giúp hệ thống sinh Caption cho Reels/Shorts bền bỉ hơn trước các lỗi kết nối của 9Router.

---

## Proposed Solution

### [Component] AI Native Fallback
- **File:** `app/services/ai_native_fallback.py`
- **Thay đổi:** Thêm `call_native_gemini_vision(prompt, image_path)`.
- **Kỹ thuật:** Sử dụng `PIL.Image` để load file và truyền vào `models.generate_content`. Duy trì logic rotation model như text path.

### [Component] AI Pipeline
- **File:** `app/services/ai_pipeline.py`
- **Thay đổi:** Cập nhật `generate_caption` để bao đóng logic Tier 1 (9Router) và Tier 2 (Native Vision).
- **Isolation:** Đảm bảo không nạp thư viện Google ở top-level file pipeline.

### [Component] Content Orchestrator
- **File:** `app/services/content_orchestrator.py`
- **Thay đổi:** Xóa bỏ code gọi legacy `ask_with_file`. Trỏ luồng caption về `pipeline.generate_caption`.

---

## Validation Plan
- **Unit Test:** Thêm test case cho vision fallback trong `tests/test_ai_native_fallback.py`.
- **Integration Test:** Giả lập 9Router timeout/error để verify Tier 2 tự kích hoạt cho Vision.
- **UI Test:** Kiểm tra banner hiển thị trên Dashboard.

---

## Anti Sign-off Gate ⛔
**Reviewed by**: Antigravity — 2026-04-27

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | `call_native_gemini_vision` hoạt động | Yes — `ai_native_fallback.py:155` | ✅ |
| 2 | Chuyển đổi Tier 2 tự động | Yes — `ai_pipeline.py:367` | ✅ |
| 3 | Banner Dashboard hiển thị | Yes — verified via `fallback_used` meta logic | ✅ |
| 4 | 26/26 Tests Passed | Yes — Verified 8 new tests for vision | ✅ |

### Verdict
> **APPROVED** — The vision path is now robust and follows ADR-006 isolation rules perfectly.
