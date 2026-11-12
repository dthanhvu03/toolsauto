"""Khối gợi ý tâm lý chèn vào prompt AI (PLAN-170)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.features.psych_kb.search import always_entries, search
from app.features.psych_kb.store import KnowledgeBase, default_kb

BLOCK_LIMIT = 900


@dataclass(frozen=True)
class Guidance:
    text: str  # "" khi không mục nào khớp
    ids: Tuple[str, ...]

    def __bool__(self) -> bool:
        return bool(self.text)


def guidance_block(query: str, use_for: Optional[str] = "threads", k: int = 2,
                   kb: KnowledgeBase = default_kb, limit: int = BLOCK_LIMIT) -> Guidance:
    """Ý «Nên / Tránh» của các mục khớp + ranh giới đạo đức, gọn trong ``limit`` ký tự.

    Không đưa câu «Ví dụ» vào reply công khai — AI sẽ chép y nguyên, reply nào cũng giống nhau."""
    hits = search(query, k=k, use_for=use_for, kb=kb)
    if not hits:
        return Guidance("", ())
    head = "Gợi ý tâm lý cho tình huống này (dùng ý, đừng chép câu, đừng nhắc tên học thuyết):"
    lines: List[str] = [head]
    ids: List[str] = []
    for hit in hits:
        e = hit.entry
        line = f"- {e.title}: {e.why} Nên: {e.do} Tránh: {e.avoid}"
        if len("\n".join([*lines, line])) > limit - 200:
            line = f"- {e.title}: Nên: {e.do} Tránh: {e.avoid}"
        if len("\n".join([*lines, line])) > limit - 200 and ids:
            break
        lines.append(line[: limit - 200])
        ids.append(e.id)
    for e in always_entries(kb):
        lines.append(f"- Luôn: {e.do} Không: {e.avoid}")
    text = "\n".join(lines)
    return Guidance(text[:limit], tuple(ids))


def advisor_context(query: str, k: int = 4, kb: KnowledgeBase = default_kb) -> Guidance:
    """Ngữ cảnh đầy đủ cho cố vấn ``/tamly``: cả «Vì sao», «Ví dụ», «Nguồn»; mọi kênh."""
    hits = search(query, k=k, use_for=None, kb=kb)
    parts, ids = [], []
    for hit in hits:
        e = hit.entry
        parts.append(f"[{e.id}] {e.title}\nDấu hiệu: {e.signs}\nVì sao: {e.why}\nNên: {e.do}\nTránh: {e.avoid}\n"
                     f"Ví dụ: {e.example}\nNguồn: {e.source}")
        ids.append(e.id)
    for e in always_entries(kb):
        parts.append(f"[{e.id}] {e.title}\nNên: {e.do}\nTránh: {e.avoid}")
    return Guidance("\n\n".join(parts) if hits else "", tuple(ids))
