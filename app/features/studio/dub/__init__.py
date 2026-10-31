"""
Bước ``dub`` — đúng một việc: video nói tiếng khác → 2 asset audio tiếng Việt (giọng đọc + nền),
ghi kết quả vào phân tích ``dub`` của asset video. Không đụng tới hình, không tạo dự án.

Chạy khi mẫu là ``reup_dub`` hoặc tham số ``dub`` bật; còn lại bỏ qua ngay. Đã có phân tích ``dub``
thì bỏ qua (Whisper + Demucs + AI chỉ chạy một lần mỗi asset). Lồng không được (đã là tiếng Việt,
không có lời…) vẫn ghi ``{"ok": false, "reason"}`` để mẫu biết mà giữ tiếng gốc. Dịch / đọc hỏng
(mạng, AI) thì thử lại theo hàng việc; lần cuối vẫn hỏng thì ghi ``ok: false`` và đi tiếp.

Dữ liệu ``dub``: ``ok``, ``reason``, ``source_lang``, ``target_lang``, ``voice_asset``,
``background_asset``, ``background_volume``, ``lines`` (câu đã dịch theo giây video gốc).
"""
from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.core.database.models import StudioAnalysis, StudioAsset, StudioTask
from app.core.media import ffmpeg_path, tts
from app.features.studio import paths, store
from app.features.studio.contracts import StageError, StageResult
from app.features.studio.dub import engine

_RETRY_REASONS = ("dịch hỏng", "đọc hỏng")


def _translate(prompt: str) -> str | None:
    text, _meta = AIUseCases.generate_text(prompt, purpose=AIPurpose.DUB_TRANSLATE)
    return text


def _synthesizer(target_lang: str, vieneu_voice: str | None = None):
    # VieNeu và piper dự phòng chỉ có giọng Việt — ngôn ngữ khác chỉ dùng edge-tts.
    engine_name = "auto" if target_lang == "vi" else "edge"
    vieneu_voice = vieneu_voice if target_lang == "vi" else None

    def synthesize(text: str, out_path: str, voice: str) -> bool:
        return tts.synthesize(text, out_path, voice=voice, engine=engine_name, vieneu_voice=vieneu_voice)

    return synthesize


def _voice(channel, params: dict) -> tuple[str | None, str]:
    """
    (giọng VieNeu hoặc None, giới cho giọng edge dự phòng). Giọng chọn cho lô (``params.vieneu_voice``, trang «Lấy từ
    TikTok») → giọng kênh → theo mẫu. Giọng VieNeu quyết định giới khi biết được.
    """
    gender = str(params.get("dub_voice") or "female")
    vn_voice = params.get("vieneu_voice") or getattr(channel, "dub_voice", None) or None
    if vn_voice:
        gender = next((v["gender"] for v in tts.vieneu_voices() if v["name"] == vn_voice and v.get("gender")), gender)
    return vn_voice, gender


def _to_flac(wav: str) -> Path:
    """WAV → FLAC cạnh nó (nhỏ một nửa, không mất chất lượng). Hỏng thì ném — không lưu nửa vời."""
    out = Path(wav).with_suffix(".flac")
    proc = subprocess.run(
        [ffmpeg_path.ffmpeg_bin(), "-y", "-loglevel", "error", "-i", wav, "-c:a", "flac", str(out)],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0 or not out.is_file():
        raise StageError(f"không ghi được FLAC: {(proc.stderr or '').strip()[-300:]}")
    return out


def run(db: Session, task: StudioTask) -> StageResult:
    asset = db.get(StudioAsset, task.asset_id) if task.asset_id else None
    if asset is None:
        raise StageError(f"không có asset #{task.asset_id}", retryable=False)
    kind, params, _template, channel = store.template_for(db, task.payload)
    if not params.get("dub", kind == "reup_dub"):
        return StageResult(asset_id=asset.id, note="mẫu không lồng tiếng")
    if asset.kind != "video" or not asset.has_audio:
        return StageResult(asset_id=asset.id, note="không có tiếng để lồng")
    if store.analysis(db, asset.id, "dub") is not None:
        return StageResult(asset_id=asset.id, note="đã lồng tiếng trước đó")

    target = str(params.get("dub_lang") or "vi")
    data: dict = {"ok": False, "target_lang": target}
    transcript = store.analysis(db, asset.id, "transcript") or {}
    if transcript.get("lang") == target:  # khỏi chạy Demucs + Whisper lần hai
        data.update(reason="đã đúng ngôn ngữ đích", source_lang=target)
    else:
        work = paths.work_dir() / f"dub{asset.id}-{uuid.uuid4().hex[:8]}"
        work.mkdir(parents=True)
        try:
            vn_voice, gender = _voice(channel, params)
            res = engine.make_tracks(
                asset.path, str(work), target_lang=target, translate=_translate,
                synthesize=_synthesizer(target, vn_voice), voice_gender=gender,
            )
            data.update(reason=res.reason, source_lang=res.source_lang)
            if not res.ok and res.reason.startswith(_RETRY_REASONS) and task.attempts < task.max_attempts:
                raise StageError(f"lồng tiếng: {res.reason}")
            if res.ok:
                common = {"kind": "audio", "origin": "dub", "move": True, "duration": asset.duration, "has_audio": True}
                voice, _ = store.add_asset(db, _to_flac(res.voice_wav), title=f"Giọng đọc #{asset.id}", **common)
                bg, _ = store.add_asset(db, _to_flac(res.background_wav), title=f"Nền #{asset.id}", **common)
                data.update(
                    ok=True, voice_asset=voice.id, background_asset=bg.id,
                    background_volume=res.background_volume, lines=res.lines,
                )
        finally:
            shutil.rmtree(work, ignore_errors=True)

    db.add(StudioAnalysis(asset_id=asset.id, kind="dub", data=data))
    db.commit()
    return StageResult(asset_id=asset.id, note=f"lồng tiếng: {data['reason']}" if not data["ok"] else data["reason"])
