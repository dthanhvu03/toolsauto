# Current Status

## System State

- Local: **http://127.0.0.1:8002** (web only; Publisher/Maintenance chạy tay khi trial)
- Reels 1080 opt-in ON
- Job **#5** (Viral #4 → kids0810): **DONE** — `post_url` đã backfill đúng `/reel/`

## Done This Session

- Prefer public `/reel/{id}` sau publish (toast → redirect → Reels scan; GraphQL chỉ last resort)
- Normalize bare `facebook.com/{id}` → `/reel/{id}`
- Backfill Job #5: match caption trên grid kids0810
- Helpers smoke OK (`_extract_reel_id` / `_normalize_post_url`)

## Post URL (Job #5)

https://www.facebook.com/reel/1580284210125564

(URL GraphQL cũ `facebook.com/1034881886179835` không phải permalink công khai.)

## Next Action

1. Anh mở link trên xác nhận Reel kids0810
2. (Tuỳ chọn) chạy MetricsChecker / Maintenance để quét views Job #5
3. Lần đăng sau: log `verified_via` = toast|redirect|reels_scan (không còn graphql_fallback nếu scan OK)
4. Commit khi yêu cầu
