"""Trình duyệt Threads cho Growth Agent: tìm bài mới theo từ khóa + đăng reply (PLAN-158).

Dùng lại ``ThreadsAdapter`` (mở profile, nhận diện checkpoint / mất đăng nhập, selector ô soạn + nút Đăng).
Lấy bài ưu tiên từ JSON mà trang tải về (``thread_items`` → code / user.username / caption.text / taken_at),
DOM chỉ là dự phòng. Gặp checkpoint → ``ThreadsSessionInvalidError``; KHÔNG thử vượt.
Luôn đóng trình duyệt trong ``finally`` (dùng ``with GrowthBrowser(...) as b``).
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, List, Optional

from app.features.threads.adapter import ThreadsAdapter, ThreadsSessionInvalidError
from app.features.threads.growth.scanner import THREADS_HOST, ScannedPost, ThreadsScanner

logger = logging.getLogger(__name__)

REPLY_BUTTON_SELECTORS = (
    'svg[aria-label="Reply"]',
    'svg[aria-label="Trả lời"]',
    'div[role="button"]:has(svg[aria-label="Reply"])',
    'div[role="button"]:has(svg[aria-label="Trả lời"])',
)
INLINE_REPLY_SELECTORS = (
    'div[role="textbox"][aria-placeholder^="Reply to"]',
    'div[role="textbox"][aria-placeholder^="Trả lời"]',
    'div[contenteditable="true"][aria-placeholder^="Reply to"]',
)
# Nút gửi: chữ Post / Đăng (hộp thoại) hoặc mũi tên tròn svg aria-label="Reply" (ô reply dưới bài, 06/11).
_POST_LABEL_XPATH = (
    "normalize-space(.)='Post' or normalize-space(.)='Đăng'"
    " or .//*[local-name()='svg'][@aria-label='Reply' or @aria-label='Trả lời']"
)
DIALOG_POST_SELECTORS = (
    'div[role="dialog"] div[role="button"]:has-text("Post")',
    'div[role="dialog"] div[role="button"]:has-text("Đăng")',
    'div[role="dialog"] button:has-text("Post")',
    'div[role="dialog"] button:has-text("Đăng")',
)

# DOM dự phòng: mỗi bài là một khối có link /@user/post/<code> chứa <time>.
_DOM_EXTRACT_JS = """
() => {
  const out = [];
  const seen = new Set();
  for (const t of document.querySelectorAll('a[href*="/post/"] time')) {
    const a = t.closest('a');
    const href = a ? a.getAttribute('href') : '';
    if (!href || seen.has(href)) continue;
    seen.add(href);
    let box = a;
    for (let i = 0; i < 12 && box && box.parentElement; i++) {
      box = box.parentElement;
      if (box.getAttribute && box.getAttribute('data-pressable-container') === 'true') break;
    }
    out.push({href, datetime: t.getAttribute('datetime') || '', text: box ? box.innerText : ''});
  }
  return out;
}
"""


def _as_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None


def _int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def posts_from_payload(payload: Any, keyword: str) -> List[ScannedPost]:
    """Đi khắp JSON, nhặt mọi nút giống bài Threads: có ``code`` + ``user.username`` + ``caption.text``."""
    found: dict[str, ScannedPost] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            user = node.get("user")
            caption = node.get("caption")
            code = node.get("code")
            if isinstance(code, str) and isinstance(user, dict) and user.get("username"):
                text = caption.get("text") if isinstance(caption, dict) else None
                info = node.get("text_post_app_info") or {}
                # Bài khoá reply / mình đã reply rồi → bỏ.
                closed = info.get("can_reply") is False or info.get("has_viewer_replied") is True
                if text and code not in found and not closed:
                    author = str(user["username"])
                    found[code] = ScannedPost(
                        thread_id=code,
                        post_url=f"{THREADS_HOST}/@{author}/post/{code}",
                        author=author,
                        content=str(text),
                        keyword=keyword,
                        created_at=_as_dt(node.get("taken_at")),
                        is_reply=bool(info.get("is_reply")),
                        likes=_int(node.get("like_count")),
                        replies=_int(info.get("direct_reply_count")),
                        author_followers=_int(user.get("follower_count")),
                    )
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(payload)
    return list(found.values())


def posts_from_dom_rows(rows: Iterable[dict], keyword: str) -> List[ScannedPost]:
    posts: List[ScannedPost] = []
    for row in rows:
        parsed = ThreadsScanner.parse_post_url(row.get("href", ""))
        if not parsed:
            continue
        author = parsed[0]
        # innerText khối bài: dòng đầu = tên, dòng thời gian ngắn ("2h", "3 giờ") — bỏ các dòng ≤ 3 ký tự + tên.
        lines = [ln.strip() for ln in str(row.get("text", "")).splitlines() if ln.strip()]
        body = [ln for ln in lines if ln != author and len(ln) > 3]
        if not body:
            continue
        post = ThreadsScanner.parse_thread_element(
            author, "\n".join(body), row["href"], keyword, _as_dt(row.get("datetime"))
        )
        if body[0].lower().startswith(("replying to", "đang trả lời", "trả lời")):
            post.is_reply = True
            post.content = "\n".join(body[1:]) or post.content
        posts.append(post)
    return posts


class GrowthBrowser:
    """Bọc ``ThreadsAdapter`` (Playwright sync). Dùng: ``with GrowthBrowser(profile) as b: ...``."""

    def __init__(self, profile_path: str, adapter_factory: Callable[[], ThreadsAdapter] = ThreadsAdapter):
        self.profile_path = profile_path
        self.adapter = adapter_factory()
        self._payloads: list[Any] = []

    # ── vòng đời ───────────────────────────────────────────────
    def __enter__(self) -> "GrowthBrowser":
        if not self.adapter.open_session(self.profile_path):
            raise ThreadsSessionInvalidError("Không mở được trình duyệt Threads")
        self._check_session()
        self.adapter.page.on("response", self._capture)
        return self

    def __exit__(self, *exc) -> None:
        self.adapter.close_session()

    @property
    def page(self):
        return self.adapter.page

    def own_handle(self) -> Optional[str]:
        return (self.adapter._own_handle or "").lstrip("@").lower() or None

    def _check_session(self) -> None:
        if self.adapter._page_needs_login():
            raise ThreadsSessionInvalidError(f"Mất đăng nhập / checkpoint ({self.page.url})")

    def _capture(self, response) -> None:
        try:
            ctype = (response.headers or {}).get("content-type", "")
            if "json" not in ctype and "graphql" not in response.url:
                return
            text = response.text()
            # GraphQL Threads đôi khi trả nhiều dòng JSON nối nhau.
            for chunk in text.splitlines() if "\n" in text else [text]:
                chunk = chunk.strip()
                if chunk.startswith("for (;;);"):
                    chunk = chunk[len("for (;;);"):]
                if chunk[:1] in "{[":
                    self._payloads.append(json.loads(chunk))
        except Exception:
            pass  # ảnh / stream / body đã giải phóng

    def _embedded_payloads(self) -> list[Any]:
        try:
            raw = self.page.eval_on_selector_all(
                'script[type="application/json"]', "els => els.map(e => e.textContent)"
            )
        except Exception:
            return []
        out = []
        for txt in raw or []:
            if txt and "thread_items" in txt:
                try:
                    out.append(json.loads(txt))
                except ValueError:
                    continue
        return out

    def _pause(self, lo: float, hi: float) -> None:
        self.page.wait_for_timeout(int(random.uniform(lo, hi) * 1000))

    # ── tìm bài ────────────────────────────────────────────────
    def search_recent(self, keyword: str, limit: int = 10, max_scrolls: int = 4, top: bool = False) -> List[ScannedPost]:
        """Tìm bài theo từ khóa — tab «Mới nhất», hoặc «Hàng đầu» khi ``top=True``."""
        self._payloads.clear()
        self.page.goto(ThreadsScanner.build_search_url(keyword, top=top), wait_until="domcontentloaded", timeout=60000)
        self._pause(3.0, 5.0)
        self._check_session()

        posts: dict[str, ScannedPost] = {}

        def harvest() -> None:
            for payload in [*self._embedded_payloads(), *self._payloads]:
                for p in posts_from_payload(payload, keyword):
                    posts.setdefault(p.thread_id, p)
            if not posts:
                try:
                    rows = self.page.evaluate(_DOM_EXTRACT_JS)
                except Exception:
                    rows = []
                for p in posts_from_dom_rows(rows, keyword):
                    posts.setdefault(p.thread_id, p)

        harvest()
        for _ in range(max_scrolls):
            if len(posts) >= limit:
                break
            self.page.mouse.wheel(0, random.randint(1400, 2200))
            self._pause(1.8, 3.2)
            harvest()

        me = self.own_handle()
        result = [p for p in posts.values() if not me or p.author.lower() != me]
        logger.info("growth.search %r%s → %d bài", keyword, " (hàng đầu)" if top else "", len(result))
        return result[:limit]

    # ── đăng reply ─────────────────────────────────────────────
    def reply(self, post_url: str, text: str) -> Optional[str]:
        """Đăng ``text`` làm reply cho ``post_url``. Trả link reply nếu bắt được, None nếu không rõ.

        Lỗi (không thấy nút / ô soạn / nút Đăng, trang báo lỗi) → ``RuntimeError``.
        """
        self._payloads.clear()
        self.page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        self._pause(3.0, 5.0)
        self._check_session()

        target = ThreadsScanner.parse_post_url(post_url)
        # Trang bài có sẵn ô «Reply to @…» ngay dưới bài (06/11); không có thì mở hộp reply bằng nút.
        box = self.adapter._find_first_visible(INLINE_REPLY_SELECTORS, timeout_ms=8000)
        if box is None:
            button = self.adapter._find_first_visible(REPLY_BUTTON_SELECTORS, timeout_ms=5000)
            if button is None:
                raise RuntimeError("Không thấy ô / nút Trả lời trên bài")
            button.click()
            self._pause(1.2, 2.2)
            box = self.adapter._find_first_visible(tuple(self.adapter.TEXTBOX_SELECTORS), timeout_ms=10000)
        if box is None:
            raise RuntimeError("Không mở được ô soạn reply")
        box.click()
        self._pause(0.6, 1.2)
        self.page.keyboard.type(text, delay=random.randint(35, 90))
        self._pause(1.0, 1.8)

        # Nút Đăng nằm trong cùng khung với ô soạn (inline) hoặc trong hộp thoại.
        scope = box.locator(f"xpath=ancestor::div[.//div[@role='button'][{_POST_LABEL_XPATH}]][1]")
        post_btn = None
        if scope.count():
            cand = scope.first.locator(f"xpath=.//div[@role='button'][{_POST_LABEL_XPATH}]").last
            if cand.count() and cand.is_visible():
                post_btn = cand
        post_btn = post_btn or self.adapter._find_first_visible(DIALOG_POST_SELECTORS, timeout_ms=4000)
        if post_btn is None or not self.adapter._wait_for_post_button_ready(post_btn):
            raise RuntimeError("Nút Đăng không bấm được")
        post_btn.click()

        snippet = " ".join(text.split())[:40]
        deadline = time.time() + 25
        while time.time() < deadline:
            self._pause(1.0, 1.5)
            if self.adapter._page_has_publish_error():
                raise RuntimeError("Threads báo lỗi khi đăng reply")
            try:
                emptied = not (box.inner_text() or "").strip()
            except Exception:
                emptied = True  # hộp thoại đã đóng
            # Ô soạn trống lại sau khi bấm gửi = Threads đã nhận. KHÔNG dựa vào việc thấy chữ trên trang
            # (reply bị tách thành nhiều thẻ mention / link → tìm chữ hụt → báo lỗi oan → đăng lại lần 2).
            if emptied:
                break
        else:
            raise RuntimeError("Ô soạn vẫn còn chữ sau 25s — chưa đăng được")
        self._check_session()

        me = self.own_handle()
        for payload in self._payloads:
            for p in posts_from_payload(payload, ""):
                if snippet and snippet in p.content and (not me or p.author.lower() == me):
                    if not target or p.thread_id != target[1]:
                        return p.post_url
        return None
