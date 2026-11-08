# PLAN-164 — Kênh hết bài thì tự bật lại nguồn đang tắt

- Executor: Claude Code · Duyệt: chủ bot (08/11: «viết thuật toán và nghiệp vụ làm cái này cho anh tự động»), nối PLAN-160/161.
- Bối cảnh: Sống Nhẹ Tuổi 40 hết bài từ 05/11 — nguồn bật duy nhất `nunhanthongtue` đã cạn, nguồn `nnpt2310` tắt từ 23/10.

## Nghiệp vụ (mỗi vòng `scan_all` tự động, ~mỗi giờ)
0. Chỉ xét kênh **còn đăng Buffer trong 14 ngày** (có job buffer tạo gần đây) — kênh đã bỏ (vd Mê Câu Cá) không bật nguồn.
1. Kênh **thiếu bài**: số video READY chưa hẹn < `LOW_READY` (5) **và** không còn nguồn nào đang bật + đang thức (không
   nghỉ vì cạn — PLAN-161) cho kênh đó.
2. Kênh thiếu bài → bot tự bật **một** nguồn đang tắt của kênh đó (nguồn quét lâu nhất trước), báo Telegram 1 tin.
3. Tôn trọng tay chủ bot:
   - Nguồn mới tắt dưới 24 giờ (chủ bot vừa tắt) → không bật.
   - Một nguồn chỉ tự bật lại tối đa 1 lần / 7 ngày (chủ bot tắt lại sau khi bot bật → để yên 7 ngày).
   - Muốn chặn hẳn một nguồn: xoá nguồn.
4. Nguồn tự bật mà vẫn cạn → PLAN-161 tự cho nghỉ 24 giờ + báo «cần nguồn mới». Kênh không còn nguồn tắt nào để bật → tin báo
   cạn của PLAN-161 đã nói «cần thêm nguồn mới».

Trạng thái lưu cùng file `storage/db/config/viral_source_rest.json` (khoá `revive:<id>`), không migration.

## Scope
- `app/features/viral_intake/sources.py`, `tests/test_viral_sources.py`.

## Proof (08/11)
- Test mới: test_starving_page_revives_one_disabled_source (bật 1 nguồn tắt ≥24h, bỏ nguồn vừa tắt, chờ 7 ngày nếu chủ bot
  tắt lại), test_no_revive_when_page_has_enough_or_active_source (còn nguồn đang quét / đủ bài / kênh đã bỏ → không bật).
  pytest viral_sources{,_ui,_page} + source_fanout 114 passed; ruff sạch.
- Mô phỏng trên DB thật (chặn commit / file / Telegram): chỉ bật nguồn 4 `nnpt2310` cho Sống Nhẹ Tuổi 40; trước khi chặn kênh
  đã bỏ thì còn bật nhầm `thacaukechuyen` (Mê Câu Cá) → đã sửa. trnvp89 không còn nguồn tắt → chờ nguồn mới.
- Còn: `pm2 restart Maintenance`.
