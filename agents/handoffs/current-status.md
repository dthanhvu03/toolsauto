# Current Status

## System State

- Local: **http://127.0.0.1:8002** (Web only)
- **PLAN-044:** brand intro + UI upload; join đã khớp fps/audio + fade ~0.28s

## Done This Session [2026-07-24]

- Brand intro Phase 1–2 + UI upload Target Pages
- **Intro join mượt hơn:** match WxH/fps/sample_rate của body; scale `cover`; `xfade`/`acrossfade` (~0.28s)

## Next Action

1. Owner: upload intro → BẬT → **Reup lại** 1 clip để nghe/nhìn điểm nối
2. Muốn cắt cứng: set `"intro_fade_sec": 0` trong `reup_presets.json`
3. Muốn letterbox thay crop: `"intro_scale_mode": "contain"`
4. Commit khi yêu cầu
