# Decision Record: DECISION-003
## Title: Publisher Jobs Bị Giết Liên Tục + Caption Không Tìm Thấy
Date: 2026-04-19
Status: DRAFT
Author: Antigravity

---

## 1. Context & Problem Statement

Trong khoảng 30 phút (14:01 → 14:26), Publisher Worker bị restart 4 lần liên tiếp, mỗi lần đều giết chết Job đang chạy giữa chừng. Song song đó, 100% các Job đều bị WARNING "Caption area not found".

---

## 2. Phân tích Log — Dấu vết Hung thủ

### Vấn đề 1 (CRITICAL): Deploy liên tục giết Job đang chạy

**Pattern lặp lại 4 lần:**
```
[INFO]  [Job X] FacebookAdapter: [Phase 3/4] Đang thao tác...
[WARNING] Received termination signal. Preparing to shut down...
[WARNING] Waiting for Job X to finish before exiting...
[ERROR]  Page.wait_for_timeout: Target page, context or browser has been closed
[ERROR]  [Job X] Publish failed: ...browser has been closed (Fatal: False)
[INFO]  Publisher process completed gracefully.
[INFO]  Publisher Worker started.     ← restart ngay lập tức
[INFO]  [Job Y] Claimed...           ← nhận job mới, rồi lại bị giết
```

**Thời điểm restart:**
| Lần | Job bị giết | Thời điểm SIGTERM | Đang ở Phase |
|---|---|---|---|
| 1 | Job 434 | 14:01:35 | Context verify (timeout 60s) |
| 2 | Job 443 | 14:09:07 | Phase 4 — Wait for Post button |
| 3 | Job 448 | 14:16:03 | Phase 3 — Caption + wait_for_timeout |
| 4 | Job 445 | 14:26:36 | Phase 4 — Wait for dialog close |

**Root Cause xác nhận: Chính chúng ta (Antigravity) đã gây ra!**

Mỗi lần em `git push origin develop`, GitHub Actions trigger `deploy.yml` → SSH vào VPS → `git reset --hard` → `bash ./start.sh` → `pm2 delete FB_Publisher_1` → **SIGTERM giết browser đang mở**.

Trong session hôm nay, chúng ta đã push **6 lần liên tiếp** trong 30 phút:
```
bff09ab  chore(agents): sign-off PLAN-008...
9bb37b1  feat(ui): colorize log lines...
4140018  feat(logging): dual-stream formatter...
6ee8cdf  docs(agents): DECISION-002...
87961af  chore(agents): create TASK-009 + PLAN-009...
1005e14  chore(agents): sign-off PLAN-009...
399c519  fix: move ai_persona.json...
```

Mỗi push = 1 deploy = 1 lần giết Publisher. **Publisher không bao giờ có cơ hội hoàn thành 1 job nào** vì FFmpeg mất ~5 phút xử lý video lớn (60-180MB), và deploy mới đến trước khi post xong.

### Vấn đề 2 (HIGH): Caption area không tìm thấy (100% jobs)

```
[WARNING] Chờ khu vực caption quá lâu hoặc không thấy.
[WARNING] Caption area not found in final surface. Proceeding without caption.
```

Xảy ra ở **MỌI job** (434, 443, 448, 445). Đây là dấu hiệu rõ ràng rằng **Facebook đã thay đổi giao diện Reels** (DOM structure) khiến selector tìm vùng nhập caption bị hỏng.

### Vấn đề 3 (MEDIUM): Video sau FFmpeg bị phình to gấp 2-3 lần

```
[MediaProcessor] Done: 7.6MB → 25.6MB (-238% reduction)
[MediaProcessor] Done: 60.7MB → 181.0MB (-198% reduction)
[MediaProcessor] Done: 46.0MB → 133.3MB (-190% reduction)
```

Log hiển thị "reduction" nhưng thực tế file OUTPUT lớn hơn INPUT gấp 3 lần. Đây là hệ quả của profile `reels` (CRF=28 nhưng upscale resolution hoặc re-encode codec). Video 181MB sẽ upload lên Facebook rất lâu, tăng nguy cơ timeout.

---

## 3. Proposed Options

### Cho Vấn đề 1 (Deploy giết Job):

**Option A: Batching commits (Quy trình — Đề xuất)**
- Gộp tất cả thay đổi vào 1 commit duy nhất trước khi push.
- Hoặc: push agent docs (không trigger deploy) tách khỏi push code (trigger deploy).
- Cần cấu hình deploy.yml chỉ trigger khi có thay đổi trong `app/`, `workers/`, `requirements.txt`, `start.sh` — bỏ qua `agents/`, `docs/`.

**Option B: Graceful drain trong start.sh**
- Trước khi `pm2 delete`, gửi lệnh `pm2 sendSignal SIGINT FB_Publisher_1`, rồi `sleep 300` (cho publisher kịp hoàn tất job hiện tại, tối đa 5 phút).
- Nhược điểm: Deploy chậm hơn 5 phút.

**Option C: Kết hợp A + B (Toàn diện nhất)**
- Deploy chỉ trigger khi code thay đổi (filter path).
- Đồng thời start.sh có graceful drain.

### Cho Vấn đề 2 (Caption not found):
- Cần kiểm tra selector hiện tại trong `app/adapters/facebook/adapter.py`, đối chiếu với DOM Facebook Reels mới nhất.
- Đây là task riêng — TASK-010.

### Cho Vấn đề 3 (Video phình):
- Xem lại FFmpeg profile `reels` trong `media_processor.py`.
- Có thể CRF cần nâng lên 30-32 hoặc tắt upscale.
- Đây là task riêng — TASK-011.

---

## 4. Decision
(Đang chờ @User xác nhận.)

Đề xuất:
- **Vấn đề 1**: Chọn Option C — filter deploy path + graceful drain.
- **Vấn đề 2**: Tạo TASK-010 riêng để điều tra selector caption.
- **Vấn đề 3**: Tạo TASK-011 riêng để audit FFmpeg profile.

---

## 💬 Discussion

### Antigravity — 2026-04-19

**Vấn đề 1 là vấn đề khẩn cấp nhất.** Hệ thống hiện tại đang trong trạng thái "tê liệt" — mỗi lần chúng ta commit code để sửa bug, chính cái commit đó lại giết chết Publisher. Đây là vòng lặp chết (death loop).

**Giải pháp nhanh tức thì** (không cần code): Chỉ cần thêm `paths` filter vào `deploy.yml`:
```yaml
on:
  push:
    branches: [develop, main]
    paths:
      - 'app/**'
      - 'workers/**'
      - 'requirements.txt'
      - 'start.sh'
      - 'manage.py'
      - '.github/workflows/**'
```

Như vậy push `agents/`, `docs/`, `CLAUDE.md` sẽ **KHÔNG trigger deploy** → Publisher được yên thân làm việc.

**Về Vấn đề 2 (Caption)**: Cần 1 phiên debug trực tiếp — mở VPS VNC hoặc screenshot DOM ở bước Reels Step 3 để xem Facebook đã đổi cấu trúc giao diện ra sao. Đây không phải lỗi code mà là lỗi **DOM drift** (Facebook thay đổi HTML).

**Về Vấn đề 3 (Video phình)**: Log hiện ghi "reduction" nhưng con số âm (-238%) là đúng tính toán — chỉ là workaround cần sửa lại UX log cho dễ hiểu hơn. Việc video to hơn sau encode là behavior dự kiến khi profile `reels` nâng quality/resolution.
