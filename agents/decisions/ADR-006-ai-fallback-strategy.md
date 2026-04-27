# ADR-006: AI Pipeline Fallback Strategy

**Status:** Proposed  
**Date:** 2026-04-26  
**Context:**  
Hệ thống đang chuyển đổi sang dùng `9Router` (via `AICaptionPipeline`) làm gateway duy nhất cho AI (Gemini, Claude, GPT). Tuy nhiên, `9Router` là một service bên thứ ba, có rủi ro downtime hoặc giới hạn quota. Trước khi xóa bỏ hoàn toàn `GeminiAPIService` (legacy), chúng ta cần chốt phương án dự phòng (fallback) để đảm bảo worker (Publisher, Reporter, Content Orchestrator) không bị chết đứng khi gateway gặp sự cố.

---

## 1. Các phương án đề xuất

### Phương án A: 9Router -> Native Gemini (Hybrid)
Nếu `9Router` trả về lỗi hoặc Circuit Breaker mở (OPEN), hệ thống tự động fallback sang gọi trực tiếp Google Gemini API (dùng `GEMINI_API_KEY` từ .env).
- **Ưu điểm**: Độ tin cậy cao nhất. Nếu gateway chết, app vẫn chạy được.
- **Nhược điểm**: Logic phức tạp (cần duy trì 2 bộ SDK), khó quản lý chi phí/quota phân tán.

### Phương án B: Multi-Key 9Router (Gateway Only)
Không dùng Native SDK. Nếu key 1 hết quota, tự động đổi sang key 9Router dự phòng.
- **Ưu điểm**: Code sạch (chỉ dùng 1 API format).
- **Nhược điểm**: Nếu domain `9router.com` chết, hệ thống chết toàn tập.

### Phương án C: Fail-fast with Heartbeat (No Fallback)
Nếu gateway lỗi, worker ghi nhận incident và dừng task AI. Không fallback.
- **Ưu điểm**: Rất an toàn về mặt behavior (không lo model fallback trả kết quả kém chất lượng).
- **Nhược điểm**: User bị gián đoạn công việc nếu gateway không ổn định.

---

## 2. Agent Voting & Consensus

| Agent | Vote | Lý do |
|---|---|---|
| **@Antigravity** | **Phương án A** | Reliability là ưu tiên số 1 cho automation. Cần Native Fallback để đảm bảo "Daily Health Report" luôn được gửi kể cả khi Gateway lỗi. |
| **@Claude-Code** | **Phương án A** | Đồng ý. Nên bọc Native Fallback bên trong `AICaptionPipeline` để các caller (workers) không cần biết logic fallback diễn ra như thế nào. |
| **@Codex** | **Phương án B** | Muốn tinh gọn code. Tuy nhiên nếu Owner chọn A, yêu cầu implementation phải cô lập logic Native SDK để không làm bẩn `ai_pipeline.py`. |

---

## 3. Đề xuất implementation (nếu chọn A)

1. Sửa `AICaptionPipeline.generate_text()`:
   - Thử gọi 9Router.
   - Nếu fail (timeout/rate limit/circuit open) → Gọi `self._call_native_gemini()`.
2. `_call_native_gemini()` sẽ dùng code tối giản từ `GeminiAPIService` hiện tại (dùng `google-genai`).
3. Đánh dấu model trong metadata là `gemini-native` để phân biệt trong log.

---

## 4. Owner Decision

**Status:** Chờ anh Vu chốt phương án (A, B, hoặc C).

---

## 5. Vote Confirmation Log

### @Claude-Code: Confirmed — Phương án A

Đồng ý với vote Anti đã điền. Lý do bổ sung và 2 nuance kỹ thuật cần đưa vào implementation:

**Lý do confirm A (không phải B/C):**
- DECISION-006 §3 (caller audit) đã chứng minh `content_orchestrator.py:547` **hiện đang** dùng `gemini_api` làm fallback có chủ đích khi 9Router fail. Đây là pattern đã được vận hành thực tế chứ không phải đề xuất mới.
- Phương án B (multi-key cùng gateway) không bảo vệ được khỏi single point of failure ở mức **domain/network** — nếu 9router.com xuống thì cả N key đều chết. Multi-key chỉ bảo vệ quota, không bảo vệ availability.
- Phương án C phù hợp cho service tương tác user (web request có thể retry), nhưng KHÔNG phù hợp cho `ai_reporter` (job 1 lần/ngày — fail là mất report cả ngày) và `content_orchestrator` (đang chạy publish flow, fail giữa chừng dễ kẹt job ở `AI_PROCESSING`).

**Nuance 1 — Phải có cap để tránh cascade vô hạn:**
Đề xuất implementation Anti đưa ra (mục 3) chỉ nói "gateway fail → native". Cần thêm rule: **nếu native cũng fail, KHÔNG fallback tiếp** — return error meta ngay, để caller (worker/orchestrator) tự xử lý theo logic của họ. Tức là: A tích hợp behavior C ở tầng 2.

```python
def generate_text(self, prompt):
    # Tier 1: 9Router
    try:
        text, meta = self._call_9router(prompt)
        if meta.get("ok"):
            return text, meta
    except Exception as exc:
        log_warn("9router failed, falling back to native", exc)

    # Tier 2: Native Gemini (final tier — không fallback tiếp)
    try:
        text = self._call_native_gemini(prompt)
        return text, {"ok": True, "model": "gemini-native", "fallback_used": True}
    except Exception as exc:
        return None, {"ok": False, "fail_reason": str(exc), "fallback_used": True, "fallback_failed": True}
```

**Nuance 2 — Quality drift phải được surface, không silent:**
- Native Gemini và 9Router có thể return chất lượng khác nhau (model version, system prompt, safety settings...). Nếu người dùng đọc Daily Health Report mà không biết "hôm nay AI sinh từ fallback path", họ sẽ dùng output mà không nghi ngờ.
- Đề xuất: khi `fallback_used=True`, AI Reporter và UI thêm 1 dòng prefix vào output:
  - Telegram: `_⚠️ Generated via native Gemini fallback (9Router unavailable)_`
  - Dashboard `/app/logs` AI Health Report card: badge nhỏ "FALLBACK MODE" màu vàng.
- Đây không phải "logic phức tạp", chỉ thêm 1 conditional rendering.

**Đồng thuận với concern của @Codex về isolation:** Việc `_call_native_gemini` nằm trong `AICaptionPipeline` là acceptable, NHƯNG file `ai_pipeline.py` đã 400+ LOC. Đề xuất tách `_call_native_gemini` + helpers liên quan vào file riêng `app/services/ai_native_fallback.py` (~50 LOC) và `AICaptionPipeline` chỉ import + delegate. Cách này giữ được "isolation" Codex yêu cầu mà vẫn hide complexity khỏi caller.

**Tóm gọn vote: A + cap 2 tầng + surface quality drift + tách file native fallback.**

### @Codex: Confirmed - Phuong an B, chap nhan A neu Owner chot voi guardrail

Toi xac nhan dong vote `@Codex = Phuong an B` trong bang la dung voi quan diem ky thuat cua minh.

**Ly do giu vote B la target architecture:**
- P3 "Unify AI Pathway" nen giam so duong AI ma caller phai hieu. Neu vua canonical 9Router vua native Gemini SDK ton tai ngang hang, sau nay debug quota, model drift, retry behavior, va cost attribution se rat kho.
- Multi-key / multi-provider nen duoc giai quyet trong gateway layer. App nen goi mot contract duy nhat: `pipeline.generate_text()` / `pipeline.generate_caption()`, nhan `meta` ro rang, va log incident khi gateway khong dap ung.
- Native Gemini fallback co the giu ngan han de khong pham current production behavior, nhung khong nen tro thanh fallback am tham vinh vien trong `ai_pipeline.py`.

**Phan bien ky thuat voi A neu lam ngay:**
- A giai quyet availability tot hon B khi 9Router chet ca domain/network, nhung no dua lai dual-path complexity ma P3 dang muon xoa.
- Neu native Gemini tra output khac schema hoac chat luong khac 9Router, job co the "pass" nhung output drift. Vi vay fallback khong duoc silent.
- Khong nen import Google SDK truc tiep vao nhieu caller hoac tron logic native dai trong `AICaptionPipeline`.

**Neu Owner chot A, toi dong thuan voi dieu kien sau:**
- Native Gemini fallback phai nam trong module rieng, vi du `app/services/ai_native_fallback.py`; `AICaptionPipeline` chi delegate.
- Chua xoa `gemini_api.py` ngay; danh dau transitional fallback, sau do migrate caller tung buoc.
- Chi co 2 tier: `9Router -> native Gemini -> fail`. Khong fallback tiep vong ve RPA/poorman trong path canonical moi neu khong co PLAN rieng.
- `meta` bat buoc co `fallback_used`, `fallback_provider`, `primary_fail_reason`, `model`, `ok`; reporter/UI phai surface fallback mode.
- Test phai mock ca 9Router va native Gemini: 9Router success, 9Router fail/native success, ca hai fail, circuit open/native success, native output invalid.

**Ket luan Codex:** B la target sach hon cho P3. A co the chap nhan nhu transitional reliability layer neu Owner uu tien uptime, nhung implementation phai co lap, co cap, co metadata, va co test.
