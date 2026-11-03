# PLAN-128 — Xe Tết: giọng Anh Tư lơ xe

- Status: Done (chờ anh nghe thử trên 8810)
- Executor: Claude Code (anh chốt 01/11: «VieNeu trên máy + dự phòng edge-tts»; đọc câu lơ xe, tên khi thả khách, tên khi
  lên xe, cảm ơn quà)

## Làm

- `server/voice.py` (Announcer): sự kiện → câu đọc (câu lơ xe tự nói + admin gõ; «Về tới X rồi! A, B và N người nữa xuống
  xe nha!» — xe chính và xe tăng cường đang chiếu; tên lên xe gom 3 giây, cách nhau ≥ 8 giây; cảm ơn quà lên bậc, mỗi người
  ≤ 1 lần / 30 giây, quà gọi xe tăng cường thì để lơ xe nói câu riêng). Chuẩn hoá chữ đọc (km → ki-lô-mét, TP.HCM, bỏ emoji
  trong tên).
- Đọc bằng VieNeu (`POST :8790/tts`, giọng mặc định Adam — nam, miền Nam, tự nhiên; 25 giọng chọn trên /control); VieNeu
  tắt / lỗi → edge-tts `vi-VN-NamMinhNeural`. Câu đã đọc lưu `storage/media/xe_tet/voice/` (giữ 600 câu gần nhất).
- Hàng đợi ưu tiên (admin > thả khách > quà > lơ xe > tên lên xe), phát lần lượt; dồn quá 3 câu thì bỏ câu ít quan trọng.
- Overlay phát giọng, nhạc nhỏ còn 30 % khi lơ xe nói. /control: bật / tắt, chọn giọng, âm lượng, ▶ Nghe thử.
- `edge-tts==7.3.1` thêm vào `xe_tet/requirements.txt` (venv-xetet; TikTokLive vẫn chạy với websockets 17).

## Proof (01/11)

- Đo VieNeu trên máy: 1,0–1,4 giây đọc một câu 4–6 giây (lần đầu 2,8 giây khởi động); đọc số «1676 km» đúng.
- Máy chủ thử 8811 (thư mục giọng riêng): Nghe thử → «Xin chào bà con! Anh Tư lơ xe đây…»; 2 người comment → «Minh Anh và
  Thu Hà lên xe về Nghệ An!» (bỏ 🌸); xuất bến «… 1379 ki-lô-mét!»; trạm «Tới trạm dừng chân Khánh Hòa!…»; «Bíp bíp!…»;
  thả khách «Về tới Nghệ An rồi! Minh Anh và Thu Hà xuống xe nha!»; overlay tải đủ file giọng (206), 0 lỗi.
- `pytest` 102 passed (thêm test_voice.py: soạn câu, gom tên, ưu tiên / bỏ câu, đọc + lưu sẵn, dự phòng edge-tts — bằng máy
  giả, không gọi mạng; conftest tắt bộ đọc nền trong test).
- VieNeu đang chạy (PM2 `VieNeu_TTS`, ~1,5 GB RAM); Studio_Heavy / Studio_Light vẫn tắt.
