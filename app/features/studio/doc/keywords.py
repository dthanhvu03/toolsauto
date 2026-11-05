"""
AI rút từ khóa tìm ảnh cho từng cảnh từ lời đã chép (PLAN-157).

Gọi ``AIUseCases.generate_text`` theo lô; AI lỗi / trả sai định dạng → cảnh đó để trống, anh tự gõ.
Hàm gọi AI tiêm được (``generate``) để test không gọi mạng.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.studio.doc.schema import Shot

logger = logging.getLogger(__name__)

GenerateFn = Callable[[str], str | None]
BATCH = 40  # số cảnh mỗi lần gọi AI
MAX_KEYWORDS = 4


def _default_generate(prompt: str) -> str | None:
    text, _meta = AIUseCases.generate_text(prompt, purpose=AIPurpose.DOC_KEYWORDS)
    return text


def build_prompt(shots: list[Shot], language: str | None) -> str:
    items = [{"id": s.shot_id, "text": s.narration[:400]} for s in shots]
    return (
        "You pick image-search keywords for a documentary video narrated in "
        f"{language or 'an unknown language'}. Each item is one scene with the narration spoken during it.\n"
        f"For every scene give 2-{MAX_KEYWORDS} short search queries for a photo that fits it: proper names "
        "(people, teams, places, events) in their usual spelling, otherwise concise English. "
        "Scenes with empty text: infer from neighbouring scenes.\n"
        'Answer ONLY a JSON object mapping scene id to a list of queries, e.g. {"SHOT-01-01": ["Old Trafford night"]}.\n\n'
        + json.dumps(items, ensure_ascii=False)
    )


def parse(text: str | None) -> dict[str, list[str]]:
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, val in data.items():
        if isinstance(val, str):
            val = [val]
        if isinstance(val, list):
            kws = [str(v).strip()[:80] for v in val if str(v).strip()][:MAX_KEYWORDS]
            if kws:
                out[str(key)] = kws
    return out


def suggest(shots: list[Shot], language: str | None, generate: GenerateFn | None = None) -> int:
    """Gắn ``keywords`` vào các cảnh chưa có. Trả số cảnh được gắn."""
    gen = generate or _default_generate
    todo = [s for s in shots if not s.keywords]
    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            found = parse(gen(build_prompt(batch, language)))
        except Exception as exc:  # AI lỗi không được làm hỏng bước lập kế hoạch
            logger.warning("[Studio] doc keywords AI lỗi: %s", exc)
            continue
        for shot in batch:
            if found.get(shot.shot_id):
                shot.keywords = found[shot.shot_id]
                done += 1
    return done
