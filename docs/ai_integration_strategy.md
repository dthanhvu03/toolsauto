# Tích hợp AI Miễn Phí vào Theo Hướng Affiliate Reels

Việc tích hợp AI vào `toolsauto` không chỉ **nên** làm, mà nó là **chiếc chìa khóa cuối cùng** để anh rảnh tay 100% trong quy trình Affiliate. Nếu không có AI, anh vẫn phải tự viết Caption (Mô tả) cho từng video và lên kịch bản Comment (CTA) cho khách hàng click. 

Dưới đây là phương án làm sao để hệ thống có một "bộ não Content" tự động hóa hoàn toàn **MÀ KHÔNG TỐN MỘT ĐỒNG PHÍ NÀO**.

---

## 1. Nên dùng con AI Miễn Phí nào tốt nhất hiện nay?

Chắc chắn là **Google Gemini API (Phiên bản Flash hoặc Pro Free Tier)**. 

### Lý do chọn Gemini API:
1.  **Hoàn toàn Miễn phí (Free Tier cực lớn):** Google cho phép anh gọi API **15 request / phút (1,500 requests/ngày)**. Đối với Tool của anh (10-20 Video một ngày), ngưỡng này là xài tẹt ga không bao giờ lố. (Khác với ChatGPT API bắt buộc phải nạp tiền ngay lập tức).
2.  **Hỗ trợ Tiếng Việt xuất sắc:** Gemini viết content thả thính, giật tít, bán hàng TikTok/Shopee cực kỳ "sao số" và hợp trend.
3.  **Hỗ trợ Đa phương tiện (Multimodal):** (Tương lai) Nó có thể "xem" luôn cái Video của anh để tự viết Caption phù hợp với Video đó! (Ví dụ: Video chị kia giáp quần áo -> tự nghĩ ra Caption bán nước giặt).
4.  **Thư viện Python sẵn sàng:** Dễ dàng `pip install google-generativeai` vào dự án của mình mà không cần setup phức tạp.

---

## 2. Áp dụng AI vào Tool của anh như thế nào để ăn tiền?

Ở hướng Số 3 (Affiliate), ta sẽ chèn AI vào khâu **Xử lý Text tự động** (Auto Text Generation) trước khi đẩy lên Playwright.

### Tính năng A: AI Tự động sinh Caption (Mô tả Video) "Giật tít"
Thay vì anh phải copy paste một cái Caption chung chung cho 100 Video, Tool sẽ gửi tín hiệu cho AI:
> **Prompt cho AI:** *Hãy đóng vai một reviewer Tikok Gen Z. Viết cho tôi 1 câu caption dài 2 dòng để đăng Facebook Reels về "Dụng cụ dọn vệ sinh nhà cửa". Yêu cầu dùng emoji vui nhộn, từ lóng học sinh, nhắc nhở người xem nhấn vào phần bình luận để lấy link mua hàng.*

*Tác dụng:* Mỗi video lên Facebook là một Description hoàn toàn mới lạ. Facebook không thể quy kết đây là hành động spam!

### Tính năng B: AI Tự động trộn Comment mồi Affiliate
Việc lập lại 1 đường link Shopee kèm 1 câu chốt "Mua ở đây: [link]" 100 lần chắc chắn chết tài khoản (Spam Alert).
> **Prompt cho AI:** *Trộn cho tôi 1 câu kêu gọi mua hàng (Call to action) tự nhiên, có vẻ như một người bình thường tình cờ thấy sản phẩm này hay và chia sẻ. Thêm biến số {link} vào cuối kèm icon chỉ tay mũi tên.*

*Kết quả AI trả về:*
- "Bữa giờ tìm mãi mới thấy gian hàng này bán rẻ rề, bác nào cần thì xúc lẹ nha 👇 {link}"
- "Lúc xem video thấy hay quá xin được link luôn cho nóng nà: {link}"
*Tác dụng:* Thoát 100% án phạt Spam Link và Comment của Facebook.

### Tính năng C: Phân tích Video bằng AI (Đỉnh lưu của Auto)
Với sức mạnh của Gemini 1.5 Flash (chạy nhận hình ảnh mượt mà), Tool FFmpeg (MediaProcessor) có thể trích 1 tấm hình Thumbnail từ Video, ném lên Gemini hỏi: *"Đây là video về sản phẩm gì?"*. Gemini trả lời là "Bộ lau nhà thông minh", Tool tự lấy khóa tìm kiếm đó để search Link Shopee tự động! *(Anh thậm chí không cần tự đi nhặt link Shopee nữa).*

---

## 3. Cách triển khai Code (Rất Dễ Dàng)

Nếu anh chốt phương án này, em có thể giúp anh code thêm một Service gọn nhẹ vào `app/services`:

```python
# Ví dụ cấu trúc file sắp tới: app/services/ai_helper.py
import google.generativeai as genai

def generate_reels_caption(product_keyword: str) -> str:
    # 1. Gọi Gemini API (Sử dụng API Key miễn phí lấy từ Google AI Studio)
    # 2. Sinh caption độc quyền
    # 3. Trả Text về cho file worker.py điền vào Playwright
```

**Kế hoạch tiếp theo:** 
Anh hãy tạo một tài khoản Google, truy cập vào **Google AI Studio** (aistudio.google.com), bấm **"Get API Key"** (Nhanh và hoàn toàn miễn phí). Cất Key đó đi, hôm nào rảnh anh em mình nhét nó vào hệ thống là Tool của anh "mọc cánh" bay luôn!
