# ADR-033 — Lệnh Telegram phải làm đúng điều nó nói

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner yêu cầu kiểm lệnh Telegram, xem kết quả rồi giao
  *"em fix hết đi em"*
- **Liên quan**: ADR-027 (tin Telegram), ADR-023 (bài học "nhãn nói dối"), ADR-019 (nguồn mới)

## Bối cảnh — chạy thật từng lệnh

Owner muốn thao tác hết trong Telegram cho khỏi mở máy. Trước khi thêm nút mới, đã **gọi
thẳng từng lệnh** với DB tạm và client giả:

| Lệnh | Kết quả thật |
|---|---|
| `/health`, `/jobs`, `/drafts`, `/resume` | ✅ chạy |
| `/status` | ❌ `WorkerService.get_status` **không tồn tại** (class chỉ có `set_status`) |
| `/pause` | ❌ `JobStatus.PAUSED` **không tồn tại** |
| `/retry <id>` | ⚠️ chỉ in *"Đang thử lại…"* rồi **kết thúc**, không có dòng nào thử lại |
| `/discovery` | ⚠️ in *"Đang quét…"* rồi ngay *"✅ hoàn tất"* — hai câu liền nhau, **không quét gì** |
| `/viral <views> <max>` | ⚠️ ghi `WorkerState`, mà chỗ đó **chỉ đường quét cũ theo account đọc**; nguồn ADR-019 đọc `viral.min_views` từ RuntimeSetting ⇒ **không ảnh hưởng nguồn Owner đang dùng**, dù báo "✅ Đã cập nhật" |

Hai lệnh gãy vì code đổi mà lệnh không đổi theo. Ba lệnh còn lại **báo thành công cho việc
không xảy ra** — cùng họ "nhãn nói dối" của ADR-023, nhưng tệ hơn vì nó khẳng định là xong.

Thêm nút bấm mới vào một bot như vậy là **xây trên nền mục** — nên sửa trước.

## Quyết định

1. **`/status`** đọc `WorkerService.get_or_create_state(db).worker_status` — đúng chỗ mà
   publisher, maintenance và `ai_generator` đang đọc.
2. **`/pause`** đặt chuỗi `"PAUSED"`, giống hệt `worker_router.py:22` của web. `/resume` đặt
   `"RUNNING"`. Không mượn `JobStatus` nữa: trạng thái **worker** và trạng thái **job** là hai
   thứ khác nhau, mượn lẫn nhau chính là gốc của lỗi này.
3. **`/retry <id>` làm thật** — gọi `JobService.retry_job(db, job_id)` (đã có sẵn). Không có
   job ⇒ báo không tìm thấy. Thiếu id ⇒ nhắc cú pháp.
4. **`/discovery` làm thật** — gọi hook `viral.force_discovery` (đã đăng ký trong
   `bootstrap_hooks`), báo số kênh tìm được. Chạy có thể lâu ⇒ chạy nền, nhắn hai lần: nhận
   lệnh và xong.
5. **`/viral` ghi đúng chỗ** — `upsert_setting(db, "viral.min_views", …)` và
   `"viral.max_videos_per_channel"`, tức nơi nguồn ADR-019 thật sự đọc. Vẫn ghi `WorkerState`
   để đường quét cũ theo account không đổi hành vi.
6. **Thêm `/help`** — liệt kê đúng những lệnh đang chạy. Không có nó thì Owner phải mở code
   mới biết bot làm được gì.
7. **Mọi lệnh phải có test gọi thật**, không chỉ đọc code. Chính vì trước đây không có test
   nào mà hai lệnh gãy nằm im không ai biết.

## Phạm vi

| Việc | File |
|---|---|
| Sửa 5 lệnh + thêm `/help` | `app/features/telegram_bot/command_handler.py` |
| Test gọi thật từng lệnh | `tests/test_telegram_commands.py` (mới) |

## Ngoài phạm vi

- Không thêm nút chọn mốc cắt trong ADR này — làm sau, trên nền đã sạch.
- Không đụng `event_router` (callback approve/cancel/style đang chạy tốt).
- Không đổi cách bot chạy (long-polling trong tiến trình Maintenance).
- Không thêm phân quyền theo người gửi: bot chỉ nói chuyện với `TELEGRAM_CHAT_ID` của Owner.

## Hết hiệu lực

Sau proof: gọi cả 9 lệnh + `/help` bằng client giả ⇒ **không lệnh nào ra `❌ Lỗi`**;
`/pause` rồi `/status` ⇒ báo `PAUSED`; `/retry` gọi đúng `JobService.retry_job`; `/discovery`
gọi đúng hook; `/viral` ghi vào **cả** RuntimeSetting lẫn `WorkerState`.

## Proof (2026-09-09)

Gọi lại toàn bộ sau khi vá:

```
v /help    → liệt kê 9 lệnh
v /status  → 🟢 RUNNING
v /pause   → 🟠 tạm dừng      v /status → 🟠 PAUSED   ← trước đây cả hai đều ❌ Lỗi
v /resume  → 🟢 chạy tiếp
v /jobs    → đếm pending/draft
v /drafts  → có nút Duyệt/Huỷ
v /retry   → "Không tìm thấy Job #123"  ← trước đây báo "đang thử lại" cho job không tồn tại
v /viral   → ghi cả RuntimeSetting lẫn WorkerState
```

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Không lệnh nào ra `❌ Lỗi` | `test_khong_lenh_nao_nem_loi` (8 lệnh) |
| `/pause` rồi `/status` ⇒ `PAUSED`, và DB có `worker_status="PAUSED"` | `test_pause_roi_status_phai_bao_PAUSED` |
| `/retry` gọi **thật** `JobService.retry_job` | `test_retry_goi_that_JobService` |
| `/retry` id lạ / không phải số / thiếu ⇒ báo rõ | 4 test |
| `/viral` ghi **cả** RuntimeSetting lẫn WorkerState | `test_viral_ghi_ca_RuntimeSetting_lan_WorkerState` |
| `/viral` tham số sai ⇒ **không ghi dòng nào** | 3 ca parametrize |
| `/discovery` gọi **thật** hook, báo số kênh; hook nổ ⇒ báo lỗi, **không** báo "hoàn tất" | 2 test |
| `/help` không quảng cáo lệnh không tồn tại | `test_help_khong_quang_cao_lenh_khong_ton_tai` |

**Toàn suite: 726 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ.**

## Hai chỗ test của chính mình viết sai, đáng ghi lại

1. **Đo nhầm nguồn sự thật.** Test "tham số sai thì không ghi" dùng `get_int` để kiểm — nhưng
   `upsert_setting` còn gọi `_push_config_value` **đẩy giá trị vào cấu hình tiến trình** (cố ý,
   để tiến trình đang chạy nhận ngay). Nên `get_int` vẫn thấy giá trị test trước để lại **dù
   DB hoàn toàn mới**. Đổi sang kiểm **dòng trong bảng `runtime_settings`** — đúng nghĩa
   "không ghi".
2. **Regex bắt luôn thẻ HTML.** `re.findall(r"/([a-z]+)")` khớp cả `</b>` ⇒ tưởng `/help` quảng
   cáo một lệnh tên `b`. Neo lại bằng `(?:^|\s)`.

Cả hai chỉ lộ khi chạy **cả file**, không lộ khi chạy từng test — vì chúng là lỗi nhiễm chéo
và lỗi khớp chuỗi, không phải lỗi logic.

## Vá bổ sung (2026-09-09, sau khi Owner chạy thật)

Ảnh chụp chat của Owner cho thấy bot **sống** (nhận được "🤖 Bot đã sẵn sàng" của ADR-034),
nhưng lộ ra hai thứ nữa:

**1. Thông báo quảng cáo một lệnh chưa bao giờ tồn tại.** Tin *"TikTok Auto-Discovery"* ghi
*"Đổi ngưỡng: Dashboard → Viral hoặc `/viral_settings`"*. Owner gõ `/viral_settings` ⇒
*"❓ Lệnh không hỗ trợ"*. Lệnh thật là `/viral <min_views> <max_videos>`.

Đây **tệ hơn** lệnh hỏng: lệnh hỏng chỉ im lặng vô dụng, còn tin này **chủ động bảo người dùng
làm một việc bất khả thi**. Đã đổi thành cú pháp thật, điền sẵn số hiện tại:
`/viral 16800 50`.

**2. Nhắn mỗi giờ dù không quét kênh nào.** Đường quét cũ đọc `competitor_urls` của account,
mà Owner có **0 account** ⇒ luôn "Quét 0 kênh đối thủ", và vẫn nhắn. Tin rác làm người ta bỏ
qua cả những tin thật. Nay `num_channels == 0` ⇒ **không nhắn**.

| Proof | Test |
|---|---|
| Không thông báo nào nhắc lệnh ngoài danh sách hỗ trợ | `test_thong_bao_khong_nhac_toi_lenh_khong_ton_tai` — quét cả `maintenance`, `formatting`, `service` |
| Quét 0 kênh ⇒ **không nhắn gì** | `test_khong_quet_kenh_nao_thi_khong_nhan_gi` |
| Có quét mà 0 video ⇒ vẫn báo, kèm **cú pháp đúng** | `test_co_quet_ma_khong_ra_video_thi_van_bao_kem_cu_phap_dung` |

**Toàn suite: 747 passed, 16 skipped, 0 failed.**

## Vá lần hai (2026-09-10) — gửi lệnh thật vào chat mới lộ

Owner bảo *"test các command trong tele thử đi"*. Không kích hoạt lệnh từ xa được (Telegram
không gửi tin của chính bot lại cho bot, và **không được gọi `getUpdates`** vì poller bên máy
Owner đang lắng nghe — gọi vào là giành mất tin của nó). Nên chạy **bộ lệnh thật với client
thật**, dữ liệu từ SQLite tạm, kết quả hiện thẳng trong chat Owner.

Lộ ra một lỗ trong chính bản vá lần đầu: **`/retry` với job có tồn tại nhưng không FAILED**.
`JobService.retry_job` chỉ nhận job `FAILED` và ném
`ValueError("Job is not in FAILED state or does not exist.")`; bản vá lần đầu chỉ kiểm job
**có tồn tại**, nên Owner nhận nguyên câu tiếng Anh nội bộ đó qua bọc `❌ Lỗi:`.

**Test cũ không bắt được vì nó mock `JobService.retry_job`** — mock thì không bao giờ chạm tới
điều kiện thật. Đây là lần thứ hai trong hai ngày một lỗi chỉ lộ khi chạy hàng thật.

Đã kiểm **trước** trong `_cmd_retry`, trả tiếng Việt nói rõ trạng thái hiện tại; thêm cả nhánh
job mất file (`retry_job` cũng ném cho ca này). Test mới dùng job **thật** trong DB tạm, 4 ca
trạng thái + 1 ca mất file.

Một test cũ phải sửa theo: `test_retry_goi_that_JobService` dựng job `FAILED` **không có**
`media_path`, nay bị chặn ở nhánh mất file. Thêm `media_path` — nó vốn định kiểm nhánh chạy
lại được, không phải nhánh mất file.

**Toàn suite: 779 passed, 16 skipped, 0 failed.**
