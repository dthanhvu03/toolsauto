# Audit prompt AI caption / status — 21/11/2026 VN

## Kết luận

Luồng caption video hiện ưu tiên một câu ngắn gây tò mò; chưa có yêu cầu nhất quán để người đọc có điều cụ thể muốn trả lời. Có cả lỗi truyền dữ liệu, cấu hình thiếu key và prompt mâu thuẫn. Chỉ sửa nội dung ô “Engagement” sẽ chưa giải quyết đủ.

Đây là audit theo yêu cầu trực tiếp của chủ bot, không phải thực thi thay đổi caption. Đã đọc current-status, full PLAN-184/187, workflow/rules và ADR-006/013/021/066/067. PLAN-184 đã kết thúc; PLAN-187 chỉ theo dõi hai bài Threads. Chưa có PLAN được giao sửa những lỗi dưới đây. Không sửa source/config/template, gọi AI thật, tạo lại caption, đăng bài, đổi lịch, restart hay bật lại growth workers. Working tree có nhiều thay đổi sẵn; audit dựa trên bản đang có, không reset/commit/push.

## Bằng chứng dữ liệu thực tế

PostgreSQL được truy vấn bằng connection riêng với `SET TRANSACTION READ ONLY` và `SET LOCAL statement_timeout = 8000`. Không import session engine có hook cập nhật SQLite. Snapshot lúc **23:35 VN 21/11/2026**:

```text
viral_materials: total=1063, with_caption=988
15 caption mới nhất: 4 có dấu ?, 11 không; trung bình 98.9 ký tự
50 caption mới nhất: 15 có dấu ?; trung bình 100.2 ký tự
15 caption: thời điểm tạo từ 17/11 14:19:24 tới 21/11 21:19:14 VN
50 job mới nhất có caption: ai_style=short: 50/50
50 job này: view_24h có dữ liệu=0; metrics_checked=true=0
runtime_settings: 8 ai.prompt.* overrides; không có ai.caption_style
growth.enabled=False
```

Đếm dấu hỏi chỉ mô tả hình thức, không phải thước đo chất lượng hay tỷ lệ tương tác. Đây là mẫu mới nhất, không phải lấy ngẫu nhiên. DB trên chưa cung cấp cơ sở kết luận caption nào tạo nhiều bình luận hơn hoặc thuật toán giảm phân phối.

Một số output lưu thật:

| Material | Caption | Nhận xét biên tập |
|---|---|---|
| 2086 | Đi qua nửa đời người mới thấm: Càng bớt nói, tâm càng an. Càng bớt dựa dẫm, lòng càng nhẹ nhõm. | Một kết luận đóng, chưa mở ra tình huống để người đọc chia sẻ. |
| 2095 | Sống đến độ tuổi này, làm đủ 7 điều này thì tâm mới thực sự an yên. | Gợi xem video, chưa có lý do rõ để trả lời. Chưa đối chiếu video nên không xác nhận số 7. |
| 2087 | Đôi khi đi chậm lại là một điều may mắn. Bạn thấy mình đang có bao nhiêu điều trong số này rồi? | Có câu hỏi nhưng phụ thuộc “những điều này”, khó trả lời chỉ từ status. |
| 2088 | Càng bước qua tuổi 40 càng nhận ra: Giữ được chữ tín và tâm an, phúc lộc tự khắc tìm đến. Bạn đã tích lũy được bao nhiêu điều trong số này? | Lặp mô-típ đếm điều với bài khác. |
| 2085 | Mẫu đầm cổ vuông đính đá nhã nhặn thế này bảo sao các quý cô U40, U50 diện đi tiệc ai cũng khen khéo chọn. | Chủ yếu khen sản phẩm; “ai cũng khen” là khẳng định chưa được audit video chứng minh. |

## Luồng thực tế đã rà

1. Material READY / nút Viết caption / tự caption: `viral_intake/service.py:951` → `ContentOrchestrator.generate_caption` → `AIUseCases` → `AICaptionPipeline` → lưu `ai_caption/ai_hashtags`. Caption có thể dẫn tới tự xếp lịch qua `service.py:1058`; vì vậy audit không gọi lại hàm này trên material thật.
2. Buffer: `buffer/queue_job.py:281` lấy caption đã lưu và nối hashtags; không tự biên tập câu hỏi. Các job Buffer mới nhất chưa có metrics trong những cột vừa kiểm.
3. Worker job AI: `viral_intake/workers/ai_generator.py:275` lấy page/niches, gọi cùng orchestrator, lưu caption vào job.
4. Studio render: `studio/caption/__init__.py:54` gọi cùng orchestrator; dự án đã có caption thì bỏ qua bước viết lại.
5. API caption đơn giản: `core/ai/service.py:13` có prompt riêng. Chưa tìm thấy UI caller hiện tại; không quy nhánh này là nguyên nhân của material live.
6. AI Studio thử prompt: `system_panel/ai_studio_service.py:49` → `BrainFactory.build_caption_prompt`; khác prompt production.
7. Threads original status: `threads/growth/content.py:138,160,264`; prompt và formatter riêng. Growth đã bị chủ bot dừng; không bật lại trong audit.
8. Threads reply/followup và chiến lược: có các bước tự review riêng, không mặc định áp dụng cho original post. Các worker/news legacy đã bị loại theo PLAN-166; không coi README cũ là luồng đang chạy.

## Phát hiện cần ưu tiên

### 1. Context tiêu đề và chỉ dẫn chia phần bị bỏ trước khi gửi AI

`app/features/viral_intake/service.py:996` truyền tiêu đề đã làm sạch và chỉ dẫn “Phần 2/3, mời xem tiếp” bằng context thường. Nhưng `app/core/orchestrator.py:484,494` chỉ lấy hai marker `ORIGINAL_VIRAL_TITLE` và `BOOST_CONTEXT`; phần context thường không được nối vào prompt ở dòng 620. Studio cũng truyền title thường.

Hệ quả: ảnh/transcript vẫn vào AI, nhưng phần ý định biên tập/tiêu đề/phần tiếp theo bị mất. Probe offline xác nhận context thường vắng mặt, context có marker xuất hiện.

### 2. Prompt `short` và yêu cầu cuối prompt mâu thuẫn

`orchestrator.py:451` yêu cầu đúng 1–2 dòng, dưới 100 ký tự, “một câu nói vu vơ, hài hước”. Dòng 603 lại yêu cầu lý tưởng 150–250 ký tự cho mọi style. Style `daily` ở dòng 465 cấm cả CTA mua hàng lẫn CMT, không phân biệt lời mời trò chuyện tự nhiên với việc xin bình luận máy móc.

Prompt chưa yêu cầu người đọc trả lời điều gì, vì sao họ muốn kể, hoặc câu hỏi cần đủ cụ thể để trả lời mà không phải đọc lại cả danh sách trong video. Nên xử lý mục tiêu và độ dài nhất quán, không ép mọi caption đều có dấu hỏi.

### 3. Setting chọn style không hoạt động ở luồng mặc định

`ai.caption_style` được đọc tại `viral_intake/service.py:1009` và `studio/caption/__init__.py:54`, nhưng không được đăng ký trong `app/core/settings.py`.

Getter ở `settings.py:2039` trả default ngay với key lạ; `get_overrides` ở dòng 2012 còn bỏ qua DB key ngoài registry. Cả hai caller dùng default `short`. Thêm một dòng DB đơn thuần cũng không chữa lỗi này. Mẫu 50 job toàn `short` phù hợp với đường đi này; chưa chứng minh từng job đều sinh từ đúng caller mặc định đó.

### 4. Status đời thường/thời trang vẫn mang vai marketing chung

Mọi style dùng ROLE Facebook Ads/Accesstrade và tối ưu CVR (`orchestrator.py:552–558`); input luôn gắn nhãn “Sản phẩm” tại dòng 506.

Material và Studio chỉ truyền tên page, không truyền `page_niches` (`service.py:1021`, `studio/caption/__init__.py:56`). Orchestrator chọn `general` nếu không có niche, trừ heuristic tên page `lamdep/da_dep` (`orchestrator.py:521–527`). Bởi vậy đã có persona Fashion trong DB cũng chưa có nghĩa caption READY đi qua persona đó. Worker job riêng có đường lấy niches; cần giữ phân biệt này khi sửa.

### 5. Chưa có kiểm tra nội dung cuối cùng phục vụ trò chuyện

`CaptionPayload` tại `app/core/ai/pipeline.py:96` chỉ loại chính xác ba câu “video hay quá!”, “tuyệt vời”, “hay quá”. Chưa kiểm chi tiết riêng của video, mô-típ lặp, câu hỏi chung chung hay việc giữ nguyên ý sau xử lý. Payload thành công được trả ở `orchestrator.py:634`.

Prompt không nhận lịch sử caption gần đây. Vì thế nhiều bài ngẫm sống có thể cùng đi vào “tuổi này/tâm an/bao nhiêu điều”. Đây là nhận xét từ mẫu, không phải kết luận mọi output đều lặp. Không nên biến quality gate thành điều kiện “bắt buộc có ?”; phải đánh giá câu hỏi có hợp nội dung và dễ trả lời không.

### 6. Fallback và sales cần tách khỏi lời kể thông thường

- `orchestrator.py:727` tìm `self.current_job`; không thấy ba caller chính gán thuộc tính này, nên fallback khó lấy lại context và có thể rơi vào random caption pool ở dòng 755.
- Sales rules dòng 443–445 yêu cầu FOMO về số lượng/ưu đãi trong ngày/voucher khi chưa bắt buộc có dữ kiện xác minh. Cần chỉ dùng chi tiết đã có bằng chứng, không đưa trải nghiệm hoặc lời khen người mua vào lời kể của chủ page nếu không có.

## Nhánh phụ phát hiện trong rà soát toàn bộ

### AI Studio chưa kiểm được đúng prompt production

- `app/features/system_panel/ai_studio_service.py:58` gọi `BrainFactory.clean_json_blocks`, nhưng class không có method đó. Khi AI đã có kết quả, call này có thể gây `AttributeError`.
- `brain_factory.py:51` tạo prompt sandbox riêng: có caption mẫu cố định ở dòng 69, schema `title/description` thay vì `caption`, không gọi `get_persona_prompt(niche)`. Chọn niche trong sandbox chưa bảo đảm đang thử persona live.
- API đơn giản ở `core/ai/service.py:14` chỉ nói “Xin hãy viết 1 viral caption.” nhưng dùng parser caption JSON. Chưa xác nhận nhánh này đang được dùng trên UI hiện tại.

### Threads original post ưu tiên funnel và có thể xóa câu hỏi

- `threads/growth/content.py:138–170`: yêu cầu deal/mẹo săn sale, hướng dẫn giỏ hàng và CTA bot; chưa có mục tiêu đối thoại, tình huống người đọc, lịch sử caption.
- `fit_post` ở dòng 197 bảo vệ dòng đầu/cuối/giỏ hàng nhưng xóa dòng giữa dài nhất; `clean_post` dòng 242 ưu tiên dành chỗ link. Câu hỏi nằm giữa có thể bị xóa để vừa giới hạn, trong khi link vẫn giữ. Đây là lỗi bảo toàn ý có thể tái hiện, chưa phải chứng minh nguyên nhân tương tác thực tế.
- Original post đi qua `_ai` kiểm độ dài tối thiểu; không dùng bước self-check của replies hoặc gate nội bộ ở `strategy_review.py`.
- Hai bài đang theo dõi dưới PLAN-187 là caption hardcode đã duyệt trong `reports/threads-content-research-20261120/publish_two_posts.py:30`, không phải output của prompt original-post hiện tại. Không dùng kết quả hai bài đó để kết luận chất lượng prompt tự động.

## Khung prompt đề xuất để Anti/Claude review

Đây là bản nháp biên tập, chưa thay prompt đang dùng. Cần sửa truyền context/style trước rồi mới đánh giá khung này trên video thật.

```text
Viết một status tiếng Việt cho đúng người đọc và giọng của page.

DỮ LIỆU: nền tảng đích; tên/ngách page; nhóm người đọc; mục tiêu bài;
tiêu đề gốc; chi tiết nhìn/nghe rõ trong video; transcript; phần mấy;
caption gần đây để tránh lặp. Dữ liệu thiếu phải giữ là chưa biết.

Nếu mục tiêu là trò chuyện:
- Chọn một chi tiết hoặc tình huống cụ thể trong nội dung làm điểm mở đầu.
- Nêu một phân vân/quan điểm gần đời sống, để người đọc có chỗ đồng ý,
  kể trải nghiệm hoặc đưa lựa chọn. Đừng kết luận hết câu chuyện.
- Khi phù hợp, kết bằng một câu hỏi ngắn có thể trả lời ngay, gắn với
  tình huống vừa nêu. Không chèn câu “Bạn nghĩ sao?” vào mọi bài.
- Không ép comment từ khóa/tag/share; không giả trải nghiệm cá nhân,
  lời người mua, giá, số lượng, thời hạn hay thông số chưa được xác minh.
- Không lặp kiểu mở đầu/câu hỏi của các caption vừa đăng cùng page.
- Giọng tự nhiên đúng nhóm đọc; không mặc định giọng bán hàng/Gen Z.
- Độ dài theo style và nền tảng đã chọn; một quy tắc độ dài thống nhất.

Tự rà: có chi tiết riêng chưa; người đọc trả lời được điều gì;
có sáo rỗng/lặp/bịa không; có giữ yêu cầu chia phần không.
Trả đúng schema caption/hashtags/keywords/affiliate_keyword/reasoning hiện có.
```

Ví dụ biên tập từ ý của material 2086 (chưa đối chiếu video, chưa đăng):

> Có những cuộc cãi vã thắng rồi vẫn thấy mệt. Với người thân, anh chị thường nói cho rõ hay đợi cả hai bình tĩnh rồi mới nói?

Ví dụ này tạo một lựa chọn cụ thể để trả lời. Cần kiểm xem video có hỗ trợ tình huống đó và giọng page có phù hợp trước khi dùng. Hiệu quả bình luận vẫn cần đo thật.

## Verification Proof

**1. Probe prompt offline trên hàm thực tế** — AST lấy riêng `generate_caption`, stub toàn bộ IO/settings/DB/AI; không import runtime:

```text
$ wsl.exe -d Ubuntu --cd /home/vu/toolsauto --exec venv/bin/python /tmp/toolsauto-caption-prompt-audit-20261121.py
source_sha256=7583e3489a585354c8fe4932c60827dc6e9e5a2d772e188401707093c3a3dbfc
network_calls=0, db_calls=0, source_mutations=0
plain_context_present=false
plain_unique_marker_present=false
marked_context_present=true
short_requires_under100=true
short_also_ideal150_250=true
daily_forbids_CMT=true
short_role_facebook_ads=true
OFFLINE_PROMPT_CAPTURE: PASS (5 diagnostic assertions; no imports of app/runtime)
```

**2. AST registry/method inspection** — không import app:

```text
registered settings=177
ai.caption_style registered=False
BrainFactory methods=get_persona_prompt,get_visual_hook_instruction,get_engagement_secrets,build_caption_prompt
clean_json_blocks defined=False
```

**3. Test hiện có chạy với DATABASE_URL SQLite memory**:

```text
$ wsl.exe -d Ubuntu --cd /home/vu/toolsauto --exec env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_material_caption.py -q
............................                                             [100%]
28 passed in 5.43s
```

Test trên kiểm plumbing/lưu dữ liệu/guard, không chứng minh caption hấp dẫn. Lần chạy chung với `tests/test_ai_pipeline.py` không collect được:

```text
tests/test_ai_pipeline.py:8
from app.core.observability.ai_pipeline import AICaptionPipeline, CircuitState
ModuleNotFoundError: No module named 'app.core.observability.ai_pipeline'
1 error in 1.48s
```

Không sửa test import trong audit này; không báo toàn suite xanh.

**4. Kiểm tra riêng nhánh Threads, subagent chạy test mock với roles/storage tạm**:

```text
python -m pytest tests/test_threads_growth.py -q -k 'clean_post_keeps_lines or load_deals_reads or next_sale_finds or write_own_post_sale or write_own_post_ai_down or bai_rieng_vua or deal_post_appends'
7 passed, 90 deselected in 1.27s
```

Các test đó chưa bắt buộc giữ câu hỏi sau rút gọn. Probe AST formatter riêng ghi nhận `before_len=700, after_len=470, question_preserved=false, cart_note_preserved=true, footer_reserved_chars=146`.

## Bàn giao

Audit hoàn tất. **Execution Done. Cần Claude Code verify + handoff.** Chưa thay đổi hành vi caption; không mark việc sửa lỗi Done. Đề nghị Anti lập các bước nhỏ: (1) giữ context thực tế; (2) thống nhất style/role/niche và setting; (3) kiểm chất lượng trên output cuối, tránh lặp. Tách việc AI Studio và Threads formatter khỏi bản sửa caption core để giữ diff hẹp. Sau sửa: probe prompt trước/sau, test hợp đồng, chọn mẫu video từng page để review; chỉ kết luận hiệu quả tương tác sau khi có số liệu thật.
