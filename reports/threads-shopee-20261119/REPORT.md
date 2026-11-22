# PLAN-180 — Bài thử Threads + link Shopee đã xuất bản

## Kết quả thật
URL: https://www.threads.com/@us28qt/post/Df7lHTTnRXl

Tài khoản @us28qt, một original339ký tự, đúng một lần gọi create_post. Attempt bắt đầu **00:06:10VN20/11/2026**, đọc lại permalink và hoàn tất lúc **00:07:49VN**. Đây là mốc bắt đầu attempt, không khẳng định giây bấmPost chính xác. Liveidentity khớp; đọc payload/DOM sau xuất bản khớp nội dung và đủ2link. own_posts có đúng1dòng slotthreads-shopee-180-p1/statusposted/URL trên. Không gửi reply/DM/broadcast trong lượt thử.

## Nội dung và nguồn hàng
Chọn một món dưới200k, gợi người đọc chọn áo basic hoặc chân váy xếp ly, nhắc xem size/ảnh đánh giá đúng phân loại. Có nhãn“Link tiếp thị liên kết”, giá tham khảo có thể đổi; không nói đã mua/dùng, không hứa chất lượng/tồn kho/hoàn tiền. Nội dung nguyên văn ở CONTENT.md và manifest.json.

| Món | Giá đã kiểm | Nguồn cập nhật | Mã riêng | Link |
|---|---|---|---|---|
| JUSTDUN Z12 dài tay |49.500đ|ProductData/db23:02:02VN19/11|TH180A02|https://s.shopee.vn/9KjkH8yoPR|
| Chân váy NgọcBích9678 |192.580đ|ProductData/api23:56:07VN19/11|TH180A01|https://s.shopee.vn/4fxuiZ8fjm|

Hai món chưa có trong own_posts3ngày gần nhất tại inventory. Chọn2thay vì3vì ứng viên thứ3đã đăng gần đây. Hai boundedProductData calls hợp lệ, đúngshop/item, giá dưới200k, elapsed0,550s/0,390s. Bridge hiện có tạo2link với subidriêng trong3,104s/2,214s; không đổiPRIMARY/native, gọi sync hoặc đổi session. Không dùng AUTOSALE/customerlink. Ảnh sản phẩm và tồn kho không có dữ liệu nên không dựng ảnh sản phẩm hay claim tồn; bài text/link. Không tự click redirect kiểm mua, không tạo link_requests/khách/đơn giả.

## Proof vận hành và kiểm thử
```
PYTHONPATH=. venv/bin/python reports/threads-shopee-20261119/trial_runtime.py
preflight: blocked=[], combined_public_last_hour=0, combined_public_last_day=7

PYTHONPATH=. venv/bin/python -u reports/threads-shopee-20261119/trial_runtime.py --publish
status=posted; create_post_called=true; verified_live_handle=us28qt
permalink_content_and_links_verified=true; worker_restored=true

venv/bin/python -m pytest -q tests/test_threads_shopee_trial.py tests/test_threads_shopee_measurement.py
21 passed in 2.40s
Ruff: All checks passed!
py_compile: exit0
git diff --check: exit0
```
Một preflight trước đó gặp worker đang làm việc nên blockedworker_idle, không claim hoặc gọi publish; sau khi workerwaiting mới chạy thật. Script có durableunknownfence, chặn mọi attempt đã có, kiểm lại role/giờ nghỉ ngay trước create_post và dùngverifyreadonly cho kết quả chưa rõ. Test dùng browser/PM2 giả và SQLite tạm; có fence, unknownkhôngrepost, identity, KeyboardInterrupt, quietboundary, quota gộp cả original/reply, SQLmissingdata/readonly.

Trong phiên xuất bản chỉ stop/start Threads_Growth để không tranh profile. PID3184112→3563054, online/unstable0 sau khôi phục; restartcounter27giữ nguyên. PM2 app khác giữ đúng PID/trạng thái/counter so ngay trước phiên. store-bot3966961/cashback-bot1456507/cashback-zalo1456511 active, PID/starttime không đổi. Hash.env và roles trước/sau khớp. Profile kiểm cuốiunlocked; lúc worker vừa phục hồi có thể bị worker giữ bình thường. Không commit/push, sửa core hay WIPPLAN-177.

Review độc lập trên artifact:12kiểm chéo PASS, không blocker. Reviewer không mở browser xác minh riêng; prooflive là lần đọc lại permalink trong phiên xuất bản. Reviewer phát hiện câu“outfit dưới200k”mơ hồ đã sửa thành“chọn một món”trước đăng, và quietgate cuối đã sửa/test trước action.

## Đo kết quả và theo dõi
Đo bằng `PYTHONPATH=. venv/bin/python reports/threads-shopee-20261119/measure_trial.py`, chỉ đọcSQLite, không gọi sync. Hai mãcampaign chưa từng dùng, không trùng link khách; conversionkhôngkhớpkhách vẫn được hệ thống lưu, không tạo cashback cá nhân.

00:14:16VN20/11:0bản ghi click/đơn đã import cho hai mã. **Chưa có dữ liệu để kết luận lượt bấm/đơn thực sau đăng**: importthànhcông cuối20:45:47VN19/11, window_end20:45:34VN, trước bài; completed_after_attempt=false và window_covers_attempt=false. Giữ measurement-baseline.json/measurement.json để đối chiếu sau những lần sync tự nhiên. Không đồng bộ thủ công.

Clicks là bản ghi, không phải người; linkpreview/tựclick có thể ảnh hưởng. Tách conversionrows/distinctorders và trạng thái validation/settlement; commissionquoted/recorded/pending không là tiền đã nhận/lợi nhuận. Impressions, cashreceived và Cashbotcustomeruse quy cho bài hiệnunavailable. Không cộng campaign này vào PLAN1795hội thoại/2kháchdùng nếu thiếu bằng chứng độc lập.

Heartbeat hiện có idtheo-d-i-t-th-capcut đã cập nhật qua automation_update, ACTIVE/15phút/cùngchat, readbackhasPLAN180+URL=true. Theo dõi mãcampaign/nguồn đọcreadonly, chỉ báo kết quả hoặc vấn đề đáng xử lý; việc xuất bản đã báo trongchat nên không báo lại. Không thêm automation/sender và không cho heartbeat chạy--publish/--verify, sửaqueue hoặc restart.

**Execution Done. Cần Claude Code verify + handoff.** Lượt thử kỹ thuật đã có bài thật; hiệu quả khách/đơn/hoa hồng còn chờ dữ liệu và Anti/Claude reviewpending, không Done/archive mục tiêu tăng trưởng.
