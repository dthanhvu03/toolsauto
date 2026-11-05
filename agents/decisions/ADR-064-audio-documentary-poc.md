# ADR-064: Audio → Documentary Video — Phase 0 POC trong Studio

## Status
Accepted cho Phase 0 POC. Owner giao triển khai theo BRD `SM-MEDIA-BRD-ATDV-001` (05/11/2026) với phạm vi POC đã chốt trong PLAN-156.

## Context
- BRD yêu cầu quy trình: audio thuyết minh → transcript → fact/beats → tìm ảnh tư liệu + quyền → storyboard → preview → export.
- Studio (ADR-061) đã có intake audio, Whisper transcript, hàng việc, render ffmpeg 1-pass, UI SPA.
- Thiếu: story beats/shots, rights gate, Ken Burns, image search, fact-check tự động.

## Decision
1. **POC nằm trong `app/features/studio/doc/`**, flow mới `audio_doc` = `intake → analyze → doc_plan` rồi dừng chờ người.
2. **Ảnh POC = upload tay + metadata quyền** (FR-20). Không gọi API tìm ảnh / không mua license.
3. **Không API trả phí** trong POC (Whisper local). Fact status gắn tay (`UNVERIFIED`/`OPINION`/…).
4. **Preview mặc định 30–60 giây** đầu audio; Ken Burns nhẹ trên ảnh tĩnh.
5. **`RIGHTS_UNKNOWN` / thiếu bằng chứng → khóa export/preview phát hành.**
6. Doc state lưu trong `studio_analysis` kind=`doc` trên asset audio (JSON). Spec render vẫn là `ProjectSpec`.
7. Migration: không bảng mới ở POC. Không đụng NAS/SKU/ERP.

## Consequences
- Được: tái dùng intake/analyze/render/UI; kiểm được rights gate và Ken Burns sớm.
- Mất / nợ Phase 1: image search, fact-check web, full 9:24 export, 9:16, quota cost, duyệt đa vai trò.