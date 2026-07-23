# Adapters layer

Cross-platform **dispatch boundary** between job queue and feature adapters.

| Module | Role |
|--------|------|
| `dispatcher.py` | `get_adapter(platform)`, `Dispatcher.dispatch(job)` |
| `contracts.py` | `AdapterInterface`, `PublishResult` |
| `generic/` | DB-driven workflow adapter |

## Platform keys

Single canonical string per MXH — `app.constants.Platform` (`facebook`, `threads`, `tiktok`, `instagram`).

- `normalize_platform()` in `dispatcher.py` lowercases/strips and maps aliases (e.g. `fb` → `facebook`).
- `Job.platform` should store canonical values; dispatcher normalizes at dispatch time.

## Dedicated adapters

Registered in `get_adapter()` fallback map:

- `app.features.facebook` → `FacebookAdapter`
- `app.features.threads` → `ThreadsAdapter`
- `app.features.instagram` → `InstagramAdapter`
- `app.features.tiktok` → `TiktokAdapter`

WorkflowRegistry (DB) may override; dedicated adapters win over Dummy/Generic for known platforms.
