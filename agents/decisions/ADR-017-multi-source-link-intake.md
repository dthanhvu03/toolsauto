# ADR-017 — Cửa vào "dán link" đa nền tảng cho xưởng nội dung

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-07 ("anh cần tải được nhiều nguồn")
- **Liên quan**: ADR-016, PLAN-042/043 (viral intake), TASK-047 (đa dạng nguồn)

## Bối cảnh

Kiểm code + DB 2026-09-07: **không có endpoint nào nhận link**. Cách duy nhất video vào
tool là `run_tiktok_competitor_scan` quét `competitor_urls` (TikTok) của account. 11
material đều TikTok, cùng một kênh. Bảng thực lực từng ghi "tải khi dán link — A" là
sai, đã hạ D.

Đường tải phía sau (`processor._process_viral_materials`) đã **đa nền tảng**: yt-dlp +
nhánh cookie cho FB/IG + TikWM dự phòng cho TikTok. Cái thiếu là **cửa vào** và **bằng
chứng** YouTube/FB/IG tải được không cần đăng nhập ở 2026. yt-dlp trong venv
`2026.03.03`, bản `2026.08.19` có sửa TikTok.

Owner muốn đi nhiều nguồn. Hai tầng: (1) dán bất kỳ link nào → tải; (2) quét tự động
kênh YouTube / Page FB / IG. **ADR này chỉ làm tầng 1** — tầng 2 là "tự dán link theo
lịch", xây trên tầng 1, cần PLAN riêng.

## Quyết định

1. `detect_platform(url) -> str | None` thuần: `tiktok.com`/`vt.tiktok.com` → `tiktok`;
   `youtube.com`/`youtu.be` → `youtube`; `facebook.com`/`fb.watch` → `facebook`;
   `instagram.com` → `instagram`; khác → `None` (từ chối, không tạo material).
2. `ViralService.add_material_from_url(db, url, *, target_page=None) -> (ok, msg, material_id)`:
   chuẩn hoá URL (bỏ query rác, giữ id), từ chối trùng (`url` unique), tạo
   `ViralMaterial(status=NEW, platform=<detect>, views=0, title="", scraped_by_account_id=None)`.
   **Material dán tay không bị lọc theo lượt xem** — kiểm `processor` có chỗ nào bỏ qua
   `views == 0` không (có nhánh instagram `views == 0` ở ~607) và giữ đường đi cho nó.
3. Endpoint `POST /viral/add-link` (Form `url`, `target_page` tuỳ chọn, `process_now` bool)
   → toast; `process_now` thì đẩy `process_material` xuống nền theo cơ chế ADR đã có.
4. UI: một ô dán link + nút "Thêm" ở đầu `/app/viral`, cùng hàng với "Quét kênh".
5. Nâng `yt-dlp` lên bản mới nhất, ghim trong `requirements.txt`.
6. **Proof bắt buộc** bằng link thật, không cookie: 1 TikTok (kênh khác), 1 YouTube Shorts,
   1 Facebook Reel công khai, 1 Instagram Reel công khai. Ghi rõ cái nào tải được, cái nào
   cần đăng nhập — cập nhật bảng thực lực đúng theo kết quả, không đoán.

## Phạm vi

| Việc | File |
|---|---|
| detect + add | `app/features/viral_intake/service.py` (hoặc `intake.py` mới nếu service.py quá dài) |
| Endpoint | `app/features/viral_intake/router.py` |
| UI | `app/templates/pages/app_viral.html` |
| Test | `tests/test_viral_link_intake.py` (mới) |
| yt-dlp | `requirements.txt` |
| Tài liệu | `docs/sales/00-doi-chieu-thuc-luc.md` theo kết quả proof |

## Ngoài phạm vi

- Không quét tự động kênh YouTube/FB/IG (tầng 2, PLAN riêng).
- Không sửa `processor.py` trừ khi proof cho thấy material dán tay bị bỏ qua (khi đó ≤5 dòng, ghi rõ).
- Không thêm nguồn Douyin/Shopee (đã D).
- Không lo bản quyền hộ Owner — chỉ ghi cảnh báo trong UI: "chỉ dán video mình được phép dùng".

## Hết hiệu lực

Sau khi dán 1 link YouTube Shorts thật → material NEW → xử lý xong `DRAFTED` có file reup.
