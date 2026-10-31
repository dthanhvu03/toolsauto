"""
Kênh và mẫu của Studio (PLAN-106 P4) — trang «Kênh & mẫu».

Kênh Studio gắn 1-1 với một kênh Buffer trong cài đặt ``BUFFER_CHANNELS`` (đọc qua ``app.core.settings``,
không import feature buffer). Mẫu là ``kind`` trong ``compose/templates.TEMPLATES`` + tham số.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import settings as runtime_settings
from app.core.database.models import StudioAsset, StudioChannel, StudioTemplate
from app.features.studio.compose.templates import TEMPLATES

CHANNEL_FLAGS = ("auto_approve", "show_credit", "take_reup", "active")
CHANNEL_ASSETS = {"logo_asset_id": "image", "intro_asset_id": "video", "outro_asset_id": "video"}

# Gợi ý tham số khi tạo mẫu mới — đúng những khoá mỗi hàm mẫu đọc (xem docstring trong templates.py).
TEMPLATE_DEFAULTS: dict[str, dict] = {
    "basic": {"trim_head": 0, "max_len": 0, "subtitles": True, "subtitle_lang": "vi", "fit": "blur_pad",
              "hook": "", "hook_sec": 3, "music_volume": 0.12, "original_volume": 1.0},
    "reup_dub": {"trim_head": 0, "max_len": 0, "dub_lang": "vi", "dub_voice": "female", "voice_volume": 1.0,
                 "background_volume": 1.0, "fit": "blur_pad", "hook": ""},
    "own_footage": {"cut_silence": True, "min_silence": 0.6, "pad": 0.12, "max_len": 0, "fit": "crop", "hook": ""},
}


class SetupError(ValueError):
    """Thông điệp đưa thẳng cho người dùng."""


def buffer_channels(db: Session | None = None) -> list[dict]:
    data = runtime_settings.get_json("BUFFER_CHANNELS", db=db) or []
    return [
        {"id": str(c["id"]).strip(), "name": str(c.get("name") or c["id"]).strip()}
        for c in data if isinstance(c, dict) and str(c.get("id") or "").strip()
    ]


def channel_row(c: StudioChannel) -> dict:
    return {
        "id": c.id, "buffer_channel_id": c.buffer_channel_id, "name": c.name, "template_id": c.template_id,
        **{f: bool(getattr(c, f)) for f in CHANNEL_FLAGS},
        **{f: getattr(c, f) for f in CHANNEL_ASSETS},
    }


def template_row(t: StudioTemplate) -> dict:
    return {"id": t.id, "name": t.name, "kind": t.kind, "params": t.params or {}}


def overview(db: Session) -> dict:
    channels = db.query(StudioChannel).order_by(StudioChannel.name).all()
    taken = {c.buffer_channel_id for c in channels}
    try:
        buffer = buffer_channels(db)
    except Exception:
        buffer = []
    return {
        "channels": [channel_row(c) for c in channels],
        "buffer_channels": [b for b in buffer if b["id"] not in taken],
        "templates": [template_row(t) for t in db.query(StudioTemplate).order_by(StudioTemplate.name)],
        "template_kinds": [{"kind": k, "defaults": TEMPLATE_DEFAULTS.get(k, {})} for k in TEMPLATES],
    }


def save_channel(db: Session, data: dict, channel_id: int | None = None) -> StudioChannel:
    if channel_id is None:
        bid = str(data.get("buffer_channel_id") or "").strip()
        if not bid:
            raise SetupError("thiếu kênh Buffer")
        if db.query(StudioChannel).filter(StudioChannel.buffer_channel_id == bid).first():
            raise SetupError("kênh Buffer này đã có trong Studio")
        name = str(data.get("name") or "").strip() or next(
            (b["name"] for b in buffer_channels(db) if b["id"] == bid), bid
        )
        channel = StudioChannel(buffer_channel_id=bid, name=name[:120])
        db.add(channel)
    else:
        channel = db.get(StudioChannel, channel_id)
        if channel is None:
            raise SetupError(f"không có kênh #{channel_id}")
        if data.get("name"):
            channel.name = str(data["name"]).strip()[:120]
    if "template_id" in data:
        tid = data["template_id"]
        if tid is not None and db.get(StudioTemplate, int(tid)) is None:
            raise SetupError(f"không có mẫu #{tid}")
        channel.template_id = tid
    for flag in CHANNEL_FLAGS:
        if flag in data:
            setattr(channel, flag, bool(data[flag]))
    for field, kind in CHANNEL_ASSETS.items():
        if field in data:
            aid = data[field]
            if aid is not None:
                asset = db.get(StudioAsset, int(aid))
                if asset is None or asset.kind != kind:
                    raise SetupError(f"{field}: asset #{aid} phải là {kind}")
            setattr(channel, field, aid)
    db.commit()
    return channel


def save_template(db: Session, data: dict, template_id: int | None = None) -> StudioTemplate:
    kind = str(data.get("kind") or "").strip()
    if kind not in TEMPLATES:
        raise SetupError(f"không có kiểu mẫu {kind!r} (có: {', '.join(TEMPLATES)})")
    name = str(data.get("name") or "").strip()
    if not name:
        raise SetupError("mẫu cần tên")
    params = data.get("params") or {}
    if not isinstance(params, dict):
        raise SetupError("params phải là object JSON")
    if template_id is None:
        template = StudioTemplate(name=name[:120], kind=kind, params=params)
        db.add(template)
    else:
        template = db.get(StudioTemplate, template_id)
        if template is None:
            raise SetupError(f"không có mẫu #{template_id}")
        template.name, template.kind, template.params = name[:120], kind, params
    db.commit()
    return template
