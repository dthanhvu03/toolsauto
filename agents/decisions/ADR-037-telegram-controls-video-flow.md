# ADR-037 — Lệnh Telegram nối vào luồng video, không chỉ vào luồng job cũ

- **Ngày**: 2026-09-10
- **Trạng thái**: **ĐÃ DUYỆT** — Owner hỏi *"mấy cái command đó nó có nối với nguồn video đồ
  không, mấy cái mình làm bữa giờ"* rồi giao *"em triển khai đi em"*
- **Liên quan**: ADR-033/034 (bot), ADR-019/026 (nguồn), ADR-031/032/036 (mốc cắt), ADR-027 (tin video)

## Bối cảnh — soi thật bộ lệnh đang có

| Lệnh | Nối vào đâu | Dùng được cho Owner? |
|---|---|---|
| `/jobs` `/drafts` `/retry` | **Job** — luồng có tài khoản Facebook | ❌ Owner có 0 tài khoản ⇒ luôn rỗng |
| `/discovery` | quét theo `competitor_urls` của tài khoản | ❌ 0 tài khoản ⇒ không quét gì |
| `/status` `/pause` `/resume` `/health` | worker, hệ thống | ✅ nhưng không liên quan video |
| `/viral <min> <max>` | ngưỡng **chung** | ⚠️ nguồn của Owner có `min_views` **riêng**, mà code lấy số riêng trước ⇒ lệnh này **không đổi được gì cho nguồn đang chạy**, dù báo "đã cập nhật" |

**Ba trên chín lệnh vô dụng** với Owner ngay lúc này. Và toàn bộ những gì dựng từ ADR-025 tới
ADR-036 — nguồn, mốc cắt, độ dài, dải khung hình, Drive, caption — **chỉ chạm Telegram ở hai
chỗ**: dán link vào (ADR-034) và nhận video ra (ADR-027/030/035).

Tức Owner **đưa vào được**, **nhận ra được**, nhưng **không điều khiển được gì ở giữa**.

## Quyết định

1. **`/nguon`** — liệt kê nguồn: nền tảng, handle, min views, quét cuối, tìm thấy, lỗi. Mỗi
   nguồn một hàng nút **Quét ngay** và **Tắt/Bật**.
2. **`/moi`** — video `NEW` chưa xử lý, kèm nút **Xử lý** từng cái. Đây là thứ Owner đang phải
   mở web bấm "Xử lý N mới".
3. **`/sansang`** — video `READY` đang chờ đăng tay, kèm nút **Gửi lại** (bắn lại file + caption).
4. **Nút chọn mốc cắt trong chat**: một **ảnh lưới 4×3** ghép từ 12 khung đã trích (ADR-032)
   + 12 nút ghi phút. Bấm ⇒ đặt mốc + xử lý lại, dùng lại đúng đường `set_clip_start`.
   Ở web là 12 ảnh rời để bấm thẳng vào ảnh; ở Telegram **không bấm được vào vùng trong ảnh**
   nên phải một ảnh + nút riêng. Mỗi nơi một cách, theo cách tương tác của nơi đó.
5. **Ba lệnh vô dụng phải nói rõ vì sao rỗng**, không hiện `Pending: 0 | Draft: 0` trông như hệ
   thống chết: thêm câu *"chưa nối tài khoản Facebook nên chưa có job nào — video đi đường
   đăng tay, xem /sansang"*. Nhãn phải nói đúng tình trạng (ADR-023).
6. **`/viral` phải nói rõ giới hạn của nó**: nguồn nào đặt ngưỡng riêng thì lệnh này không đụng
   tới. Báo "đã cập nhật" mà không nói điều đó là nửa sự thật.
7. **Mọi thứ đi qua `feature_hooks`.** `telegram_bot` không được import `viral_intake`
   (import-linter, ADR-007). Thêm hook ở `bootstrap_hooks` — đúng cách ADR-034 đã làm.

## Phạm vi

| Việc | File |
|---|---|
| Hook cho nguồn / material / khung hình | `app/bootstrap_hooks.py` |
| 3 lệnh mới + sửa 4 lệnh cũ | `app/features/telegram_bot/command_handler.py` |
| Callback: quét, tắt/bật, xử lý, gửi lại, chọn mốc | `app/features/telegram_bot/event_router.py` |
| Ghép ảnh lưới từ 12 khung | `app/features/viral_intake/service.py` |
| Test | `tests/test_telegram_video_controls.py` (mới) |

## Ngoài phạm vi

- Không đưa trang Thiết lập vào chat (mấy chục ô, gõ lệnh chậm hơn mở web).
- Không đăng Facebook từ Telegram.
- Không đổi bộ lệnh worker (`/status` `/pause` `/resume` `/health`).

## Hết hiệu lực

Sau proof: `/nguon` liệt kê nguồn thật kèm nút chạy được; `/moi` và `/sansang` liệt kê đúng
trạng thái; bấm nút quét/xử lý/gửi lại gọi đúng hook; gửi ảnh lưới + 12 nút, bấm một nút ⇒
`clip_start_sec` bằng đúng giây đó; `/jobs` rỗng ⇒ nói rõ vì sao.

## Proof (2026-09-10)

Ảnh lưới dựng thật từ 12 khung: **800×1068, 103 KB** — vừa cỡ xem trên điện thoại.

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| `/nguon` liệt kê nguồn kèm nút `scan:` và `tgsrc:` | `test_nguon_liet_ke_kem_nut_quet_va_tat` |
| Nguồn đang tắt ⇒ nút đổi thành "Bật"; có lỗi ⇒ hiện lỗi | 2 test |
| `/moi` lọc đúng `NEW`, `/sansang` lọc đúng `READY` | 2 test |
| `/sansang` có thêm nút **Chọn đoạn** | `test_sansang_co_them_nut_chon_doan` |
| Quét và Xử lý **trả lời ngay rồi chạy nền** (mất hàng chục giây tới vài phút) | 2 test |
| Nút Chọn đoạn gửi **ảnh lưới + đúng 12 nút** ghi phút | `test_nut_chon_doan_gui_anh_luoi_va_12_nut` |
| Ghép ảnh hỏng ⇒ **vẫn có 12 nút** (ảnh chỉ là tiện ích phụ) | `test_ghep_anh_hong_thi_van_co_nut` |
| Bấm mốc ⇒ `set_clip` rồi xử lý lại, đúng material và đúng giây | `test_bam_moc_thi_dat_clip_va_xu_ly_lai` |
| Mốc hỏng / đặt mốc thất bại ⇒ báo rõ, không ném | 2 test |
| `/jobs` `/drafts` rỗng ⇒ **nói rõ vì sao** | sửa nội dung, `/help` liệt kê `/sansang` |
| `telegram_bot` vẫn không import `viral_intake` | `lint-imports`: 2 hợp đồng giữ |

**Toàn suite: 799 passed, 16 skipped, 0 failed.**

## Cái canh của ADR-033 tự bắt được lỗi của ADR-037

`test_help_khong_quang_cao_lenh_khong_ton_tai` đỏ ngay khi thêm `/nguon` `/moi` `/sansang`:
danh sách lệnh hợp lệ trong test **chép tay** nên lệch. Đúng thứ nó sinh ra để bắt.

Không vá bằng cách thêm ba chữ vào danh sách, mà **tách `handler_map()` ra khỏi
`handle_command`** để test đọc thẳng bảng thật. Từ nay thêm lệnh không thể làm cái canh này
lệch nữa — nó luôn so với sự thật, không so với một bản chép.
