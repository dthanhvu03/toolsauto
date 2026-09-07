# Tích hợp miễn phí đáng làm — khảo sát 2026-09-07

> 5 agent lùng mạng song song theo 5 hướng, mỗi mục **mở trang gốc và ghi ngày kiểm**.
> Mục ghi **[T]** chỉ có nguồn thứ cấp — chưa tin được. Xếp hạng theo *vá đúng chỗ đang
> hỏng ÷ công sức*, không theo "hay ho". Tool một người dùng, local Windows, tiếng Việt,
> kiếm tiền bằng affiliate — mọi thứ "free" phải là **free tier có số cụ thể**, và phải
> **cho phép thương mại** (video affiliate là thương mại).

## Kết luận ngắn

| Hạng | Việc | Vá cái gì đang hỏng | Công sức | Cần PLAN? |
|---|---|---|---|---|
| 1 | Key Gemini `AIza…` + Groq làm dự phòng qua 3 biến `.env` | Chuỗi AI caption chết (401) | 15 phút | Không |
| 2 | Đếm click bằng **Sub ID** của Shopee Affiliate / AccessTrade | P0-2 "link đếm click" hỏng → **xoá tính năng**, không sửa | 0 code | Không |
| 3 | **healthchecks.io** ping cuối backup + mỗi vòng worker | Postgres tắt 3 lần không ai biết; Drive im lặng hỏng; FB chết 5 tuần | 30 phút | ADR nhỏ (1 dòng trong worker) |
| 4 | **Tailscale** `serve 8002` | Xem dashboard từ điện thoại, không mở port | 20 phút | Không |
| 5 | **Meta Graph API** đăng Page — spike bằng curl trước, code sau | Playwright + cookie = hành vi Meta cấm, đã mất tài khoản | 2 giờ spike, PLAN riêng nếu đạt | **Có** |
| 6 | Phụ đề đốt: `faster-whisper → pysubs2 → ffmpeg ass=` | Video "khác gốc" hơn; thư viện đã có trong requirements | 5 giờ | Có |
| 7 | Nhạc nền **Meta Sound Collection** + `ffmpeg amix` | Rủi ro bản quyền trên FB thấp nhất (Meta là chủ giấy phép) | 1 giờ | Có (nhỏ) |
| 8 | **rclone** thay Drive for Desktop + `rclone check` | "Drive im lặng hỏng" thành fail có báo | 1,5 giờ | Có (sửa ADR-012) |
| 9 | Postgres cài thẳng làm Windows Service | Docker Desktop **không** sống trước khi đăng nhập Windows (issue mở 3 năm) | 2 giờ | Có (ADR) |
| 10 | TTS: `edge-tts` (HoaiMy/NamMinh) + `piper-tts` vi_VN dự phòng | Voice-over caption | 3 giờ | Có |

**Loại bỏ, đừng tốn thời gian:** Bitly Free (không có click), ElevenLabs Free (không giấy phép thương mại), F5-TTS tiếng Việt (CC-BY-NC), Kokoro (không có tiếng Việt), stable-ts (archive 05/2026), GitHub Models (đóng 07/2026), Cerebras (trial cần thẻ), Real-ESRGAN (dormant, lợi ít), scraping TikTok Creative Center / Shopee (vi phạm ToS, nguy cơ khoá TK ads/affiliate), self-host shortener trên PC local (PC tắt = link chết), Uptime Kuma cùng máy (chết chung với thứ nó giám sát).

---

## 1. AI caption — vá chuỗi đang chết

Phát hiện thêm khi đọc code: `app/core/ai/native_fallback.py:22-35` còn liệt kê `gemini-2.0-flash` / `flash-lite` — trang models Google ghi **đã shut down**. Cần thay bằng `gemini-3.5-flash` / `-lite`. (Backend, ghi để Anti đưa vào PLAN.)

| # | Dịch vụ | Model | Free tier | OpenAI-compat | Việc trong code | Rủi ro | Nguồn (kiểm 07/09) |
|---|---|---|---|---|---|---|---|
| 1 | **Gemini API** | `gemini-3.5-flash`, dự phòng `-lite`, `2.5-flash` | Có free tier cho mọi Flash; **số RPM/RPD Google đã rút khỏi docs**, chỉ hiện sau đăng nhập AI Studio | SDK có sẵn | Đặt `GEMINI_API_KEY` dạng `AIza…`; sửa list model | Unpaid: Google **dùng để train + người thật đọc** | ai.google.dev/gemini-api/docs/pricing, /terms |
| 2 | **Groq** | `qwen/qwen3.8-27b` (vision, JSON schema) | **30 RPM, 1.000 RPD, 8K TPM, 200K TPD** → ~50 caption/ngày | `https://api.groq.com/openai/v1` | Chỉ đổi `OPENROUTER_BASE_URL/KEY/MODEL` | Model *Preview*, có thể rút; **không train trên dữ liệu** | console.groq.com/docs/rate-limits, /your-data |
| 3 | OpenRouter `:free` | `google/gemma-4-31b-it:free` | **20 RPM, 50 RPD** chưa nạp; nạp $10 một lần → 1.000 RPD | Có (đã cắm) | Đổi `OPENROUTER_MODEL` khỏi `openrouter/free` (random) | Do Google AI Studio phục vụ → cùng chính sách train Gemini | openrouter.ai/docs/api-reference/limits |
| 4 | Cloudflare Workers AI | `@cf/google/gemma-3-12b-it` | 10.000 neuron/ngày ≈ 300K token in | Có | Đổi base URL | Chưa kiểm compat nhận `image_url` | developers.cloudflare.com/workers-ai/platform/pricing |
| — | Mistral, SambaNova | — | Mistral bắt SĐT + opt-in train [T]; SambaNova docs 404 | — | — | Không xác minh được | — |

**STT tiếng Việt:** (a) `faster-whisper` chỉ cần `pip install` — nó **đã trong requirements nhưng chưa cài**; model tiếng Việt fine-tune `erax-ai/EraX-WoW-Turbo-V1.1-CT2` (MIT) load thẳng bằng `WhisperModel(<repo>)`. (b) Groq Whisper turbo free **28.800 giây audio/ngày**. (c) Gọn nhất về kiến trúc: gửi thẳng video cho Gemini (audio 32 tok/s) → bỏ luôn Whisper lẫn collage — cần PLAN backend.

**LLM local (Ollama gemma4:12b):** CPU-only 1–3 token/s → 2–5 phút/caption. Không đáng, trừ khi cần riêng tư tuyệt đối.

## 2. Đếm click — xoá P0-2 thay vì sửa

Chỉ số duy nhất Owner đo là "có ai bấm link không". Cách rẻ nhất, **0 code, số click trùng với số sàn dùng để tính đơn**:

- **Shopee Affiliate**: tạo link kèm **Sub ID** = mã bài (vd `fb_20260907_j12`); dashboard đã có cột "lượt click, chuyển đổi". [G] help.shopee.vn/portal/10/article/122906
- **AccessTrade VN**: `POST api.accesstrade.vn/v1/product_link/create` với `sub1..sub4`, trả sẵn `short_link`; có cả create-link TikTok Shop và **"top sản phẩm bán chạy"** — nguồn xu hướng hợp lệ duy nhất có API. [G] developers.accesstrade.vn

Nếu sau này cần domain đẹp + API vào bảng affiliate: **Short.io Free** — 1.000 link, 50k click/tháng, 5 custom domain, API 50 req/s [G] short.io/pricing. **Không** Bitly (Free 5 link/tháng, không click), **không** Dub (Free đang mờ).

Xu hướng: TikTok Creative Center có region Vietnam nhưng **chỉ xem tay** (Top Products bắt đăng nhập Business, ToS cấm bot). pytrends **archive 04/2025**; Google Trends API chính thức đang alpha, phải nộp form. Meta Ad Library API: quảng cáo thương mại ngoài EU **không có** trong API.

Nguồn video reup hợp lệ: **không tìm được** nền tảng nào cho affiliate tải và reup video nhà bán một cách chính thức (Shopee Video cấm watermark nền tảng khác; TikTok Shop "authorize affiliate videos" là chiều creator→seller). Cách hợp lệ: xin phép seller hoặc tự quay.

## 3. Ops — "chết không ai biết"

| Nỗi đau | Chọn | Free | Ghép vào đâu | Nguồn |
|---|---|---|---|---|
| Backup/worker chết im | **healthchecks.io** | 20 check, kênh Telegram/ntfy/Discord/email, ping `hc-ping.com/<uuid>` + `/fail` | 1 dòng `requests.get()` cuối `db backup`, mỗi vòng `maintenance`, `fb_publisher`; login fail → `/fail` | healthchecks.io/pricing |
| Kênh báo không cần bot | **ntfy.sh** | Không tài khoản, topic = mật khẩu, 60 burst rồi 1 msg/10s | Thay/bổ sung `notify_telegram()` — 1 POST | docs.ntfy.sh/publish |
| Dashboard từ điện thoại | **Tailscale** Personal | 6 user, thiết bị không giới hạn, `tailscale serve 8002` → HTTPS trong tailnet | Không đụng code, dashboard vẫn bind 127.0.0.1 | tailscale.com/kb/1312/serve |
| ″ tạm thời | Cloudflare Quick Tunnel | Không tài khoản, URL ngẫu nhiên, không Access | Chỉ để test | …/trycloudflare |
| Drive im lặng hỏng | **rclone** → Drive | Free; **phải tạo OAuth client riêng** (client chung ngừng 2026); `rclone check --one-way --missing-on-dst` | Thay bước copy sang `G:`; fail → không ping healthchecks | rclone.org/drive |
| Backup có khôi phục được? | Kopia / restic | `snapshot verify --verify-files-percent` | Bước 2 | kopia.io/docs |
| Postgres tắt sau reboot | **Postgres cài thẳng** (EDB), `pg_ctl register -S auto` | Docker Desktop chỉ chạy **sau đăng nhập Windows**; issue docker/roadmap#515 mở từ 2023 | Đổi `DATABASE_URL`, bỏ compose — cần ADR | postgresql.org/download/windows |
| Ổ C: 8 GB | `docker system prune -a` (không `--volumes`), `pip cache purge`, `cleanmgr /verylowdisk`, WizTree, `wsl --shutdown` + `compact vdisk` | — | — | docs.docker.com, learn.microsoft.com |

Loại: Cronitor (không Telegram), Gotify (chỉ Android, cần máy sống), bore (không TLS/auth), Uptime Kuma cùng máy.

## 4. Meta Graph API — thay Playwright cho việc đăng Page

**Câu trả lời:** cá nhân đăng lên Page **của mình** qua API là miễn phí, **không cần App Review, không cần Business Verification**. Meta viết rõ: *"If your app will only be used by app users who have a role on the app itself you do not need to complete verification; these users can grant your app any permissions at any time."* [G] developers.facebook.com/docs/development/release/business-verification · /docs/graph-api/overview/access-levels

**Bẫy:** app ở **Development mode** thì bài đăng **công chúng không thấy**. Phải chuyển **Live mode** (chỉ cần Privacy Policy URL, icon, category — không nộp review). Có mâu thuẫn câu chữ giữa hai trang doc → **bắt buộc test thực nghiệm** trước khi code.

| Nội dung tool đang có | API | Ghi chú |
|---|---|---|
| Feed chữ + link | ✅ `POST /{page-id}/feed` | `pages_manage_posts` + `pages_read_engagement` + `pages_show_list` |
| Ảnh | ✅ `/{page-id}/photos` | nhiều ảnh: `published=false` + `attached_media` |
| **Reels** | ✅ `/{page-id}/video_reels` 3 bước | 3–90 s, 9:16, ≥540×960, **30 Reels/24h** |
| Story ảnh / video | ✅ `/photo_stories`, `/video_stories` | ≤60 s; media **không được dùng lại** từ bài cũ |
| Story có **link bấm / sticker / chữ đè** | ❌ | Doc không có — mục này trong bảng thực lực đã là D |
| Comment kèm ảnh | ✅ `/{post-id}/comments` + `attachment_url` / `source` | `pages_manage_engagement` |
| Lên lịch feed/Reels | ✅ `scheduled_publish_time` | 10 phút → 30 ngày |
| Lên lịch story | ❌ (không thấy trong doc) | |
| Sửa/xoá bài | ⚠️ chỉ bài do chính app đăng | |
| Profile cá nhân / Group | ❌ | |

**Token:** user token → long-lived (60 ngày) → `GET /me/accounts` → Page token **không hết hạn** (mất khi đổi mật khẩu / thu hồi app). Page trong Business Manager → **System User token** cũng không hết hạn. Rate: 4800 × engaged users / 24h.

**Rủi ro — đây là lý do đáng làm nhất:** Account Integrity (cập nhật 2026-05-29) cấm *"using an account through automated means, such as scripting (unless… through authorized routes)"*. Graph API + OAuth = authorized route; **Playwright + cookie phiên = chính xác hành vi bị cấm**. Meta *không* tuyên bố "API thì không bị khoá" — nhưng lỗi API chỉ chặn token, còn lỗi browser automation khoá dây chuyền profile → Page → BM (đúng thứ đã xảy ra 31/07).

**Instagram:** Content Publishing API tương tự, Standard Access cho tài khoản mình; Reels ≤15 phút, 100 bài/24h; Stories không sticker/link.

**Checklist spike (2 giờ, làm trước bất kỳ dòng code nào):**
1. Tài khoản dev **mới** (không phải tài khoản đã khoá) → Create App loại Business
2. Settings › Basic: Privacy Policy URL, icon 1024², category
3. Graph API Explorer: user token với 4 quyền `pages_*` → đổi long-lived → `/me/accounts` → Page token → Debugger phải ghi "Expires: Never"
4. Chuyển **Live mode** → `curl POST /{page-id}/feed` một bài chữ
5. Kiểm bằng tài khoản **không có role**: bài có công khai không. **Đạt mới viết PLAN.**
6. Thư viện: gọi thẳng `requests` (v25); `facebook-sdk` chết từ 2018

Công cụ có sẵn: Meta Business Suite lên lịch tới 75 ngày [T]; Postiz self-host có FB post/Reels nhưng **không FB Stories** (issue #1185 not planned).

## 5. Xử lý video — "khác gốc" và hấp dẫn hơn

| Nhu cầu | Chọn | Free / license | Ghép vào | Công sức | Nguồn |
|---|---|---|---|---|---|
| Phụ đề đốt vào video | **faster-whisper 1.2.1** (`word_timestamps`) → **pysubs2 1.9.0** (ASS, style CapCut) → `ffmpeg -vf ass=` ; font **Be Vietnam Pro** (OFL) | MIT/OFL, local | Sau tải, trước ghép intro | 5 giờ | github.com/SYSTRAN/faster-whisper, tkarabela/pysubs2 |
| Karaoke từng chữ | — | stable-ts **archive 2026-05-30**; WhisperX align tiếng Việt lỗi (PR #776) | Không làm | — | |
| TTS tiếng Việt | **edge-tts 7.2.8** `vi-VN-HoaiMyNeural`/`NamMinhNeural` + fallback **piper-tts 1.8.0** (`vi_VN-vais1000-medium`, offline) | edge-tts không có ToS (issue 503 còn mở); piper GPL-3 chỉ ràng buộc khi phân phối | Voice-over trước ghép | 3 giờ | github.com/rany2/edge-tts, pypi piper-tts |
| TTS có giấy tờ | FPT.AI **100.000 ký tự/tháng** | Free tier rõ, tốc độ thấp | Thay edge-tts | 1 giờ | docs.fpt.ai/…/tts-pricing |
| Nhạc nền | **Meta Sound Collection** (facebook.com/sound) | 14k track, thương mại OK, **chỉ dùng trên Meta** — khớp đầu ra hiện tại | Tải tay 20–30 track vào `storage/`, `ffmpeg amix` | 1 giờ | facebook.com/sound/collection/terms |
| Nhạc nền phụ | Pixabay Music | Không API music, cấm mass download | Tải tay | — | pixabay.com/service/terms |
| Thumbnail chữ Việt | Pillow + Be Vietnam Pro, `unicodedata.normalize('NFC')` | Không cần libraqm | Ảnh bìa Reels | 1–2 giờ | pillow.readthedocs.io |
| AI ảnh | Pollinations 1 pollen/IP/giờ; HF $0.10/tháng | Quá ít để chạy thường xuyên | Không | — | |
| Tải TikTok không watermark | yt-dlp 2026.08.19 — chọn format `play_addr` (`-f b`) | Thay đổi theo vùng (issue #15690) | Bước tải | 30 phút | github.com/yt-dlp/yt-dlp |
| Editor tay | DaVinci Resolve 21 free (UHD, không Neural); Clipchamp free 1080p | — | Ngoài pipeline | 0 | blackmagicdesign.com |

Loại: ElevenLabs Free (không Commercial License), F5-TTS VI (CC-BY-NC-SA), Kokoro (không VI), Real-ESRGAN (push cuối 2024), Bing Image API (reverse-engineered, cookie đổi 2–4 tuần), Uppbeat Free (3/tháng + credit).

## Không xác minh được (ghi để không tin nhầm)

- Số RPM/RPD free tier Gemini; free tier SambaNova; điều kiện Mistral Free.
- Điều kiện cấp **Shopee Open API** cho affiliate cá nhân (trang cần đăng nhập); TikTok Shop Partner Center có duyệt cá nhân; Lazada app key.
- Cloudflare Zero Trust Free = 50 user; Discord webhook rate limit; localhost.run thời gian phiên.
- Mâu thuẫn doc Meta về Live mode + Standard Access → cần spike thực nghiệm.
- Uppbeat / CapCut / Clipchamp pricing (trang gốc 404/429); Google Cloud TTS free tier; YouTube Audio Library dùng ngoài YouTube.
- edge-tts có còn chạy hôm nay (chưa chạy thử).
