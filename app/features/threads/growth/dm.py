"""Tin nhắn riêng Threads trên web (PLAN-171): đọc Inbox / Requests, đọc một cuộc trò chuyện, gửi tin.

Khảo sát chỉ đọc 13/11 (bản sao hồ sơ @us28qt):
- Danh sách: ``/messages`` (Inbox) và ``/messages/requests`` (Requests). Mỗi cuộc là ``a[href^='/messages/t/<id>/']``,
  chữ hàng = «tên · tin cuối · tuổi» (``6d``, ``1w``, ``1y``…).
- Cuộc trò chuyện ``/messages/t/<id>/``: không qua GraphQL → đọc DOM. Bong bóng là phần tử ``dir=auto`` có nền
  (khách nền sáng bên trái, mình nền tối bên phải); dòng tên / ngày / «12 followers» nền trong suốt → bỏ.
- Requests: phải bấm **Accept** mới có ô nhập (``[role=textbox]`` «Message...»).
Không nhắn trước cho ai: chỉ mở cuộc có sẵn trong hộp tin.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

BASE = "https://www.threads.com"
INBOX, REQUESTS = "inbox", "requests"
_FOLDER_URL = {INBOX: f"{BASE}/messages/", REQUESTS: f"{BASE}/messages/requests"}
_THREAD_HREF = re.compile(r"/messages/t/(\d+)/?")
_AGE = re.compile(r"^(\d+)\s*([smhdwy])$")
_AGE_DAYS = {"s": 0, "m": 0, "h": 0, "d": 1, "w": 7, "y": 365}
_ACCEPT_LABELS = ("Accept", "Chấp nhận")
_TEXTBOX = "[role='textbox']"

# Bong bóng tin: chữ lá trong khung chat (bên phải danh sách), leo lên tối đa 8 tầng tìm khung có nền + bo góc.
_BUBBLES_JS = """() => {
  const out = [];
  const paneLeft = Math.min(490, window.innerWidth * 0.38);
  const mid = (paneLeft + window.innerWidth) / 2;
  for (const el of document.querySelectorAll('div[dir="auto"], span[dir="auto"]')) {
    const t = (el.innerText || '').trim();
    if (!t || el.querySelector('div[dir="auto"], span[dir="auto"]')) continue;
    if (el.closest("[role='textbox']")) continue;
    const r = el.getBoundingClientRect();
    if (r.left < paneLeft || r.width === 0) continue;
    let bub = el, depth = 0, found = false;
    while (bub && depth < 8) {
      const s = getComputedStyle(bub);
      if (s.backgroundColor && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.borderRadius !== '0px') { found = true; break; }
      bub = bub.parentElement; depth++;
    }
    if (!found || bub.querySelector("[role='textbox']") || bub.closest("[role='textbox']")) continue;  // ô nhập + chữ gợi ý
    const br = bub.getBoundingClientRect();
    out.push({t, mine: (br.left + br.right) / 2 > mid});
  }
  return out;
}"""


@dataclass(frozen=True)
class DmRow:
    thread_id: str
    handle: str
    preview: str
    age_days: Optional[int]  # None: không đọc được tuổi
    folder: str


@dataclass(frozen=True)
class DmMessage:
    mine: bool
    text: str


def parse_age(token: str) -> Optional[int]:
    m = _AGE.match((token or "").strip().lower())
    return int(m.group(1)) * _AGE_DAYS[m.group(2)] if m else None


def rows_from(raw: List[dict], folder: str) -> List[DmRow]:
    """``[{href, text}]`` (chữ hàng: «tên\\ntin cuối\\n·\\ntuổi») → DmRow, bỏ trùng / hàng điều hướng."""
    out: List[DmRow] = []
    seen = set()
    for item in raw or []:
        m = _THREAD_HREF.search(item.get("href") or "")
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        parts = [p.strip() for p in (item.get("text") or "").split("\n") if p.strip() and p.strip() != "·"]
        if not parts:
            continue
        age = parse_age(parts[-1]) if len(parts) > 1 else None
        preview = " ".join(parts[1:-1] if age is not None else parts[1:])
        out.append(DmRow(m.group(1), parts[0].lstrip("@"), preview, age, folder))
    return out


_PLACEHOLDERS = {"message...", "tin nhắn..."}


def messages_from(raw: List[dict]) -> List[DmMessage]:
    """Bong bóng ``[{t, mine}]`` → tin theo thứ tự trên trang (cũ → mới). Thẻ xem trước link (``t.me``…) là bong bóng
    riêng cùng phía người gửi — giữ, vô hại. Bỏ chữ gợi ý của ô nhập."""
    out: List[DmMessage] = []
    for item in raw or []:
        text = (item.get("t") or "").strip()
        if text and text.lower() not in _PLACEHOLDERS:
            out.append(DmMessage(bool(item.get("mine")), text))
    return out


def unanswered(messages: List[DmMessage]) -> List[DmMessage]:
    """Các tin của khách sau tin cuối của mình (rỗng nếu tin cuối là của mình)."""
    tail: List[DmMessage] = []
    for msg in reversed(messages):
        if msg.mine:
            break
        tail.append(msg)
    return list(reversed(tail))


def signature(messages: List[DmMessage]) -> str:
    """Dấu vân tay các tin khách chưa được trả lời — đổi khi khách nhắn thêm."""
    tail = unanswered(messages)
    return hashlib.sha1("\n".join(m.text for m in tail).encode()).hexdigest()[:16] if tail else ""


class DmBrowser:
    """Thao tác hộp tin trên ``GrowthBrowser`` đang mở (cùng hồ sơ, không mở trình duyệt thứ hai)."""

    def __init__(self, growth_browser):
        self.gb = growth_browser

    @property
    def page(self):
        return self.gb.page

    def _pause(self, lo: float, hi: float) -> None:
        self.page.wait_for_timeout(int(random.uniform(lo, hi) * 1000))

    def _open(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self._pause(4.0, 6.5)
        self.gb._check_session()

    def list(self, folder: str) -> List[DmRow]:
        self._open(_FOLDER_URL[folder])
        raw = self.page.eval_on_selector_all(
            "a[href*='/messages/t/']", "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText}))"
        )
        return rows_from(raw, folder)

    def _thread_url(self, thread_id: str, folder: str) -> str:
        suffix = "?inbox_override=requests" if folder == REQUESTS else ""
        return f"{BASE}/messages/t/{thread_id}/{suffix}"

    def _accept_button(self):
        # Chữ «Accept» nằm trong div con của div[role=button] → CSS :text-is không khớp (13/11: 5 tin gửi hụt).
        for label in _ACCEPT_LABELS:
            btn = self.page.get_by_role("button", name=label, exact=True)
            if btn.count() and btn.first.is_visible():
                return btn.first
        return None

    def read(self, thread_id: str, folder: str) -> List[DmMessage]:
        self._open(self._thread_url(thread_id, folder))
        return messages_from(self.page.evaluate(_BUBBLES_JS))

    def send(self, thread_id: str, folder: str, text: str) -> None:
        """Gửi ``text`` vào cuộc đang mở (gọi sau ``read`` cùng cuộc). Requests: bấm Accept trước. Lỗi → RuntimeError."""
        if not self.page.url.split("?")[0].rstrip("/").endswith(thread_id):
            self._open(self._thread_url(thread_id, folder))
        accept = self._accept_button()
        if accept is not None:
            accept.click()
            self._pause(2.5, 4.0)
        elif folder == REQUESTS and not self.page.locator(_TEXTBOX).count():
            raise RuntimeError("Tin chờ (Requests) không thấy nút Accept")
        box = self.page.locator(_TEXTBOX).last
        try:
            box.wait_for(state="visible", timeout=10000)
        except Exception as exc:
            raise RuntimeError("Không thấy ô nhập tin nhắn") from exc
        box.click()
        self._pause(0.6, 1.2)
        lines = [ln for ln in text.split("\n")]
        for i, line in enumerate(lines):
            if line:
                self.page.keyboard.type(line, delay=random.randint(35, 85))
            if i < len(lines) - 1:
                self.page.keyboard.press("Shift+Enter")
        self._pause(0.8, 1.6)
        self.page.keyboard.press("Enter")
        deadline = time.time() + 15
        while time.time() < deadline:
            self._pause(0.8, 1.2)
            try:
                if not (box.inner_text() or "").strip():
                    break
            except Exception:
                break
        else:
            raise RuntimeError("Ô nhập vẫn còn chữ sau 15s — chưa gửi được")
        self.gb._check_session()
