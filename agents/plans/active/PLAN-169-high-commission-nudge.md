# PLAN-169 — Kéo khách sang món hoàn cao (C → B → A)

- Trạng thái: chủ bot duyệt 12/11 («oke vậy em triển khai đi nhé»). Executor: Claude Code (chủ bot giao trực tiếp).
- Bối cảnh: link bot tạo trung bình ~7,95% hoa hồng nhưng đa số đơn về 2,5%. 4/9 đơn có link: khách mua món / shop
  khác nên mất phần XTRA (XTRA do shop góp, chỉ tính khi mua đúng shop; khác shop chỉ còn Shopee Comm ~2,5%).
  Khách cần giảm giá → mọi thứ xoay quanh «rẻ + hoàn».
- Giữ nguyên: thẻ Telegram dùng link dài `an_redir` (hoa hồng như link rút gọn, không chậm 2–4,5 giây, không phụ thuộc
  shopee-mcp). Không hứa «hoàn X%», số vẫn là «ước tính / khoảng».

## Phạm vi (mỗi mục một công tắc, admin bật/tắt)
1. **C — Nhắc mua đúng món ở món có XTRA.** Thẻ link có hoàn và có phần shop góp (`seller_commission_vnd > 0`) thêm
   một dòng ngắn. Món không XTRA giữ thẻ như cũ (thẻ tối giản theo chủ bot 31/10). Công tắc mặc định bật.
2. **B — Deal hời xếp theo tổng tiết kiệm** = (giá thường − giá nay) + số hoàn; món hoàn cao có nhãn «🔥 Hoàn cao».
   Không gọi thêm API (kho deal đã có số hoàn).
3. **A — Gợi ý món tương tự, sau hoàn rẻ hơn (thử nghiệm).** Sau thẻ link món không XTRA, tìm món cùng loại có
   (giá − hoàn) thấp hơn rõ rệt → 1 nút gợi ý. Tối đa 3 lần/khách/ngày, link gợi ý đánh dấu để đo. Chạy ~2 tuần,
   ít người bấm thì tắt.

## Ngoài phạm vi
- Không đổi cách tính hoàn, không đổi link Telegram sang rút gọn, không đổi /magiam.

## Tiến độ
- [x] **C** (12/11): `cashback_bot/upsell.py` (công tắc `xtra_card_note_enabled`, mặc định bật), dòng `XTRA_HINT`
  «📌 Mức hoàn này chỉ có khi mua đúng món, đúng shop này.» ngay dưới số hoàn, chỉ khi có hoàn và
  `seller_commission_vnd > 0`. Admin: 🔥 Deal hời → «⚪ Tắt / 📌 Bật nhắc đúng món» (`c:dl:xn:on|off`, ghi lịch sử).
- [x] **B** (12/11): `upsell.deal_rank` — kho deal, tin deal gửi khách và 🔥 Deal hôm nay xếp theo
  (giá thường − giá nay + hoàn) / giá thường; món hoàn ≥ 4% giá có nhãn «· 🔥 hoàn cao». Công tắc
  `deals_rank_by_saving` (mặc định bật; tắt = xếp % rẻ hơn như cũ, không nhãn), admin `c:dl:sv:on|off`.
- Proof C+B: tests/test_cashback_plan169.py 6 passed; cashback + zalo + deal + bot-users 1219 passed, 1 hỏng sẵn
  phụ thuộc giờ thật (`test_b9_doi_tai_khoan_cho_7_ngay…`); ruff sạch.
- Cần: `systemctl restart cashback-bot cashback-zalo`.
- [ ] **A**: chờ chủ bot chốt cách tìm «món tương tự» (xem handoff).
