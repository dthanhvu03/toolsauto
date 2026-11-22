# PLAN-183 — Ba bài Threads cho ZT báo mã

Executor: Codex — chủ bot đã cho ngoại lệ lập PLAN.
Ngày20/11/2026. TASK-069. Trạng thái: Execution Done — bộ nháp/ảnh sẵn; xuất bản/Claude/Anti pending.

## Yêu cầu và startup
Chủ bot chuyển trọng tâm: “em ơi mình làm content đi em”. Đã đọc current-status, PLAN181/182 đầy đủ và ADR066/067; đối chiếu số183/069 với active/archive không trùng. Đây là biên tập nội dung được chủ bot giao trực tiếp, không thay lịch2nháp/6h hoặc workflowAI PLAN179.

## Scope và đầu ra
Soạn3bài Threads, mỗi bài≤470ký tự, giọng tự nhiên: hỏi wishlist; hướng dẫn đọc điều kiện mã; lời mời vào ZT báo mã. Hai bài đầu không link, bài thứ ba reuseinvite PLAN181/hết30/11 và disclosureaffiliate. Không tự dựng giá/mã/đã mua/khách hàng/kết quả hoặc hứa tăngreach.

Tạo2ảnh checklist/wishlist bằng chữ rõ, ghi mẫu ghi chú hoặc checklist, không giả giao diện voucher thật. Bài thứ ba dùng asset ảnh thật PLAN182. Lưu CONTENT.md + content.json và ảnh trong reports/zt-threads-content-20261120/. Kiểm chính tả/độ dài/link/hash, xem trực tiếp cả2ảnh. Không sửa core/HTML/CSS/template/config hoặc tạo công cụ mới.

Đây là bộ nội dung đã soạn, chưa tự đăng thêm bài mới hoặc tự lập lịch; hai bài công khai PLAN181/182 giữ nguyên. Không DM/broadcast/quét/inbox/API/Shopeesync, không restart/commit/push. Ghi rõ trạng thái từng bài, tránh gọi nháp là đã đăng.

## Proof và handoff
Chạy kiểm tra tĩnh độ dài/hash/link/ảnh và visualQA, lưu outputthật. Cập nhật TASK/current-status/PLAN172. Khi xong ghi “Execution Done. Cần Claude Code verify + handoff.”; xuất bản và kết quả vẫn pending.

## Execution Notes / Verification Proof
Đã soạn3bài ZT-BF-C01/C02/C03:245/255/296ký tự. Tạo2PNG1080×1350, reuse1ảnh thật PLAN182; root xem cả2 và xem lại headlineC02 sau sửa thành “Lưu mã rồi, sao không giảm?”. Link chỉ xuất hiệnC03 + disclosure, giữ thời hạn30/11. Mẫu wishlist ghi rõ tự điền, checklist không giả mã hay giá thật.

Kiểm Python vớiPillow/hashlib/json/re:3/3caption+imagehash/dimensions/links/status PASS; output thật reports/zt-threads-content-20261120/verification.json. CONTENT.md vàcontent.json có đủ3caption/ảnh/trạng thái. new_public_actions=0,new_schedules=0. Không viết test cho artifact có thể sửa lại; đã visualQA và kiểm dữ liệu trực tiếp.

**Execution Done. Cần Claude Code verify + handoff.** Đã làm bộcontent, chưa đăng/lập lịch thêm. Xuất bản/kết quả/Claude/Anti pending; không commit/push.
