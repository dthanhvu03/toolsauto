# TASK-013: Điều tra mutation/field còn thiếu trong luồng Direct Publish Reels

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-013 |
| **Status** | Done |
| **Priority** | P0 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-013 |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Objective
Xác định chính xác mutation hoặc các field cấu hình bổ sung nào đang bị thiếu khiến bài đăng bị ẩn (unavailable) mặc dù `ComposerStoryCreateMutation` trả về ID thành công. 

---

## Scope
- Dùng trình duyệt Playwright (có UI hoặc headless) để thực hiện luồng publish Reels bình thường thông qua UI.
- Ghi lại (intercept) toàn bộ network traffic GraphQL xảy ra ngay sau khi upload video và nhấn nút "Publish".
- So sánh payload của `ComposerStoryCreateMutation` do hệ thống gửi (job 737) với payload thực tế khi bấm UI.
- Tìm kiếm các mutation khác xảy ra (ví dụ `ComposerStoryPublishMutation`, thiết lập Audience/Privacy).

## Out of Scope
- Không can thiệp sửa trực tiếp `scripts/graphql_publish_job.py` ngay trong task này nếu chưa xác định được rõ ràng mutation bị thiếu.

---

## Blockers
- Không.

---

## Acceptance Criteria
- [x] Record lại file HAR hoặc file JSON chứa danh sách các request GraphQL lúc nhấn nút Publish bằng UI.
- [x] Chỉ ra được điểm khác biệt: Payload của ta thiếu gì, hoặc cần gọi thêm mutation nào sau khi upload.
- [x] Ghi lại JSON payload mẫu của request bị thiếu vào `Verification Proof`.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*
- [x] Bước 1: Tạo script `scripts/investigate_graphql.py` để chạy UI flow và capture GraphQL request/response + dump JSON.
- [x] Bước 2: Chạy nhiều vòng capture (`investigate_graphql_*.json`), vòng cuối đã bắt được `ComposerStoryCreateMutation` và so sánh với baseline direct-fire `capture_737_023704.json`.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*
```
Artifacts:
- logs/investigate_graphql_20260424_043436.json
- logs/investigate_graphql_20260424_043615.json
- logs/investigate_graphql_20260424_043755.json
- logs/investigate_graphql_20260424_043924.json
- logs/investigate_step0.png
- logs/investigate_upload.png
- logs/investigate_after_publish.png

Key findings from run `investigate_graphql_20260424_043924.json`:
- Có `ComposerStoryCreateMutation` (doc_id=25626053667071515), KHÔNG thấy `ComposerStoryPublishMutation`.
- UI response trả: `publishing_flow="FALLBACK"` + `story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcxMTIxMjQ4NDI4ODc`.

Diff với baseline direct-fire (`capture_737_023704.json`):
- UI doc_id: `25626053667071515` vs Direct doc_id: `35222657370682144`.
- UI av/user/actor: `61575286626546 / 61575286626546 / 61575286626546` (personal context).
- Direct av/user/actor: `658349620689021 / 61575286626546 / 658349620689021` (page context).
- UI `unpublished_content_data`: `{"scheduled_publish_time":1777012793,"unpublished_content_type":"SCHEDULED"}`
- Direct `unpublished_content_data`: `{"unpublished_content_type":"PUBLISHED"}`
- Direct có `post_publish_story_data={"reshare_post_as_sticker":"DISABLED"}`, UI payload không có field này.

Payload snippet (UI run):
{
  "fb_api_req_friendly_name": "ComposerStoryCreateMutation",
  "doc_id": "25626053667071515",
  "av": "61575286626546",
  "__user": "61575286626546",
  "variables": {
    "input": {
      "actor_id": "61575286626546",
      "audience": {"privacy": {"base_state": "EVERYONE"}},
      "unpublished_content_data": {
        "scheduled_publish_time": 1777012793,
        "unpublished_content_type": "SCHEDULED"
      }
    }
  }
}
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-24 | New | Task được tạo bởi Anti |
| 2026-04-24 | Planned | PLAN-013 được tạo |
| 2026-04-24 | Assigned | Assign cho Codex |
| 2026-04-24 | In Progress | Codex thực thi điều tra và capture nhiều vòng UI publish |
| 2026-04-24 | Verified | Đã có file JSON capture + diff payload chi tiết với baseline direct-fire |
| 2026-04-24 | Done | Anti APPROVED PLAN-013; Claude Code archived + chuyển sang TASK-014 (patch code) |
