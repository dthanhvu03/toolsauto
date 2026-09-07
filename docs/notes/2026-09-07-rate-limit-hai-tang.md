# Rate limit hai tầng của Facebook — và tool đang tôn trọng tới đâu

> Ghi 2026-09-07. Nguồn: bài "Social post: Tại sao 0 view?" (Jack Nguyễn), đối chiếu với
> tài liệu Meta agent đã mở cùng ngày (`docs/research/2026-09-07-tich-hop-mien-phi.md` §4).

## Ý chính của bài (đã đối chiếu)

| Ý | Đối chiếu tài liệu Meta | Kết luận |
|---|---|---|
| **Page Access Token** → Business Use Case (BUC) rate limit, tính **theo Page**, cửa sổ trượt 24h; Page mới hạn mức rất thấp | Pages API: **4800 × số engaged users / 24h** cho mỗi Page. Page mới ≈ 0 engaged users ⇒ hạn mức gần 0 | ✅ đúng, có số cụ thể |
| **User Access Token** (via) → Platform rate limit theo người dùng: giờ, ngày, và QPS | Platform limit: 200 call × số user / giờ; có chặn burst | ✅ đúng |
| Hai tầng tồn tại **đồng thời**; đổi via không cứu Page cạn hạn mức, đổi Page không cứu via cạn hạn mức | Hai cơ chế độc lập trong doc | ✅ đúng — điểm giá trị nhất của bài |
| Bài "thành công" nhưng **0 view thật** do ngưỡng ngầm chống spam/đề xuất | Không có tài liệu công khai | ⚠️ chỉ kiểm chứng bằng quan sát |
| Dính limit mà cố đăng ⇒ thời gian hồi kéo dài | Doc nói vượt limit thì bị chặn tới khi cửa sổ trôi; không nói kéo dài | ⚠️ kinh nghiệm cộng đồng, hợp lý, chưa có nguồn chính thức |

**Tách bạch với trường hợp của Owner:** tài khoản mất 31/07/2026 **không phải** vì rate limit
— đó là lớp *Account Integrity* (cookie phiên rò rỉ + automation qua trình duyệt, hành vi
Meta cấm thẳng). Rate limit là chuyện *sau khi* dựng lại Page trong BM.

## Tool đang tôn trọng hai tầng này tới đâu

| Nguyên tắc | Tool | Trạng thái |
|---|---|---|
| Hạn mức theo **Page** | `publish.posts_per_page_per_day` — đếm DONE hôm nay theo `target_page` + nền tảng | Mặc định nay = **2** (trước = 0 = tắt) |
| Hạn mức theo **via** | `Account.daily_limit` mặc định 3/ngày | ✅ |
| Không dồn bài | `Account.cooldown_seconds` giữa 2 bài cùng account+nền tảng + nghỉ ngẫu nhiên 30–90 s | Mặc định nay = **14400 s (4 giờ)** (trước 1800 s = 30 phút) |
| "Sáng – trưa – tối" | Không có logic giãn theo buổi | Dùng hẹn giờ tay; cooldown 4 giờ đã ép giãn |
| 1 via → nhiều Page cùng lúc | Mutex 1 job RUNNING / (account, nền tảng) ⇒ đăng tuần tự | Bảo thủ hơn bài — an toàn, chỉ chậm |
| Dính limit thì dừng | Circuit breaker vô hiệu account khi lỗi liên tiếp | ✅ với lỗi rõ; ❌ với "0 view thật" (không có tín hiệu máy đọc được) |

## Quy tắc vận hành rút ra

1. **Page mới**: 2 bài/ngày/Page, cách nhau ≥ 4 giờ, khung sáng – trưa – tối. Không hơn
   trong 2 tuần đầu (khớp TASK-058).
2. **1 via gánh ≤ 3 Page**, tổng ≤ `daily_limit` = 3 bài/ngày/via lúc đầu.
3. **Graph API với Page mới**: hạn mức BUC gần 0 ⇒ *mỗi lời gọi đều đếm*, kể cả poll trạng
   thái Reel. Script spike poll **30 s/lần**; trong lúc test chỉ đăng 1–2 bài/ngày.
4. Thấy dấu hiệu limit (lỗi 4/17/32/613, hoặc 0 view thật 2 bài liên tiếp): **dừng 24 giờ**,
   không đổi via/Page để "lách".
5. Không dùng lại via cũ đã bị khoá cho bất kỳ Page mới nào.

## Nguyên văn bài (lưu để khỏi mất)

Thông thường ae vẫn nghe các Bro chỉ dẫn 1 ngày page phải đăng bao nhiêu post để tránh 0
view… thì đấy đều là theo cảm tính. Bài này đưa ra 1 góc nhìn để hiểu bản chất và cách thức
các nền tảng social đưa ra quyết định như thế nào.

Trước tiên anh em phải hiểu là FB không cấm bạn dùng tool hay API, nhưng họ có một "luật
ngầm" mang tên Rate Limit. Nếu không hiểu rõ sự khác nhau giữa User Token (Via) và Page
Token, bạn sẽ liên tục bị khoá mõm mà không hiểu lý do.

**A. Page Access Token** — Business Use Case (BUC) Rate Limits: giới hạn phân bổ riêng cho
từng Page trong khung thời gian trượt 24 giờ. Page có lượng tương tác và người xem càng cao
thì hạn mức càng lớn. Page mới hạn mức cực kỳ thấp, mỗi ngày chỉ nên rải rác vài bài.

**B. User Access Token** — Platform Rate Limits: giới hạn tổng số thao tác của từng tài khoản
trong 1 giờ và 24 giờ; thêm giới hạn truy vấn mỗi giây (QPS) — gửi dồn dập là bị chặn ngay.

Hai tầng A và B tồn tại cùng lúc, có thể còn tầng thiết bị/IP/quốc gia. Tránh được cả A và
B thì bài post tối ưu nhất.

Ví dụ: Page mới đăng 20 bài/ngày → quá limit Page → SAI. Page mới 3 bài/ngày OK, nhưng 3
bài/phút → quá limit giờ của Page → SAI. Page mới 3 bài sáng–trưa–tối → OK. 10 bài × 5 Page
bằng 1 via → Page OK nhưng via quá limit ngày → SAI. 1 via đăng lên 3 Page một lúc → OK hơn
1 via đăng 1 Page 3 bài một lúc (spam 0 s delay thì < 10 view).

Đó là lý do Page 0 view mà đổi via vẫn nghẽn — cái cạn là Page, không phải via. Via dính
limit ngày thì đổi n Page cũng không đăng được. Một số via/Page có limit cao hơn đôi chút.

Chính sách chống spam và cơ chế đề xuất cũng có "hạn mức ngầm" — bài báo thành công nhưng
reach vĩnh viễn 0 view (0 view thực sự). Dính limit mà cố đăng thì thời gian hồi có thể
kéo dài — tác giả từng bị khoá đúng 1 năm vì cố đấm ăn xôi.

Hiểu bản chất limit thì tự tính được: 1 ngày nên đăng bao nhiêu bài/Page, 1 via gánh bao
nhiêu Page, Page mới đi bài tần suất thế nào.

— Jack Nguyễn
