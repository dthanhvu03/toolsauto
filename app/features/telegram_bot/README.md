# Feature: telegram_bot

Bot lệnh + poller/event router; thông báo job dùng `app.core.notifier`.

| Entry | Path |
|-------|------|
| HTTP | `router.py` |
| Logic | `service.py`, `command_handler.py`, `event_router.py`, `poller.py` |

Depends on: `app.core.queue`, `app.core.observability`, `app.core.notifier`.
