# PLAN-182 — Bổ sung ảnh thật vào chuỗi Black Friday

Executor: Codex — ngoại lệ lập PLAN chủ bot đã duyệt.
TASK: TASK-068. Ngày: 20/11/2026 VN. Trạng thái: Execution Done; Claude/Anti và kết quả pending.

## Ủy quyền và startup
Chủ bot: “em kèm ảnh trong bài viết nó mới uy tín chứ em”. Đây là yêu cầu bổ sung ảnh cho bài PLAN181 vừa đăng. Đã đọc current-status, fullPLAN181, ADR066/067; scan số active/archive không có182/068. Phối hợp PLAN172 trước code. Không giả Anti/Claude signoff.

## Scope
1. Chụp thật kênh ZT báo mã bằng Computer Use; chỉ crop phần tên kênh/tin hướng dẫn ghim617. Không đăng danh sách chat riêng, coupon cũ chưa kiểm, số liệu giả hoặc lời hứa giảm giá.
2. Tạo một ảnh minh họa có chữ Black Friday27/11/2026 và ảnh chụp thật, lưu asset đã crop; không sửa nội dung trong ảnh chụp. Visual QA trước upload.
3. Read-only xem bài https://www.threads.com/@us28qt/post/Df8jAaUCVmk và menu thật. Nếu UI hỗ trợ thêm ảnh vào bài gốc thì sửa đúng bài; nếu không, thêm tối đa một ảnh ở phần nối tiếp do chính @us28qt trả lời bài gốc. Báo rõ vị trí, không xóa/đăng lại bài gốc hay tạo original mới.
4. Operational script riêng reports/zt-blackfriday-20261120, không sửa core/template/config/botflow. Fence at-most-once trước nút submit, unknown không replay; exact account/parent/caption/image hash và preview, quota/quiet/minspacing/currentACTIVE giữ nguyên. Chỉ pause/restore riêng Threads_Growth để dùng profile, close finally. Không dùng Windows UI để submit; Threads dùng Playwright hiện có ADR066.
5. Verify permalink/caption/media/parent thật, chụp ảnh kết quả, readback worker restored và cập nhật PLAN/TASK/current-status/report/PLAN172. Nếu thiếu proof giữ pending.

## Trình tự và proof
1. Asset + xác định khả năng edit bằng UI, không mutation công khai.
2. Viết/test guard tối thiểu, prepare preview rồi submit tối đa một lần.
3. Read-only verify, restore runtime finally, ghi lệnh/output thực tế.

Không tạo link/ghim/TGmessage mới; không DM/reply người lạ/broadcast/like, thay cadence/role/privacy, gọi syncShopee, sửa tiền/DBschema hay restart Store/Cashbot/Zalo/nativepilot. Không commit/push. Không coi có ảnh là bằng chứng uy tín hoặc hiệu quả kinh doanh.

## Rollback và handoff
Không tự xóa nội dung công khai. Unknown phải đọc lại trước quyết định. Kết thúc ghi “Execution Done. Cần Claude Code verify + handoff.”; business results và Claude/Anti pending.

## Execution Notes / Verification Proof
- Đã tạo ảnh1080×1350/786981bytes từ crop thật guide617, loại chat riêng/coupon chưa kiểm. VisualQA root và reviewer đạt; raw screenshot đã xóa/sourcegone, asset/cropexists.
- `PYTHONPATH=. venv/bin/python -m pytest -q tests/test_zt_blackfriday_image.py`: **25 passed in3.27s**. RuffAllcheckspassed, pycompile/gitdiffcheckexit0. Test gồm title-onlySVG thực tế, linkdisplayshortening, quota/identity/fence/unknown/restore. Không dùng discoveridentity có điều hướng trong composer.
-10:01:32→10:02:21VN prepare: đúngparent, menu khôngEdit, caption/ảnhpreviewđạt, submitfalse. Vì vậy dùng một continuation theo scope; không xóa/repostoriginal.
-10:06:51→10:07:50VN publish: submittrue duy nhất, statusposted, URL https://www.threads.com/@us28qt/post/Df8pynHiYfZ . Một ảnh/rawmedia+DOM, exactcaption, ownreply và originalparentpage/payload verified; root/reviewer xem ảnh thật sau reload. Rawparentrefunavailable được ghi rõ, không claimrawparentIDproof.
- Một own_posts slotzt-bf26-threads-image-p1/posted, originalslotgiữposted. Worker1103039online; PM2khác/systemdPID/starttime/.env/roleshashkhớpbaseline. Fullproof reports/zt-blackfriday-20261120/IMAGE-REPORT.md, image-publication.json, image-verification-diagnostic.json, image-runtime-after.json. Heartbeat cũ thêm context, không lịch mới.

**Execution Done. Cần Claude Code verify + handoff.** Chưa có kết quả kinh doanh do ảnh; Claude/Anti pending. Không commit/push.
