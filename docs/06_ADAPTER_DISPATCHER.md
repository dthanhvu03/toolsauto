# Adapter interface & dispatcher

## Base adapter contract
publish(job) -> PublishResult
- ok: bool
- details: dict (posted_url?, timing, notes)
- error: str (if ok==false)
- artifacts: dict (screenshot_path?, html_dump?)

## Dispatcher rules
- Map platform -> adapter instance
- Validate job fields before calling adapter
- Wrap adapter call in try/except
- Normalize errors

## Adapter guidelines (quality)
- Must be deterministic
- Must implement:
  - open_session()
  - publish()
  - close_session()
- Must capture debug artifacts on failure

## Acceptance criteria
- Thêm platform mới chỉ cần thêm file adapter + register