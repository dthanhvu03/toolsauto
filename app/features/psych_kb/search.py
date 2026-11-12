"""Tìm mục kho hợp câu hỏi — BM25 thuần Python trên chữ bỏ dấu (PLAN-170).

Tiếng Việt viết rời từng âm tiết nên đếm cả từ đơn lẫn cặp 2 âm tiết liền nhau («link lạ» → «link_la»); cặp được nhân đôi
trọng số vì khớp cặp nói lên nhiều hơn khớp một âm tiết lẻ. Trường «Dấu hiệu» (cách khách nói) nặng gấp 3, tiêu đề gấp 2.
Không mục nào đạt ``MIN_SCORE`` → trả ``[]`` (prompt giữ như cũ).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from app.features.psych_kb.store import Entry, KnowledgeBase, default_kb

K1, B = 1.4, 0.75
MIN_SCORE = 12.0
BIGRAM_WEIGHT = 2.0
FIELD_WEIGHTS = (("signs", 3), ("title", 2), ("why", 1), ("do", 1), ("avoid", 1), ("example", 1))

# Âm tiết quá phổ biến trong reply Threads — khớp chúng không nói lên gì.
STOPWORDS = frozenset(
    "a ah ak b ban be bi bot cai cho co cua da dang de di do duoc dc gi ha hay hoac khi khong ko la lam len luon ma minh "
    "moi mot n nay nao ne nha nhe nhieu nhu nhung o oi qua ra roi sao se t tai the thi thoi toi tren trong tu va vao vay "
    "ve vi voi xong y ạ à".split()
)


def fold(text: str) -> str:
    """Bỏ dấu, hạ chữ thường: «Sợ ấn link lạ» → «so an link la»."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def tokens(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", fold(text))
    out = [w for w in words if w not in STOPWORDS and len(w) > 1]
    out += [f"{a}_{b}" for a, b in zip(words, words[1:]) if not (a in STOPWORDS and b in STOPWORDS)]
    return out


def _doc_tokens(entry: Entry) -> List[str]:
    out: List[str] = []
    for name, weight in FIELD_WEIGHTS:
        out += tokens(getattr(entry, name)) * weight
    return out


@dataclass(frozen=True)
class Hit:
    entry: Entry
    score: float


def rank(query: str, entries: Sequence[Entry]) -> List[Hit]:
    q = Counter(tokens(query))
    if not q or not entries:
        return []
    docs = [Counter(_doc_tokens(e)) for e in entries]
    lengths = [sum(d.values()) for d in docs]
    avg = sum(lengths) / len(lengths) or 1.0
    n = len(docs)
    df = Counter(t for d in docs for t in d)
    hits = []
    for entry, doc, length in zip(entries, docs, lengths):
        score = 0.0
        for term in q:
            tf = doc.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            part = idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / avg))
            score += part * (BIGRAM_WEIGHT if "_" in term else 1.0)
        if score > 0:
            hits.append(Hit(entry, round(score, 3)))
    return sorted(hits, key=lambda h: (-h.score, h.entry.id))


def search(query: str, k: int = 3, use_for: Optional[str] = None, kb: KnowledgeBase = default_kb,
           min_score: float = MIN_SCORE) -> List[Hit]:
    """Tối đa ``k`` mục khớp nhất (bỏ mục «luôn áp dụng» — ``guidance_block`` tự thêm)."""
    pool = [e for e in kb.entries() if e.fits(use_for) and not e.always]
    return [h for h in rank(query, pool) if h.score >= min_score][:k]


def always_entries(kb: KnowledgeBase = default_kb) -> Iterable[Entry]:
    return [e for e in kb.entries() if e.always]
