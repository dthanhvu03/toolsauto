# PLAN-013: Điều tra GraphQL Mutation bị thiếu cho luồng Direct Publish

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-013 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-013 |
| **Related ADR** | None |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Goal
Reverse-engineer luồng publish Facebook Reels bằng cách thực thi đăng video thông qua UI và bắt network GraphQL, từ đó xác định mutation nào thực sự làm nhiệm vụ "Public" video, hoặc xác định tham số `privacy/audience` nào bị thiếu trong `ComposerStoryCreateMutation`.

---

## Context
- Việc fire `ComposerStoryCreateMutation` bằng ID video trả về `story_id`, nhưng bài viết bị lỗi `Trang này không hiển thị` (Failed ở PLAN-012).
- Có khả năng luồng Create chỉ tạo một "Draft Story" hoặc thiếu thông tin Audience, và Facebook cần thêm một mutation nữa như `ComposerStoryPublishMutation` để live bài viết.

---

## Scope
- Viết script test nhỏ hoặc bổ sung debug mode vào script Playwright hiện có để: Đăng nhập -> Vào Creator -> Upload Video -> Bắt GraphQL -> Bấm nút Publish.
- Dump tất cả POST requests tới `/api/graphql/` (hoặc các domain graph của facebook) vào file log JSON.
- Phân tích và chỉ ra sự khác biệt giữa payload đang dùng so với payload chuẩn của UI.

## Out of Scope
- Không tự fix mã nguồn worker chính ở bước này. Chỉ làm nhiệm vụ trinh sát (Investigate) và chẩn đoán bệnh.

---

## Proposed Approach
**Bước 1**: Tạo một script `scripts/investigate_graphql.py` dùng Playwright. Chạy với chế độ `headless=False` (hoặc `headless=True` nhưng dùng account test).
**Bước 2**: Lắng nghe `page.on("request")` cho route `*graphql*`. Lọc các request có các biến `friendlyName` liên quan đến `Composer`, `Publish`, `Audience`, `Privacy`.
**Bước 3**: Tự động hoặc click thủ công nút "Publish" qua UI. Trích xuất payload của request kích hoạt việc đăng bài.
**Bước 4**: Phân tích payload đó, copy đoạn JSON quan trọng vào `Verification Proof` và so sánh với payload hiện tại.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Payload quá dài/obfuscated | Med | Lọc trước và chỉ extract những phần có từ khóa `publish`, `audience`, `video_id`, `client_mutation_id`. |

---

## Validation Plan
- [x] Check 1: Lấy được payload JSON của mutation thực sự xảy ra lúc click "Publish". (**PASS**)
- [x] Check 2: Chỉ ra được trường khác biệt hoặc mutation name còn thiếu một cách trực quan. (**PASS**)

---

## Rollback Plan
Không có.

---

## Execution Notes
- ✅ Bước 1: Tạo script mới `scripts/investigate_graphql.py` (Playwright UI flow + capture request/response + dump JSON + compare baseline).
- ✅ Bước 2: Gắn listener `page.on("request")` + `page.on("response")`, lọc POST tới GraphQL (`/api/graphql`, `graph.facebook.com`, `/ajax/`), parse `variables.input`, `friendly_name`, `doc_id`, `audience`, `unpublished_content_data`.
- ✅ Bước 3: Chạy auto flow upload + next + publish + confirm schedule; dump output thực tế:
  - `logs/investigate_graphql_20260424_043436.json` (run 1)
  - `logs/investigate_graphql_20260424_043615.json` (run 2)
  - `logs/investigate_graphql_20260424_043755.json` (run 3)
  - `logs/investigate_graphql_20260424_043924.json` (run cuối có `ComposerStoryCreateMutation`)
- ✅ Bước 4: So sánh payload UI-run (file `investigate_graphql_20260424_043924.json`) với baseline direct-fire (`logs/capture_737_023704.json`) và xác định khác biệt quan trọng.

**Verification Proof**:
```
# Command 1: compile script
$ /home/vu/toolsauto/venv/bin/python -m py_compile scripts/investigate_graphql.py
# exit=0

# Command 2: run investigation
$ /home/vu/toolsauto/venv/bin/python scripts/investigate_graphql.py --account-id 4 --headless
[REQ] useComposerVideoUploaderConfigQuery doc_id=9734072893355148 av=61575286626546
[REQ] ReelsComposerPrivacySelectorQuery doc_id=26471663529158011 av=61575286626546
[REQ] ReelsComposerBoostQuery doc_id=9380291732068456 av=61575286626546
[REQ] CometCreatorComposerScheduleSettingPageWrapperQuery doc_id=26138993149025852 av=61575286626546
[REQ] ComposerStoryCreateMutation doc_id=25626053667071515 av=61575286626546
output_file: /home/vu/toolsauto/logs/investigate_graphql_20260424_043924.json
requests: 40 | responses: 40
publish_clicked: True
baseline_capture: /home/vu/toolsauto/logs/capture_737_023704.json

# Command 3: summarize mutation list + diff
UI_FRIENDLY_NAMES= ..., ComposerStoryCreateMutation, ReelsComposerPrivacySelectorQuery, ...
HAS_ComposerStoryPublishMutation= False
UI_CREATE_doc_id= 25626053667071515
BASE_CREATE_doc_id= 35222657370682144
UI_av_user_actor= 61575286626546 61575286626546 61575286626546
BASE_av_user_actor= 658349620689021 61575286626546 658349620689021
UI_unpublished_content_data= {"scheduled_publish_time": 1777012793, "unpublished_content_type": "SCHEDULED"}
BASE_unpublished_content_data= {"unpublished_content_type": "PUBLISHED"}
UI_has_post_publish_story_data= False
BASE_has_post_publish_story_data= True
UI_CREATE_RESPONSE_status= 200
UI_CREATE_RESPONSE_id_hint= story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcxMTIxMjQ4NDI4ODc
UI_CREATE_RESPONSE_contains_FALLBACK= True

# Extracted payload snippets (actual)
# UI run (ComposerStoryCreateMutation)
{
  "doc_id": "25626053667071515",
  "av": "61575286626546",
  "__user": "61575286626546",
  "variables.input.actor_id": "61575286626546",
  "variables.input.audience.privacy.base_state": "EVERYONE",
  "variables.input.unpublished_content_data": {
    "scheduled_publish_time": 1777012793,
    "unpublished_content_type": "SCHEDULED"
  }
}

# Direct-fire baseline (ComposerStoryCreateMutation)
{
  "doc_id": "35222657370682144",
  "av": "658349620689021",
  "__user": "61575286626546",
  "variables.input.actor_id": "658349620689021",
  "variables.input.audience.privacy.base_state": "EVERYONE",
  "variables.input.unpublished_content_data": {
    "unpublished_content_type": "PUBLISHED"
  },
  "variables.input.post_publish_story_data": {
    "reshare_post_as_sticker": "DISABLED"
  }
}

# Kết luận điều tra:
# 1) Không bắt được mutation riêng kiểu ComposerStoryPublishMutation (HAS_ComposerStoryPublishMutation=False).
# 2) UI publish thực tế vẫn dùng ComposerStoryCreateMutation nhưng doc_id khác hẳn baseline.
# 3) Khác biệt quan trọng nằm ở context + publish mode:
#    - UI: av/actor_id theo personal (6157...), unpublished_content_data=SCHEDULED
#    - Baseline direct-fire: av/actor_id theo page (6583...), unpublished_content_data=PUBLISHED
#    - Baseline có thêm post_publish_story_data; UI payload không có.
# 4) Response UI create có publishing_flow=\"FALLBACK\".
```

Execution Done. Cần Claude Code verify + handoff.

---

## Anti Sign-off Gate ⛔
**Reviewed by**: Antigravity — 2026-04-24

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Record lại file HAR/JSON chứa GraphQL lúc publish. | Yes — log JSON được dump ra | ✅ |
| 2 | Chỉ ra điểm khác biệt/thiếu sót. | Yes — xác định được doc_id khác biệt và thiếu PublishMutation | ✅ |
| 3 | Ghi lại JSON payload. | Yes — snippet payload được đính kèm | ✅ |

### Scope & Proof Check
- [x] Executor làm đúng Scope
- [x] Proof là output thực tế
- [x] Proof cover hết Validation Plan

### Verdict
> **APPROVED** — Codex đã hoàn thành xuất sắc việc dump traffic và tìm ra mấu chốt: Không có `ComposerStoryPublishMutation`, Facebook UI vẫn dùng `ComposerStoryCreateMutation` nhưng với `doc_id` khác (`25626053667071515`). Hơn nữa, phát hiện lỗi truyền sai context (Page vs Personal) ở payload cũ. Task hoàn thành.

---

## Handoff Note
- **Trạng thái sau execution**: Xác định được lỗi publish ảo: payload cũ (direct-fire) dùng **sai `doc_id`** (`35222657370682144` thay vì UI thật `25626053667071515`) và **trộn context page/personal** (av/actor=page `658349620689021` nhưng `__user`=personal `61575286626546`). Không cần `ComposerStoryPublishMutation` — UI vẫn chỉ dùng `ComposerStoryCreateMutation`, nhưng đúng `doc_id` + đúng context.
- **Những gì cần làm tiếp**: Codex patch `scripts/graphql_publish_job.py` theo TASK-014 / PLAN-014 (align `doc_id` + giải quyết context page vs personal).
- **Archived**: Yes — 2026-04-24
