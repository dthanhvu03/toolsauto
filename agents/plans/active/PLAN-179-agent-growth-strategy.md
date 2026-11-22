# PLAN-179 — Đổi chiến lược và nhiệm vụ nhóm agent tăng trưởng

> **Owner stopped20/11/2026 — PLAN185:** chủbot hủy toàn bộ agent tăngtrưởng để chọn hướng mới dựa research. Runtime2processstopped/PID0,growth.enabled=false,heartbeatđãxóa; khôngtựbậtlại. Giữcode/history/proof cũ bên dưới. Statusnàythaythế mọi chỉdẫn tiếp tục chạy nền trong PLAN.

| Mục | Giá trị |
|---|---|
| Trạng thái | Execution Done — đã nạp mã; Claude/Anti verify và kết quả48h pending |
| Executor | Codex |
| TASK | TASK-065 |
| Liên quan | PLAN-176, PLAN-178, PLAN-172, ADR-066, ADR-067 |
| Ngày | 19/11/2026 |

## Ủy quyền
Chủ bot yêu cầu trực tiếp “THAY ĐỔI CHIẾN LƯỢC CHO CÁC AGENT, VÀ NHIỆM VỤ CHO CÁC AGENT”. Ngoại lệ cho Codex lập PLAN và triển khai đã được chủ bot cho phép ở phiên PLAN-178, tiếp tục áp dụng cho yêu cầu này. Báo phối hợp vào PLAN-172 trước khi sửa. Không ký thay Anti.

## Vấn đề đã xác minh
Từ 05:24 đến 22:34 VN ngày 19/11: 4 reply Cashbot, 0 reply Store, 0 DM mới, 1 followup skipped. Ba bài deal do lịch cũ. Đợt thử CapCut sau24h:0khách/đơn. Ba chuyên viên chỉ chạy khi cohort đổi, nên không có nhiệm vụ mới. Báo cáo48 bài giữ là24bài bị xét2lần, không phải48cơ hội. Online không phải kết quả kinh doanh.

## Chiến lược 48 giờ
Thử tiếp cận hai nhóm trong cùng Threads worker: nhu cầu mua phù hợp và câu hỏi CapCut cụ thể cần trợ giúp. Trả lời hữu ích trước ở nhóm trợ giúp, tuyệt đối không link/chào bán ở nhánh này. Ưu tiên truy vấn có nhu cầu, xoay truy vấn theo lượt và giảm mỗi tài khoản xuống tối đa6lượt tìm trong trần hiện có. Không tăng số tin để bù chất lượng.

Mục tiêu đánh giá trong48h (mục tiêu, không cam kết): ít nhất5cuộc hỏi đáp hai chiều có phản hồi và2khách mới dùng thật (Cashbot tạo link; Store đơn đã giao). Độ phù hợp của hội thoại chưa có nhãn đầy đủ nên không coi số đã trả lời là lead đủ điều kiện. Cửa sổ đánh giá neo theo mốc bắt đầu, giữ nguyên qua restart. Số quét/reply là chẩn đoán hoạt động, không coi là khách. Mẫu ít/thiếu attribution phải ghi rõ; không đủ dữ liệu thì không tuyên bố uplift.

## Nhiệm vụ mới và đầu ra
| Vai | Việc | Nhịp/đầu ra |
|---|---|---|
| Tìm cơ hội | Ưu tiên người hỏi mua và câu hỏi sử dụng cụ thể; loại seller/job/rác, chống trùng | Mỗi lượt quét hiện tại120phút; đếm buyer/help và lý do loại |
| Tương tác | Giúp đúng câu hỏi; trả lời người chủ động hỏi lại; chuyển tiền/đơn/bảo hành cho chủ shop | Giữ DM10phút/followup20phút, tài khoản được bật |
| Đo kết quả | Tổng hợp khách mới, dùng thật, đơn, hội thoại theo cửa sổ24h/7ngày; tách Threads với nguồn khác | Bảng kết quả chỉ đọc, loại admin/test được cấu hình, không PII |
| Điều phối chuyển đổi | Từ bảng kết quả và nhu cầu đã thấy, chọn tối đa2thử nghiệm/việc cụ thể, có điều kiện giữ/bỏ | Review định kỳ6giờ ngay cả khi cohort0, đề xuất nội bộ |
| Nội dung | Viết2nháp riêng theo vấn đề có bằng chứng, chỉ rõ nhóm đọc/CTA/điều kiện cần xác minh | Review6giờ; draft chưa được đăng tự động |

## Phạm vi source
1. acquisition.py/evaluator.py/runner.py: lane buyer/help_first, chấm helpfulness đúng lane, help-first không biến thành link khi AI lỗi/nháp ngắn; kiểm lại nội dung khi gửi. tests/test_customer_acquisition.py và tests/test_threads_growth.py.
2. Mới search_strategy.py + tests/test_growth_search_strategy.py: pure plan jobs, tối đa6/account/currentcap, ưu tiên query nhu cầu và newest, xoay qua vòng. worker.py dùng planner thay shuffle toàn bộ; hai lỗi trang liên tiếp dừng batch để giữ nhịp tiếp khách.
3. Mới strategy_review.py + tests/test_growth_strategy_review.py: evidence aggregate từ SQLite mode=ro, bảng kết quả24h/7d, ba role review6h; flank riêng khỏi business-event queue của CapCut. Có lock, claim bucket trước AI và per-role checkpoint; không tốn AI mỗi5s, lỗi provider không lặp vô hạn. Lưu latest/drafts/history trong reports/customer-agents/strategy/.
4. growth_funnel.py thêm optional exclusion admin/test có kiểm thử, mặc định cũ giữ nguyên. Không đưa raw conversions/users/source tự do vào prompt; nhóm nguồn whitelist.
5. capcut_supervisor.py dùng executor nền hiện có để chạy review_due ngoài luồng event cũ; không tạo fake cohort events. customer_agents.py/worker.py sửa đếm hold duy nhất mỗi vòng và last_activity chỉ cập nhật khi có hoạt động hữu ích; status ghi chiến lược/missions/lane counts và đường dẫn review.
6. Cập nhật heartbeat đang có: đọc business scorecard + reviews, báo kết quả và đề xuất cần quyết định, không spam “online”/mỗi reply; tránh trùng event/bài. Lập nhiệm vụ/drafts đầu thật trên aggregate, không gửi tin thử.
7. Reload chỉ Threads_Growth và CapCut_Agent_Supervisor sau test, giữ config role/quota/quiet-hours, các bot hệ thống và WIP PLAN-177. Verify code loaded, heartbeat/review có output và giới hạn thực tế.

## Ngoài phạm vi
Không tăng quota/cadence, thêm kênh/browser worker, bật DM AnLinh, coldDM/broadcast, tiền/QR/order/vendor/giá, profile/login, HTML/CSS, commit/push. Nội dung original Store mới chỉ draft. Không thay thử nghiệm T1/T2 của PLAN-172 hay sửa cấu trúc production DB.

## Thứ tự
1. Đọc startup + PLAN đầy đủ; chụp baseline, giao các file không chồng nhau.
2. Implement hai lane/search và review chủ động, test riêng bằng DB/AI/browser giả.
3. Tích hợp trạng thái, counters và background review; chạy regression và replay DB thật readonly.
4. Nạp mã đúng2worker, gọi1lượt review có giới hạn trên dữ liệu thật qua facade hiện có, không gửi khách; ghi rõ fallback nếu AI lỗi.
5. Ghi proof vào PLAN/TASK/current-status; để Anti/Claude verify/handoff pending. Mốc đánh giá48h được lưu để sau này quyết định giữ/bỏ, chưa coi mục tiêu đạt.

## Kiểm chứng và rủi ro
- Boundary: generic edit/xu hướng không tự thành lead; refusal/free/crack/job/seller/dispute không được pitch; help question cụ thể mới mở lane, no URL/offer, fallback im lặng; buyer vẫn dùng đúng link.
- Search: giới hạn/tài khoản/role, rotate, cap0, giữkeyword custom hợp lệ; không vượtbudget hiện tại.
- Review: unchanged cohort vẫn chạy1bucket6h, restart/concurrent không gọi trùng completed role, missing DB báo unavailable không0; claim-before-call là at-most-once attempt/bucket, pending khi hardkill không tự suy success.
- Privacy: loại admin/test theo cấu hình; không xuất khách/ID/handle/rawDM/unknown source/credential. Tổng Store và Cashbot khác định nghĩa không cộng doanhthu.
- Metrics: unique holds, counts không phải conversion, first-touch không perpost/causal, số ngày đủ24h mẫu số chính xác.
- Model errors/long calls không chặn watcher5s; review draft không nối tới sender/queue.

## Rollback
Revert đúng blocks PLAN-179, giữ WIP trước đó; reload riêng2worker. Không xóa queue/customer/history. Giữ evidence và review state để audit.

## Proof và handoff
### Execution Notes
- Đã triển khai đủ phạm vi1–7. Hai lane buyer/help_first kiểm lại bài+nháp trước gửi; helper không URL/offer, AI lỗi hoặc nháp ngắn không đổi thành câu có link. Search tối đa6/account, ưu tiên nhu cầu/newest, xoay query/phân bổ đa bot; hai lỗi trang liên tiếp dừng batch.
- Ba role có review riêng6h ngay cả cohort0, SQL24h/7d + strategy-to-date48h; lock/claim trước AI, tối đa2facade calls/bucket. Đã sửa holdunique/last_activity và status5missions. Không thêm process/browser worker.
- Lượt thật2facadecalls: primary400 chat_completions_disabled, fallback9Router gemini-3.8-flash-n thành công. Bản model có lỗi sản phẩm/chung chung, bị operator đánh needs_revision, giữ rawhistory; đã có2thử nghiệm/2nháp sửa nội bộ trong reports/customer-agents/strategy/OPERATOR-REVIEW-20261119.md, chưa gửi khách. Future buckets có offer_context từ code/catalog whitelist và semantic gate; không tái gọi bucket cũ để sửa báo cáo đẹp.
- Đã đổi heartbeat hiện có thành“Theo dõi kết quả nhóm agent”,15phút/cùng chat: báo kết quả/hội thoại/việc cần quyết định, không báo mỗi reply/online. Đọc lại automation.toml xác nhận ACTIVE/id/cadence/thread và PLAN-179 trong prompt.

### Verification Proof thực tế
```
venv/bin/python -m pytest -q tests/test_growth_strategy_review.py tests/test_growth_search_strategy.py tests/test_customer_agent_runtime.py tests/test_customer_acquisition.py tests/test_customer_engagement.py tests/test_threads_growth.py tests/test_threads_dm.py tests/test_psych_kb.py tests/test_capcut_supervisor.py tests/test_capcut_supervisor_runtime.py tests/test_store_campaign.py tests/test_growth_funnel.py tests/test_growth_report.py
394 passed in 72.91s (0:01:12)
Ruff: All checks passed!
py_compile + git diff --check: exit 0
same-bucket probe: already_attempted, provider_calls=0, state_unchanged=true
pm2 restart Threads_Growth CapCut_Agent_Supervisor: exit 0, both success
```
23:16:45VN: Threads PID1318674→3184112/restarts26→27; supervisor242927→3186655/3→4; online/unstable0. Status thật có PLAN-179/missions/counters và review6h/poll5s. Các PM2 khác PID không đổi so snapshot ngay trước reload;3systemd bot vẫn active/samePID, roleshash unchanged. Independent reviewer34tests/28,91s, không blocker mới. Full proof + snapshots: reports/customer-agents/strategy/ROLLOUT-20261119.md, rollout-before.json, rollout-after.json.

### Kết quả đang chờ
Mốc bắt đầu23:03:51VN19/11, đánh giá23:03:51VN21/11; review sau00:00VN20/11. SQLreadonly23:17:24VN: **0hội thoại hai chiều,0khách mới dùng thật** từ mốc bắt đầu; không nói đạt mục tiêu. Độ phù hợp hội thoại chưa đo đầy đủ, chưa khử trùng xuyên kênh/bot và chưa attribution theo bài. Lượt AI đầu không qua duyệt nội dung dù structurally ready; operator-review.json là trạng thái biên tập ưu tiên cho slot đó.

**Execution Done. Cần Claude Code verify + handoff.** Anti sign-off/Claude verification và kiểm chứng kết quả48h pending, không Done/archive mục tiêu kinh doanh.
