# PLAN-059 — Tách `app/features/facebook/adapter.py` (3.029 dòng) thành mixin + module hàm thuần

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐỀ XUẤT — chưa duyệt, KHÔNG execute**
- **Executor**: (chưa chỉ định — Anti quyết)
- **Nguồn**: AUDIT-001 §24 (God object số 1), TD-11 (P2); `current-status.md` phiên 2026-09-07
- **Liên quan**: ADR-007 (ranh giới module), ADR-008, `.importlinter`, PLAN-058 (format), TASK-059 (3 lỗi ngầm)
- **Điều kiện tiên quyết để execute**: có **≥1 tài khoản Facebook chạy được** (kèm ≥1 Page test do account đó quản lý) để verify thật **sau mỗi bước** từ Bước 2 trở đi. Chưa có account ⇒ plan này nằm ở `active/` với trạng thái ĐỀ XUẤT, không ai được bắt đầu.

> Ràng buộc vai trò: CLAUDE.md cấm Claude Code viết adapter. Plan này là **refactor không đổi hành vi** (vùng "Refactor readability/DRY"), nhưng file đích là adapter ⇒ Anti phải chỉ định Executor và, nếu giao Claude Code, ghi rõ ngoại lệ như ADR-011 đã làm.

## Vì sao chưa làm ngay

1. **Không có account Facebook** (mất vĩnh viễn 31/07/2026, `current-status.md` phiên 2026-09-05 (d)). Adapter chỉ có ý nghĩa khi mở trình duyệt thật; không mở được thì mọi bước từ 2 trở đi chỉ là "import không lỗi".
2. **Test hiện có không bao phủ hành vi trình duyệt.** 4 file test (65 test) gọi `FacebookAdapter` chỉ qua hàm thuần/static hoặc `FacebookAdapter()` với `page=None`, hoặc **grep source `adapter.py`**. Không test nào mock Playwright, không `patch(...)` nào trỏ vào adapter. Refactor lỗi ở cụm chuyển Page sẽ **xanh hết** trên CI và chỉ lộ ra khi một bài đăng nhầm Page — sự cố nặng nhất của hệ (docstring `story_composer.py`).
3. **Adapter không còn trên đường găng.** Owner đã chốt hướng C (xưởng nội dung + đăng tay). Tách sớm chỉ tạo diff lớn trên file rủi ro nhất mà không đổi được giá trị nào cho tới khi tự động đăng quay lại.
4. Code đang chứa **3 lỗi ngầm bị nuốt** (xem §Lỗi ngầm, TASK-059). Tách "nguyên trạng" sẽ mang lỗi theo; tách "kèm sửa" thì không còn là refactor không đổi hành vi. Phải quyết trước, và quyết đó cần chạy thật mới xác nhận được.

## Hiện trạng — 11 cụm trách nhiệm trong một class

Số dòng đếm từ `def` tới trước `def` kế tiếp (tổng 3.002 + 27 dòng trống giữa các khối = 3.029).

| # | Cụm | Thành viên (dòng) | Dòng | Verify được bằng |
|---|---|---|---:|---|
| A | Header module, exception, logger | imports + `_FB_HOST_NETLOCS` (1-35), `JobLoggerAdapter` (37), `PageMismatchError` (44), `__init__` (54) | 58 | import |
| B | Phiên / auth | `open_session` (60), `_is_session_alive` (74), `_try_recover_session` (82), `_ensure_authenticated_context` (443), `close_session` (1921) | 103 | **chạy thật** |
| C | Primitive Playwright: locator, selector động, timing, điều hướng | `_is_visible` (303), `_find_first_visible` (308), `_get_dynamic_selectors` (314), `_wait_and_locate_array` (340), `_report_selector_outcome` (359), `_get_dynamic_timing` (369), `_click_locator` (383), `_normalize_fb_text` (411), `_safe_goto` (424) | 136 | import + unit cho `_normalize_fb_text`; còn lại **chạy thật** |
| D | Helper URL / ID (hàm thuần) | regex consts (88), `_extract_reel_id` (96), `_normalize_post_url` (112), `_facebook_numeric_id_from_url` (2281), `_extract_page_id_from_current_page` (2289, cần page), `_normalize_fb_profile_url_for_compare` (2320), `_is_fb_homepage_url` (2332) | 114 | **unit test** (trừ `_extract_page_id_from_current_page`) |
| E | Xác minh danh tính Page | `_verify_page_identity` (493), `_verify_page_context_via_switch_banner` (2343), `_urls_indicate_same_fb_page_context` (2369), `_verify_posting_context_matches_target` (2392), `_resolve_target_page_name` (1671) | 140 | `_urls_indicate_same_fb_page_context`, `_resolve_target_page_name` unit được; còn lại **chạy thật** |
| F | Chuyển profile / Page | `_switch_to_personal_profile` (546), `_switcher_row_has_page_id` (2433), `_resolve_switcher_clickable` (2442), `_fb_aria_switch_label_is_carousel_noise` (2451), `_fb_aria_switch_label_is_primary_switch_cta` (2465), `_try_click_switcher_aria_label` (2474), `_activate_profile_switcher_row` (2532), `_reopen_profile_switch_dialog` (2577), `_switch_to_page_context` (2595-3029) | **677** | 2 static label fn unit được; còn lại **chạy thật, có Page** |
| G | Artifact thất bại / kết quả | `_build_publish_details` (142), `_capture_failure_artifacts` (247), `_failure_result` (274) | 61 | unit với page giả đơn giản |
| H | Đăng Reels | `publish` (627-1389, **763 dòng**), `_scan_reels_for_new_post` (150), `check_published_state` (1861) | **918** | **chạy thật**; dry-run được với `SAFE_MODE=true` (dừng trước nút Đăng, `adapter.py:1116`) |
| I | Đăng feed + suy link từ GraphQL | `publish_feed` (1391), `_walk_for_post_ids` (1562), `_compose_post_url` (1589), `_post_url_from_payload` (1597), `POST_URL_MARKERS`/`STORY_URL_MARKERS` (1612), `_walk_for_post_urls` (1616), `_find_latest_feed_post_url` (1639) | 260 | 4 hàm thuần: **unit test có sẵn**; `publish_feed`: **chạy thật (đăng thật, không SAFE_MODE)** |
| J | Đăng story | `story_overlay_text` (1654), `_story_author_mismatch` (1687), `_identity_key` (1699), `publish_story` (1713) | 206 | 3 hàm thuần: **unit có sẵn**; `publish_story`: **chạy thật** |
| K | Bình luận + ảnh | `CTA_POOL`, `COMMENT_PHOTO_BUTTON_LABELS`, `COMMENT_FILE_INPUT_SELECTORS` (1951-1973), `_attach_comment_image` (1975), `post_comment` (2016-2279) | 329 | `_attach_comment_image(path không tồn tại)` unit có sẵn; còn lại **chạy thật** |

## Bề mặt public PHẢI giữ nguyên (đo bằng grep toàn repo)

| Ai dùng | Cần gì từ `app.features.facebook.adapter` |
|---|---|
| `app/adapters/dispatcher.py:13,57,153,358` | `FacebookAdapter`, `PageMismatchError`, **`FacebookAdapter.CTA_POOL`** (class attr), method `open_session`, `check_published_state`, `post_comment(post_url, comment_text, image_path=None)`, `publish_feed`, `publish_story`, `publish`, `close_session` |
| `app/features/facebook/workers/publisher.py:25,565-664` | `PageMismatchError`, `FacebookAdapter()`, `open_session`, **`adapter.page`** (truyền cho `FacebookEngagementTask`), `close_session` |
| `app/features/facebook/__init__.py:7,20` | lazy re-export `FacebookAdapter`, `PageMismatchError` từ module `app.features.facebook.adapter` |
| `tests/test_feed_post_url.py` | `FacebookAdapter._post_url_from_payload`, `._walk_for_post_ids`; **đọc source `app/features/facebook/adapter.py`** (3 test) |
| `tests/test_facebook_feed_post.py` | `FacebookAdapter._walk_for_post_urls`, `hasattr(..., "publish_feed")` |
| `tests/test_facebook_story_post.py` | `FacebookAdapter.story_overlay_text`, `FacebookAdapter()._story_author_mismatch`, `._walk_for_post_urls(markers=FacebookAdapter.STORY_URL_MARKERS)`, `hasattr(..., "publish_story")` |
| `tests/test_comment_image.py` | `inspect.signature(FacebookAdapter.post_comment)`, `FacebookAdapter()._attach_comment_image`, gán `adapter.logger`; **đọc source `adapter.py`** (1 test) |
| `app/adapters/contracts.py` | `AdapterInterface` abstract: `open_session`, `publish`, `check_published_state`, `close_session` |

Kết luận: mọi tên trên (kể cả tên bắt đầu bằng `_`) là **hợp đồng**, phải còn truy cập được qua `FacebookAdapter.<tên>` sau khi tách. Mixin giữ được điều này tự nhiên; module hàm thuần thì phải để lại staticmethod/classmethod uỷ quyền trên class.

## Test bị ảnh hưởng — đổi test, không đổi hành vi

| Test | Vì sao vỡ khi tách | Sửa trong cùng bước |
|---|---|---|
| `test_feed_post_url.py::test_link_tu_mutation_duoc_uu_tien_hon_link_tren_feed` | assert chuỗi `is_mutation = "Mutation" in req_post` trong `adapter.py` | trỏ `ADAPTER_PY` → file chứa `publish_feed` |
| `test_feed_post_url.py::test_listener_chi_gan_khi_sap_bam_dang` | `src.index(...)` 3 mốc trong `adapter.py`; mốc `feed_browse` hiện khớp lần đầu ở `publish()` (939) chứ không phải `publish_feed` (1478) — thứ tự vẫn đúng nhưng là tình cờ | trỏ về file feed; khi đó cả 3 mốc cùng nằm trong `publish_feed` — test chặt hơn |
| `test_comment_image.py::test_dinh_anh_that_bai_van_gui_comment_chu` | split source `adapter.py` tại `image_attached = self._attach_comment_image(image_path)` | trỏ về file comment |
| `test_feed_post_url.py::test_listener_khong_con_loc_theo_ten_mutation_doan_truoc` | assert chuỗi **không** có — vẫn xanh dù chuyển đi đâu (xanh giả, TD-07) | không cần sửa; ghi nhận |

Hệ quả thiết kế: **`adapter.py` phải giữ là một file** (không đổi thành package `adapter/`), vì đường dẫn `app/features/facebook/adapter.py` bị 2 file test hard-code và vì `__init__.py` import theo tên module.

## Đích — sơ đồ sau khi tách

```
app/features/facebook/
├── adapter.py                         ≈ 120 dòng — GIỮ TÊN FILE
│     JobLoggerAdapter, PageMismatchError (định nghĩa tại đây, không đổi module path)
│     class FacebookAdapter(SessionMixin, BrowserPrimitivesMixin, FailureArtifactsMixin,
│                           PageIdentityMixin, ProfileSwitchMixin,
│                           ReelsPublishMixin, FeedPublishMixin, StoryPublishMixin,
│                           CommentMixin, AdapterInterface):
│         __init__ (playwright/context/page/logger)
│         staticmethod/classmethod uỷ quyền → fb_urls / graphql_urls (giữ FacebookAdapter._walk_for_post_urls ...)
├── core/
│   ├── session.py                     (đã có)
│   ├── fb_urls.py            [MỚI]    cụm D (hàm thuần) + _normalize_fb_text, _identity_key, regex, _FB_HOST_NETLOCS
│   └── graphql_urls.py       [MỚI]    _walk_for_post_urls, _walk_for_post_ids, _compose_post_url,
│                                      _post_url_from_payload, POST_URL_MARKERS, STORY_URL_MARKERS
├── adapter_mixins/            [MỚI — tên do Anti chốt; theo tiền lệ pages/reels/*Mixin]
│   ├── __init__.py
│   ├── browser.py                     BrowserPrimitivesMixin — cụm C (trừ _normalize_fb_text)
│   ├── artifacts.py                   FailureArtifactsMixin — cụm G
│   ├── session.py                     SessionMixin — cụm B
│   ├── identity.py                    PageIdentityMixin — cụm E + _extract_page_id_from_current_page
│   ├── switcher.py                    ProfileSwitchMixin — cụm F
│   ├── comment.py                     CommentMixin — cụm K (CTA_POOL ở đây; FacebookAdapter.CTA_POOL vẫn resolve qua MRO)
│   ├── story.py                       StoryPublishMixin — cụm J
│   ├── feed.py                        FeedPublishMixin — cụm I (publish_feed, _find_latest_feed_post_url)
│   └── reels.py                       ReelsPublishMixin — cụm H
├── pages/…                            (đã có, không đụng)
```

Nguyên tắc chọn mixin thay vì page object mới: (1) tiền lệ `pages/reels/` (commit `c0b7ca7`) đã dùng mixin và ổn định 2 tháng; (2) mọi hàm đều đọc `self.page`/`self.logger` và gọi chéo nhau (`publish` → 15 helper), mixin giữ nguyên `self.` nên diff chỉ là cắt-dán + import; (3) test gọi helper qua class vẫn chạy không sửa; (4) không cần đổi dispatcher/publisher. Chuyển sang page object thật (như `FacebookFeedComposer`) là bước sau, khi đã có test hành vi.

## Scope

- Tạo các module mới liệt kê ở sơ đồ; **cắt-dán nguyên văn**, chỉ sửa import và `logger_name`.
- `adapter.py` co lại còn composition root; giữ `JobLoggerAdapter`, `PageMismatchError` **định nghĩa tại `adapter.py`** (dispatcher/publisher import từ đây; `except PageMismatchError` phải cùng object).
- Thêm 1 test surface-invariant mới `tests/test_facebook_adapter_surface.py` (xem Bước 0).
- Sửa 3 test grep-source (bảng trên) trỏ đúng file mới, trong cùng commit với bước di chuyển tương ứng.

## Out of scope — KHÔNG làm trong plan này

- Không sửa 3 lỗi ngầm (TASK-059) — sửa sau khi có account để chứng minh đỏ→xanh.
- Không gộp 4 bản `_is_visible/_click_locator` (adapter, `pages/reels/page.py`, `feed_composer.py`, `story_composer.py`).
- Không xoá khối inline 705-715 trong `publish()` dù trùng `_resolve_target_page_name`.
- Không đổi `.importlinter`, không chạm nợ `metrics_checker -> pages.reels`.
- Không sửa `scripts/seed.py:16` (đường dẫn `app.adapters.facebook.adapter` đã chết từ trước).
- Không đổi chữ ký method nào, không đổi tên log `FacebookAdapter:` (log_normalizer.py:32 strip theo prefix này).
- Không chuyển `adapter.py` thành package.

## Thứ tự bước — mỗi bước = 1 commit, dừng được sau bất kỳ bước nào

Ký hiệu verify: **[U]** test hành vi có sẵn; **[I]** import + surface-invariant + `lint-imports`; **[L]** bắt buộc chạy thật với Facebook.

| Bước | Việc | Dòng rời adapter | Verify | Rủi ro riêng |
|---|---|---:|---|---|
| **0** | Baseline: chạy `pytest tests/test_feed_post_url.py tests/test_facebook_feed_post.py tests/test_facebook_story_post.py tests/test_comment_image.py -q`, full suite, `lint-imports`; ghi số. Thêm `tests/test_facebook_adapter_surface.py`: đóng băng danh sách tên attr/method của `FacebookAdapter` (snapshot `dir()` lọc dunder) + `inspect.signature` của 7 method public + `FacebookAdapter.CTA_POOL` là list ≥6 + `app.features.facebook.adapter` có `PageMismatchError`, `JobLoggerAdapter` + **không mixin nào định nghĩa trùng tên method** với mixin khác. | 0 | [I] | Không có — chỉ thêm test |
| **1** | Cụm D + hàm thuần của I/J → `core/fb_urls.py`, `core/graphql_urls.py`. Trên class giữ staticmethod/classmethod uỷ quyền cùng tên. `_walk_for_post_urls` hiện `markers or FacebookAdapter.POST_URL_MARKERS` (1620) → module const. | ≈190 | **[U]** 7 test `test_feed_post_url` + 2 `test_facebook_feed_post` + 6 `test_facebook_story_post` + [I] | Thấp. Bước duy nhất được test hành vi bao phủ thật. |
| **2** | Cụm G → `adapter_mixins/artifacts.py`; cụm C → `adapter_mixins/browser.py`. | ≈195 | [I] + [U] `_attach_comment_image` (đi qua `self.page`=None) + **[L] nhẹ**: mở session, `_safe_goto` trang chủ, `_get_dynamic_selectors("switch_menu","account_menu_button",...)` trả list | `@playwright_safe_action(logger_name=__name__)` đổi tên logger (`...adapter` → `...adapter_mixins.browser`). Kiểm không có filter/handler nào lọc theo logger name. |
| **3** | Cụm B → `adapter_mixins/session.py`. | ≈103 | [I] + **[L]**: `open_session` → `_is_session_alive` True → `close_session` → `open_session` lại (đường recover) | `_ensure_authenticated_context` chứa lỗi ngầm (c); di chuyển nguyên trạng. |
| **4** | Cụm K → `adapter_mixins/comment.py`; sửa `test_comment_image.py` grep path. | ≈329 | [U] 2 test comment + [I] + **[L]: post_comment thật lên 1 bài trên Page test, có ảnh và không ảnh** (không có SAFE_MODE — đăng thật) | `CTA_POOL` chuyển sang mixin; dispatcher đọc `FacebookAdapter.CTA_POOL` → surface test bắt. |
| **5** | Cụm J → `adapter_mixins/story.py`. | ≈206 | [U] 7 test story + [I] + **[L]: đăng 1 tin ảnh dưới danh nghĩa Page**, xác nhận `author_label` khớp Page | Đăng nhầm danh nghĩa cá nhân — kiểm chip tác giả trước khi bấm. |
| **6** | Cụm I (`publish_feed`, `_find_latest_feed_post_url`) → `adapter_mixins/feed.py`; sửa 2 test grep-source trong `test_feed_post_url.py`. | ≈180 | [U] + [I] + **[L]: đăng 1 bài chữ + 1 bài ảnh lên Page test**, lấy được `post_url` từ GraphQL | Listener `page.on("response")` gắn/gỡ trong `finally` — giữ nguyên thứ tự; test grep-source (sau khi trỏ lại) là chốt. |
| **7** | Cụm E → `adapter_mixins/identity.py`; cụm F → `adapter_mixins/switcher.py`. **Bước rủi ro nhất.** | ≈817 | [I] + **[L] bắt buộc, có ≥1 Page**: (a) từ profile cá nhân → `_switch_to_page_context(name, target_page_url=...)` True và `_verify_posting_context_matches_target` (True, …); (b) từ Page → `_switch_to_personal_profile(name)` True; (c) cố ý đưa URL Page sai → `_verify_page_identity` raise `PageMismatchError` | Đăng nhầm Page. Lỗi ngầm (b) `al_lower` nằm ở đây — chạy thật sẽ thấy log `Switch via aria-label` **không bao giờ** xuất hiện; đó là hành vi cũ, không phải hồi quy. |
| **8** | Cụm H (`publish`, `_scan_reels_for_new_post`, `check_published_state`) → `adapter_mixins/reels.py`. `adapter.py` còn ≈120 dòng. | ≈918 | [I] + **[L] hai pha**: (1) `SAFE_MODE=true` chạy tới `Post button found` rồi trả `safe_mode_dry_run_id`; (2) `SAFE_MODE=false` đăng 1 Reel thật, `verified_via` ∈ {toast, redirect, reels_scan} | Lỗi ngầm (a) `SessionLocal` ở đây. `publish()` 763 dòng có closure `intercept_graphql` bắt biến local — cắt-dán nguyên khối, không tách closure. |

Mỗi bước: commit riêng, message `refactor(fb): PLAN-059 bước N — <cụm>`; ghi proof vào §Proof. Hết account giữa chừng ⇒ dừng ở bước vừa có proof [L], phần còn lại giữ trong `adapter.py`, plan vẫn hợp lệ.

## Rủi ro chung

| Rủi ro | Mức | Chặn bằng |
|---|---|---|
| Hai mixin cùng định nghĩa một tên → MRO chọn nhầm im lặng | Cao | test "không trùng tên" ở Bước 0; đặt `AdapterInterface` cuối MRO |
| Refactor xanh CI nhưng đăng nhầm Page | **Rất cao** | Bước 7 chỉ được commit khi có proof (a)(b)(c) chạy thật; cấm skip |
| Feed/story/comment không có SAFE_MODE → verify là đăng thật | Trung bình | dùng Page test riêng, xoá bài sau; ghi URL bài vào proof |
| Đổi logger name qua `playwright_safe_action(logger_name=__name__)` | Thấp | grep handler/filter theo `app.features.facebook.adapter`; log_normalizer chỉ strip prefix msg |
| Test grep-source xanh giả (TD-07) | Trung bình | 3 test được trỏ lại; thêm surface test hành vi ở Bước 0 |
| Executor "tiện thể" sửa lỗi ngầm | Trung bình | Out of scope ghi rõ; reviewer diff phải là cắt-dán thuần |

## Lỗi ngầm phát hiện khi đọc — KHÔNG sửa trong plan này, xem TASK-059

| # | Vị trí | Lỗi | Hậu quả hiện tại |
|---|---|---|---|
| (a) | `adapter.py:695` | `SessionLocal` không import trong file | `NameError` bị `except Exception` nuốt → warning "Could not load job account"; nhánh lazy-load chưa từng chạy |
| (b) | `adapter.py:2500-2502` | `al_lower` chưa gán (chỉ có `al_norm`) | `NameError` mỗi candidate, `except: continue` → `_try_click_switcher_aria_label` **luôn False**; chuyển Page sống nhờ fallback 3a2b/3a2/3b |
| (c) | `adapter.py:463-468` | `search_terms` chỉ gán khi `not recovery_btn`, vòng `for` chạy vô điều kiện | `UnboundLocalError` khi thấy nút "Tiếp tục"; `_switch_to_page_context:2609` gọi ngoài `try` → lan lên `publish()` thành `unexpected` |
| — | `adapter.py:3003` | dump HTML vào `BASE_DIR / "tests"` lúc runtime | rác trong thư mục test của repo |

## Vì sao KHÔNG chọn phương án khác

- **Tách thành page object mới (như `FacebookFeedComposer`) ngay**: phải đổi `self.` thành `composer.` ở hàng trăm chỗ trong `publish()`, không còn là cắt-dán, không verify được khi thiếu account. Để sau.
- **Biến `adapter.py` thành package**: phá 2 test hard-code đường dẫn và làm `__init__.py` lazy import đổi ngữ nghĩa. Không đáng.
- **Big-bang một commit**: không dừng giữa chừng được khi account chết lần nữa; ADR-007 đã từ chối big-bang ở quy mô nhỏ hơn.

## Verify — tổng hợp

```
# Mỗi bước, offline:
pytest tests/test_facebook_adapter_surface.py tests/test_feed_post_url.py \
       tests/test_facebook_feed_post.py tests/test_facebook_story_post.py \
       tests/test_comment_image.py -q
pytest tests/ -q --tb=short --ignore=tests/test_threads_world_news.py
lint-imports
python -c "from app.features.facebook import FacebookAdapter, PageMismatchError; print(FacebookAdapter.__mro__)"

# Bước 2-8, chạy thật (ghi output + URL bài/tin/comment vào Proof):
#   account: <tên>, page test: <url>, SAFE_MODE=<true|false>, kết quả PublishResult(...)
```

## Proof
*(để trống — điền khi execute; không có proof [L] thì bước đó chưa Done)*

## Rollback
Mỗi bước là 1 commit độc lập ⇒ `git revert <sha>` bước đó; các bước trước vẫn đứng. Không có migration, không có thay đổi DB.

## Không làm trong PLAN này
- Không đụng dispatcher, publisher, `pages/*`, `engagement.py`.
- Không thay đổi hành vi, kể cả sửa lỗi (a)(b)(c).
- Không chạy khi chưa có account — kể cả Bước 1, trừ khi Anti tách riêng Bước 0-1 thành ngoại lệ "offline-only" (hai bước này được test hành vi bao phủ thật, không cần trình duyệt).
