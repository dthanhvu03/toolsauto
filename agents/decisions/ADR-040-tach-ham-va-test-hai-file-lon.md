# ADR-040 — Tách hàm 770 dòng, và test cho hai file lớn nhất chưa có test

- **Ngày**: 2026-09-10
- **Trạng thái**: **ĐÃ DUYỆT** — Owner: *"triển khai cho xong đi em"*
- **Liên quan**: ADR-039 (ruff — mục "ngoài phạm vi" hẹn đúng hai việc này), ADR-020 (mỗi Page
  một niche), ADR-038 (bảy lỗi code-review)

## Bối cảnh

ADR-039 đo được ba con số và **cố ý để lại**:

| Chỉ số | Trước | Sau ADR này |
|---|---|---|
| Hàm dài nhất trong luồng viral | **770 dòng** | **660 dòng** |
| `app/core/account.py` (936 dòng) | **0 test** | **52 test** |
| `app/core/config_service.py` (1041 dòng) | **0 test** | **28 test** |
| Toàn suite | 816 | **914** |

Lý do chọn đúng hai file này: `account.py` quyết định **video đi vào Page nào**, còn
`overview_warnings_api` trong `config_service.py` quyết định **băng cảnh báo đỏ/vàng ở trang
Tổng quan** — tức thứ Owner nhìn để tin hệ thống đang ổn. Cả hai ngồi giữa mọi luồng mà không
ai canh.

## Quyết định 1 — tách `_process_viral_materials`, tách CÓ CHỌN

Hàm 770 dòng, trong đó một vòng `for mat in materials:` dài 570 dòng chứa **12 lệnh
`continue`**. `continue` là lý do không thể "đập hết ra": khối nào điều khiển vòng lặp thì tách
ra là đổi hành vi.

Nên chỉ tách **hai khối có `continue` = 0**:

| Hàm mới | Việc |
|---|---|
| `_finish_ready_material` | Nhánh READY khi không có account: caption tự động → chép Drive → báo Telegram |
| `_caption_metadata_for` | Dựng chuỗi `[AI_GENERATE] …`, bóc marker `BOOST_CONTEXT` khỏi tiêu đề |
| `_resolve_target_page` | Chọn Page đích: chia đều hay chấm điểm từ khoá (ADR-020) |

Ở nhánh READY, lệnh `continue` **ở lại chỗ gọi** — hàm tách ra không điều khiển vòng lặp, và
có chú thích nói rõ điều đó để lần sau không ai gộp nốt vào.

Hai chi tiết suýt làm hỏng khi tách, giữ lại làm ghi chú:

1. **Hai regex BOOST_CONTEXT không phải một.** Bản để *đọc* có nhóm bắt; bản để *xoá* ăn luôn
   khoảng trắng hai bên. Gộp làm một là tiêu đề còn hai dấu cách dính nhau ở giữa.
2. `import random` / `import re as _re` nằm giữa thân vòng lặp — đưa lên đầu file theo
   `RULES.md`.

## Quyết định 2 — hai lỗi thật do việc viết test lôi ra

Cả hai cùng một gốc: `set()` dùng cho danh sách Page, mà **setter `target_pages_list` lấy phần
tử ĐẦU làm `target_page` — tức Page chính**.

| Chỗ | Hậu quả |
|---|---|
| `delete_page_config` | Xoá **một Page phụ** ⇒ danh sách xáo ⇒ **Page chính đổi** |
| `update_page_config` | Chỉ **lưu niche của một Page bất kỳ** ⇒ cũng xáo cả danh sách |

Vì sao nguy: `_resolve_target_page` khoá video generic về `acc_pages[0]` khi không khớp từ
khoá. Page chính đổi nghĩa là **video đi sang Page khác niche, không có lỗi nào báo** — đúng họ
"nhãn nói dối".

**Chứng minh, chạy trên code chưa vá:**

```
4 Page: [mecauca, tet, phu, x]   →  xoá "tet"
kết quả cũ: ['x', 'phu', 'mecauca']   ← Page chính hoá ra "x"
kết quả sau khi vá: ['mecauca', 'phu', 'x']
```

Test 3 Page viết lần đầu **qua được** — do may. `set` chuỗi còn đổi thứ tự theo từng lần chạy
(hash ngẫu nhiên mỗi tiến trình), nên test đó vô giá trị. Phải chọn đúng bộ bốn URL tái hiện
được rồi mới vá.

Bản vá cũng tránh một bẫy ngược: **Page đã có thì giữ nguyên chỗ**, không gỡ-ra-thêm-lại —
làm vậy là đẩy Page chính xuống cuối mỗi lần Owner lưu chính nó.

## Ghi lại, KHÔNG vá ở ADR này

`normalize_tiktok_source_url("https://vt.tiktok.com/ZS8Kx/")` trả
`https://www.tiktok.com/@ZS8Kx` — link rút gọn, đuôi là mã chuyển hướng chứ không phải tên
kênh. Vá đúng phải gọi mạng để giải link; việc riêng, quyết định riêng. Đã khoá bằng test ghi
rõ *"hành vi hiện tại — sai, đã biết"* để không ai tưởng là đúng.

Chữ trong `overview_warnings_api` **không dấu** (*"Khong co preset active"*) — trái quy ước
chữ trên web phải có dấu. Test khẳng định theo **cấu trúc** (mức độ, chỗ dẫn tới, ngưỡng) chứ
không bám câu chữ, nên sửa lại chữ sau không phải sửa test. Chưa sửa vì đây là chữ Owner nhìn
thấy — đổi thì Owner chốt.

## Phạm vi

| Việc | File |
|---|---|
| Tách 3 hàm, dời import lên đầu | `app/features/viral_intake/processor.py` |
| Giữ thứ tự Page (2 chỗ) | `app/core/account.py` |
| Test mới | `tests/test_processor_page_routing.py` (18), `tests/test_account_service.py` (52), `tests/test_overview_warnings.py` (28) |

## Ngoài phạm vi

- **Chưa tách `publish` 765 dòng** trong `facebook/adapter.py` — nay là hàm dài nhất repo. Nó
  đụng Playwright thật, không có test nào phủ; tách mù là liều.
- Bốn khối còn lại trong `_process_viral_materials` (preflight, tải, kết quả reup) đều **có
  `continue`** — cần thiết kế lại cách báo lỗi trước, không phải cắt dán.
- Phần `start_login` / `confirm_login` của `account.py` cần Playwright thật — chưa test.
- `tests/test_threads_world_news.py` vẫn đang bị `--ignore` ở CI (hỏng từ 2026-05-03 vì
  `app.services.ai_runtime` đã bị xoá hẳn). Chưa quyết số phận.

## Hết hiệu lực

Proof: `ruff check .` sạch · `lint-imports` 2 hợp đồng giữ · **914 passed, 16 skipped, 0
failed** (trước: 816) · hai test lỗi thứ tự Page đã chạy trên code chưa vá và **đỏ đúng chỗ**.
