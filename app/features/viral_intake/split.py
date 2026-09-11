"""
ADR-041 — chia một video dài thành N phần, cắt ở chỗ "đang gay cấn".

Hai bước tách bạch, Owner đứng giữa:

- ``propose_split`` — TÍNH kế hoạch (mốc + lý do từng phần), lưu lên cha, trả về để Owner xem.
- ``apply_split``   — TẠO N phần con theo kế hoạch đã lưu; mỗi phần là một material bình
  thường có ``clip_start_sec``/``clip_length_sec`` riêng, đi nguyên đường xử lý cũ.

Tool không tự cắt: tính sai thì Owner thấy trước khi tốn ffmpeg và trước khi đăng.

``plan_cuts`` là hàm THUẦN (không DB, không ffmpeg, AI truyền vào) — ba tầng, tầng nào cũng
nói rõ mình là tầng nào (``by``): ``ai`` → ``boundary`` → ``even``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy.orm import Session

import app.config as config
from app.constants import ViralStatus
from app.core.database.models import ViralMaterial
from app.core.media.segments import Line, Silence, scene_changes, silences, snap_to_boundary, transcript_segments
from app.features.viral_intake.service import ViralService, _clean_title_for_context, ai_provider_ready

logger = logging.getLogger(__name__)

MIN_PART_SEC = 20.0
MAX_PART_SHARE = 0.6  # không phần nào chiếm quá 60% video — "chia" mà một phần ôm gần hết là chưa chia
MIN_PARTS, MAX_PARTS = 2, 6

AskAI = Callable[[str], Optional[str]]


@dataclass
class Plan:
    n: int
    parts: list[tuple[float, float]]  # [(start, end), …] giây, liên tục, phủ hết video
    hooks: list[str]  # lý do dừng ở cuối mỗi phần (phần cuối: "kết")
    by: str  # "ai" | "boundary" | "even"
    note: str = ""
    duration: float = 0.0
    lines: int = 0  # số câu lời thoại có được — để tin nhắn nói rõ tool "nghe" được gì
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "n": self.n,
                "parts": [[round(s, 2), round(e, 2)] for s, e in self.parts],
                "hooks": self.hooks,
                "by": self.by,
                "note": self.note,
                "duration": round(self.duration, 2),
                "lines": self.lines,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | None) -> Optional["Plan"]:
        try:
            d = json.loads(raw or "")
            parts = [(float(s), float(e)) for s, e in d["parts"]]
            return cls(
                n=int(d["n"]), parts=parts, hooks=list(d.get("hooks") or []), by=str(d.get("by") or "?"),
                note=str(d.get("note") or ""), duration=float(d.get("duration") or 0), lines=int(d.get("lines") or 0),
            )
        except Exception:
            return None


# ── tầng 1: lời thoại + AI ───────────────────────────────────────────────────


def build_prompt(n: int, lines: list[Line], duration: float) -> str:
    """Prompt cho AI chọn câu KẾT của mỗi phần. Trả JSON, không văn."""
    rows = "\n".join(f"[{i}] {_mmss(ln.start)}–{_mmss(ln.end)}: {ln.text}" for i, ln in enumerate(lines))
    return (
        f"Đây là lời thoại của một video dài {_mmss(duration)}, đánh số từng câu kèm mốc thời gian.\n"
        f"Hãy chia video thành {n} PHẦN để đăng lần lượt (Phần 1/{n}, 2/{n}, …). Giữ NGUYÊN mạch truyện, "
        f"không bỏ đoạn nào. Mỗi phần phải KẾT THÚC ở một câu khiến người xem muốn xem phần tiếp theo "
        f"(vừa hé lộ, sắp có chuyện, câu hỏi chưa trả lời). Không được cắt giữa một ý đang nói dở.\n"
        f"Ràng buộc: các phần dài tương đối đều nhau, mỗi phần ít nhất {int(MIN_PART_SEC)} giây, "
        f"không phần nào dài quá {int(MAX_PART_SHARE * 100)}% video.\n\n"
        f"Trả về DUY NHẤT một JSON, không giải thích thêm, dạng:\n"
        f'{{"parts": [{{"end_line": <chỉ số câu kết của phần 1>, "hook": "<một câu ngắn: vì sao dừng ở đây>"}}, '
        f'… (đúng {n - 1} mục, phần cuối không cần)]}}\n\n'
        f"LỜI THOẠI:\n{rows}"
    )


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_ai_plan(text: str | None) -> Optional[list[tuple[int, str]]]:
    """``[(end_line, hook), …]`` hoặc ``None`` nếu AI trả thứ không đọc được."""
    if not text:
        return None
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        out = []
        for item in d.get("parts") or []:
            out.append((int(item["end_line"]), str(item.get("hook") or "").strip()))
        return out or None
    except Exception:
        return None


def _cut_after_line(lines: list[Line], idx: int) -> float:
    """Mốc cắt = cuối câu + nửa khoảng lặng tới câu sau (tối đa 1 giây) — không đứt lời."""
    end = lines[idx].end
    if idx + 1 < len(lines):
        gap = max(0.0, lines[idx + 1].start - end)
        return end + min(gap / 2.0, 1.0)
    return end


def _ai_cuts(duration: float, n: int, lines: list[Line], ask_ai: AskAI) -> Optional[tuple[list[float], list[str]]]:
    if len(lines) < n * 2:  # ít câu quá thì AI cũng chỉ đoán
        return None
    try:
        raw = ask_ai(build_prompt(n, lines, duration))
    except Exception as exc:
        logger.warning("[SPLIT] AI hỏng (%s) — lùi về ranh giới.", exc)
        return None
    items = parse_ai_plan(raw)
    if not items or len(items) != n - 1:
        return None
    cuts, hooks = [], []
    for idx, hook in items:
        if not 0 <= idx < len(lines):
            return None
        cuts.append(_cut_after_line(lines, idx))
        hooks.append(hook or "AI chọn")
    return cuts, hooks


# ── tầng 2/3: ranh giới / chia đều ──────────────────────────────────────────


def _boundary_cuts(duration: float, n: int, silence_list: list[Silence], scenes: list[float]) -> tuple[list[float], str, str]:
    even = [duration * i / n for i in range(1, n)]
    cuts, missed = [], []
    for i, t in enumerate(even, 1):
        snapped = snap_to_boundary(t, silence_list=silence_list, scenes=scenes)
        if snapped is None:
            missed.append(i)
            cuts.append(t)
        else:
            cuts.append(snapped)
    if not missed:
        return cuts, "boundary", "chia đều rồi kéo về khoảng lặng / đổi cảnh gần nhất"
    if len(missed) == len(even):
        return even, "even", "không có khoảng lặng hay đổi cảnh nào gần — chia đều, CHƯA tính"
    return cuts, "boundary", "mốc " + ", ".join(str(i) for i in missed) + " không có ranh giới gần, để chia đều"


def _valid(cuts: list[float], duration: float, n: int) -> bool:
    if len(cuts) != n - 1:
        return False
    edges = [0.0] + list(cuts) + [duration]
    for a, b in zip(edges, edges[1:]):
        if b - a < MIN_PART_SEC or b - a > MAX_PART_SHARE * duration:
            return False
    return True


def plan_cuts(
    duration: float,
    n: int,
    *,
    lines: list[Line],
    silence_list: list[Silence],
    scenes: list[float],
    ask_ai: AskAI | None,
) -> Plan:
    """Ba tầng, tầng nào ra kết quả cũng nói rõ mình là tầng nào."""
    n = max(MIN_PARTS, min(MAX_PARTS, int(n)))
    # Đo thật (2026-09-11): video có nhạc nền ⇒ `silencedetect` trả 0 khoảng lặng, trong khi
    # Whisper vẫn tách được 28 câu. Cuối mỗi câu là ranh giới tốt nhất — đưa vào tầng 2 luôn,
    # để không AI vẫn không cắt giữa câu.
    silence_list = list(silence_list) + [
        Silence(start=a.end, end=max(a.end, b.start)) for a, b in zip(lines, lines[1:])
    ]
    if ask_ai and lines:
        got = _ai_cuts(duration, n, lines, ask_ai)
        if got and _valid(got[0], duration, n):
            cuts, hooks = got
            return Plan(n=n, parts=_parts(cuts, duration), hooks=hooks + ["kết"], by="ai",
                        note="AI đọc lời thoại, chọn câu kết mỗi phần", duration=duration, lines=len(lines))
        if got:
            logger.info("[SPLIT] AI trả mốc không hợp lệ (%s) — lùi về ranh giới.", [round(c) for c in got[0]])

    cuts, by, note = _boundary_cuts(duration, n, silence_list, scenes)
    if not _valid(cuts, duration, n):
        cuts, by, note = [duration * i / n for i in range(1, n)], "even", "ranh giới gần nhất làm phần quá ngắn — chia đều"
    return Plan(n=n, parts=_parts(cuts, duration), hooks=["—"] * (n - 1) + ["kết"], by=by, note=note,
                duration=duration, lines=len(lines))


def _parts(cuts: list[float], duration: float) -> list[tuple[float, float]]:
    edges = [0.0] + [float(c) for c in cuts] + [float(duration)]
    return [(a, b) for a, b in zip(edges, edges[1:])]


def _mmss(sec: float) -> str:
    s = int(round(sec))
    return f"{s // 60}:{s % 60:02d}"


# ── bước 1: đề nghị ──────────────────────────────────────────────────────────


def propose_split(db: Session, material_id: int, n: int) -> dict:
    """
    Tính kế hoạch chia và lưu lên cha. Trả ``{"ok", "msg", "plan", "sheet"}``.

    Chậm (Whisper ≈ 0.9× độ dài video trên CPU, đo 2026-09-11) — gọi từ luồng nền.
    """
    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return {"ok": False, "msg": f"Không tìm thấy material #{material_id}"}
    if getattr(mat, "parent_material_id", None):
        return {"ok": False, "msg": f"#{material_id} đã là một phần con — chia từ video gốc #{mat.parent_material_id}."}
    if not MIN_PARTS <= int(n) <= MAX_PARTS:
        return {"ok": False, "msg": f"Số phần phải từ {MIN_PARTS} tới {MAX_PARTS}."}

    src = ViralService.find_source_path(mat.id, mat.platform)
    if not src:
        return {"ok": False, "msg": f"#{material_id} chưa có file gốc trên máy — bấm ⚙️ Xử lý một lần trước (file gốc giữ 7 ngày)."}
    duration = ViralService.probe_duration(src)
    if duration < int(n) * MIN_PART_SEC:
        return {"ok": False, "msg": f"Video chỉ dài {_mmss(duration)}, không đủ chia {n} phần (mỗi phần ≥ {int(MIN_PART_SEC)}s)."}

    ai_ok, _why = ai_provider_ready(db)
    ask_ai: AskAI | None = None
    if ai_ok:
        from app.core.ai.use_cases import AIPurpose, AIUseCases

        def ask_ai(prompt: str) -> Optional[str]:
            text, _meta = AIUseCases.generate_text(prompt, purpose=AIPurpose.SPLIT_PLAN)
            return text

    lines = transcript_segments(src)
    plan = plan_cuts(
        duration, int(n),
        lines=lines,
        silence_list=silences(src),
        scenes=scene_changes(src),
        ask_ai=ask_ai,
    )
    if not ai_ok and lines:
        plan.note += " (AI chưa sẵn sàng: " + _why + ")"

    mat.split_plan = plan.to_json()
    db.commit()

    ViralService.ensure_source_frames(mat.id, src)
    sheet = ViralService.build_frame_sheet(mat.id)
    return {"ok": True, "msg": f"Đã tính kế hoạch chia {plan.n} phần cho #{material_id}.", "plan": plan, "sheet": sheet}


# ── bước 2: tạo phần con ─────────────────────────────────────────────────────


def existing_parts(db: Session, parent_id: int) -> list[ViralMaterial]:
    return (
        db.query(ViralMaterial)
        .filter(ViralMaterial.parent_material_id == parent_id)
        .order_by(ViralMaterial.part_index.asc())
        .all()
    )


def apply_split(db: Session, material_id: int) -> dict:
    """
    Tạo N phần con theo ``split_plan`` đã lưu trên cha. Trả ``{"ok", "msg", "child_ids"}``.

    Mỗi phần: material mới, ``clip_start/length`` riêng, file gốc NỐI CỨNG sang tên của con
    để ``find_source_path(con)`` thấy và tên ``_reup`` không đụng nhau. Không nối cứng được
    (khác ổ) thì copy — tốn đĩa nhưng đúng.
    """
    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return {"ok": False, "msg": f"Không tìm thấy material #{material_id}"}
    plan = Plan.from_json(getattr(mat, "split_plan", None))
    if not plan:
        return {"ok": False, "msg": f"#{material_id} chưa có kế hoạch chia — bấm 🧩 Chia phần trước."}

    old = existing_parts(db, mat.id)
    if old:
        ids = ", ".join(f"#{c.id}" for c in old)
        return {"ok": False, "msg": f"#{material_id} đã chia rồi ({ids}). Xoá các phần cũ trên web trước nếu muốn chia lại."}

    src = ViralService.find_source_path(mat.id, mat.platform)
    if not src:
        return {"ok": False, "msg": f"File gốc của #{material_id} không còn — bấm ⚙️ Xử lý để tải lại rồi chia."}

    base_title = _clean_title_for_context(mat.title) or f"Video #{mat.id}"
    platform_dir = os.path.join(str(config.REUP_DIR), mat.platform or "unknown")
    os.makedirs(platform_dir, exist_ok=True)
    ext = os.path.splitext(src)[1] or ".mp4"

    child_ids: list[int] = []
    for i, (start, end) in enumerate(plan.parts, 1):
        child = ViralMaterial(
            platform=mat.platform,
            url=f"{mat.url}#phan{i}",
            title=f"{base_title} (Phần {i}/{plan.n})",
            views=mat.views,
            scraped_by_account_id=mat.scraped_by_account_id,
            target_page=mat.target_page,
            target_pages=mat.target_pages,
            status=ViralStatus.NEW,
            parent_material_id=mat.id,
            part_index=i,
            part_total=plan.n,
            clip_start_sec=int(round(start)),
            clip_length_sec=max(1, int(round(end - start))),
        )
        db.add(child)
        db.commit()
        dest = os.path.join(platform_dir, f"viral_{child.id}_phan{i}{ext}")
        try:
            if not os.path.exists(dest):
                try:
                    os.link(src, dest)
                except OSError:
                    shutil.copy2(src, dest)
        except Exception as exc:
            child.status = ViralStatus.FAILED
            child.last_error = f"Không nối được file gốc: {exc}"[:255]
            db.commit()
            logger.error("[SPLIT] Phần %s của #%s không có file: %s", i, mat.id, exc)
        child_ids.append(child.id)

    logger.info("[SPLIT] #%s → %s phần: %s", mat.id, plan.n, child_ids)
    return {"ok": True, "msg": f"Đã tạo {len(child_ids)} phần từ #{material_id}.", "child_ids": child_ids}


def describe_plan(material_id: int, plan: Plan) -> str:
    """Tin nhắn Telegram (HTML) mô tả kế hoạch — nói rõ tầng nào tính."""
    import html as html_mod

    tang = {"ai": "🧠 AI đọc lời thoại", "boundary": "〰️ theo khoảng lặng / đổi cảnh", "even": "➗ chia đều"}.get(plan.by, plan.by)
    rows = []
    for i, ((s, e), hook) in enumerate(zip(plan.parts, plan.hooks), 1):
        why = f" — <i>{html_mod.escape(hook)}</i>" if hook and hook not in ("—", "kết") else ""
        rows.append(f"<b>Phần {i}/{plan.n}</b>: {_mmss(s)} → {_mmss(e)} ({_mmss(e - s)}){why}")
    nghe = f"nghe được {plan.lines} câu" if plan.lines else "KHÔNG nghe được lời thoại"
    return (
        f"🧩 <b>Kế hoạch chia #{material_id}</b> · gốc {_mmss(plan.duration)}\n"
        + "\n".join(rows)
        + f"\n\nCách tính: {tang} ({nghe}). {html_mod.escape(plan.note)}"
    )
