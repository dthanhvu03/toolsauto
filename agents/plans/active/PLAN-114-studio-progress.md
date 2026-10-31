# PLAN-114: Studio — hiện tiến trình từng video (bước nào, bao lâu, lỗi gì)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-114 |
| **Status** | Approved — anh yêu cầu 31/10 («ui ux… không tiến trình và quy trình các bước khi thực thi gì hết») |
| **Executor** | Claude Code (vai UX; ngoại lệ ADR-061 Studio) |
| **Created** | 2026-10-31 |

---

## Vấn đề (anh chụp màn hình 31/10)
- Bấm «Tải & dựng» chỉ có 1 câu toast rồi tắt. Không thấy video đang ở bước nào; video #9 kẹt 25 phút gửi Telegram
  (mạng đẩy 16 KB/s) mà không nơi nào báo.
- Bảng Studio chỉ có dòng «Đang xử lý N bước». Video chưa thành dự án (đang tải / phân tích) thì không hiện ở đâu.

## Thiết kế
- **Một «việc» = một chuỗi bước** của `studio_tasks` (theo `parent_id` từ việc gốc). Các bước lấy từ `pipeline.FLOWS[flow]`.
- **Backend** `studio/progress.py` (đọc DB, không sửa gì) → `GET /studio/api/jobs` (`ids=` lọc theo việc gốc;
  mặc định: việc đang chạy / chờ + việc xong / lỗi trong 2 giờ qua).
  Mỗi việc trả về:
  - tên (tiêu đề / link / tên file), nguồn (TikTok / tải lên / reup), dự án (id + trạng thái);
  - từng bước: `done` / `skipped` / `running` / `queued` / `retry` / `failed` / `pending`, kèm ghi chú
    (vd «đã tải 7.6 MB», «103.1s · GPU») và thời gian chạy;
  - tóm tắt: đang ở bước nào và bao lâu rồi; lỗi gì; hay đã xong.
  Bước `review` đang chạy = «Đang gửi bản xem trước qua Telegram».
- **Web:** component `JobsPanel`:
  - thanh bước (✓ xong · ⟳ đang chạy kèm đồng hồ · ○ chưa tới · – bỏ qua · ✕ lỗi) + 1 dòng trạng thái + nút mở dự án;
  - tự hỏi lại mỗi 3 giây khi còn việc chạy;
  - ở bảng Studio thay dòng «Đang xử lý N bước»; ở trang «Lấy từ TikTok» hiện ngay dưới sau khi bấm «Tải & dựng»
    (đúng các video vừa gửi).
- (Kèm, lỗi PLAN-113) Trình edit theo chế độ đăng tay: duyệt được khi không kênh, ô kênh có «Đăng tay», sau khi duyệt có
  Tải video / Chép caption / Đã đăng; phụ đề: video không lời thoại thì không hiện ô tick gây hiểu lầm.

## Scope
`progress.py`, `router.py` (`/jobs`), `editor.update_meta` (`channel_id=0` = đăng tay), SPA (`JobsPanel`,
`ManualPostActions`, `StudioBoardPage`, `StudioTiktokPage`, `StudioEditorPage`, `SubtitleEditor`), test.

## Out of Scope
- Nút «Thử lại» cho việc lỗi.
- Huỷ việc đang chạy.
- Gửi Telegram nhẹ hơn cho video lớn: đã đề xuất riêng, chờ anh duyệt.

## Validation
- pytest: tiến trình đúng từng trạng thái (đang chạy, chờ thử lại, lỗi, bỏ qua, dừng sớm, xong chờ duyệt).
- ruff, lint-imports, tsc + build.
- Trình duyệt thật trên web tạm: chạy pipeline thật, chụp lúc đang chạy và lúc xong.

## Rollback
Chỉ đọc + giao diện; bỏ component là về như cũ.

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — CHƯA restart trên máy thật** (`pm2 restart` bị chặn quyền ở PLAN-113, chờ anh). Không migration.
  - `progress.py` (chỉ đọc): việc = chuỗi `parent_id`; bước `done / skipped / running / queued / retry / failed / pending / waiting`;
    trạng thái việc `running / queued / retry / failed / review / done / stopped` + câu tóm tắt; việc gửi đăng đặt tên «Dự án #id»,
    đăng tay ghi «Đang ghi nhận đăng tay». `router.py`: `GET /jobs?ids=`.
  - `fetch/`: lỗi yt-dlp đổi thành câu Việt + giữ câu gốc trong ngoặc (`video riêng tư (This video is private)`), bỏ tiền tố trùng.
  - SPA `JobsPanel` (thanh bước + đồng hồ bước đang chạy theo giờ server + ghi chú từng bước + link «Xem & duyệt dự án #id»,
    hỏi lại 3 giây khi còn việc chạy) ở bảng Studio (ẩn việc đã xong — đã có thẻ) và trang «Lấy từ TikTok» (lô vừa gửi, nhớ qua
    tải lại trang bằng localStorage có try/catch).
  - Lỗi PLAN-113 sửa kèm: trình edit đăng tay (nút «Duyệt (đăng tay)», ô kênh «Đăng tay» → `channel_id=0`, sau duyệt có
    `ManualPostActions` dùng chung với thẻ, không còn câu «đã sang Buffer»), phụ đề không lời thoại không hiện ô tick.

**Verification Proof**:
```
$ unshare -n pytest tests/test_studio_progress.py tests/test_studio_links.py -q → 15 passed; bộ Studio đầy đủ (10 file test) → 158 passed
$ ruff → All checks passed; lint-imports: 2 contract Studio KEPT
$ tsc --noEmit ok; npm run build ok
# DB thật (chỉ đọc): progress.jobs → #41 TikTok «Đang gửi bản xem trước qua Telegram», #49 Render lại «Chờ tới lượt: Duyệt»
#   (đúng thực tế: bước review kẹt 20 phút vì mạng đẩy 16 KB/s, việc khác của làn light xếp sau).
# Trình duyệt thật (web tạm + worker nền chạy pipeline thật, mỗi bước chậm 4 giây; 5 link: 3 thường, 1 trùng, 1 riêng tư):
#   lúc chạy: «Đang chờ ×4 / Đang chạy: Nhận file 0:01»; lúc xong: 3 «Chờ duyệt» (Duyệt = vòng chờ, Đăng chưa tới),
#   1 «Dừng ở Nhận file: trùng asset #1», 1 «Lỗi — Tải về hỏng: video riêng tư (This video is private)»;
#   tải lại trang vẫn theo dõi 5 việc; trình edit: «Duyệt (đăng tay)» → Tải video / Chép caption / Đã đăng → POSTED;
#   390 px không tràn; 0 lỗi JS.
```
**Để chạy trên máy thật:** `pm2 restart Web_Dashboard Studio_Heavy Studio_Light && pm2 save`.
