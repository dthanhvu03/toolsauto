# PLAN-068: Buffer đọc đúng suất 24 giờ, giãn hỏi trạng thái bài lên 60 phút

- Executor: Claude Code (Owner giao trực tiếp 2026-10-23, nối PLAN-061, PLAN-067)
- Status: Code xong, đang chạy thật

## Bối cảnh

Tài liệu Buffer (https://developers.buffer.com/guides/api-limits.html): giới hạn theo từng key. Gói Free có 100 request/15 phút, **250 request/24 giờ**, 3000 request/30 ngày. Mỗi response có header:

```
RateLimit: "100-in-15min";r=98;t=897
RateLimit: "250-in-1day";r=248;t=86397
RateLimit: "3000-in-30days";r=2969;t=696980
```

- `client._note_budget` đọc `x-ratelimit-limit/remaining`. Đó là con số 3000, tức cửa sổ 30 ngày. Mức giữ 70% vì vậy không bao giờ chặn đúng lúc: key 2 báo "1617/3000" nhưng đã cạn 250 suất ngày.
- `sync_posted.INTERVAL_SEC` = 15 phút, tức 96 request/ngày mỗi key, gần 40% suất ngày.

## Scope

1. `client.py` `_note_budget`: đọc header `RateLimit` (một hoặc nhiều dòng, có hoặc không có khoảng trắng). Lấy cửa sổ đang chật nhất (r/q thấp nhất) làm `limit/remaining` cho mức giữ 70%. Response thành công mà một cửa sổ còn `r=0` thì cho key nghỉ `t` giây ngay, không chờ 429 (429 làm job FAILED). Không có header `RateLimit` thì vẫn đọc `x-ratelimit-*` như cũ.
2. `sync_posted.py`: `INTERVAL_SEC` 15 → 60 phút.
3. Test trong `tests/test_buffer_rate_limit_guard.py`.

## Không làm

- Không đổi mức giữ 70%, nhịp vòng 5 phút, `cluster_router`.
- Không đổi luồng first_comment (mỗi bài đang thử kèm bình luận rồi gửi lại không bình luận). Ghi nhận để Owner quyết riêng.

## Rollback

Revert commit.

## Definition of Done

- Header 3 cửa sổ, 1day `r=142` → `limit=250, remaining=142`.
- 1day `r=0; t=20282` trên response 200 → key nghỉ 20282s, request sau không gửi.
- Không có `RateLimit` → giữ hành vi `x-ratelimit-*`.
- Sync trạng thái tối đa 1 lần/60 phút.
- pytest Buffer pass như trước. Chạy thật: log có suất ngày đúng (dòng "Giữ 70% suất API" ghi `/250`).

## Proof

2026-10-23, Claude Code:

- `tests/test_buffer_rate_limit_guard.py` 15 passed (5 test mới: chọn cửa sổ chật nhất 60/250 thay vì 2500/3000; header chữ thường có khoảng trắng; response 200 mà cửa sổ ngày `r=0` → key nghỉ 20282s, request sau không gửi; không có `RateLimit` thì đọc `x-ratelimit-*`; `INTERVAL_SEC` = 3600).
- Mức giữ 70% tính theo cửa sổ có tỉ lệ còn lại thấp nhất. Có thể là cửa sổ 30 ngày (3000 ≈ 100 request/ngày về lâu dài), không chỉ cửa sổ ngày.
- Hồi quy pass: adversarial 148, api 16, cluster_challenger 22, fuzz_probes 102, cooldown_store 8, first_comment 23, manager 15, media 7, queue 8, slots 9, sync_posted 11, e2e_cluster 186, challenger_m1_r3_1 57.
- `test_buffer_cluster.py` 8 fail, `test_challenger_m1_2_concurrency.py` 4 fail: **cùng số trên code trước PLAN-068** (`git stash`). Nguyên nhân: các test này đọc `BUFFER_CHANNELS` và job thật trong DB (ví dụ chờ `'Uyển Nhi'` ở mã `6ad724e7…d1f9`), mà mã kênh vừa đổi ở PLAN-067. Lỗi cách ly test có sẵn, không sửa ở đây.
- Chạy thật 20:07 ICT: restart PM2, không 429; key mới xếp job 1118 (Sống Nhẹ 14:30 24/10); "Bo qua hoi suat kenh … giu request cho dang bai" = mức giữ đang chặn request phụ. Đến 20:10 có 6 bài hẹn trên key mới (Uyển Nhi 2, Sống Nhẹ 4, tối đa 10/kênh).
