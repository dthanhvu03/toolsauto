# PLAN-172 — Vận hành tăng trưởng Cashbot + AI Pass Store (đến 12/12)

- Executor: Claude Code (ADR-067: chủ bot giao toàn quyền vận hành 15/11)
- Script đo (chỉ đọc): scratchpad f74d4a4a/funnel.py → sẽ chuyển vào repo cùng báo cáo hằng ngày (tuần 1).

## Mục tiêu (Claude chọn)
**Chỉ số chính: số khách dùng thật trong 7 ngày, gộp 2 bot** (Cashbot: tạo link; Store: nạp xong hoặc có đơn).

| Chỉ số | 15/11 (gốc) | 12/12 |
|---|---|---|
| Khách dùng thật 7 ngày (2 bot) | 24 | **60** |
| Store: khách Threads có đơn đầu | 7% (6/76) | 20% |
| Store: khách mua ≥2 lần | 1 | 8 |
| Cashbot: khách đến qua mời bạn | 0 | 10 |
| Cashbot: khách tạo link ngày 12/12 | — | 30 |

## Bảng số gốc 15/11 (chỉ đọc DB)
**AI Pass Store** (99 khách)
| nguồn | vào | tạo mã nạp | nạp xong | có đơn | mua ≥2 |
|---|---|---|---|---|---|
| threads | 76 | 10 (13%) | 6 (7%) | 6 (7%) | 0 |
| tự vào | 23 | 6 (26%) | 6 (26%) | 6 (26%) | 1 |
- 46/76 khách Threads rời bot trong vòng 10 phút. Doanh thu đơn done 494.300đ (Threads 215.600đ).
- Mã nạp: 13 paid / 12 cancelled — khách tạo mã rồi bỏ gần một nửa.

**Cashbot** (54 khách)
| nguồn | vào | tạo link | bấm link | có đơn | quay lại ≥2 ngày |
|---|---|---|---|---|---|
| tự vào | 39 | 30 (76%) | 21 (53%) | 9 (23%) | 15 (38%) |
| threads | 13 | 3 (23%) | 3 (23%) | 1 (7%) | 1 (7%) |
- Từ chối 40 lần, trong đó 25 lần «invalid_link» là khách gõ chữ thường (0–48 ký tự): khách muốn hỏi chuyện, bot không hiểu.
- Mời bạn: 4 mã đã tạo, **0** người được mời.

## Chẩn đoán
1. **Store rơi ở bước đầu**: khách đến vì bài «giá AI» (threads_ai_price 50/76) → thấy danh sách → đi. Bot bắt nạp ví trước
   (tối thiểu 10.000đ) rồi mới mua, nhiều bước với món giá 1.100–34.000đ.
2. **Cashbot sản phẩm tốt, kênh sai**: khách tự vào dùng 76%, khách Threads 23%. Tin nhắn chữ không có link bị từ chối, khách đi.
3. **Mời bạn chưa chạy**: chưa ai mời được ai.

## Thử nghiệm (mỗi lần tối đa 2, đo sau 7 ngày, giữ hoặc bỏ)
- [x] **T1 (bắt đầu 15/11) Store — khách mới vào thẳng danh sách món**: trước đó /start → trang chủ «Số dư 0đ · trừ thẳng
      vào số dư» (khách tưởng phải nạp trước) → bấm Mua hàng → … Giờ khách mới thấy luôn danh sách + câu «Không cần nạp
      trước: chọn món → quét QR → bot gửi hàng ngay» (cũng ở trang chủ). Link `buy_<id>` + QR đúng số tiền đã có sẵn.
      Đo 22/11: khách Threads mới từ 16/11 có đơn đầu (gốc 7%).
- [x] **T2 (bắt đầu 15/11) Cashbot — tin chữ → AI (9Router) trả lời**: `cashback_bot/chat_ai.py`. Tin có nội dung (≥4 ký tự,
      không «ok/cảm ơn», không dáng link) → «💬 đang trả lời» → AI trả lời ở luồng nền, qua hàng đợi chung (TG + Zalo).
      AI lỗi / SKIP → câu mẫu cũ. 1 câu AI / khách / 45 giây. Tắt nhanh: bot_state `chat_ai:off`. Không lưu nội dung tin.
      Bật chỉ trong poller.py / zalo_bot.py (`chat_ai_enabled`). Thử thật 9Router 4 câu: đúng, không bịa, rác → SKIP (~12s/câu).
      Đo 22/11: khách bị invalid_link (chữ) có tạo link trong 24h không (gốc: đa số đi luôn).
- [x] T3 (16/11) Cashbot nhắc khách vào 24–72h chưa tạo link: `engagement.send_start_nudges` (START_NUDGE), cả đời 1 lần,
      chung ngân sách 1 tin / 7 ngày, 19:00–21:30, nhường lượt sale, tôn trọng /thongbao. Chạy theo cờ link_nudge_enabled (đang bật).
      Ghi chú cũ: Dùng lại `engagement.py` (đã có LINK_NUDGE cho link chưa
      mua, đang bật; nhắc sale Black Friday 27/11 tối + 12/12 đã được chủ bot duyệt từ 27/10) — chỉ thiếu nhánh «vào chưa tạo link».
- [x] T4 (16/11, Cursor) Store → Cashbot: sau đơn done, mời dùng Cashbot (`store_bot/cashbot_invite.py`,
      mã `store_xsell`, 1 lần/khách; CLI `--send` cho hàng đợi). Đo: khách Store nhận tin → tạo link Cashbot (src store_xsell).
- [x] T5 một phần (16/11, Cursor): chẩn đoán 0 lượt — referral bật, 4 mã tạo, 0 gắn; tin ví chỉ có chữ `/moiban`.
      Vá: tin «tiền vào ví» thêm nút `u:p:invite`. Chưa làm: ảnh chia sẻ / broadcast INVITE_ANNOUNCE.
- [ ] T6 (tuần 4) 12/12: bài ghim + đếm ngược + nhắc khách cũ.

## Hạ tầng (tuần 1)
- [x] Báo cáo 8h sáng (16/11): `cashback_bot/growth_report.py` (chỉ đọc 2 DB) + nối vào vòng poller; một lần / ngày
      (bot_state `growth_report_day`), qua hàng đợi admin. Bản 16/11 gửi tay lúc 08:28 (sent). Tự chạy từ 17/11 sau restart cashback-bot.

## Nhật ký
- 15/11: nhận quyền, đo số gốc, chọn mục tiêu, viết ADR-067.
- 15/11: làm T1 + T2. Proof: test_store_bot (+1) / store_nudge 101 passed; test_cashback_chat_ai 6 passed; bộ cashback + store
  + bot_users + psych_kb chạy lại (xem current-status). Cần restart: `systemctl restart store-bot cashback-bot cashback-zalo`.
- 16/11: chủ bot hỏi sao sáng không có báo cáo — 15/11 mới ghi «next», chưa làm. Làm growth_report + test (2 passed),
  gửi bản 16/11. Số sáng 16/11: dùng thật 7 ngày 25; Store 15/11 vào 50 khách (Threads); T1 0/13 có đơn (qua đêm).
- 16/11: đơn DODORO (ysbSylyJ) về bot 08:39 — Shopee trả chậm ~32h, không phải lỗi sync.
- 16/11: Store đóng tay (closed_manual) từ sau 21:28 15/11 tới ~09:30 16/11, ví FatCat 40.729đ → 35 khách mới gặp shop nghỉ
  (xem món được, không mua được) — T1 đêm đầu không đo được. Thêm đếm bước Store: state `step:product|confirm:<id>` (lần đầu),
  báo cáo sáng hiện vào → xem món → chọn số lượng → mã nạp → đơn + cảnh báo 🔴 khi shop đóng tay. Đo T1 tính lại từ 16/11 sáng.
- 16/11: chủ bot đồng ý (1) không đóng shop khi ví FatCat thấp — đơn chờ ví (waiting_funds) đã có; tin cảnh báo ví thêm
  «Không cần đóng shop»; (2) shop nghỉ → nút «🔔 Báo tôi khi shop mở» (danh sách món + màn món), state `wake:<id>`;
  vòng nền `check_reopen` thấy nghỉ → mở thì nhắn 1 lần rồi xoá (cả đóng tay lẫn giờ nghỉ hằng ngày). 104 passed.
- 16/11 09:31: nhắn 1 lần khách vào Store lúc shop đóng tay (15/11 21:28 → 16/11 09:30), chưa mua, chưa tắt báo: 33 khách →
  32 nhận, 1 đã chặn bot (đánh dấu blocked). Có nút 🔕. Đánh dấu state `reopen_note_1115:<id>`. Đo: số đơn của 32 khách này tới 18/11.
- 16/11: AI Cashbot chưa trả lời câu nào (chưa khách nào gõ chữ từ khi bật). Làm T3 (START_NUDGE) — cashback 1230 passed.
- 16/11 (Cursor, chủ bot giao T4 + T5 nếu còn giờ; Claude tạm không đụng cashback/store): T4 `cashbot_invite` + hook
  `after_sale`; T5 nút mời trên tin tiền vào ví. Proof: test_store_cashbot_invite 7 passed + test nút ví; ruff sạch.
- 16/11 ~11:45 (toàn quyền): restart store-bot + cashback-bot + cashback-zalo; `--send` **10/10 ok, 0 chặn**; hàng đợi 0.
  Baseline src=`store_xsell` = 0 (chờ khách bấm). Chưa commit.
