# ADR-034 — Dán link vào chat là xong: nhận link Telegram + bot báo còn sống

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner: *"mọi thứ để ở tele thì tốt biết mấy"* rồi
  *"oke em triển khai đi em"*
- **Liên quan**: **ADR-033 (dọn lệnh bot — nền để làm cái này)**, ADR-017 (dán link),
  ADR-019 (nguồn), ADR-028 (dò kênh từ link video), ADR-027 (tin video xong)

## Bối cảnh

Owner lười mở máy. Luồng hằng ngày hiện có ba bước, bước đầu **bắt buộc mở web**: thấy video
hay trên TikTok → mở máy → mở `/app/viral` → dán link → bấm Thêm.

Trong khi đó `event_router._handle_message` đang có đúng một dòng:

```python
if not text.startswith("/"): return
```

Tức **mọi tin nhắn không phải lệnh đều bị vứt** — kể cả link Owner gửi vào. Đây là chỗ rẻ nhất
để bỏ hẳn bước "mở máy" khỏi đầu luồng.

**Không bê cả web vào chat.** Chat dở ở bảng biểu và cấu hình, giỏi ở "một việc một nút". Bảng
100 video và trang Thiết lập mấy chục ô vẫn ở web; chỉ luồng hằng ngày chuyển sang Telegram.

## Quyết định

1. **Tin nhắn có link ⇒ xử lý, không vứt.** Bóc URL đầu tiên trong tin bằng regex — Owner bấm
   "Chia sẻ" từ app TikTok thì tin kèm cả chữ mô tả, không phải link trần.
2. **Link kênh ⇒ thêm nguồn tự quét** (`SourceService.add_source`).
   **Link video ⇒ thêm material và xử lý ngay** (`ViralService.add_material_from_url` +
   nền). Phân biệt bằng `SourceService.detect_channel` — hàm thuần, không mạng.
3. **Nút "➕ Thêm cả kênh này làm nguồn"** kèm theo tin trả lời của link video. Kênh TikTok
   không liệt kê được bằng `@handle` thì đây là **đường duy nhất** để thêm nó (ADR-028), mà
   Owner đang ở trong chat chứ không ở web.
   `callback_data` là `src:<material_id>` chứ không phải URL: Telegram giới hạn 64 byte, link
   TikTok dài hơn thế.
4. **Chỉ nghe `TELEGRAM_CHAT_ID` của Owner.** Bot công khai với ai biết tên nó; không lọc thì
   người lạ dán link là tool tải và xử lý hộ họ. Tin từ chat khác ⇒ bỏ qua im lặng.
5. **Bot báo "đã sẵn sàng" mỗi lần Maintenance khởi động.** Bộ nhận lệnh chỉ sống trong tiến
   trình đó; chạy `start.ps1` thường là **không có bot mà không có gì báo** — Owner nhắn vào
   chat, không ai trả lời, thế thôi. Càng dồn việc vào Telegram thì cái chết âm thầm này càng
   nguy.
6. **Mỗi đường mới một bộ test gọi thật.** ADR-033 vừa cho thấy 5 lệnh hỏng nằm im vì không
   có test nào.

## Phạm vi

| Việc | File |
|---|---|
| Nhận link trong tin nhắn, lọc theo chat id | `app/features/telegram_bot/event_router.py` |
| Callback "thêm kênh này làm nguồn" | `app/features/telegram_bot/event_router.py` |
| Báo bot đã sẵn sàng | `app/features/system_panel/workers/maintenance.py` |
| Test | `tests/test_telegram_link_intake.py` (mới) |

## Ngoài phạm vi

- Không đưa bảng video hay trang Thiết lập vào chat.
- Không đăng Facebook từ Telegram (cần trình duyệt).
- Không nâng giới hạn 50 MB của Bot API.
- Không đụng các lệnh `/…` đã dọn ở ADR-033.

## Hết hiệu lực

Sau proof: gửi link video vào chat ⇒ material được tạo và xử lý nền, tin trả lời có nút thêm
kênh; gửi link kênh ⇒ nguồn được tạo; gửi chữ không có link ⇒ im lặng; tin từ chat lạ ⇒ bỏ
qua; Maintenance khởi động ⇒ bot nhắn "đã sẵn sàng".

## Proof (2026-09-09)

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Link video ⇒ tạo material **và** xử lý nền đúng material đó | `test_link_video_tao_material_va_xu_ly_nen` |
| Tin trả lời có nút "➕ Thêm cả kênh này làm nguồn", `callback_data` ≤ 64 byte | `test_link_video_kem_nut_them_kenh` |
| Bóc được link lẫn trong chữ (bấm Chia sẻ từ app TikTok) | `test_boc_duoc_link_lan_trong_chu_khi_bam_chia_se` |
| Bỏ dấu câu dính cuối link (`.` `,` `)`) | 3 ca parametrize |
| Link kênh ⇒ tạo nguồn, **không** xử lý video nào, **không** kèm nút | `test_link_kenh_tao_nguon_va_khong_xu_ly_video` |
| Tin không có link ⇒ im lặng; tin `/lệnh` ⇒ vẫn đi đường cũ | 2 test |
| Hook từ chối / nổ / xử lý nền nổ ⇒ **báo rõ**, không im, không ném | 3 test |
| Nút thêm kênh gọi đúng hook, thất bại thì báo rõ | 2 test |
| Tin **và** nút bấm từ chat lạ ⇒ bỏ qua | 2 test |
| Chào "bot đã sẵn sàng" **sau** khi poller chạy | `test_maintenance_chao_sau_khi_poller_chay` |

**Toàn suite: 744 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ.**

## Ranh giới module giữ được nhờ hook

`telegram_bot` **không** import `viral_intake` — import-linter chặn feature gọi feature
(ADR-007). Thêm ba hook ở `bootstrap_hooks` (nơi duy nhất được biết mọi feature):
`viral.add_link`, `viral.add_source_from_material`, `viral.process_one`. Đây cũng đúng cách
`/discovery` đã làm từ trước.

## Một lỗ đã có sẵn, vá luôn

`poller._process_update` chỉ lọc `message` theo chat id, **không lọc `callback_query`**. Trước
ADR này hậu quả nhỏ (nút chỉ có trong chat Owner), nhưng từ nay tin nhắn link làm tool **tải và
xử lý hộ người gửi**, nên siết cho đều. Có test hồi quy.
