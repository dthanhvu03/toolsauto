# ADR-026 — Sửa tại chỗ nguồn video (Min views / Max video / Page đích)

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-09: *"oke triển khai cho anh đi"*,
  sau khi báo rằng thêm sửa tại chỗ là đụng backend và cần ADR.
- **Liên quan**: **ADR-019 (bổ khuyết hợp đồng `SourceService`)**, ADR-020 (nhiều Page),
  ADR-025 (trang riêng `/app/viral/sources`)

## Bối cảnh

Owner đặt `Max video/lần = 3` cho nguồn `@thacaukechuyen`, quét mãi vẫn "Tìm thấy 0" — đúng
thiết kế (chỉ ngó 3 video mới nhất, cả 3 đã có trong kho). Muốn nâng lên 50 thì **không có
đường nào**: hợp đồng `SourceService` của ADR-019 mục 2 chỉ có `list_sources`, `add_source`,
`set_enabled`, `delete_source`, `scan_source`, `scan_all` — **không có `update`**. Bảng nguồn
vì thế chỉ cho Bật/Tắt, Quét, Xoá.

Cách duy nhất hiện nay là **Xoá rồi Thêm lại**. Nó không mất video đã quét (`ViralMaterial`
không có khoá ngoại tới `viral_sources`, `delete_source` cũng không cascade), nhưng mất lịch
sử quét của dòng nguồn và bắt Owner gõ lại danh sách Page — một thao tác sửa số lại hoá thành
xoá dữ liệu.

**Điểm kỹ thuật quyết định hình dạng UI:** hai cột `Min views` và `Max video` trong
`fragments/viral_sources.html` mang class `hidden xl:table-cell` — **màn < 1280px không hiện
chúng**. Owner dùng tool qua UltraViewer ở khung hẹp hơn thế. Nếu biến hai ô đó thành input
tại chỗ thì Owner **vẫn không sửa được** — đúng cái bẫy vừa gây ra ADR-025 (mục điều hướng
trỏ vào thứ không hiện trên màn hẹp). Vì vậy ô sửa **không được nằm trong cột có thể bị ẩn**.

## Quyết định

1. **`SourceService.update_source(db, source_id, *, min_views=None, max_videos=None,
   target_pages=None) -> tuple[bool, str]`** — bổ sung vào hợp đồng ADR-019 mục 2.
2. **Rỗng nghĩa là "về mặc định", không phải "giữ nguyên".** Form luôn gửi đủ ba trường, nên
   `min_views=""` / `max_videos=""` ⇒ ghi **NULL** ⇒ nguồn dùng lại setting chung
   (`viral.min_views`, `viral.max_videos_per_channel`). Không có đường nào để "bỏ trống mà
   giữ số cũ" — nhập lại số nếu muốn giữ. Ghi rõ vì đây là chỗ dễ hiểu ngược nhất.
3. **Kiểm giá trị, từ chối bằng thông báo tiếng Việt** (không raise, giống mọi hàm khác của
   service): `min_views` phải ≥ 0; `max_videos` phải trong `1..MAX_VIDEOS_CAP` (500 — đúng
   trần `scan_source` đang áp). Số sai ⇒ `(False, "...")`, không ghi gì.
4. **`target_pages`**: nhận `list[str]` đã chuẩn hoá bởi `_parse_target_pages` sẵn có của
   router (mỗi dòng một URL, bỏ trùng, giữ thứ tự — ADR-020 mục 6). Danh sách rỗng ⇒ ghi
   `target_pages = NULL` **và xoá luôn `target_page` legacy**: không để lại hai nguồn sự thật
   khiến "đã xoá hết Page" mà `target_pages_list` vẫn trả một Page cũ.
5. **Không cho sửa `url` / `platform` / `handle`.** Đổi URL nghĩa là kênh khác hẳn, phải dò
   lại nền tảng và handle, lại vướng `url` UNIQUE — xoá rồi thêm mới đúng hơn. Sửa số thì
   giữ nguyên dòng, giữ nguyên lịch sử quét.
6. **Route `POST /viral/sources/{id}/update`** trong `viral_intake/router.py`, đúng khuôn các
   route nguồn khác: `Form(...)`, `htmx_toast_response(..., extra_triggers=_SOURCES_TRIGGERS)`
   để bảng tự nạp lại, lỗi bất ngờ đi qua `_sources_error_toast` (toast đỏ, không 500).
7. **UI — hàng mở rộng, không phải input trong cột:** nút **"Sửa"** ở cột Thao tác bật/tắt một
   `<tr>` phụ `colspan` ngay dưới hàng đó, chứa ba ô (Min views, Max video/lần, Page đích) +
   nút **Lưu** + **Đóng**. Hàng phụ luôn hiện đủ ở mọi bề ngang ⇒ không dính bẫy
   `hidden xl:table-cell` ở mục Bối cảnh. Ô Page đích mang lại cảnh báo spam của ADR-020 mục 6.
   Bật/tắt bằng thuộc tính `hidden` qua `onclick` nội tuyến — fragment bị htmx thay mới mỗi
   lần `refreshViralSources`, listener gắn rời sẽ mất theo.

## Phạm vi

| Việc | File |
|---|---|
| `update_source` + kiểm giá trị | `app/features/viral_intake/sources.py` |
| Route `POST /viral/sources/{id}/update` | `app/features/viral_intake/router.py` |
| Nút "Sửa" + hàng form | `app/templates/fragments/viral_sources.html` |
| Test service (SQLite thật) | `tests/test_viral_sources.py` (thêm mục) |
| Test route + UI (service giả) | `tests/test_viral_sources_ui.py` (thêm mục) |

## Ngoài phạm vi

- Không sửa `url` / `platform` / `handle` (mục 5).
- Không đụng `scan_source`, `scan_all`, lịch quét mỗi giờ, `MAX_VIDEOS_CAP`.
- Không migration — dùng đúng các cột `viral_sources` đã có.
- Không đổi form "Thêm nguồn" ở đầu trang.
- Không thêm lịch sử/nhật ký thay đổi cho nguồn.

## Hết hiệu lực

Sau proof: sửa `Max video/lần` của một nguồn đang có từ 3 → 50 rồi bấm Quét, nguồn dùng số
mới mà **không mất** `last_scanned_at` / `last_found`; bỏ trống ô ⇒ cột hiện "mặc định"; nhập
0 hoặc 501 ⇒ toast đỏ và **không** ghi vào DB; xoá hết Page ⇒ cột Page đích về "—"; hàng sửa
hiện đủ ba ô ở khung hẹp.

## Proof (2026-09-09)

Chạy thật trên SQLite + template thật, đúng ca của Owner:

```
them: True  Đã thêm nguồn tiktok @thacaukechuyen
sua : True  Đã lưu nguồn @thacaukechuyen — min views 1,000, max video 50, không Page đích.
sau khi sua -> min_views=1000  max_videos=50  target_page=None
hang sua -> <td colspan="10">, hx-post="/viral/sources/1/update", 3 ô + Lưu + Đóng
```

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Sửa max 3 → 50, **không mất** `last_scanned_at` / `last_found` | `test_update_source_changes_numbers_and_keeps_scan_history` |
| Ô trống ⇒ NULL ⇒ dùng ngưỡng chung (không phải giữ số cũ) | `test_update_source_empty_means_back_to_default_not_keep_old` |
| 0 / 501 / chữ / âm ⇒ toast đỏ, **không ghi gì vào DB** | `test_update_source_rejects_bad_values_without_touching_db` (5 ca) |
| Số sai ra tiếng Việt chứ không phải 422 JSON | `test_update_bad_number_is_vietnamese_error_toast_not_422` |
| Xoá hết Page ⇒ sạch cả `target_page` legacy | `test_update_source_clearing_pages_also_clears_legacy_column` |
| Page giữ thứ tự, bỏ trùng, bỏ dòng rỗng | `test_update_passes_parsed_values_and_refreshes_table` |
| `url` / `platform` / `handle` không đổi | khẳng định trong test giữ lịch sử quét |
| Hàng sửa **không** nằm trong cột `hidden xl:table-cell` | `test_edit_row_is_not_inside_a_column_that_hides_on_narrow_screens` |
| Ô đổ sẵn số hiện tại; nguồn dùng mặc định ⇒ ô rỗng | `test_fragment_has_edit_button_and_prefilled_form` |
| id lạ / service ném lỗi ⇒ toast đỏ, không 500 | `test_update_unknown_id_is_error_toast`, `test_update_service_exception_is_error_toast_not_500` |

**Toàn suite: 599 passed, 16 skipped, 0 failed.**

### Một file ngoài phạm vi đã dự tính

`tests/test_source_fanout_ui.py` phải sửa **helper `_row`**: nó cắt slab từ
`id="viral-source-N"` tới hàng nguồn **kế tiếp**, nên nuốt luôn hàng sửa mới chèn, làm
assert *"không in nguyên URL ra bảng"* (ADR-020) đỏ. Bản thân quy tắc đó **không bị vi phạm**
— cột Page vẫn chỉ hiện tên rút gọn; URL đầy đủ nằm trong textarea của hàng sửa, đúng ý
thiết kế. Đã thu hẹp `_row` dừng ở `</tr>` đầu tiên: giữ nguyên ý định của test, và từ nay
miễn nhiễm với mọi thứ chèn thêm sau hàng nguồn. Không đổi một assert nào.
