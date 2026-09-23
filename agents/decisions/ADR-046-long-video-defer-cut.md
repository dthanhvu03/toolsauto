# ADR-046 — Video dài: lần đầu giữ full, hỏi Chia / Cắt trên Telegram

## Context

Owner đặt `reup.max_duration_sec` (vd. 90) để cắt ngắn khi đăng tay. Video nguồn 6–11 phút
bị cắt ngay → không kịp **🧩 Chia phần** (cần file gần độ dài gốc). Xóa source sau reup làm
chia phần khó hơn.

## Decision — Hướng A

1. Setting `viral.long_video_sec` (mặc định **180**). Nguồn dài hơn ngưỡng và chưa có
   `clip_length_sec` / không phải phần con → lần Xử lý đầu **bỏ qua** «Độ dài tối đa»
   (`ignore_configured_max` → `NO_CUT_DURATION`).
2. Tin READY: nếu output còn dài ≈ nguồn → nút **🧩 Chia phần** + **✂️ Cắt ngắn** (+ Đã đăng).
3. **✂️ Cắt ngắn** (`cat90:<id>`): gắn `clip_length_sec` = `reup.max_duration_sec` (nếu ≤0
   thì 90), giữ `clip_start_sec`, rồi `process_one` (tải lại + cắt). Không dùng
   `reprocess_reup` (chỉ xào lại file `_reup` đã cắt).
4. Đặt `viral.long_video_sec = 0` → tắt trì hoãn (hành vi cũ).

## Consequences

- Lần đầu tốn dung lượng / thời gian encode full hơn.
- 📱 vẫn cần file `_reup` local (hoặc Drive) đủ lớn — không đổi trong ADR này.
- Phần con / đã đặt độ dài riêng: vẫn cắt theo quy tắc cũ.

## Files

| Thành phần | Path |
|---|---|
| Setting | `app/core/settings.py` → `viral.long_video_sec` |
| Defer | `ViralService.should_defer_duration_cut` + `processor.py` |
| Reup | `ReupProcessor.process(..., ignore_configured_max=)` |
| Nút / tip | `formatting.material_ready_buttons` / `material_ready_message` |
| Callback | `event_router._handle_cut_short` (`cat90`) |
