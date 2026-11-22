# PLAN-180 — Thử nội dung tuyển chọn + link Shopee trên Threads

| Mục | Giá trị |
|---|---|
| Executor | Codex — ngoại lệ lập PLAN đã được chủ bot duyệt |
| TASK | TASK-066 |
| Ngày | 19/11/2026, giờ Việt Nam |
| Trạng thái | Execution Done — một bài thật đã verify; hiệu quả/Claude/Anti pending |
| Liên quan | PLAN-172/177/179, ADR-066/067 |

## Ủy quyền và phối hợp
Chủ bot yêu cầu trực tiếp: “oke em thử trên threads với mô hình rải link shopee và làm content trên theads thử đi”. Được chuẩn bị và xuất bản lượt thử thật, gồm tra cứu sản phẩm/tạo link cần thiết cho bài, không phải yêu cầu xin phép lại. Ngoại lệ cho Codex lập PLAN và triển khai từ PLAN-178 tiếp tục áp dụng. Ghi phối hợp PLAN-172 trước code/action. Không ký thay Anti. ADR-067 cấm tự đồng bộ Shopee vẫn áp dụng cho sync rộng; lần này chỉ tra tối đa3món đã chọn và tạo tối đa3link phục vụ yêu cầu trực tiếp.

## Thử nghiệm cụ thể
Một bài tuyển chọn tối đa3món thời trang nữ dưới200k, có link affiliate Shopee riêng từng món, trên @us28qt (Cashbot). Nội dung gồm nhu cầu/ngân sách, tên món rút gọn, giá tham khảo đã kiểm, câu hỏi gợi phản hồi và nhãn link tiếp thị liên kết. Không giả đã mua/dùng, không hứa chất lượng/hoàn tiền hay dùng mức hoa hồng17–18% từ ảnh làm mức hoàn. Link chiến dịch công khai không gắn ví/cashback của khách hoặc admin. Dữ liệu thiếu thì giảm số món, không bịa.

Đây là một bài original bổ sung theo yêu cầu trực tiếp, không bật scheduler mới hoặc tăng quota. Mọi publicaction chỉ trên chính tài khoản/bài thử; không rải lặp vào bài người lạ, không DM/broadcast. Giữ mọi inbound/giờ nghỉ00:30–06:30VN và quyền AnLinh hiện có. Nếu sang giờ nghỉ trước publish thì giữ bản cụ thể và chờ giờ hợp lệ.

## Phạm vi
1. Readonly kho deal/cache, chọn tối đa3món có IDs/name/url/time/giá đáng dùng; xác minh giới hạn qua ProductData hiện có nếu cần. Không bật native, đổiPRIMARY, gọi order sync, sửa sản phẩm/tiền/ví/giá hay chạy chiến dịch khách.
2. Lưu manifest công khai dưới reports/threads-shopee-20261119/: nội dung,3sản phẩm,sub_id8ký tự riêng từng món,quote provenance/time,link,claims và giới hạn. Tạo link bằng bridge hiện có, failclosed; không đổi bridge/npm/session/login/config. Nếu xác minh ảnh có sẵn thì chỉ dùng ảnh sản phẩm thật; không tạo ảnh giả sản phẩm.
3. Script vận hành trong thư mục report, dùng GrowthBrowser hiện có; preflight mặc định không publish. Kiểm role, giờ nghỉ, hạn mức gộp hoạt động đã có, DBaccountACTIVE, profileunlocked và liveidentity. Claim một slot duy nhất trong own_posts trước create_post, lưu unknown trước hành động; tối đa1create_post cho slot. Retry chỉ khi chứng minh chưa gọi create_post; unknown phải verifyreadonly trước, không đăng lại mù.
4. Tránh tranh profile: chờ worker idle/profile rảnh, tạm dừng riêng Threads_Growth nếu cần cho phiên xuất bản, khôi phục trong finally ngay khi đóng browser; ghi PID/trạng thái trước/sau. Không stop/restart systemdbot, supervisor, bridge hoặc app khác. Không đổi quota/cadence/roles.
5. Verify permalink và text/đúnglinks bằng lượt đọc thật; ghi vào own_posts đúng slot, không tạo growth reply/khách giả. Không coi click tự kiểm/linkpreview là khách.
6. Bảng đo readonly theo mã chiến dịch và lượt phản hồi thực; kiểm khả năng order-import có lưu unknownsubids trước khi hứa attribution. Impressions/click/hoa hồng không có dữ liệu phải ghi unavailable, không0. Đơn pending/hoa hồng dự kiến không gọi tiền thực nhận. Giữ PLAN17948h riêng.
7. Cập nhật heartbeat hiện có để theo dõi bài thử, không thêm lịch; báo bài thật khi xuất bản, kết quả/đơn hoặc lỗi đáng xử lý sau đó. Ghi proof PLAN/TASK/current-status/PLAN172, Claude/Anti verify pending.

## Verify và rủi ro
Test trọng tâm bằng temporarySQLite/browserfake cho fence/unknown/no-duplicate, identity/role/quiet/quota, quote/linkallowlist và dry-run. Không viết test lặp cho nội dung Markdown. Ruff/compile/diffcheck script có sửa. Lượt thật chỉ1publish, ghiURL+time+bodymatch+links và DBrow. Nếu checkpoint/challenge dừng, không thử vượt. API403/challenge không retry; lỗi nguồn không biến thành claim giá/hoa hồng chắc chắn.

## Rollback và handoff
Khôi phục Threads_Growth trong finally; không xóa bài đã đăng hay dữ liệu/slot/history khi chưa có yêu cầu. Không commit/push, không sửa source/WIPPLAN-177 hoặc HTML/CSS. Kết thúc ghi “Execution Done. Cần Claude Code verify + handoff.” cho phần đã có proof; kết quả kinh doanh tiếp tục theo dõi, không tự Done/archive.

## Execution Notes / Verification Proof
- Đọc current-status, PLAN172/178/179, ADR066/067; tạo/đọc đầy đủ PLAN180 và phối hợp trước code/action. Hai agent inventory/runbook, reviewer độc lập; chỉ root gọi2ProductData+2shortlink và1publish. Không đọc/gửi rawinbox.
- Chọn2món chưa có trong own_posts3ngày: JUSTDUNZ12/49.500đ, NgọcBích9678/192.580đ; ProductData xác minh đúngID/giá/source/time, links riêngTH180A02/TH180A01 không trùng khách. Không chọn món thứ3đã đăng gần đây. Manifest/text339ký tự có giá tham khảo/disclosure, khôngclaimảnh/tồn/cashback; CONTENT.md bản chính xác.
- Scripttrial_runtime.py mặc địnhpreflightreadonly; unknownfence trướccreate, khônglặp, liveidentity, role/quietrecheckcuối,quota gộp original/reply, stop/start riêngThreads_Growth vàfinallyrestore; verifykhôngrepost. measure_trial.py chỉ đọc importedaggregate, phân biệt unavailable vàmissingnet, trảlastsuccesswindow.
```
venv/bin/python -m pytest -q tests/test_threads_shopee_trial.py tests/test_threads_shopee_measurement.py
21 passed in 2.40s
Ruff All checks passed!; py_compile và git diff --check exit0
preflight blocked=[], public_last_hour0/public_last_day7
--publish: posted, create_post_called=true, verified_live_handle=us28qt
permalink_content_and_links_verified=true, worker_restored=true
own_posts slotthreads-shopee-180-p1: đúng1dòngposted
```
- Bài thật **https://www.threads.com/@us28qt/post/Df7lHTTnRXl**. Attempt00:06:10VN20/11→verify/finallydone00:07:49VN; đúng1create_post, khôngretry. Nội dung/2link khớp trên permalink. Mộtpreflightbusy trướcđó khôngclaim/publish.
- Threads_GrowthPID3184112→3563054online/unstable0 sau pause/restore. PM2khác vàsystemdbotPID/starttime khôngđổi, env/roleshashsame; profile cuốiunlocked. Khôngcore/WIPPLAN177/PRIMARY/native/sync/commit/push. Reviewer12artifactcheckspass, không mởbrowser/xuấtbảnthêm.
- Heartbeat hiện có đã thêmURL/mãcampaign+measure readonly, giữACTIVE/15phút/cùngchat, readbackconfirmed. Không thêm lịch.
- **Kết quả kinh doanh chưa biết**:00:14:16VN có0importedclicks/conversions nhưng syncwindow kết thúc20:45:34VN19/11 trướcbài, khôngcoi0thực. Impressions/cashreceived/customeruseattributionunavailable; hoa hồngghi nhận khôngtiềnđãnhận/lợinhuận. Mục tiêuPLAN179giữriêng.

Full proof: reports/threads-shopee-20261119/REPORT.md, manifest.json, quotes.json, links.json, trial-publication.json, runtime-baseline.json/runtime-after.json và measurement.json. **Execution Done. Cần Claude Code verify + handoff.** Anti/Claude và đánhgiákếtquảpending, không Done/archive mục tiêu kinh doanh.
