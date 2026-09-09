# ADR-028 — Kênh TikTok không liệt kê được bằng @handle: dán link video, tool tự dò channel_id

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner báo lỗi 2026-09-09 và gửi link video của kênh để kiểm chứng.
- **Liên quan**: **ADR-019 (mở rộng `add_source` / dạng `url` của nguồn)**, ADR-026 (sửa nguồn)

## Bối cảnh

Nguồn `@thacaukechuyen` quét ra lỗi, bảng cắt còn `ERROR: [tiktok:user] thacaukechuyen: Una…`.
Nguyên văn tái hiện được trên máy dev:

```
ERROR: [tiktok:user] thacaukechuyen: Unable to extract secondary user ID.
If you are able to get the channel_id from a video posted by this user,
try using "tiktokuser:channel_id" as the input URL
```

Đã loại trừ hai giả thuyết dễ nghĩ nhất, bằng kiểm chứng chứ không đoán:

| Giả thuyết | Kiểm | Kết luận |
|---|---|---|
| yt-dlp cũ | `pip index versions yt-dlp` | Đang là **2026.8.19 = bản mới nhất**. Không phải. |
| TikTok chặn mọi kênh | quét thử `@tiktok`, `@charlidamelio` | `@tiktok` ✅, `@charlidamelio` ❌ giống hệt. **Lỗi theo từng kênh**, không phải cả nền tảng. |

TikTok trả trang kênh thiếu khối dữ liệu mà extractor cần, với một số tài khoản. Cách yt-dlp
gợi ý — `tiktokuser:<channel_id>` — **chạy thật**, đã kiểm trên đúng kênh của Owner:
5 video kèm `view_count` (2.000.000 / 93.900 / 21.000 …).

Nhưng `channel_id` **chỉ lấy được từ một video của kênh**, mà `add_source` hiện **từ chối
thẳng link video** (`_classify` trả `MSG_VIDEO_LINK`). Nên hôm nay Owner không có đường nào.

**Một cái bẫy đã tự dẫm phải khi kiểm, ghi lại để không ai mất thêm một vòng:** `channel_id`
dài **76 ký tự**; lần thử đầu vô tình cắt còn 70 và `tiktokuser:` báo **đúng cùng một lỗi**
"Unable to extract secondary user ID". Tức thông báo đó **không phân biệt** "kênh không liệt
kê được" với "channel_id sai/cụt" — đừng đọc nó rồi vội kết luận cách này không dùng được.

## Quyết định

1. **Ô "URL kênh" nhận thêm link một VIDEO TikTok.** `add_source` chỉ đổi ở đúng nhánh
   `MSG_VIDEO_LINK` của TikTok: chạy `yt-dlp --dump-json` trên link video đó để lấy
   `channel_id` + `uploader`, rồi lưu nguồn với `url = "tiktokuser:<channel_id>"`,
   `handle = uploader`, `platform = "tiktok"`. Link kênh `@handle` vẫn đi **nguyên đường cũ**
   — không đụng gì tới các nguồn đang chạy được.
2. **`_classify` giữ nguyên: thuần, không mạng.** Bước dò `channel_id` là một hàm riêng, chỉ
   gọi khi đã biết đây là link video TikTok. Trộn mạng vào `_classify` thì `detect_channel` và
   `reject_reason` — vốn là hàm kiểm tra rẻ, có test — hoá thành hàm gọi mạng.
3. **Dò là việc có mạng nên phải có hạn giờ và không được raise**: timeout riêng
   (`RESOLVE_TIMEOUT_SEC = 60`, ngắn hơn quét vì chỉ đọc metadata một video); mọi hỏng hóc trả
   `(False, thông báo tiếng Việt)` như mọi nhánh từ chối khác của `add_source`.
4. **Đổi câu lỗi khi quét gặp đúng ca này** thành hướng dẫn tiếng Việt: nói rõ TikTok không
   cho liệt kê kênh này bằng `@handle` và bảo Owner dán link **một video** của kênh vào ô URL
   kênh. Nguyên văn tiếng Anh cụt ở cột Lỗi không nói cho Owner biết phải làm gì.
5. **Hiển thị**: nguồn dạng `tiktokuser:<id>` không phải URL mở được. Bảng nguồn dựng lại link
   từ handle (`https://www.tiktok.com/@<handle>`) cho những nguồn có `url` không bắt đầu bằng
   `http`. Owner nhìn vẫn thấy `@thacaukechuyen` và bấm vào vẫn ra kênh.
6. **Không đụng `_video_url`**: đã kiểm bản liệt kê qua `tiktokuser:` vẫn trả
   `uploader = thacaukechuyen`, nên link video sinh ra vẫn đúng dạng
   `https://www.tiktok.com/@thacaukechuyen/video/<id>` như đường cũ — cùng dạng `scan.py` lưu,
   nên chống trùng theo URL vẫn khớp.

## Phạm vi

| Việc | File |
|---|---|
| Dò `channel_id` từ link video + nhánh mới trong `add_source` | `app/features/viral_intake/sources.py` |
| Câu lỗi hướng dẫn khi quét gặp ca này | `app/features/viral_intake/sources.py` |
| Link hiển thị cho nguồn `tiktokuser:` + nhắc ở ô nhập | `app/templates/fragments/viral_sources.html`, `app/templates/pages/app_viral_sources.html` |
| Test | `tests/test_viral_sources.py` |

## Ngoài phạm vi

- **Không tự cứu nguồn đang hỏng.** Cách duy nhất lấy `channel_id` là từ một video của kênh;
  kênh này `last_found = 0` nên trong kho không có video nào của nó để lần ra. Owner xoá nguồn
  rồi thêm lại bằng link video — một thao tác, không đáng dựng cơ chế dò ngược.
- Không nhận chuỗi `tiktokuser:<id>` gõ tay ở ô URL kênh: thêm một đường vào là thêm một thứ
  phải kiểm, mà không giải quyết thêm ca nào.
- Không đụng YouTube, không đụng `scan_all`, lịch quét, `MAX_VIDEOS_CAP`.
- Không dùng cookie/đăng nhập để cứu các kênh khác — việc khác, rủi ro khác.

## Hết hiệu lực

Sau proof: dán link video của `@thacaukechuyen` vào ô URL kênh ⇒ nguồn được tạo với
`url = tiktokuser:<76 ký tự>`, `handle = thacaukechuyen`; quét ra video thật kèm views; nguồn
`@handle` cũ vẫn thêm và quét như trước; link video hỏng ⇒ toast đỏ tiếng Việt, không tạo nguồn.

## Proof (2026-09-09)

**Chạy thật trên đúng kênh của Owner** (link video do Owner gửi, không mock, SQLite tạm):

```
them nguon: True | Đã thêm nguồn tiktok @thacaukechuyen
  url    = tiktokuser:MS4wLjABAAAAMgUbPA6oIGGcX7yl0__2kSP_0aeeresNEOf8RsraKcdygGfYqJn5GMSrYFQZDC8Z
  handle = thacaukechuyen | platform = tiktok

quet: found=5 skipped=0 error=None
  2,000,000 views | Muốn giàu phải ra biển         | .../@thacaukechuyen/video/7682789967273250069
     94,100 views | Muốn giàu phải ra biển         | .../@thacaukechuyen/video/7682021726942694676
     21,000 views | Dùng 5 Con Tôm Sống Làm Mồi…   | .../@thacaukechuyen/video/7681306788917939476
     36,900 views | Muốn giàu phải ra biển         | .../@thacaukechuyen/video/7680506543476935956
     17,600 views | Muốn giàu phải ra biển nha…    | .../@thacaukechuyen/video/7680183551786110229
```

Link video sinh ra đúng dạng `@thacaukechuyen/video/<id>` như đường cũ (mục 6) ⇒ chống trùng
theo URL vẫn khớp với những gì `scan.py` đã lưu.

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Link video ⇒ nguồn `tiktokuser:<76 ký tự>`, handle đúng | chạy thật ở trên + `test_add_source_tu_link_video_tiktok_thanh_nguon_tiktokuser` |
| Quét ra video thật kèm views | `found=5`, views 2.000.000 → 17.600 |
| Nguồn `@handle` cũ **không tốn lượt mạng nào** | `test_link_kenh_handle_van_di_duong_cu_khong_goi_yt_dlp` — `cmds == []` |
| FB/IG/YouTube vẫn từ chối như cũ | `test_link_video_ngoai_tiktok_van_bi_tu_choi_nhu_cu` (3 ca) |
| Video không có `channel_id` ⇒ từ chối, không tạo nguồn | `test_video_khong_co_channel_id_thi_tu_choi_co_ly_do` |
| yt-dlp lỗi / quá giờ ⇒ toast đỏ tiếng Việt, không raise | `test_yt_dlp_loi_khi_do_thi_tu_choi_khong_raise`, `test_do_channel_id_qua_lau_thi_tu_choi_khong_treo` |
| Quét gặp lỗi này ⇒ ghi hướng dẫn tiếng Việt vào cột Lỗi | `test_quet_gap_loi_secondary_user_id_thi_ghi_huong_dan_tieng_viet` |
| Bảng hiện link kênh bấm được cho nguồn `tiktokuser:` | render fragment ⇒ `https://www.tiktok.com/@thacaukechuyen` |

**Toàn suite: 621 passed, 16 skipped, 0 failed.**

### Một test cũ phải sửa — và lý do đáng nhớ

`test_add_source_rejects_fb_ig_video_and_duplicate` có dòng khẳng định link video TikTok bị
từ chối. Từ ADR này nó **không còn bị từ chối** mà rơi vào nhánh dò — nghĩa là test đó bắt đầu
**gọi mạng thật**, phá cam kết "không mạng" ghi ngay ở đầu file. Đã bỏ dòng đó và để lại cảnh
báo tại chỗ: *đừng gọi `add_source` với link video TikTok trong test không mock*. Mọi ca của
nhánh mới nằm ở mục ADR-028 cuối file, đều mock `subprocess.run`.
