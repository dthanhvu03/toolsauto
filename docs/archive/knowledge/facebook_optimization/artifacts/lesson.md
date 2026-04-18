# Facebook Post Verification & Log Localization

## Context
The Facebook post publishing process was experiencing high latency during post-link verification. Additionally, technical logs in English were confusing for end-users.

## Solution
We implemented a two-pronged solution:

### 1. Fast-Track Verification
Instead of waiting blindly for the profile to refresh, the system now:
- **Instant Catch:** Monitors for the Facebook "Success Toast" notification immediately after clicking "Post" to capture the URL.
- **Direct Navigation:** Navigates directly to the profile's **Reels Tab** (bypassing the slow main feed) and performs a high-speed JavaScript scan for the new post.
- **Fallbacks:** Uses deep-diving into the latest 5 reels and a final profile refresh only if fast-track methods fail.

### 2. Vietnamese Log Translation (LogNormalizer v2)
A unified translation system was added to `LogNormalizer`:
- **Localized Steps:** Maps technical phases to user-friendly steps like `[Bước 1/5]: Tìm nơi đăng bài`.
- **Auth Reporting:** Translates critical errors like "Account logged out" to `⚠️ Tài khoản đã bị đăng xuất hoặc cần xác minh lại (Checkpoint).`.
- **Aggressive Cleaning:** Uses regex to strip timestamps and technical prefixes (e.g., `FacebookAdapter:`) for a cleaner dashboard view.

## Related Files
- `app/adapters/facebook/adapter.py`: Core logic for Step 5/5 verification.
- `app/services/log_normalizer.py`: The translation dictionary and regex cleaner.
- `app/services/log_service.py`: Hooks the translator into the real-time stream.

## Lessons Learned
- **Aria-Labels for Toasts:** Facebook's success toasts can be detected via `[role="alert"]` or specific text like "View" / "Xem".
- **Regex Stripping:** To keep logs clean in the UI, it's safer to strip timestamps at the normalization layer rather than in the raw logging, to preserve technical logs for developers.
- **Playwright Python evaluate() Trap:** 
    - **Issue:** In the Python version of Playwright, `page.evaluate(script, *args)` does NOT support multiple positional arguments for the script. If you pass script + 2 args, it throws a "takes from 2 to 3 positional arguments but 4 were given" error.
    - **Fix:** Always wrap multiple arguments into a single list or dictionary: `page.evaluate(script, [arg1, arg2])` and use destructuring in JavaScript: `([arg1, arg2]) => { ... }`.
