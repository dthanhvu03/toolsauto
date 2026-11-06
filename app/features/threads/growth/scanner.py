"""Kiểu dữ liệu + tiện ích cho bài Threads quét được.

Quét thật (trình duyệt) nằm ở ``growth/browser.py``; module này không mở trình duyệt.
"""

from __future__ import annotations

import hashlib
import math
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

THREADS_HOST = "https://www.threads.com"
# /@user/post/<code>  (domain threads.com hoặc threads.net cũ)
POST_URL_RE = re.compile(r"/@([A-Za-z0-9._]+)/post/([A-Za-z0-9_-]+)")


@dataclass
class ScannedPost:
    thread_id: str
    post_url: str
    author: str
    content: str
    keyword: str
    created_at: Optional[datetime] = None
    is_reply: bool = False  # bài là reply của bài khác (không phải bài gốc)
    likes: int = 0
    replies: int = 0
    author_followers: int = 0

    @property
    def reach(self) -> int:
        return reach_score(self.likes, self.replies, self.author_followers)


def reach_score(likes: int, replies: int, followers: int) -> int:
    """Ước lượng bao nhiêu người sẽ thấy reply của mình dưới bài này (06/11: reply dưới bài vắng chỉ 3–24 lượt xem).

    Reply nhiều = đang có người đọc phần bình luận (×3); like ×1. Follower tác giả (log: 100 → 20, 10k → 40) chỉ cộng khi
    JSON có — kết quả tìm kiếm Threads hiện KHÔNG kèm follower của tác giả bài (06/11), nên thực tế ≈ 3·reply + like.
    Chỉ dùng để XẾP THỨ TỰ / lọc, không phải số lượt xem thật.
    """
    return round(10 * math.log10(1 + max(followers, 0)) + 3 * max(replies, 0) + max(likes, 0))


# Chữ chỉ tiếng Việt mới có (đ, ă, ơ, ư + nguyên âm mang dấu thanh) — Threads hầu như không trả detected_language.
_VI_CHARS = set("ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ")


def is_vietnamese(text: str, min_chars: int = 3) -> bool:
    lowered = (text or "").lower()
    return sum(1 for ch in lowered if ch in _VI_CHARS) >= min_chars


class ThreadsScanner:
    """Tiện ích URL / mã bài Threads."""

    @staticmethod
    def build_search_url(keyword: str, top: bool = False) -> str:
        """``top=False``: tab «Mới nhất»; ``top=True``: tab «Hàng đầu» (bài đang được nhiều người xem)."""
        encoded = urllib.parse.quote(keyword)
        tail = "" if top else "&filter=recent"
        return f"{THREADS_HOST}/search?q={encoded}&serp_type=default{tail}"

    @staticmethod
    def parse_post_url(url: str) -> Optional[tuple[str, str]]:
        """``(author, code)`` từ link bài, hoặc None."""
        m = POST_URL_RE.search(url or "")
        return (m.group(1), m.group(2)) if m else None

    @classmethod
    def canonical_post_url(cls, url: str) -> Optional[str]:
        parsed = cls.parse_post_url(url)
        return f"{THREADS_HOST}/@{parsed[0]}/post/{parsed[1]}" if parsed else None

    @staticmethod
    def generate_thread_id(author: str, content: str) -> str:
        """Dự phòng khi không có mã bài trong URL."""
        raw = f"{author}:{content.strip()[:100]}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @classmethod
    def parse_thread_element(
        cls, author: str, content: str, url: str, keyword: str, created_at: Optional[datetime] = None
    ) -> ScannedPost:
        parsed = cls.parse_post_url(url)
        if parsed:
            author = author or parsed[0]
            thread_id = parsed[1]  # mã bài Threads: ổn định, không đổi khi bài bị sửa
            post_url = cls.canonical_post_url(url)
        else:
            thread_id = cls.generate_thread_id(author, content)
            post_url = url or f"{THREADS_HOST}/@{author}"
        return ScannedPost(
            thread_id=thread_id,
            post_url=post_url,
            author=author,
            content=content,
            keyword=keyword,
            created_at=created_at,
        )
