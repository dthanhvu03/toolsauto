# Logging & Debug

## Log destinations
- logs/app.log (FastAPI)
- logs/worker.log (Worker)
- logs/jobs/<job_id>/ (artifacts per job)

## What to log
- Job state transitions: PENDING -> RUNNING -> DONE/FAILED
- Adapter step timing:
  - open_composer_ms
  - upload_ms
  - type_caption_ms
  - publish_wait_ms
- Errors with:
  - step name
  - short reason
  - artifact paths

## Error artifacts (required)
- screenshot.png
- page.html (dump)
- optional trace.zip

## Acceptance criteria
- Khi fail: đọc log biết fail ở bước nào + có ảnh để nhìn