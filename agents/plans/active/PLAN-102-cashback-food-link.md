# PLAN-102 — Link ShopeeFood: báo «sắp có hoàn tiền», vẫn gửi link đặt món gắn affiliate

- Executor: Claude Code. Ngày 29/10/2026, chủ bot yêu cầu: «vẫn triển khai nếu người dùng ShopeeFood, nhưng mình sẽ
  thông báo tính năng sớm triển khai, vẫn gửi lại link food aff cho khách, để khách thích bấm thì bấm».
- Trạng thái: đang làm.

## Bối cảnh
- Thử FOODTEST 28/10 (PLAN-098):
  - link `an_redir` tới `spf.shopee.vn` mở đúng món trong app;
  - app Shopee (Tiếp thị liên kết → ShopeeFood) ghi 1 lượt click ngày 28/10;
  - đơn chủ bot tự đặt không ra trong «Đơn chuyển đổi», chưa rõ lý do.
- Vì vậy chưa hoàn tiền Food được, nhưng link gắn affiliate dùng được.

## Thiết kế
- Khách gửi link ShopeeFood (`spf.shopee.vn`, `shopeefood.vn`):
  - bot trả tin «🍜 Hoàn tiền ShopeeFood sắp có», ghi rõ đơn ShopeeFood chưa được hoàn tiền;
  - kèm nút «🛵 Đặt trên ShopeeFood» = `s.shopee.vn/an_redir?origin_link=<link Food>&affiliate_id=<id>&sub_id=FOODLINK`;
  - trên Zalo, link đặt món là tin riêng, mở đầu «👉 Link đặt món ShopeeFood (đơn Food chưa được hoàn tiền):».
- Chung một sub_id `FOODLINK`:
  - mỗi khách không có mã riêng vì Food chưa hoàn tiền;
  - báo cáo Food của Shopee / AddLiveTag tách được đơn đến từ bot.
- Không lưu link Food. Bản ghi `link_requests` như cũ: `food_link`, chỉ độ dài tin. Telegram gửi lại cùng update thì
  bot ghép lại link từ tin.
- Không gọi nguồn dữ liệu sản phẩm, không tính suất gửi link.

## Không đổi
- Không đổi schema, không thêm `.env`. Không đổi luồng link sàn / TikTok.

## Kiểm
- Test: tin Telegram (chữ, nút, link đúng `origin_link` / `affiliate_id` / `sub_id`, gửi lại cùng update), `food_url`
  (bỏ dấu câu cuối, http → https, bỏ link có user:pass, không nhận link sàn), `build_food_redir` từ chối link không
  phải Food; tin Zalo (chữ «link ở tin dưới», tin link riêng, không có câu «sẽ không được hoàn»).
- Toàn bộ `tests/test_cashback_*.py` + `ruff check cashback_bot`.

## Kết quả (29/10)
- Code:
  - `shopee_url.food_url`; `affiliate.build_food_redir`, `FOOD_SUB_ID = "FOODLINK"`;
  - `messages.FOOD_LINK` (chữ mới), `FOOD_BUTTON`, `food_link_reply(affiliate_url)`;
  - `service._food_link` (cả lúc Telegram gửi lại cùng update);
  - `zalo_render.FOOD_LEAD` + câu «link ở tin dưới».
- Test: `test_link_shopeefood_tra_loi_ro_chua_ho_tro` (sửa), `test_link_shopeefood_chi_ghep_link_food`,
  `test_zalo_link_shopeefood_bao_sap_co_va_gui_link_dat_mon`.
- Toàn bộ: 919 qua, 1 hỏng có sẵn (`test_b9…`, phụ thuộc ngày thật). Ruff sạch.
- Trạng thái: xong code, chờ chủ bot restart.
