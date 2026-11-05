"""
PLAN-157 — cấu hình Audio→Doc. Một chỗ duy nhất đọc ``doc.*`` từ Cài đặt vận hành (/app/settings).

Các module khác chỉ nhận ``DocConfig`` (test truyền thẳng, không cần DB settings). Giá trị mặc định nằm ở
``app/core/settings.py`` — đổi trên web là lần dựng / lần tìm sau ăn ngay, không restart.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import get_args

from sqlalchemy.orm import Session

from app.core import settings as runtime_settings
from app.features.studio.doc.schema import Motion

MOTIONS: tuple[str, ...] = get_args(Motion)
SOURCES: tuple[str, ...] = ("wikimedia", "openverse", "pexels", "pixabay", "google")


@dataclass(frozen=True)
class DocConfig:
    default_language: str = "auto"
    preview_sec: int = 0  # 0 = toàn bộ audio
    shot_sec: float = 7.0
    shot_min_sec: float = 2.0
    shot_max_sec: float = 12.0
    beat_pause_sec: float = 1.2
    beat_max_sec: float = 90.0
    width: int = 1920
    height: int = 1080
    fps: int = 30
    fit: str = "crop"
    subtitles: bool = True
    subtitle_font_size: int = 48
    subtitle_margin_v: int = 80
    subtitle_max_chars: int = 180
    voice_volume: float = 1.0
    credit: str = ""
    motions: tuple[str, ...] = ("slow_zoom_in", "pan_left", "slow_zoom_out", "pan_right", "static")
    kb_zoom_max: float = 1.2
    kb_zoom_per_sec: float = 0.045
    kb_pan_zoom: float = 1.15
    kb_upscale: float = 2.0
    sources: tuple[str, ...] = ("wikimedia", "openverse")
    keys: dict[str, str] = field(default_factory=dict)  # pexels / pixabay / google / google_cx
    candidates_per_source: int = 6
    image_min_width: int = 1280
    image_max_mb: int = 25
    search_timeout_sec: int = 10
    ai_keywords: bool = True
    rights_ok: str = "verified_or_approved"
    rights_need_proof: bool = True
    auto_verify_licenses: tuple[str, ...] = ("cc0", "pdm", "cc-by", "cc-by-sa", "pexels", "pixabay")

    @property
    def language(self) -> str | None:
        """Mã ngôn ngữ cho Whisper; ``None`` = tự nhận."""
        return None if self.default_language in ("", "auto") else self.default_language

    @property
    def preview_ms(self) -> int:
        return max(0, int(self.preview_sec)) * 1000


def parse_motions(raw: str) -> tuple[str, ...]:
    """``"slow_zoom_in, abc,pan_left"`` → ``("slow_zoom_in", "pan_left")``; rỗng / toàn tên sai → ``("static",)``."""
    names = tuple(n for n in (x.strip() for x in str(raw or "").split(",")) if n in MOTIONS)
    return names or ("static",)


def parse_list(raw: str) -> tuple[str, ...]:
    return tuple(x.strip().lower() for x in str(raw or "").split(",") if x.strip())


def _canvas(raw: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in str(raw).lower().split("x", 1))
        return w, h
    except ValueError:
        return 1920, 1080


def load(db: Session | None = None) -> DocConfig:
    g = runtime_settings.get
    gi = lambda k, d: runtime_settings.get_int(k, d, db=db)  # noqa: E731
    gb = lambda k, d: runtime_settings.get_bool(k, d, db=db)  # noqa: E731
    gs = lambda k, d="": runtime_settings.get_str(k, d, db=db)  # noqa: E731

    def gf(key: str, default: float) -> float:
        try:
            return float(g(key, db=db, default=default))
        except (TypeError, ValueError):
            return default

    d = DocConfig()
    w, h = _canvas(gs("doc.canvas", "1920x1080"))
    keys = {name: gs(f"doc.{name}_key").strip() for name in ("pexels", "pixabay", "google")}
    keys["google_cx"] = gs("doc.google_cx").strip()
    return DocConfig(
        default_language=gs("doc.default_language", d.default_language) or "auto",
        preview_sec=gi("doc.preview_sec", d.preview_sec),
        shot_sec=gf("doc.shot_sec", d.shot_sec),
        shot_min_sec=gf("doc.shot_min_sec", d.shot_min_sec),
        shot_max_sec=gf("doc.shot_max_sec", d.shot_max_sec),
        beat_pause_sec=gf("doc.beat_pause_sec", d.beat_pause_sec),
        beat_max_sec=gf("doc.beat_max_sec", d.beat_max_sec),
        width=w,
        height=h,
        fps=gi("doc.fps", d.fps),
        fit=gs("doc.fit", d.fit) or d.fit,
        subtitles=gb("doc.subtitles", d.subtitles),
        subtitle_font_size=gi("doc.subtitle_font_size", d.subtitle_font_size),
        subtitle_margin_v=gi("doc.subtitle_margin_v", d.subtitle_margin_v),
        subtitle_max_chars=gi("doc.subtitle_max_chars", d.subtitle_max_chars),
        voice_volume=gf("doc.voice_volume", d.voice_volume),
        credit=gs("doc.credit").strip(),
        motions=parse_motions(gs("doc.motions", ",".join(d.motions))),
        kb_zoom_max=gf("doc.kb_zoom_max", d.kb_zoom_max),
        kb_zoom_per_sec=gf("doc.kb_zoom_per_sec", d.kb_zoom_per_sec),
        kb_pan_zoom=gf("doc.kb_pan_zoom", d.kb_pan_zoom),
        kb_upscale=gf("doc.kb_upscale", d.kb_upscale),
        sources=tuple(s for s in SOURCES if gb(f"doc.src_{s}", s in d.sources)),
        keys=keys,
        candidates_per_source=gi("doc.candidates_per_source", d.candidates_per_source),
        image_min_width=gi("doc.image_min_width", d.image_min_width),
        image_max_mb=gi("doc.image_max_mb", d.image_max_mb),
        search_timeout_sec=gi("doc.search_timeout_sec", d.search_timeout_sec),
        ai_keywords=gb("doc.ai_keywords", d.ai_keywords),
        rights_ok=gs("doc.rights_ok", d.rights_ok) or d.rights_ok,
        rights_need_proof=gb("doc.rights_need_proof", d.rights_need_proof),
        auto_verify_licenses=parse_list(gs("doc.auto_verify_licenses", ",".join(d.auto_verify_licenses))),
    )


def public(cfg: DocConfig) -> dict:
    """Phần cấu hình UI cần biết (không lộ key)."""
    return {
        "default_language": cfg.default_language,
        "preview_sec": cfg.preview_sec,
        "canvas": f"{cfg.width}x{cfg.height}",
        "sources": list(cfg.sources),
        "ai_keywords": cfg.ai_keywords,
        "rights_ok": cfg.rights_ok,
        "rights_need_proof": cfg.rights_need_proof,
    }


def window_end_ms(cfg: DocConfig, duration_ms: int) -> int:
    """Mốc cuối bản dựng: ``preview_sec=0`` → toàn bộ audio; lớn hơn audio → cắt về độ dài audio."""
    if duration_ms <= 0:
        return cfg.preview_ms
    return min(cfg.preview_ms, duration_ms) if cfg.preview_ms > 0 else duration_ms


def ui(db: Session | None = None) -> dict:
    """``GET /studio/api/doc/config``: cấu hình hiện tại (không key) + ngôn ngữ chọn được, nhãn lấy từ Cài đặt."""
    spec = runtime_settings.SETTINGS.get("doc.default_language")
    labels = (spec.enum_labels or {}) if spec else {}
    choices = (spec.choices or []) if spec else ["auto"]
    return {
        **public(load(db)),
        "languages": [{"code": c, "label": labels.get(c, c)} for c in choices],
        "settings_url": "/app/settings",
    }
