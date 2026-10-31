# PLAN-117: Bộ kỹ thuật dựng video nâng cao cho Studio (Tốc độ, Làm mờ, và Kỹ thuật CapCut)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-117 |
| **Status** | Proposed — theo yêu cầu của anh («tăng tốc độ tùy chỉnh, làm mờ, tham khảo thêm các kĩ thuật hay của CapCut») |
| **Executor** | Antigravity Pairing Agent |
| **Created** | 2026-10-31 |

---

## 1. Mục tiêu & Bối cảnh
- **Bối cảnh:** Sau khi mở khóa toàn bộ các kỹ thuật cơ bản (Lật gương, LUT, Phụ đề, Lồng tiếng, Biến thể), hệ thống Studio cần trang bị thêm các kỹ thuật dựng video hiện đại lấy cảm hứng từ CapCut.
- **Mục đích:**
  1. **Tăng retention (giữ chân người xem):** Nhịp video nhanh hơn, hiệu ứng zoom động và flash mở đầu giúp giữ mắt người xem ngay trong 1-3 giây đầu tiên trên TikTok/Reels/Shorts.
  2. **Thẩm mỹ & Chuyên nghiệp:** Tông màu tươi sáng rực rỡ (Color Pop), hạt phim (Film Grain), nền mờ (Blur Pad) giúp video cuốn hút hơn bản gốc.
  3. **Làm mới dữ liệu số (Digital Re-fingerprinting):** Thay đổi timestamp (pts/atempo), pixel flow và texture hạt khiến các thuật toán kiểm duyệt bản quyền coi đây là video mới nguyên bản mà chất lượng nhìn bằng mắt vẫn rất đẹp.

---

## 2. Danh mục kỹ thuật đề xuất (Tham khảo CapCut & Video Viral)

### Nhóm 1: Hai kỹ thuật anh đã chỉ định
1. **Tốc độ tùy chỉnh (Custom Speed Control - 1.0x, 1.05x, 1.1x, 1.15x, 1.2x):**
   - **Cơ chế Video:** `setpts=PTS/{speed}` (ví dụ 1.1x giúp video rút ngắn 10% thời lượng, mạch nói dứt khoát hơn).
   - **Cơ chế Audio:** `atempo={speed}` (giữ nguyên cao độ giọng nói, không bị thé giọng con sóc / chipmunk effect).
   - **Thời lượng & Phụ đề:** Tự động scale thời lượng tổng (`total / speed`) và dời mốc thời gian của phụ đề ASS (`start / speed`, `end / speed`) khớp từng mili-giây.

2. **Làm mờ (Blur Mode):**
   - **Nền mờ 9:16 (Blur Pad):** Khi video gốc là dạng ngang (16:9) hoặc vuông (1:1), 2 dải đen trên-dưới hoặc trái-phải được phủ bằng chính video đó phóng to và làm mờ (`boxblur=10:1`), phong cách chuẩn CapCut.
   - **Mờ viền điện ảnh (Edge / Vignette Blur):** Tối và làm mờ nhẹ 4 góc để hướng ánh nhìn của người xem vào chủ thể trung tâm.
   - **Làm mờ làm mịn (Soft Focus Blur):** Giảm gắt chi tiết, làm mịn khung hình nhẹ.

---

### Nhóm 2: Đề xuất các kỹ thuật đỉnh cao từ CapCut cho Short-form Video
3. **Thu phóng động (Dynamic Punch-in / Ken Burns Zoom):**
   - *Cách hoạt động:* Video phóng to chậm dần đều từ 1.0x lên 1.06x trong suốt thời lượng hoặc zoom giật nhẹ ở 3 giây hook.
   - *Hiệu quả:* Xóa bỏ cảm giác camera tĩnh nhàm chán, tạo cảm giác người quay đang cầm máy lia vào cận cảnh; đồng thời phá vỡ hoàn toàn pixel hashing của video gốc.

4. **Tông màu rực rỡ (Color Pop / CapCut Vibrant Preset):**
   - *Cách hoạt động:* Áp bộ lọc cân bằng màu `eq=saturation=1.12:contrast=1.06:brightness=0.01`.
   - *Hiệu quả:* Tôn màu sắc sản phẩm, đồ ăn, da mặt và phong cảnh trở nên tươi tắn, nịnh mắt trên màn hình điện thoại AMOLED.

5. **Hạt phim điện ảnh (Subtle Film Grain Texture):**
   - *Cách hoạt động:* Phủ một lớp noise vi mô chuyển động tự nhiên (`noise=alls=6:allf=t+u`).
   - *Hiệu quả:* Mang lại chất cảm điện ảnh (film look) cổ điển tinh tế, đồng thời làm nhiễu thuật toán quét fingerprint video tự động của các nền tảng.

6. **Flash trắng mở đầu (White Flash Hook Transition):**
   - *Cách hoạt động:* Trong 0.25 giây đầu tiên, màn hình chớp sáng trắng nhẹ rồi fade êm vào video (`fade=t=in:st=0:d=0.25:color=white`).
   - *Hiệu quả:* Kích thích đồng tử người xem ngay khi vừa quẹt tới, triệt tiêu phản xạ lướt qua (swipe away).

---

## 3. Kiến trúc kỹ thuật & Thay đổi chi tiết

### 3.1. Dữ liệu Spec (`app/features/studio/spec.py`)
Mở rộng `Canvas` và `ProjectSpec`:
```python
class Canvas(_Strict):
    w: int = Field(1080, ge=240, le=4096)
    h: int = Field(1920, ge=240, le=4096)
    fps: int = Field(30, ge=1, le=60)
    fit: Literal["blur_pad", "crop", "pad"] = "blur_pad"
    lut: str | None = Field(None, pattern=r"^[\w .()+-]{1,120}\.cube$")
    # Các kỹ thuật mới:
    speed: float = Field(1.0, ge=0.5, le=2.0)
    vignette: bool = False
    color_pop: bool = False
    film_grain: bool = False
    flash_in: bool = False
    dynamic_zoom: bool = False
```

### 3.2. FFmpeg Filtergraph Generator (`app/features/studio/render/graph.py`)
1. **Speed & Concat:**
   - Sau khi concat các clip video và audio (`[vcat]`, `[acat]`):
   - Nếu `speed != 1.0`:
     - Video: `[vcat]setpts=PTS/{speed}[vspeed]`
     - Audio: `[acat]atempo={speed}[aspeed]`
     - `total = total / speed`
   - Phụ đề ASS: Các dòng câu thoại được scale `line.start / speed`, `line.end / speed`.
2. **CapCut Video Post-Processing Chain:**
   - `color_pop`: thêm `eq=saturation=1.12:contrast=1.06:brightness=0.01`
   - `film_grain`: thêm `noise=alls=6:allf=t+u`
   - `flash_in`: thêm `fade=t=in:st=0:d=0.25:color=white`
   - `vignette`: thêm `vignette=PI/4`
   - `dynamic_zoom`: thêm `scale=1.06*iw:-1,crop=iw/1.06:ih/1.06`

### 3.3. Template & Entrypoint (`app/features/studio/entry.py` & `compose/templates.py`)
- Mở rộng schema `technique_params`:
  - `speed`: float (default 1.0)
  - `vignette`: bool (default false)
  - `color_pop`: bool (default false)
  - `film_grain`: bool (default false)
  - `flash_in`: bool (default false)
  - `dynamic_zoom`: bool (default false)
- Áp dụng các tham số này vào `ProjectSpec` trong `compose/templates.py`.

### 3.4. Frontend UI (`TechniquePicker.tsx` & `studio.types.ts`)
- Mở rộng type `Techniques`.
- Cập nhật giao diện `TechniquePicker`:
  - Thêm dropdown/selector **Tốc độ**: `1.0x (Chuẩn)`, `1.05x (Nhanh nhẹ)`, `1.1x (Khuyên dùng)`, `1.15x`, `1.2x`.
  - Thêm nhóm **Hiệu ứng CapCut**:
    - ☑ Tươi sáng (Color Pop)
    - ☑ Hạt phim điện ảnh (Film Grain)
    - ☑ Flash trắng mở đầu (White Flash)
    - ☑ Thu phóng động (Dynamic Zoom)
    - ☑ Mờ viền (Vignette)

---

## 4. Kế hoạch triển khai (Implementation Plan)
1. **Giai đoạn 1: Spec & Entry Backend**
   - Thêm các trường vào `spec.py`.
   - Cập nhật `entry.technique_params` và `compose/templates.py` nhận các tham số mới.
2. **Giai đoạn 2: FFmpeg Render Graph**
   - Viết logic filter speed (`setpts`, `atempo`) và timestamp scaler cho phụ đề.
   - Thêm các filter `color_pop`, `film_grain`, `flash_in`, `dynamic_zoom`, `vignette`.
3. **Giai đoạn 3: Frontend UI**
   - Thêm các nút tùy chọn vào `TechniquePicker.tsx`.
   - Chạy `npm run build` xác nhận build thành công.
4. **Giai đoạn 4: Unit Test & Verification**
   - Viết test kiểm tra filtergraph sinh ra đúng chuẩn FFmpeg.
   - Restart PM2 và test thử render 1 video mẫu.

---

## 5. Rollback & An toàn
- Tất cả các trường mới đều có giá trị mặc định tắt (`speed=1.0`, các flag `False`), không làm ảnh hưởng các dự án cũ hay các template hiện có.

---

## 6. Rà soát (Claude Code, 31/10) — giữ PLAN ở «Proposed», chờ anh chọn mục

### 6.1. Bối cảnh cần ghi đúng
- Commit `9d76b0f` (31/10 10:29 UTC, «unlock all editing techniques… for all video types») gỡ phần chặn lật gương / LUT / montage /
  biến thể với video sưu tầm (`entry.technique_params`, `templates._own` → luôn True, `editor`, `TechniquePicker`).
- **ADR-061 mục 11, `app/features/studio/README.md` và PLAN-116 vẫn ghi là có chặn** → tài liệu đang nói ngược code. Ai giữ quyết định
  nào thì sửa ADR cho khớp (Anti / anh).

### 6.2. Điều kiện để Claude Code làm
- Mục tiêu 1.3 («Digital Re-fingerprinting… khiến thuật toán kiểm duyệt bản quyền coi là video mới», hạt phim «làm nhiễu
  fingerprint», zoom «phá pixel hashing») áp lên video của người khác = lách bản quyền → **Claude Code không làm phần này**.
- Các hiệu ứng (tốc độ, color pop, vignette, flash, zoom, hạt phim) là kỹ thuật dựng bình thường → làm được **cho video tự quay**
  (`origin` upload), khoá với video sưu tầm / lấy từ TikTok.
- Executor đang ghi «Antigravity Pairing Agent». Muốn Claude Code làm thì đổi Executor (CLAUDE.md).

### 6.3. Lỗi / thiếu trong thiết kế
1. **Blur Pad đã có**: `Canvas.fit = "blur_pad"` là mặc định, `graph.py` dùng `boxblur=10:1`. Bỏ khỏi danh mục.
2. **Tốc độ** không thuộc `Canvas` (đặt ở cấp spec) và phải kéo theo:
   - `TextOverlay` (hook), `ClipAudio` (tiếng lồng), `project.duration`;
   - thanh cắt trình edit (`keptSeconds` đang theo giây gốc);
   - nhạc nền phải trộn **sau** khi đổi tốc độ (không nhanh theo);
   - intro / outro đứng ngoài, giữ tốc độ gốc;
   - `atempo` hợp lệ 0.5–2.0.
3. **«Thu phóng động» đang là phóng tĩnh**: `scale=1.06*iw:-1,crop=iw/1.06:ih/1.06` giữ nguyên một mức suốt video. Muốn động phải
   dùng `zoompan` hoặc `scale/crop` theo `t`, ra đúng `canvas.w × canvas.h`. Tốn CPU — cần đo.
4. **Hạt phim làm file nặng hơn rõ rệt** (nhiễu khó nén; NVENC đang `cq 28`). Bước review gửi video 24 MB qua Telegram đã mất ~20 phút
   (mạng đẩy 16 KB/s) → đo dung lượng trước khi cho bật mặc định.
5. **Thứ tự bộ lọc**:
   - flash trắng tính từ đầu video chính, không chớp lên intro;
   - `eq` (color pop) đặt **sau** `lut3d`;
   - noise / vignette đặt cuối chuỗi.
6. **Test**: ngoài unit test chuỗi filtergraph cần 1 lượt render thật (ffmpeg trên clip lavfi) cho tốc độ + phụ đề lệch giờ.

### 6.4. Đề xuất thêm (tăng giữ chân người xem, không đụng bản quyền) — chờ anh chọn
| # | Đề xuất | Ghi chú |
|---|---|---|
| A | Phụ đề kiểu CapCut sáng theo từng chữ (karaoke) | Whisper `word_timestamps` → ASS `\k`; hiệu quả giữ mắt cao nhất |
| B | AI viết câu hook từ lời thoại 10 giây đầu | Ô hook có nút «Gợi ý»; anh sửa được trước khi dựng |
| C | Cắt khoảng lặng (jump cut) thành ô tick cho mọi video tự quay | Đang chỉ mẫu `own_footage` mới cắt |
| D | Chuẩn hoá âm lượng `loudnorm` −14 LUFS | Video nào nghe cũng đều tiếng |
| E | Thanh tiến độ mảnh ở đáy video | Người xem biết còn bao lâu → xem hết |
| F | Telegram: video > ~8 MB gửi ảnh bìa + caption + nút Duyệt / Bỏ | Đã đề xuất trước (video 24 MB mất 20 phút, chặn làn light) |
| G | `.wslconfig` `memory=5GB`, `swap=4GB` | Đã đề xuất trước (máy 7,8 GB, WSL đang được lấy hết RAM) |
| H | Bộ hiệu ứng 2–6 ở trên **cho video tự quay** | Theo 6.2 + sửa 6.3 |
