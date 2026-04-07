# Task: GenericAdapter No-Code

## Bước 1-4: Backend Core ✅
- [x] StepConfig schema + ValueResolver
- [x] ActionExecutor (7 actions, retry, log, screenshot)
- [x] GenericAdapter (load workflow → execute steps)
- [x] Dispatcher + auto-scaffold → GenericAdapter mặc định

## Bước 5: UI Step Builder ✅
- [x] Step Builder template: mỗi step = 1 row (Name, Action dropdown, Selector Keys, Value Source, Required, Timeout)
- [x] Controls: + Thêm step, ▲▼ di chuyển, 📋 Nhân bản, 🗑 Xóa
- [x] Form động: action = Navigate → hiện URL field, action = Click → hiện Selector Keys field
- [x] saveSteps() serialize JSON object array → DB
- [x] Backward-compatible: legacy string steps → "📋 Legacy" badge
- [x] E2E test: Tab Workflows, Add Step, Change Action — ALL PASS ✅

## Bước 6: Test Workflow + Logs (pending)
- [ ] Nút "Test Workflow" trên UI
- [ ] Dry-run với mock job, hiện kết quả trực quan
