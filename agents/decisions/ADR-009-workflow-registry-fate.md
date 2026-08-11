# ADR-009: Số phận WorkflowRegistry / GenericAdapter ("no-code layer")

## Status
Proposed — cần Owner chốt. Không thực thi trước khi có quyết định.

## Context

Tầng "no-code" gồm 4 bảng DB + ~4.3k dòng code:

| Thành phần | Dòng | Bảng DB | Số row thật (2026-08-11) |
|---|---|---|---|
| `app/templates/pages/platform_config.html` | 1777 | — | — |
| `app/core/config_service.py` | 1034 | — | — |
| `app/adapters/generic/action_executor.py` | 723 | `workflow_definitions` | **0** |
| `app/core/workflow_registry.py` | 512 | `platform_configs` | **0** |
| `app/adapters/generic/adapter.py` | 292 | `platform_selectors` | **0** |
| | | `cta_templates` | **0** |

`workflow_registry.py` tự mô tả: *"Replaces all hardcoded selectors, timing, CTA,
and adapter routing"*. Thực tế **chưa từng có một dòng dữ liệu nào**, nên mọi
đường đi đều rơi về fallback hardcode.

Tệ hơn, nhánh routing adapter **không thể thắng kể cả khi có dữ liệu**:

```python
# dispatcher.py:88 — mọi platform đang tồn tại đều nằm trong _DEDICATED_ADAPTERS
if platform in _DEDICATED_ADAPTERS and isinstance(registry_adapter, (DummyAdapter, GenericAdapter)):
    return _DEDICATED_ADAPTERS[platform]()   # ← luôn ghi đè Registry
```

`_DEDICATED_ADAPTERS` = {facebook, threads, instagram, tiktok} = **toàn bộ**
`Platform` enum. Nên `platform_configs.adapter_class` chỉ có tác dụng cho một
platform thứ 5 chưa tồn tại. `GenericAdapter` là code không thể chạm tới trong
cấu hình hiện tại.

Ba tiêu thụ còn lại **có** fallback chạy thật và có ý nghĩa vận hành khác nhau:

- `locator.py:239` — selector DB là **primary**, heuristic là fallback.
  Giá trị thật: vá selector khi Facebook đổi DOM **mà không cần deploy**.
- `dispatcher.py:140` — CTA DB, fallback `FacebookAdapter.CTA_POOL`.
- `dispatcher.py:184` — `workflow.steps` bật/tắt step; `None` = adapter chạy đủ step.

## Decision (đề xuất)

**Tách đôi, đừng xử cả cụm cùng một số phận.**

### Giữ — có giá trị vận hành thật
- `platform_selectors` + `WorkflowRegistry.get_selectors()` + `locator.py`
- `cta_templates` + `_inject_cta`

Nhưng phải **thừa nhận trong UI** rằng bảng đang trống và hệ thống đang chạy
bằng heuristic — hiện `/platform-config` không cho biết điều đó.

### Khai tử — ảo tưởng no-code
- `GenericAdapter` + `ActionExecutor` (1015 dòng) — không thể tới được
- `platform_configs.adapter_class` routing trong `get_adapter()`
- `workflow_definitions` + phần scaffolding "tạo platform mới" của `config_service`

Lý do: nó hứa "thêm platform không cần code", nhưng thêm platform thật vẫn phải
viết adapter riêng (bằng chứng: cả 4 platform đều có adapter tay). Giữ lại thì
mỗi lần đọc `dispatcher.get_adapter()` đều phải hiểu một nhánh chết.

### Phương án thay thế (nếu Owner muốn giữ no-code)
Seed thật `platform_selectors` cho Facebook từ `app/features/facebook/selectors.py`
để tầng này có ít nhất một người dùng thật, rồi đo xem hot-patch selector có thực
sự được dùng trong 1 tháng không. Không seed = coi như đã trả lời "khai tử".

## Consequences

- Xoá ~1015 dòng không thể chạm tới; `get_adapter()` còn một nhánh duy nhất
- `/platform-config` phải bỏ tab tạo platform / workflow → UI ngắn lại đáng kể
- Migration: giữ bảng, chỉ ngừng đọc (không DROP — theo RULES.md)
- **Không làm được trong phiên này**: xoá 1k dòng đường publish mà không chạy
  được pytest là đánh bạc. Chờ khôi phục Python → task riêng.

## Bằng chứng

```
psql: select count(*) from platform_configs|platform_selectors|workflow_definitions|cta_templates → 0,0,0,0
dispatcher.py:63-68, 88-94  → _DEDICATED_ADAPTERS phủ toàn bộ Platform enum
grep -rn "GenericAdapter" app → chỉ dispatcher (để ghi đè) + chính nó
```
