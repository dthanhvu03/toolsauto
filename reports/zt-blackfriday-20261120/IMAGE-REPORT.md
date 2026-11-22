# PLAN182 — Ảnh thật cho chuỗi ZT Black Friday

Trạng thái: đã đăng một ảnh continuation và xác minh sau reload. **Execution Done. Cần Claude Code verify + handoff.** Kết quả kinh doanh/Claude/Anti pending.

## Asset và nội dung
- Chủ bot yêu cầu kèm ảnh. Ảnh `zt-blackfriday-guide.png`, PNG1080×1350/786981bytes, ghép tiêu đề ngày27/11/2026 với crop thật duy nhất tin hướng dẫn ghim617 trong kênh ZT báo mã. Không sửa chữ trong crop, không coupon cũ/số liệu người dùng giả.
- Crop `guide617-crop.png` không có danh sách chat riêng; screenshot toàn cửa sổ chỉ dùng tạm, đã xóa và kiểm sourcegone/cropexists. Bản crop và ảnh cuối là asset/proof được giữ.
- Caption163ký tự: “Đây là tin hướng dẫn thật trong kênh ZT báo mã 🛍️ Mình chuẩn bị săn Black Friday 27/11 cùng nhau, xem điều kiện mã rồi hãy chốt nhé. Link vào kênh ở bài phía trên.” Hash/caption/parent/asset đã được reviewer độc lập đối chiếu.

## Vị trí ảnh
Parent: https://www.threads.com/@us28qt/post/Df8jAaUCVmk . `image-edit-inspection.json`/`image-parent-menu.png` xác minh menu thật không có Edit; có Insights/Copylink/Embed/Save/Pin/Archive/Postoptions/Delete. Không xóa hay đăng lại original. Chỉ một ảnh continuation cùng @us28qt dưới chính parent, theo PLAN182.

## Proof trước khi gửi
```
PYTHONPATH=. venv/bin/python -m pytest -q tests/test_zt_blackfriday_image.py
25 passed in 3.27s
venv/bin/ruff check reports/zt-blackfriday-20261120/image_trial.py tests/test_zt_blackfriday_image.py
All checks passed!
```
- Liveprepare10:01:32→10:02:21VN20/11: identityus28qt, exactparentpayload/nội dung/anchorinvite khớp, menu khôngEdit, đúngcaption và một ảnh preview, submit_called=false, statusprepared. Ảnh `image-composer.png` đã xem trực tiếp, dưới parent cólinkTelegram. Worker khôi phục1077191online, PM2khác khớp; không post ở bước chuẩn bị.
- Probe trước đó bị guard từ chối trước submit do DOM không có pressableattribute và SVG dùng titleReply/More thay aria-label. Đã sửa operationalscript theo DOM thật và thêm regression. Các lần đọc chỉ kiểm UI, không tạo bài; proof lỗi đầu giữ `image-inspect-first-failure.json`, diagnostic cuối giữ `image-parent-diagnostic.json`.
- Root phát hiện discoveridentity có điều hướngProfile; đã thay kiểm nonnavigating trước submit và có regression. Fence BEGINIMMEDIATE claimunknown trước click; timeout không replay; --verify chỉ đọc. Không sửa core/roles/quota/flow/tiền/nativepilot hoặc gọi syncShopee.

## Kết quả đăng/khôi phục
-10:06:51→10:07:50VN20/11, `--publish` đúng một submit, một slot `zt-bf26-threads-image-p1`/posted, một ảnh. URL: https://www.threads.com/@us28qt/post/Df8pynHiYfZ . Caption163ký tự/hash/ảnh khớp, rawpayload is_reply=true/reply_to_authorus28qt/media_count1 và DOM cùng parentpage đã kiểm. Root và reviewer đều xem `image-published.png`, ảnh cuối hiển thị thật, có Author badge trong chuỗi.
- Raw parent reference không được payload cung cấp (`parent_reference_available=false`); không tuyên bố đã chứng minh rawparentID. Vị trí dựa vào scopedparent trước submit, exactparentpage/payload khi tải lại và ownreply/media/DOM/screenshot. `image-verification-diagnostic.json` lưu giới hạn này.
- `image-runtime-after.json`: other_pm2_same=true, systemd_same=true, env_roles_hashes_same=true. Threads_Growth1103039online/restarts0. DB_Backupstopped PIDnull/0 được chuẩn hóa cùng một trạng thái, không phải restart. Store/Cashbot/Zalo PID25744/25731/25732 và ActiveEnterTimestamp giữ nguyên. Rawfullwindowscreenshot không còn; finalasset/crop/proof giữ lại.
- SQLite read-only đúng một row ảnh/posted; originalslot vẫn posted/urlDf8jAaUCVmk, không xóa/repost, không tạo TGtin/ghim/link mới. Reviewer độc lập xác nhận proof/row/hash/ảnh và25testspass. Compile và gitdiffcheckexit0. Heartbeat hiện có được thêm context ảnh cùng campaign, không thêm lịch hoặc tự đăng; chủ bot đã được thông báo10:08VN.

**Execution Done. Cần Claude Code verify + handoff.** Không suy có ảnh thành uy tín/khách/doanh thu; không commit/push. Kết quả kinh doanh và Anti/Claude pending.
