# ADR-025 — Tách "Nguồn video" thành trang riêng `/app/viral/sources`

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT + ĐÃ THỰC THI** — Owner chọn phương án B ngày 2026-09-09 sau
  khi được nêu rằng B đụng backend, cần ADR mới, và làm vỡ ý "một trang cho luồng viral"
  của ADR-019; sau đó yêu cầu review nhiều góc rồi triển khai. Proof ở cuối file.
- **Liên quan**: **ADR-019 mục 5 (ADR này thay thế đúng mục đó)**, ADR-020 mục 6 (ô nhiều
  Page — giữ nguyên), ADR-022 (gọn UI màn hẹp — phần nhớ đóng/mở khối sẽ bị bỏ)

## Bối cảnh

ADR-019 mục 5 đặt khối "Nguồn tự động" làm `<details>` gấp/mở **bên trong** `/app/viral`.
Mục sidebar **"Nguồn video"** vì thế không phải trang, chỉ là link neo
`/app/viral#viral-sources-panel` (`layouts/app.html:172`, commit `b449d8c` — commit đó ghi
rõ "mở sẵn khối Nguồn tự động").

Sau đó ADR-022 (`b1fa630`) đổi mặc định khối thành **đóng khi màn < 1280px**, và script
nhớ trạng thái ở `app_viral.html:216-231` **không đọc `location.hash`**. Hai thay đổi này
không được ghép lại với nhau, nên trên khung UltraViewer Owner đang dùng:

> Bấm "Nguồn video" ở sidebar → nhảy vào `/app/viral` với khối **đóng kín** → nhìn như một
> mục menu chết.

Sửa vá (ép mở khi có hash) chữa được triệu chứng nhưng giữ nguyên cái gốc: **một mục
điều hướng cấp một trỏ vào một khối gấp trong trang khác**. Trạng thái hiển thị của nó phụ
thuộc `localStorage` của từng máy — không tất định, và không sửa được từ phía server.

## Quyết định

1. **Trang riêng** `GET /app/viral/sources` — wrapper mỏng trong
   `app/platform/dashboard_shell/router.py`, đặt ngay cạnh `/app/viral/table`. Chỉ
   `TemplateResponse`. Đây là phần backend duy nhất của ADR này.
   **Không chép nguyên khuôn `app_viral` (`router.py:83`)**: hàm đó nhận
   `db: Session = Depends(get_db)` rồi **không dùng** — mở một session DB mỗi lần vào trang
   cho không. Route mới **không nhận `db`**. (Không sửa `app_viral` cũ trong ADR này —
   ngoài phạm vi, ghi lại thành nợ.)
   Docstring hai chiều bắt buộc: `/app/viral/sources` (trang, dashboard_shell) và
   `/viral/sources` (fragment htmx, viral_intake) chỉ khác bốn ký tự — mỗi hàm phải trỏ
   sang hàm kia, nếu không phiên sau sẽ sửa nhầm file.
2. **Không đụng bất kỳ endpoint `/viral/sources*` nào** — `list_sources`, `add_source`,
   `toggle`, `delete`, `scan`, `scan-all` trong `features/viral_intake/router.py` giữ
   nguyên chữ ký, nguyên hành vi, nguyên `htmx_toast_response`. Fragment
   `fragments/viral_sources.html` cũng giữ nguyên. ⇒ **`tests/test_viral_sources_ui.py`
   (17 test) không phải sửa một dòng nào** — đã kiểm: file đó chỉ chạm fragment và các
   endpoint POST, không hề tham chiếu `#viral-sources-panel`.
3. **Thống nhất tên gọi: "Nguồn video".** Hiện sidebar ghi "Nguồn video" còn khối trong
   trang ghi "Nguồn tự động" — đang là khối gấp thì không ai để ý, thành trang riêng thì
   bấm một đằng ra tiêu đề một nẻo. Trang mới dùng `page_title` **"Nguồn video"**,
   `silo_breadcrumb('Facebook', 'Nguồn video')`, và `page_subtitle` mang phần giải thích cũ
   ("Kênh TikTok / YouTube Shorts, tự quét mỗi giờ"). Nav giữ nguyên chữ "Nguồn video".
4. **Trang mới `pages/app_viral_sources.html`** nhận nguyên xi phần thân của `<details>`
   hiện tại — form thêm nguồn (kèm ô nhiều Page + cảnh báo spam của ADR-020 mục 6), hai
   dòng chú thích, và `div#viral-sources` với `hx-get="/viral/sources"`. Bỏ vỏ `<details>`,
   bỏ luôn script `viral.sourcesPanelOpen`: trang mở ra là thấy, không còn trạng thái nhớ
   theo máy.
5. **`/app/viral` chỉ còn luồng video** — gỡ khối `<details>` và script kèm theo; thay bằng
   một link "Nguồn tự động →" trong dòng liên kết chân khối (chỗ đang có
   *Tài khoản → Target Pages · Nguồn TikTok · Hàng đợi*), để người đang xem bảng video vẫn
   đi tới nguồn được một nhịp (mục 5 này là thứ giữ cho việc tách trang không làm mất dấu
   luồng — bỏ nó đi thì ADR này thành một mục menu cụt).
6. **Sửa trạng thái active của sidebar**: `p.startswith('/app/viral')` hiện sẽ tô sáng
   **cả hai** mục khi ở trang mới. Đổi "Nội dung viral" sang điều kiện loại trừ
   `/app/viral/sources`, và "Nguồn video" sang `p.startswith('/app/viral/sources')`.
   Không sửa chỗ này thì trang mới trông như đang ở trang cũ.
7. **Dọn hết link neo cũ**: `layouts/app.html:172` và `app_tiktok_links.html:14` trỏ thẳng
   `/app/viral/sources`. Không để `#viral-sources-panel` sót lại ở đâu — id đó biến mất.

## Phạm vi

| Việc | File |
|---|---|
| Route trang (~5 dòng, không query DB) | `app/platform/dashboard_shell/router.py` |
| Trang mới | `app/templates/pages/app_viral_sources.html` (mới) |
| Gỡ `<details>` + script nhớ trạng thái | `app/templates/pages/app_viral.html` |
| Nav href + trạng thái active | `app/templates/layouts/app.html` |
| Link chéo | `app/templates/pages/app_tiktok_links.html` |
| Test | `tests/test_viral_sources_page.py` (mới) |

**Ghi chú luật**: 5 file cho một việc — vượt ngưỡng "3 file/1 bug" của `RULES.md`. Ngưỡng
đó dành cho **sửa bug**; đây là thay đổi điều hướng có ADR, và 5 file là **số tối thiểu** để
không bỏ sót link chết. Ghi ra đây để phiên sau không tưởng là sơ suất.

## Ngoài phạm vi

- Không đổi `SourceService`, `scan_source`, `scan_all`, lịch quét mỗi giờ.
- Không đổi schema `viral_sources`, không migration.
- Không đổi ô "Page đích" nhiều dòng và cảnh báo spam (ADR-020 mục 6) — bê nguyên.
- Không gộp `/app/tiktok-links` (Kho kênh cũ) vào trang mới.
- Không đụng `maintenance.py` hay hook `viral.scan_sources`.
- Không sửa `Depends(get_db)` thừa của `app_viral` cũ (nợ đã ghi ở mục 1).

## Rủi ro đã cân

- **Một luồng thành hai trang**: thêm một cú bấm cho người vừa thêm nguồn vừa xem kết quả.
  Chấp nhận được vì thêm nguồn là việc làm một lần rồi thôi, còn xem bảng video là việc
  hằng ngày — trang `/app/viral` gọn hẳn đúng theo tinh thần ADR-022.
- **Bookmark cũ** `/app/viral#viral-sources-panel` vẫn mở được `/app/viral`, chỉ là không
  còn khối nguồn. Không cần redirect; đổi lại có link ở mục 4.

## Hết hiệu lực

Sau proof: `/app/viral/sources` trả 200 và render bảng nguồn thật; thêm/bật/tắt/xoá/quét
một nguồn từ trang mới chạy đúng như trước; sidebar tô sáng đúng một mục ở mỗi trang;
`grep -r "viral-sources-panel"` không còn kết quả; tiêu đề trang khớp chữ trên sidebar; `tests/test_viral_sources_ui.py` xanh
mà không sửa gì.


## Proof (2026-09-09)

Review nhiều góc trước khi gõ code đã sửa ba lỗ trong bản thảo đầu: bỏ `Depends(get_db)`
thừa, thêm vỏ trang + thống nhất tên gọi, ghi cảnh báo hai URL na ná nhau (mục 1 và 3).

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| `/app/viral/sources` trả 200, render đúng form + bảng nguồn | `test_page_serves_and_keeps_the_same_source_endpoints` |
| Endpoint `/viral/sources*` không đổi | `hx-post="/viral/sources/add"`, `/scan-all`, `hx-get="/viral/sources"` còn nguyên trên trang mới |
| Tiêu đề trang khớp chữ trên sidebar | `test_page_title_matches_the_sidebar_wording` — có "Nguồn video", không còn "Nguồn tự động" |
| Ô nhiều Page + cảnh báo spam (ADR-020 mục 6) theo sang | `test_page_keeps_multi_page_field_and_spam_warning` |
| Route không mở session DB | `test_page_route_opens_no_db_session` (soi `inspect.signature`) |
| `/app/viral` sạch khối nguồn | `test_viral_page_no_longer_carries_the_sources_panel` — không còn `viral-sources-panel`, `sourcesPanelOpen`, `<details` |
| Luồng không đứt đoạn | `test_viral_page_still_links_to_the_sources_page` |
| Không còn link neo chết | `test_no_dead_anchor_left_anywhere` (`layouts/app.html`, `app_tiktok_links.html`) |
| Sidebar sáng đúng một mục mỗi trang | `test_sidebar_highlights_only_the_*` — `/app/viral/sources` → chỉ `/app/viral/sources`; `/app/viral` → chỉ `/app/viral` |
| `tests/test_viral_sources_ui.py` xanh mà không sửa gì | **17 test xanh**, file không đổi một dòng |

`tests/test_viral_sources_page.py` (10 test) + `test_viral_sources_ui.py`,
`test_duplicate_ui.py`, `test_viral_router_background.py` (59 test): **69 xanh**.

Toàn bộ suite (`layouts/app.html` là layout dùng chung nên phải chạy hết):
**582 passed, 16 skipped, 0 failed**. Bỏ qua `tests/test_threads_world_news.py` — file đó
lỗi collection (`No module named 'app.services'`) từ commit `8326183` (refactor
`app/services` → `app/features/threads/service/`), **không liên quan ADR này**; đây là nợ
sẵn có, ghi lại để ai đó dọn.

Hệ quả sang việc khác: mục **Next Action #1** của phiên 2026-09-08 (c) — *"Owner mở
`/app/viral` đóng khối Nguồn tự động một lần cho máy nhớ"* — **thành thừa**, khối đó không
còn. Cơ chế `localStorage 'viral.sourcesPanelOpen'` bị gỡ hẳn, không còn trạng thái UI phụ
thuộc từng máy ở trang này.
