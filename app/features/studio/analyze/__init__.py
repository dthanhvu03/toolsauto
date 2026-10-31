"""
Bước ``analyze`` — đúng một việc: đọc một asset **một lần** rồi lưu vào ``studio_analysis``.

- ``probe``: thời lượng, khung, có tiếng hay không (ghi luôn lên asset — compose / render cần).
- ``transcript``: ``{"lang", "lines"}`` — ngôn ngữ Whisper nhận ra + lời thoại kèm mốc giây, đã lọc câu
  bịa. Phụ đề, lồng tiếng, chia đoạn đều đọc lại đây.
- ``silences`` / ``scenes``: ranh giới để cắt gọn và chia đoạn.

Kết quả đã có thì bỏ qua — chạy lại bước này không tốn thêm Whisper.
payload ``analyze``: danh sách kind muốn chạy (mặc định theo loại asset).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.core.database.models import StudioAnalysis, StudioAsset, StudioTask
from app.core.media import ffmpeg_path, segments, speech
from app.features.studio.contracts import StageError, StageResult

DEFAULT_KINDS = {
    "video": ("probe", "transcript", "silences", "scenes"),
    "audio": ("probe", "transcript"),
    "image": ("probe",),
}


def probe(path: str) -> dict:
    """``{"duration", "width", "height", "has_audio"}`` từ ffprobe. Hỏng thì ném — không đoán số."""
    proc = subprocess.run(
        [ffmpeg_path.ffprobe_bin(), "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration", "-of", "json", path],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise StageError(f"ffprobe hỏng: {(proc.stderr or '').strip()[:300]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    try:
        duration = float((data.get("format") or {}).get("duration") or 0.0)
    except ValueError:
        duration = 0.0
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def _compute(kind: str, asset: StudioAsset) -> object:
    if kind == "probe":
        return probe(asset.path)
    if kind == "transcript":
        if not asset.has_audio:
            return {"lang": None, "lines": []}
        lines, lang = speech.transcribe(asset.path, language=None)
        return {"lang": lang, "lines": [{"start": x["start"], "end": x["end"], "text": x["text"]} for x in lines]}
    if kind == "silences":
        return [asdict(s) for s in segments.silences(asset.path)] if asset.has_audio else []
    if kind == "scenes":
        return segments.scene_changes(asset.path)
    raise StageError(f"không có kiểu phân tích {kind!r}", retryable=False)


def run(db: Session, task: StudioTask) -> StageResult:
    asset = db.get(StudioAsset, task.asset_id) if task.asset_id else None
    if asset is None:
        raise StageError(f"không có asset #{task.asset_id}", retryable=False)
    kinds = (task.payload or {}).get("analyze") or DEFAULT_KINDS.get(asset.kind, ("probe",))
    if "probe" in kinds:  # probe trước: transcript / silences cần biết có tiếng hay không
        kinds = ["probe", *[k for k in kinds if k != "probe"]]

    done = {r.kind for r in db.query(StudioAnalysis.kind).filter_by(asset_id=asset.id)}
    ran = []
    for kind in kinds:
        if kind in done:
            continue
        data = _compute(kind, asset)
        if kind == "probe":
            asset.duration = data["duration"] or None
            asset.width = data["width"] or None
            asset.height = data["height"] or None
            asset.has_audio = data["has_audio"]
        db.add(StudioAnalysis(asset_id=asset.id, kind=kind, data=data))
        db.commit()
        ran.append(kind)
    return StageResult(asset_id=asset.id, note=("đã chạy " + ", ".join(ran)) if ran else "đã có sẵn")
