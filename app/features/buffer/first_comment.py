"""FirstComment generation and fallback helper for Buffer publishing."""
from __future__ import annotations

import logging
import random
import re

from app.core.ai.use_cases import AIUseCases

logger = logging.getLogger(__name__)

# 8 curated engaging starter comments (<90 chars)
FALLBACK_STARTER_COMMENTS: list[str] = [
    "Mọi người xem xong thấy sao? Để lại ý kiến cho mình biết với nhé! 👇",
    "Có ai cùng chung cảm nhận với mình không nhỉ? Bình luận chia sẻ nha! ✨",
    "Thả tim và lưu lại kẻo lúc cần tìm lại không thấy nha cả nhà! ❤️",
    "Nếu thấy hữu ích thì đừng quên lưu lại và chia sẻ cho bạn bè nhé! 📌",
    "Follow kênh để xem thêm nhiều video thú vị mỗi ngày nha cả nhà! 🔔",
    "Đố cả nhà chi tiết ấn tượng nhất trong clip là gì nè? Comment nhé! 😉",
    "Xem đi xem lại vẫn cuốn ghê, ai cùng cảm nhận thì chia sẻ nha! 🙋‍♂️",
    "Cả nhà có mẹo nào hay hơn không, chia sẻ cho mọi người cùng học hỏi với! 💬",
]


def sanitize_comment(text: str) -> str:
    """Sanitize AI-generated first comment.

    - Strips surrounding quotes, smart quotes, backticks, and markdown code fences.
    - Strips common prefixes ('First comment:', 'Bình luận:', etc.) even if wrapped in quotes or markdown.
    - Removes hashtags, markdown links (keeping anchor text), and raw URLs.
    - Strips markdown formatting (bold, italic, strikethrough).
    - Normalizes multi-spaces and newlines.
    - Clamps length to <= 150 characters.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # Remove code blocks if wrapped in ``` ... ```
    # Require whitespace/newline after language tag so characters like 'B' are not eaten
    cleaned = re.sub(r"^```(?:[a-zA-Z0-9_-]+\s+)?([\s\S]*?)```$", r"\1", cleaned).strip()

    # Repeatedly strip surrounding quotes/backticks/markdown formatting and prefixes (up to 4 passes)
    for _ in range(4):
        prev = cleaned

        # Strip surrounding quotation marks, smart quotes, backticks, and backslashes
        cleaned = re.sub(r'^[“"\'`«‘\\]+|[”"\'`»’\\]+$', "", cleaned).strip()

        # Strip markdown bold/italic/strike delimiters at borders
        cleaned = re.sub(r"^[*_~`]+|[*_~`]+$", "", cleaned).strip()

        # Strip prefixes like "First comment:", "Comment:", "Bình luận:", "Bình luận đầu tiên:"
        # Also handles optional markdown bold/italic surrounding the prefix name or colon
        cleaned = re.sub(
            r"^(?:bình\s+luận(?:\s+đầu\s+tiên)?|first\s*comment|comment)[*_~`\s]*[:：\-–—]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()

        if cleaned == prev:
            break

    # Remove hashtags (#tag)
    cleaned = re.sub(r"#\S+", "", cleaned)

    # Remove markdown links [anchor](url) -> keep anchor
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    # Remove raw URLs
    cleaned = re.sub(r"https?://\S+|www\.\S+", "", cleaned)

    # Remove inline markdown formatting like **bold**, *italic*, __bold__, _italic_, ~~strike~~
    cleaned = re.sub(r"[*_~`]{1,3}", "", cleaned)

    # Normalize whitespace & newlines into single spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Final trim of any quotes or backslashes revealed after formatting removal
    cleaned = re.sub(r'^[“"\'`«‘\\]+|[”"\'`»’\\]+$', "", cleaned).strip()

    # Clamp length to <= 150 characters
    if len(cleaned) > 150:
        cleaned = cleaned[:147].rstrip() + "..."
        if len(cleaned) > 150:
            cleaned = cleaned[:150]

    return cleaned


def get_or_create_first_comment(caption: str, topic: str = "") -> str:
    """Generate contextual first comment via AIUseCases with guaranteed safe fallback.

    Guarantees:
    - Returns string <= 150 characters.
    - Safe fallback to FALLBACK_STARTER_COMMENTS on any AI exception, timeout, rate limit, or empty output.
    - Publishing is never blocked.
    """
    clean_caption = (caption or "").strip()
    if not clean_caption:
        return random.choice(FALLBACK_STARTER_COMMENTS)

    try:
        raw_text, meta = AIUseCases.generate_first_comment(clean_caption, topic)
        if raw_text and str(raw_text).strip():
            comment = sanitize_comment(raw_text)
            if comment and len(comment) <= 150:
                return comment
            logger.warning("[FirstComment] Sanitized comment invalid or empty; using fallback.")
        else:
            logger.info("[FirstComment] Empty AI response; using fallback.")
    except Exception as exc:
        logger.warning(
            "[FirstComment] AI generation failed (%s: %s); using fallback.",
            type(exc).__name__,
            exc,
        )

    fallback = random.choice(FALLBACK_STARTER_COMMENTS)
    return fallback
