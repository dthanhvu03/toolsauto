# PLAN-190 — Vá caption: giữ ngữ cảnh, viết status có chỗ để người đọc trò chuyện

## Metadata

| Field | Value |
|---|---|
| ID | PLAN-190 |
| Status | In Progress — code steps 0–8 complete; sample review, Claude verification, rollout, and Anti sign-off pending |
| Executor | Codex |
| Created by | Codex — chủ bot giao trực tiếp “lên plan vá cho anh đi em” |
| Related Task | TASK-076 |
| Related ADR | ADR-006, ADR-021, ADR-066, ADR-067 |
| Created / Updated | 2026-11-21 VN |

Không ghi giả Anti sign-off. Yêu cầu hiện tại là lập PLAN; không tự chuyển sang execute. Khi có chỉ đạo triển khai, làm từng bản vá nhỏ dưới đây, ghi proof sau từng bước. Các mục tích hợp vượt ba file được nêu riêng ở cuối, không nằm trong bản vá đầu.

## Goal

Caption nhận đủ tiêu đề/ngữ cảnh, đúng phong cách và dữ kiện; status mở ra một tình huống hoặc ý kiến mà người đọc có thể phản hồi tự nhiên. Có lựa chọn viết dài hơn một câu quảng cáo chung chung. Không bắt mọi bài có dấu hỏi, không tự nối “Bạn nghĩ sao?” vào mọi output.

Đầu ra kỹ thuật là code có proof và bộ nháp trước/sau được review. Tăng bình luận thực tế là kết quả phải đo sau xuất bản, không phải điều có thể chứng minh bằng unit test.

## Startup / Context

- Đã đọc current-status mới nhất, đầy đủ PLAN-184/187/188, workflow/rules và các ADR liên quan trong phiên; đọc lại audit `reports/ai-caption-audit-20261121/AUDIT.md`.
- Scan đầu phiên thấy maxPLAN188/TASK074. Trong lúc soạn, chat khác đã dùng PLAN189/TASK075 cho Threads conversation agent; đã đổi tài liệu caption sang PLAN190/TASK076 và kiểm source cũ vắng/destination mới có cho từng lần move. Giữ nguyên hồ sơ và công việc chat kia.
- Đã đọc PLAN189-threads-conversation-agent: chat kia hủy monitor PLAN187 và làm nhiệm vụ riêng. PLAN190 không quản lý monitor/agent Threads; phải theo trạng thái vận hành mới nhất, không khôi phục quyền cũ từ handoff lịch sử.
- Audit 23:35 VN: 15 caption mới nhất trung bình 98.9 ký tự; 50 job mới nhất đều mang `ai_style=short`. Không suy nhãn style của job Buffer thành bằng chứng caller cụ thể đã sinh caption.
- Probe offline xác nhận context thường bị bỏ, `short` mâu thuẫn dưới100/150–250, `daily` cấm CMT. `ai.caption_style` chưa đăng ký. Material/Studio thiếu niche ở nhiều trường hợp; sandbox AI Studio gọi method không tồn tại.
- Test audit: material 28 pass; Threads targeted 7 pass/90 deselected. `test_ai_pipeline.py` collect fail vì import đường dẫn đã xóa. Đã kiểm thêm `test_ai_pipeline_async.py`: còn import `app.services` và đường pipeline cũ; chưa chạy lại, không ghi thêm kết quả giả.
- Checkout có nhiều WIP. Trước code phải ghi hash/diff nền từng file đích; không reset/stash toàn repo hoặc ghi đè thay đổi của chat khác.

## Phạm vi và thứ tự

Làm **đợt 1 trước**, hoàn thành test + review nháp rồi mới tới các lỗi phụ ở đợt 2. Mỗi hàng là một thay đổi logic riêng, tối đa ba file tính cả test. Nếu thực tế cần thêm file cho cùng lỗi, dừng bước đó và báo Anti theo AGENTS.md; không đổi tên phase để né giới hạn.

### Đợt 1 — Luồng caption video/material đang dùng

| Bước | Thay đổi | File được phép sửa |
|---|---|---|
| 0 | Phục hồi test AI theo module hiện tại, xác lập baseline | `tests/test_ai_pipeline.py`, `tests/test_ai_pipeline_async.py` |
| 1 | Giữ context thường, title marker và chỉ dẫn chia phần | `app/core/orchestrator.py`, `tests/test_caption_prompt_contract.py` mới |
| 2 | Thống nhất prompt theo mục tiêu trò chuyện/bán hàng và ngân sách độ dài | `app/core/orchestrator.py`, test hợp đồng prompt trên |
| 3 | Đăng ký style dùng thật, thêm lựa chọn `conversation` | `app/core/settings.py`, `tests/test_caption_style_settings.py` mới |
| 4 | Material nhận niche từ dữ liệu tài khoản/page đã có, khi đúng đích | `app/features/viral_intake/service.py`, `tests/test_material_caption.py` |
| 5 | Tránh caption trùng gần đây trong luồng material, retry có giới hạn | `app/core/orchestrator.py`, `app/features/viral_intake/service.py`, `tests/test_material_caption.py` |

#### Bước 0 — Baseline test

- Đổi import/monkeypatch target đã xóa sang `app.core.ai.pipeline`, `app.core.ai.native_fallback` đúng code hiện tại; không tạo shim production chỉ để test cũ collect.
- Chạy material + facade + pipeline sync/async trong môi trường test tách biệt. Ghi chính xác lỗi có sẵn nếu còn; không sửa transport/provider để làm xanh ngoài scope.
- Gate: hai module collect được; đường mock không gọi AI, notifier, ghi config/cookie thật. Nếu có regression mới do bản vá test thì sửa trong đúng hai file này trước bước 1.

#### Bước 1 — Dữ liệu đầu vào không bị mất

- Giữ tương thích `ORIGINAL_VIRAL_TITLE` / `BOOST_CONTEXT`; context thường phải xuất hiện trong khối dữ liệu riêng, không bị bỏ chỉ vì thiếu marker.
- Giữ “Phần n/m”, phần kết và lời dẫn tới phần tiếp theo khi caller cung cấp. Không bơm trùng nguyên marker và title đã trích.
- Phân biệt dữ liệu title/transcript/boost với chỉ dẫn hệ thống; không làm theo yêu cầu thay vai hoặc tự quảng cáo nằm trong nội dung nguồn.
- Test phải bắt đúng lỗi cũ: plain title mất khỏi prompt; marker vẫn được giữ; chỉ dẫn phần con bị mất. Có case context rỗng và input chứa marker/lời chỉ dẫn lẫn trong dữ liệu.
- Giữ nguyên signature và schema trả về hiện có ở bước này.

#### Bước 2 — Prompt có mục tiêu rõ

- Non-sales dùng vai biên tập status theo nội dung, không mặc định Facebook Ads/Accesstrade/CVR hoặc gọi mọi cảnh là “sản phẩm”. Persona DB hiện có là gợi ý giọng, không được lấn mục tiêu và dữ kiện thật của bài.
- Khung nội dung: **chi tiết thật → tình huống/quan điểm gần người đọc → cơ hội phản hồi phù hợp**. Có thể là một lựa chọn cụ thể, trải nghiệm muốn nghe thêm, hoặc nhận xét còn chỗ để góp chuyện.
- `daily` cho phép lời mời chia sẻ tự nhiên; bỏ cấm chung mọi CMT. `short` vẫn ngắn nhưng không yêu cầu “một câu vu vơ”. `humor` không bị ép giọng Gen Z nếu không hợp nội dung/người đọc.
- Sales chỉ dùng giá, ưu đãi, số lượng, thời hạn đã có dữ kiện. Bỏ chỉ dẫn tự tạo FOMO, trải nghiệm bản thân và lời khen của người mua. Không sửa luồng affiliate/link hoặc hứa tự trả link ngoài khả năng hiện có.
- Thêm style `conversation`; unknown style giữ fallback tương thích. Không đổi tên hay loại bỏ style cũ.
- Một ngân sách độ dài duy nhất trong prompt; bỏ đoạn global150–250 mâu thuẫn. Bảng mục tiêu đề xuất, tính riêng phần caption, không tính hashtags:

| Style | Mục tiêu ký tự | Cách viết |
|---|---:|---|
| short | 80–160 | 1–2 câu, một ý cụ thể |
| conversation | 180–350 | status trò chuyện, một tình huống và một hướng phản hồi |
| daily | 180–400 | chia sẻ tự nhiên, không giả chuyện của người đăng |
| humor | 80–220 | một quan sát và câu chốt hợp ngữ cảnh |
| sales | 250–500 | lợi ích có dữ kiện, CTA đúng khả năng |
| general | 150–300 | trung tính khi chưa xác định mục tiêu |

- Tất cả phải nằm trong `ai.max_caption_length` / giới hạn cấu hình hiện hành; nếu cap nhỏ hơn khoảng mục tiêu phải thu hẹp khoảng, không tạo hai lệnh bất khả thi. Không thay đổi chính sách đọc runtime override hiện có ngoài các file được giao.
- Không hard-code nền tảng đích là TikTok chỉ vì video nguồn từ TikTok; khi chưa có đích thì dùng quy tắc trung tính.
- Test capture prompt bằng facade mock: không có mâu thuẫn độ dài, không ép CTA mua hàng ở non-sales, có quy tắc không bịa và không hỏi máy móc. Kiểm key/schema/meta cũ được giữ.

#### Bước 3 — Style phải chọn được

- Thêm `ai.caption_style` vào registry dưới dạng enum gồm các style cũ và `conversation`. Default vẫn là `short` để việc đăng ký key không tự đổi toàn hệ thống.
- Không sửa `config.py`, không cần migration. Đặt `studio_only=True` để không tự sinh control mới trên form Settings; không thêm template/UX trong PLAN này.
- Test bằng DB tạm và reset cache: không override → short; override conversation/daily → getter đọc đúng; invalid value bị từ chối; style truyền trực tiếp ở material/Studio vẫn ưu tiên hơn global.
- Việc chuyển setting thật sang `conversation` thuộc bước rollout sau khi review nháp, không ghi DB khi đang làm plan/unit test.

#### Bước 4 — Niche có nguồn gốc, thiếu thì giữ chưa biết

- Chỉ lấy `Account.page_niches_map` khi xác minh material được tạo từ tài khoản đó và `target_page` khớp khóa đích. `scraped_by_account_id` chỉ là nguồn lookup, không phải bằng chứng mọi page của tài khoản đều cùng niche.
- Nếu không tìm thấy đúng mapping, truyền niche rỗng; dùng giọng biên tập trung tính và nội dung nhìn/nghe rõ. Không đoán tuổi/giới/ngách từ tên page, không lấy đại page đầu tiên.
- Buffer hiện chỉ có `{id,name}`; Studio chưa có cột niche/audience. Bước này không giả rằng đã cấu hình đủ cho hai nhánh đó. Caption của chúng vẫn hưởng prompt trung tính mới từ bước 2.
- Test material: mapping đúng đích được truyền; sai đích/không account/không metadata giữ rỗng; không thay status, schedule, notifier trong test.

#### Bước 5 — Đa dạng và chất lượng, làm hẹp ở material

- Service lấy tối đa **5 caption gần nhất của đúng target_page**, loại material đang viết lại và caption rỗng, thứ tự ổn định. Nếu không có đích xác định thì không lấy caption của page khác. Không tải khách hàng, comment hay dữ liệu nhận dạng người đọc.
- Bổ sung đối số nội bộ tùy chọn `recent_captions=None` cho orchestrator, giữ caller cũ hoạt động. Đưa lịch sử vào prompt dưới dạng dữ liệu để tránh lặp cách mở và câu hỏi.
- Chặn cứng các ca kiểm chứng được: caption rỗng; trùng toàn văn sau chuẩn hóa khoảng trắng/hoa thường; các câu mẫu chung chung đã biết; quá cap. Không dùng regex để tự phán mọi nội dung “sáo rỗng”, không lấy dấu `?` làm điều kiện đạt.
- Gate cơ học rỗng/câu mẫu/quá cap đặt ở orchestrator nên áp dụng cho mọi caller dùng orchestrator, gồm worker và Studio. So sánh trùng với history chỉ thực hiện khi caller cấp history; trong bản vá này chỉ material cấp history. Test phải kiểm caller cũ không truyền đối số vẫn nhận caption hợp lệ như trước.
- Nếu output vi phạm, tối đa **một lần viết lại qua facade hiện có**, chỉ thêm feedback cụ thể; không chạy lại Whisper/FFmpeg, không tạo worker/call loop mới. Các attempt AI bổ sung phải được đếm/log rõ. Không thay provider/fallback chain.
- Hết lượt vẫn vi phạm: báo lỗi qua contract hiện hành, giữ caption cũ nếu có, không lưu random caption như một lần sinh thành công; không gọi schedule/notifier success. Tận dụng đường `ai_caption_error` có sẵn, không thêm schema DB.
- Test cả primary/fallback mocked ở boundary orchestrator: output xấu không lọt gate; output tốt được nhận; tối đa hai facade attempts; không đọc lịch sử khác page; rewrite không tự so trùng với caption cũ của chính nó; failure giữ caption cũ và không schedule.
- Lịch sử/cơ chế chống trùng mới ở bước này **chỉ nối cho material READY**. Worker job và Studio được hưởng prompt mới và gate cơ học nhưng chưa được nối history; không báo đã giải quyết diversity toàn bộ caller.
- Gate ba file là giới hạn thật. Nếu cần module/helper thứ tư hoặc thay nhiều caller để làm đúng, dừng bước5 và đưa phần tích hợp đó sang mục ngoài scope ở cuối; không làm một bản nửa vời rồi đánh PASS.

### Đợt 2 — Lỗi phụ tách biệt, không chặn việc review đợt 1

| Bước | Thay đổi / acceptance | File được phép sửa |
|---|---|---|
| 6A | Sửa thiếu `clean_json_blocks`; plain/fenced JSON đọc được, malformed/AI failure giữ contract tuple/error hiện tại | `app/core/ai/brain_factory.py`, `tests/test_ai_studio_service.py` mới |
| 6B | Sandbox dùng persona đã chọn và dữ liệu thử riêng; bỏ caption mẫu cố định. Giữ `title/description/hashtags` cho UI. Ghi rõ chưa phải mô phỏng đầy đủ video/transcript production | Hai file của6A |
| 7 | API caption đơn giản yêu cầu JSON đúng `CaptionPayload`, giữ bản nháp dưới data; response `{caption,meta}` và URL giữ nguyên | `app/core/ai/service.py`, `tests/test_ai_service.py` mới |
| 8 | Threads formatter bảo toàn câu hỏi/ý chính khi rút gọn, prompt original có mục tiêu trò chuyện khi phù hợp; giữ link/cart/disclosure bắt buộc với bài mua hàng | `app/features/threads/growth/content.py`, `tests/test_threads_growth.py` |

- Bước8 sửa code và test offline; không bật worker đã dừng, không tạo bài, không gọi AI thật hay đổi roles/quota. File Threads hiện có WIP nên phải review diff theo hunk trước khi chạm.
- Regression case: bản dài không được xóa câu hỏi rồi vẫn coi caption đạt; không bỏ body của một món mà còn giữ link món đó như thể nội dung vẫn đủ. Nếu không rút gọn được trong budget mà giữ các phần bắt buộc, trả không có draft theo đường hiện có để worker bỏ qua; không cắt dở câu rồi tự đăng.
- Review nháp cuối sau formatting. Không thay các prompt reply/DM đang nằm ngoài scope. Hai bài PLAN187 và hai bài PLAN188 là text duyệt tay; không dùng kết quả của chúng làm proof prompt tự động hiệu quả.

## Ngoài phạm vi bản vá này

- UI/HTML/CSS, schema/migration, public route/response, provider/model, queue/quota/account/profile, khách hàng và tiền.
- Tự viết lại hàng loạt caption đã lưu; gọi `generate_caption_for_material` trên DB thật để “thử”; đăng bài/tương tác; can thiệp monitor/agent thuộc PLAN189; bật lại Threads_Growth/CapCut_Agent_Supervisor.
- Refactor lớn orchestrator/brain factory hoặc chuẩn hóa toàn bộ AI architecture. Orchestrator vốn lớn; giữ diff nhỏ. Nếu cần tách module để tránh thêm trách nhiệm, trình lại file scope trước khi code.
- **Hai tích hợp cần PLAN/phạm vi riêng**: (a) cấu hình niche/audience chung theo ID ổn định cho Buffer+Studio; (b) history/diversity và review nội dung theo dữ liệu từng caller cho material+worker+Studio. Gate cơ học trong orchestrator ở bước5 vẫn thuộc bản vá này; không tương đương hai tích hợp trên. Mỗi tích hợp đó cần nhiều hơn ba file tính cả test, không lách bằng cách chia tên bước. Chưa coi hai hạng mục đó là được giao trong PLAN190.

## Validation Plan và nghiệm thu

### Test / source proof

- [ ] Trước mỗi bước: ghi git status, diff nền và SHA256 file đích; không làm mất WIP khác.
- [ ] Bước0 collect pipeline sync/async; ghi baseline pass/fail thực tế.
- [ ] Bước1–2 test prompt capture qua mock: title/context/part, style, dữ liệu không đáng tin, output contract.
- [ ] Bước3 test registry + override trên DB tạm; không ghi setting thật.
- [ ] Bước4–5 test material bằng DB tạm, mock queue/notifier/AI; chứng minh guard history/retry/no success side effects.
- [ ] Bước6–8 test đúng nhánh đã sửa; mock mọi network/AI và runtime files.
- [ ] `python -m py_compile` cho file sửa; Ruff chọn file sửa; `git diff --check`; không chạy refactor/lint fix toàn repo.

Lệnh dự kiến, sau khi file test mới tồn tại; kết quả bên dưới chỉ được điền từ output thật:

```bash
env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_ai_pipeline.py tests/test_ai_pipeline_async.py tests/test_ai_use_cases.py tests/test_material_caption.py -q
env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_caption_prompt_contract.py tests/test_caption_style_settings.py -q
env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_ai_studio_service.py tests/test_ai_service.py tests/test_threads_growth.py -q
```

### Review nháp trước/sau

- [x] Chọn cố định **15 mẫu**:5ngẫm sống,5thời trang,5nội dung khác; có cả trường hợp không transcript/thiếu niche. Lưu ID/hash/tiêu đề/caption cũ và dữ kiện từ clip; không chỉ suy nội dung từ title. Claude review từng mẫu vẫn pending.
- [ ] Dùng fixture hoặc bản sao asset/DB tạm để kiểm plumbing. Khi triển khai được chỉ đạo, có thể sinh nháp AI thật bằng **orchestrator trực tiếp trong harness cô lập**, tối đa15mẫu + tối đa1rewrite/mẫu; chỉ lưu `reports/ai-caption-repair-20261121/`. Redirect THUMB_DIR, transcript/temp và pipeline runtime-state sang thư mục riêng của harness; dùng settings snapshot đọc-only, stub schedule/notifier. Chặn nhánh RPA/shared Gemini cookies/browser ngay trong harness, không sửa persisted flag. Log attempt thực tế và fallback API, lỗi provider giữ pending. Không gọi service/router/processor/worker live vì có thể ghi caption và tự xếp lịch.
- [ ] Claude review mỗi mẫu theo5tiêu chí: bám dữ kiện; cụ thể thay vì sáo rỗng; đúng giọng/người đọc đã biết; có cơ hội phản hồi tự nhiên khi phù hợp; không lặp công thức/câu hỏi trong bộ mẫu. Mỗi tiêu chí0/1/2; đạt tối thiểu8/10, tiêu chí dữ kiện phải2/2.
- [ ] Mẫu có metadata thiếu không được bịa để đạt điểm. Mẫu lỗi phải chỉnh prompt hoặc giữ pending; không thay bằng mẫu dễ hơn để làm đẹp tỷ lệ.
- [ ] Ghi rõ đây là chất lượng biên tập nháp. Chưa có lượt tiếp cận/bình luận thật thì chưa kết luận tăng tương tác.

## Rollout / Rollback

1. Hoàn tất proof offline và review nháp; viết bảng các caller đã/ chưa nối history/niche.
2. Khi chủ bot chỉ đạo triển khai bản vá này, bước đổi style thật chỉ thực hiện **sau khi review đạt**: lưu giá trị cũ hoặc trạng thái chưa có key; đặt `ai.caption_style=conversation` qua settings service hiện có; readback từ session/process mới sau cacheTTL. Đây chỉ là cấu hình cho caption mới có dùng globalsetting. Không đổi caption/job đã lưu hay style được chọn tường minh.
3. Không tự restart cả stack. Nếu một process cần reload code, xác định đúng worker/web và đưa lệnh trong handoff; PLAN lập ở đây chưa thực hiện thao tác runtime.
4. Mỗi bản vá là một diff/commit riêng khi được yêu cầu commit. Rollback chỉ hunk của bản vá so với hash nền đã ghi; không `git reset --hard`, không restore toàn file chứa WIP khác. Nếu không tách hunk an toàn được thì giữ nguyên và báo.
5. Rollback setting: khôi phục đúng giá trị cũ; nếu trước đó không có key thì lưu tường minh giá trị effective cũ `short`, ghi rõ có thêm override để giữ hành vi cũ. Không gọi reset_setting vì hàm này cũng DELETE dòng production. Chỉ được xóa dòng setting khi chủ bot approve trực tiếp thao tác đó. Không xóa/repost nội dung đã đăng, không phục hồi caption cũ hàng loạt.
6. Không đủ proof live/nháp: ghi pending, không mark toàn PLAN Done/archive.

## Risks

| Risk | Cách xử lý |
|---|---|
| Trò chuyện thành câu hỏi máy móc hoặc câu tương tác rẻ | Không bắt có `?`; review ý cụ thể và khả năng trả lời |
| Caption dài lấn clip hoặc bị cắt mất câu chốt | Một budget theo style/cap; review output sau formatting |
| Niche từ tài khoản quét sai page đích | Chỉ dùng mapping exact target; thiếu giữ unknown |
| Không có metadata Buffer/Studio | Prompt trung tính; map chung được tách ngoài scope |
| Rewrite tăng chi phí/độ trễ | Tối đa1rewrite, không chạy lại xử lý media, log attempts |
| Provider fallback trả random caption | Gate cuối bắt lỗi cụ thể; failure không lưu/schedule success |
| Thử caption làm tự đăng hoặc gửi Telegram | DB tạm và mock; AI live chỉ gọi orchestrator trực tiếp |
| WIP từ chat khác bị đè | Baseline từng file, diff theo hunk, rollback chọn lọc |
| Test cũ còn lỗi sau đổi import | Ghi baseline thật; không sửa provider ngoài scope |

## Execution Notes / Verification Proof

**Code execution complete. Steps 0–8 have execution proof; fixed 15-sample review, Claude verification, rollout, and Anti sign-off remain pending.**

- Startup/số thứ tự: lượt đầu max188/074; concurrency phát sinh189/075; chuyển tài liệu caption sang190/076, source/destination checks từng file đều True/True. Không sửa PLAN189/TASK075 của chat kia.
- Bằng chứng root-cause và kết quả test audit nằm trong `reports/ai-caption-audit-20261121/AUDIT.md`; không tính là proof bản vá.
- Bước 0–8: PASS theo execution updates và proof bên dưới; baseline test còn 6 failure có sẵn được ghi rõ ở Step 0.
- Unit/regression tests: các suite mục tiêu đã chạy; regression gate Studio/API/Threads 109 passed.
- Harness đã sinh đủ 15 mẫu cố định và 8 bản sửa (23/30 facade calls); Codex preliminary score 14/15 đạt ngưỡng, nhưng mẫu 2061 là 6/10 nên AC8 FAIL/PENDING. Claude review cả 15 mẫu: PENDING.
- Rollout/style readback/runtime: PENDING; chưa đổi live setting hoặc runtime.

Khi thực thi xong phần code có proof, ghi **“Execution Done. Cần Claude Code verify + handoff.”** Không dùng câu đó để khẳng định PLAN190 đã triển khai trong lúc mới lập plan.

## Anti Sign-off Gate

Reviewed by: Antigravity — PENDING.

| Acceptance group | Proof sau vá | Pass |
|---|---|---|
| Context/part/markers | PENDING | PENDING |
| Style/prompt/facts/schema | PENDING | PENDING |
| Material niche/history/retry | PENDING | PENDING |
| Sandbox/API/Threads formatter | PENDING | PENDING |
|15mẫu + scope/rollback/handoff | PENDING | PENDING |

Verdict: PENDING — không giả approval, không archive.

## Handoff Note

Code steps 0–8 đã triển khai và có proof. Claude review 15 mẫu + Anti sign-off và rollout vẫn chờ; hai tích hợp vượt scope ở trên vẫn là backlog rõ ràng.

## Step 0 execution update — 2026-11-22

- Baseline before edits: 	ests/test_ai_pipeline.py SHA256 3121d91a7a19f5a1a102ff540680ba58d9cf983cfcf35b3655c1d24f0198354a; 	ests/test_ai_pipeline_async.py SHA256 952d360f83707bf3451001754191f9eaa38b9d10be4be184286e2f06d22bc34. Both had no pre-existing diff. Other repo WIP was preserved.
- Changed only test import/monkeypatch paths from removed pp.core.observability.ai_pipeline / pp.services.* to pp.core.ai.pipeline / pp.core.ai.native_fallback; production code unchanged.
- Baseline before path repair: env/bin/python -m pytest tests/test_ai_pipeline.py tests/test_ai_pipeline_async.py -q → collection failed in both modules (pp.core.observability.ai_pipeline missing; pp.services missing), 2 errors in 0.58s.
- After path repair: env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_ai_pipeline.py tests/test_ai_pipeline_async.py tests/test_ai_use_cases.py tests/test_material_caption.py -q → **44 passed, 6 failed, 5 warnings in 9.77s**. Both modules now collect. One sync test retains stale transport expectations (expected timeout 120s and http://router.test; current pipeline uses timeout (5.0, 90.0) and configured http://localhost:20128). Five async tests cannot run because this environment has no pytest async plugin (sync def functions are not natively supported). These are recorded baseline failures; no production/provider changes made to mask them. Mock fallback reported OPENROUTER_API_KEY not set; no live AI call was made.
- Step 0 gate: **PASS for module collection and baseline captured**; test suite baseline remains **44/50 passing**. Next: Step 1, preserving plain context, title markers, and supplied part instructions.


## Step 1 execution update — 2026-11-22

- Changed only app/core/orchestrator.py and new tests/test_caption_prompt_contract.py. Caller context is now retained in a labeled untrusted data block; title and boost marker values are extracted once, their marker wrappers are removed from plain context, and ordinary context remains intact. This preserves supplied part labels, endings, and continuation cues while telling the model not to follow instructions embedded in source text. No AI/provider or media call was made by the tests.
- Proof: venv/bin/python -m pytest tests/test_caption_prompt_contract.py -q -> 3 passed in 1.75s; py_compile PASS; Ruff output: All checks passed!; git diff --check exit 0.
- Step 1: PASS. Next: Step 2.


## Step 2 execution update — 2026-11-22

- Updated only app/core/orchestrator.py and tests/test_caption_prompt_contract.py. Added conversation style guidance; short, conversation, daily, humor, sales, and general each have one caption target. The hard cap and target interval now use config.MAX_CAPTION_LENGTH. Non-sales prompts use a neutral editor role without the Facebook Ads/Accesstrade sales framing; sales prompts require confirmed facts and prohibit invented FOMO, personal use, buyer praise, and unsupported link/DM promises. Unknown style falls back to general.
- Proof: venv/bin/python -m pytest tests/test_caption_prompt_contract.py -q -> 11 passed in 1.47s; py_compile PASS; Ruff output: All checks passed!; git diff --check exit 0.
- Step 2: PASS. Next: Step 3, register ai.caption_style and conversation without changing the default.


## Step 3 execution update — 2026-11-22

- Registered ai.caption_style as a studio-only enum with short as its default and choices short, conversation, daily, humor, sales, and general. No config.py change or migration.
- SQLite-only proof: env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_caption_style_settings.py -q -> 3 passed in 1.31s. Tests cover default, conversation/daily overrides, and rejection of invalid values. DB session/table is created in memory; process environment is restored by monkeypatch.
- Direct style precedence was already exercised for material by the prior Step 0 run (test_material_caption included in the 44 passing tests); Studio currently selects explicit params.caption_style before the global getter. No caller code changed in this step.
- Step 3: PASS. Next: Step 4, exact target-page niche mapping for material.


## Step 4 execution update — 2026-11-22

- Material caption now reads Account.page_niches_map only through mat.scraped_by_account_id and only passes the entry keyed by the exact mat.target_page. Missing source account, target page, or exact mapping results in an empty niche list. No guessing from page names and no other files changed.
- Proof: env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_material_caption.py -q -> 30 passed in 9.73s; py_compile PASS; Ruff output: All checks passed!; git diff --check exit 0 after removing whitespace from our own handoff line. Tests use SQLite temp DB and mock scheduler/AI; no live data or scheduling.
- Step 4: PASS. Next: Step 5, same-page recent-caption history and one bounded rewrite gate.


## Step 5 execution update — 2026-11-22

- Baseline before this step: app/core/orchestrator.py SHA256 4fbd18641c2fb1a1fd96062874730f4335843833b435f4abf8482cf7fdd135e2; app/features/viral_intake/service.py SHA256 d6709f838675f8a6c663bfbf177f6eea23d9c953a684f945758fa948d5fdc456; tests/test_material_caption.py SHA256 a9f947d843966bfdd111017b4157500a22c5d9fc49fbda2bdf8c7d1a7b0fc4d3.
- Service now loads at most five non-empty captions from the exact target_page, ordered by caption timestamp then id, excludes the material being edited, and passes no history if there is no target page. Orchestrator accepts optional recent_captions for old-caller compatibility and presents history only as untrusted reference data.
- Added mechanical gates for empty captions, exact known generic templates, normalized full-text duplicates when history was supplied, and configured hard-cap overflow. A failure gets one facade rewrite with specific feedback; a second failure raises the existing OutputContractViolation. Material failure preserves an existing caption and skips schedule success. No new schema/module, provider chain changes, live AI, notifier, or scheduler calls.
- Proof: env DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_material_caption.py -q -> 36 passed in 5.69s; venv/bin/python -m pytest tests/test_caption_prompt_contract.py tests/test_caption_style_settings.py -q -> 14 passed in 2.93s; py_compile PASS; Ruff: All checks passed!; git diff --check exit 0.
- Step 5: PASS. Next: Step 6A, AI Studio JSON parsing contract.


## Step 6A execution update — 2026-11-22

- Added BrainFactory.clean_json_blocks to remove a surrounding Markdown fence while leaving plain JSON unchanged. AIStudioService's existing malformed-output tuple and raised pipeline-error behavior remain unchanged.
- Proof: venv/bin/python -m pytest tests/test_ai_studio_service.py -q -> 4 passed in 1.25s; py_compile PASS; Ruff: All checks passed!; git diff --check exit 0. All AI responses are mocked; no network call.
- Step 6A: PASS. Next: Step 6B, use selected persona and separate test input without presenting a fixed sample as source truth.


## Step 6B execution update — 2026-11-22

- AI Studio sandbox now includes the selected persona and niche, labels its generated scene as synthetic test data, removes the fixed 2026 product claim, and states that the sandbox is not a production video/transcript simulation. JSON keys title/description/hashtags remain present for the UI.
- Proof: venv/bin/python -m pytest tests/test_ai_studio_service.py -q -> 6 passed in 2.36s; py_compile PASS; Ruff: All checks passed!; git diff --check exit 0. Mock responses only; no network.
- Step 6B: PASS. Next: Step 7, validate API simple-caption payload contract while preserving response shape.

## Step 7 execution update — 2026-11-22

- API simple-caption prompt now labels the caller draft as untrusted reference data and serializes it safely; instructions inside the draft are explicitly not followed. AIService accepts only CaptionPayload instances from the facade, and the public caption/meta response plus hashtag formatting are unchanged. Router/URL untouched.
- Proof: venv/bin/python -m pytest tests/test_ai_service.py -q -> 3 passed in 1.45s; py_compile PASS; Ruff: All checks passed!; git diff --check exit 0. AI facade is mocked; no network or route call.
- Step 7: PASS. Next: Step 8, inspect existing Threads formatter WIP by hunk before any edit.


## Step 8 execution update — 2026-11-22

- Baseline before this step (including pre-existing WIP): app/features/threads/growth/content.py SHA256 3c62b3c14da75abe3b02385da103b529722c0d5e2e7fa637ca956b21728b22dc; tests/test_threads_growth.py SHA256 0892c57a46fcd8836065706a4f6eea6ce94b5ee8a86c884f1ae28715a604dd64. Reviewed the existing diff before editing and retained its unrelated prompt/test hunks.
- Formatter now preserves first/last lines, question lines, cart note, and all deal rows when an item-link footer is present. It removes only removable extra lines; if required text still exceeds budget, it returns no body and the writer skips the draft. Conversation objective is added to own-post deal/sale prompts without forcing a question. Mandatory link/footer format is unchanged.
- Proof: venv/bin/python -m pytest tests/test_threads_growth.py -q -> 100 passed in 7.55s; py_compile PASS; Ruff: All checks passed!; git diff --check exit 0. Offline tests; AI calls mocked.
- Combined final regression gate: venv/bin/python -m pytest tests/test_ai_studio_service.py tests/test_ai_service.py tests/test_threads_growth.py -q -> 109 passed in 4.92s.
- Step 8: PASS. **Execution Done. Cần Claude Code verify + handoff.** Code steps 0–8 have proof; fixed 15-sample review, style setting rollout/readback, Claude review, and Anti sign-off remain pending. No live setting, worker, publish, or AI action performed.

## Fixed sample generation and preliminary review — 2026-11-22

- Selected and preserved the exact 15 samples in `reports/ai-caption-repair-20261121/sample_manifest.json`; copied source assets and used a read-only PostgreSQL transaction. The isolated harness blocked RPA/browser fallback and redirected temporary media/state; temporary directory was removed. No live caption, setting, schedule, worker, or runtime was changed.
- Initial batch: 15/15 drafts returned, one facade call each, no internal rewrite. All calls received primary Xingchi HTTP 400 `chat_completions_disabled`, then succeeded via configured 9Router Gemini 3.8 Flash fallback. Four transcripts were empty and several were noisy/short; frames were inspected.
- Codex preliminary review was below gate at 7/15. A narrow Step 2 prompt change and contract test addressed unsupported audience/body/fabric assumptions and repetitive list questions. Proof: `pytest tests/test_caption_prompt_contract.py -q` → **12 passed in 1.49s**; `py_compile` PASS; Ruff “All checks passed!”; `git diff --check` PASS.
- Generated exactly one additional draft for each of the eight initial failures; total **23/30** facade calls. Revised preliminary result: **14/15** pass threshold; sample 2061 remains **6/10** because it invents an audience behavior and lacks a natural reply opening. Full per-sample scores and evidence are in `reports/ai-caption-repair-20261121/review.md` and outputs/provider metadata in `drafts.json`.
- **AC8 FAIL/PENDING.** Codex scoring is only a preliminary review, not Claude verification. Claude must review all 15 drafts and sample 2061 must be corrected or remain pending. No live style setting, process restart, or rollout. Anti sign-off remains pending; do not mark Done/archive.
- Execution Done. Cần Claude Code verify + handoff.
