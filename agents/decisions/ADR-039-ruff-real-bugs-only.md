# ADR-039 — ruff: bật luật bắt lỗi thật, cố ý KHÔNG đụng định dạng

- **Ngày**: 2026-09-10
- **Trạng thái**: **ĐÃ DUYỆT** — Owner hỏi code có scale/maintain/clean/theo quy chuẩn không,
  rồi giao *"triển khai vá đi em"*
- **Liên quan**: ADR-007 (ranh giới module), ADR-038 (bảy lỗi do code-review bắt)

## Bối cảnh — đo trước

| Chỉ số | Giá trị |
|---|---|
| Mã nguồn `app/` | **198 file · 48.813 dòng** |
| Test | 56 file · 12.306 dòng (**816 test xanh**) |
| Hàm > 100 dòng | **52** |
| Hàm > 200 dòng | **14** (dài nhất **770 dòng**) |
| File không được test nào nhắc tới | **70/198 (35%)** |
| Linter / formatter / type-checker | **KHÔNG CÓ CÁI NÀO** |

Dự án có ADR (34 cái), `RULES.md`, import-linter chạy ở CI, CI chạy test mỗi push — **luật
kiến trúc thì có người canh, luật viết code thì không ai canh**.

## Quyết định

1. **Bật `ruff` chỉ với `F` (pyflakes) và `E9`.** Đây là những luật mà vi phạm nghĩa là **chạy
   sai**: gọi tên không tồn tại, import chết, gán rồi không dùng, lỗi cú pháp.
2. **CỐ Ý không bật luật định dạng, không chạy `ruff format`.** Bật lên là một diff gần như
   toàn bộ 48.813 dòng — **không đổi hành vi một dòng nào**, mà xoá sạch `git blame` và nhấn
   chìm mọi review sau. Cái giá đó không đáng.
   Kết quả: diff của ADR này là **52 file, +62/−97** — nhỏ, đọc được, toàn nội dung thật.
3. **`scripts/archive/` nằm ngoài phạm vi** — script đã cho vào kho lưu, có file còn lỗi cú
   pháp từ lâu. Bắt lỗi ở đó chỉ tạo tiếng ồn vì không ai sửa.
4. **`ruff check .` chạy trong CI**, trước bước test. Vi phạm mới làm CI đỏ.
5. **Thêm luật thì thêm từng nhóm, vá sạch rồi mới commit.** Đừng bật cả loạt rồi rải `noqa` —
   `noqa` rải khắp nơi chính là cách một bộ luật chết.

## Bảy lỗi thật ruff bắt được ngay lượt chạy đầu

**Năm `NameError`** — tất cả nằm im vì bị `except` nuốt, nên chưa ai thấy:

| Chỗ | Hậu quả |
|---|---|
| `facebook/adapter.py:695` `SessionLocal` chưa import | Nằm trong `try/except` ⇒ **chưa bao giờ tải được account**, chỉ ghi log "Could not load job account" mãi |
| `facebook/adapter.py:2499-2501` `al_lower` **chưa từng tồn tại** | Vòng lặp có `except: continue` ⇒ **mọi ứng viên bị bỏ qua** ⇒ hàm chuyển Page bằng aria-label luôn trả `False` |
| `threads/workers/publisher.py:161` gọi hàm chưa import | Hàm nằm ở `app.core.settings`, file đã import sẵn thành `runtime_settings` |

Riêng `al_lower`: bản vá dùng `al.lower()` **chứ không phải** `al_norm` — vì
`_normalize_fb_text` **bỏ dấu** (`chuyển` → `chuyen`) trong khi ba chuỗi so sánh có dấu.

**Hai khai báo `global` thiếu tên** trong `ai_generator.py` — nghiêm trọng hơn cả:

| Hàm | Thiếu | Hậu quả |
|---|---|---|
| `process_draft_job` (dòng 204) | `GEMINI_CIRCUIT_RESET_TIME` | Gán vào biến **cục bộ** ⇒ mốc hết hạn toàn cục giữ nguyên `0` ⇒ `time.time() >= 0` luôn đúng ⇒ **ngắt mạch vừa mở đã đóng lại ở vòng sau** |
| `run_loop` (dòng 664) | `GEMINI_CONSECUTIVE_FAILURES` | Bộ đếm lỗi **không bao giờ reset** |

Tức tin Telegram báo *"🛑 Circuit breaker: tạm ngưng 30 phút"* **chưa bao giờ đúng** — worker
vẫn nện Gemini liên tục sau khi cookie hỏng. Lại đúng họ "nhãn nói dối" của cả tuần.

Ba biến thừa còn lại vô hại, đã dọn. Riêng `a2` trong `test_cross_account_media_guard.py`:
tài khoản thứ hai **phải tồn tại** cho tiền đề của test — bỏ cái tên biến, **giữ lời gọi**.

## Phạm vi

| Việc | File |
|---|---|
| Cấu hình | `ruff.toml` (mới) |
| Chạy ở CI | `.github/workflows/deploy.yml` |
| Ghim phiên bản | `requirements.txt` |
| 5 `NameError` + 2 `global` thiếu | `facebook/adapter.py`, `threads/workers/publisher.py`, `viral_intake/workers/ai_generator.py` |
| 97 chỗ tự vá (import chết, f-string rỗng, biến thừa) | 52 file |

## Ngoài phạm vi

- **Không chạy `ruff format`** (lý do ở mục 2).
- Không bật `mypy` — thêm chú thích kiểu cho 48k dòng là việc khác hẳn.
- **Không tách hàm 770 dòng** — việc riêng, rủi ro riêng, cần đầu óc tỉnh táo.
- Không viết test cho 70 file đang trống.

## Hết hiệu lực

Sau proof: `ruff check .` sạch; `import app.main` chạy; 26 bảng model vẫn đăng ký đủ sau khi
xoá 97 import; **816 test xanh**; `lint-imports` 2 hợp đồng giữ.
