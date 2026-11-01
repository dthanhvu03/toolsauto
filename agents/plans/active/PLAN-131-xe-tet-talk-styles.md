# PLAN-131 — Xe Tết: lơ xe nói chợ búa theo kiểu Bến xe / Gen Z / Gen Y, đọc đều

- Status: Done (chờ anh cho khởi động lại 8810 để nạp)
- Executor: Claude Code (anh yêu cầu 01/11: «nhiều phong cách chợ búa gen z, gen y, bỏ từ nha với !, nói không nhấn nhá»)

## Làm
- `server/game/talk.py`: bảng câu theo 3 kiểu × 21 tình huống (147 câu): «ben» (lơ xe bến xe: cha nội, hổng chờ, nhích vô),
  «genz» (gét gô, khum, toang, quay xe, ét ô ét, đỉnh nóc kịch trần, uy tín), «geny» (chuẩn không cần chỉnh, bó tay chấm
  com, chất như nước cất, quẩy lên). «mix» (mặc định) bốc trong cả ba. Không «!», không «nha»; chữ lóng Anh viết theo cách
  đọc tiếng Việt cho máy đọc đúng.
- Thiết lập `talk_style` (mix | ben | genz | geny), nút «Kiểu nói» trên /control (phần giọng lơ xe); engine + giọng đọc tên
  lên / xuống xe, cảm ơn quà dùng chung kiểu.
- `voice.speakable`: «!» đọc như dấu chấm (cả câu admin gõ) → giọng đều, không nhấn.

## Proof (01/11)
- pytest 114 passed: mọi câu ở mọi kiểu điền đủ chỗ trống, không «!», không «nha»; kiểu nào cũng đủ 21 tình huống; thiết lập
  tới engine + giọng đọc; «Chào bà con tối nay!!» đọc thành «Chào bà con tối nay.».
