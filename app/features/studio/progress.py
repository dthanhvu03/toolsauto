"""
Tiến trình từng video cho web (PLAN-114) — chỉ đọc ``studio_tasks``, không sửa gì.

Một **việc** = một chuỗi bước nối theo ``parent_id`` từ việc gốc (``parent_id`` rỗng). Danh sách bước của việc lấy từ
``pipeline.FLOWS[flow]``; bước chưa có task là «chưa tới». Bước có thể tự bỏ qua (mẫu không lồng tiếng…) hoặc dừng
sớm (trùng video, chờ duyệt) — xem ``_SKIP`` và ``_state``.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.database.models import StudioProject, StudioTask
from app.features.studio.contracts import ProjectStatus, TaskStatus
from app.features.studio.pipeline import FLOWS

WINDOW_SEC = 2 * 3600  # việc xong / lỗi trong 2 giờ qua vẫn hiện để anh thấy kết quả
MAX_JOBS = 30
MAX_TASKS = 3000

LABEL = {
    "fetch": "Tải về", "intake": "Nhận file", "analyze": "Phân tích", "dub": "Lồng tiếng", "compose": "Dựng",
    "render": "Render", "caption": "Caption AI", "review": "Duyệt", "publish": "Đăng",
}
DOING = {
    "fetch": "Đang tải video về", "intake": "Đang đưa vào kho", "analyze": "Đang nghe lời thoại + tìm cảnh",
    "dub": "Đang dịch + lồng tiếng", "compose": "Đang dựng", "render": "Đang render", "caption": "AI đang viết caption",
    "review": "Đang gửi bản xem trước qua Telegram", "publish": "Đang chuyển sang Buffer",
}
SOURCE = {
    "link": "TikTok", "upload": "Tải lên", "reup": "Reup", "rerender": "Render lại", "recompose": "Đổi mẫu",
    "publish": "Gửi đăng",
}
# ghi chú của bước tự bỏ qua — hiện «bỏ qua», không phải «xong»
_SKIP = ("mẫu không lồng tiếng", "không có tiếng để lồng", "đã lồng tiếng trước đó", "đã có caption", "tắt caption",
         "đã có sẵn", "đã ở chờ duyệt")


def _step(stage: str, task: StudioTask | None) -> dict:
    step = {"stage": stage, "label": LABEL.get(stage, stage), "status": "pending", "note": None,
            "started_at": None, "finished_at": None, "attempts": 0, "run_after": None}
    if task is None:
        return step
    note = task.error or None
    status = {
        TaskStatus.DONE: "skipped" if (note or "").startswith(_SKIP) else "done",
        TaskStatus.RUNNING: "running",
        TaskStatus.FAILED: "failed",
    }.get(task.status, "retry" if task.attempts else "queued")
    step.update(status=status, note=note, started_at=task.claimed_at, finished_at=task.finished_at,
                attempts=task.attempts, run_after=task.run_after if status == "retry" else None)
    return step


def _state(flow: str, chain: list[StudioTask], project: StudioProject | None) -> tuple[str, str]:
    """(trạng thái việc, một câu tóm tắt)."""
    last = chain[-1]
    label = LABEL.get(last.stage, last.stage)
    if last.status == TaskStatus.RUNNING:
        extra = f" (lần {last.attempts})" if last.attempts > 1 else ""
        doing = DOING.get(last.stage, label)
        if last.stage == "publish" and project is not None and not project.channel_id:
            doing = "Đang ghi nhận đăng tay (không qua Buffer)"
        return "running", doing + extra
    if last.status == TaskStatus.QUEUED:
        if last.attempts:
            return "retry", f"{label} lỗi, sẽ thử lại (lần {last.attempts}/{last.max_attempts}): {last.error or ''}".strip()
        return "queued", f"Chờ tới lượt: {label}"
    if last.status == TaskStatus.FAILED:
        return "failed", f"{label} hỏng: {last.error or 'không rõ lỗi'}"
    # bước cuối đã xong: hết flow, hoặc dừng có chủ đích
    if project is not None and project.status == ProjectStatus.REVIEW:
        return "review", "Xong — chờ anh duyệt"
    if last.stage == FLOWS.get(flow, [None])[-1]:
        return "done", last.error or "Xong"
    if project is not None and project.status == ProjectStatus.REJECTED:
        return "stopped", "Dự án đã bỏ"
    return "stopped", f"Dừng ở {label}: {last.error or ''}".rstrip(": ")


def _job(root: StudioTask, chain: list[StudioTask], projects: dict[int, StudioProject]) -> dict:
    flow_steps = FLOWS.get(root.flow) or [t.stage for t in chain]
    by_stage = {t.stage: t for t in chain}
    steps = [_step(stage, by_stage.get(stage)) for stage in flow_steps]
    pid = next((t.project_id for t in reversed(chain) if t.project_id), None)
    project = projects.get(pid) if pid else None
    state, summary = _state(root.flow, chain, project)
    if state == "review":  # «Duyệt» = chờ anh bấm (không phải đã duyệt); bước sau đó chưa tới
        for s in steps:
            if s["stage"] == "review":
                s["status"] = "waiting"
    p = root.payload or {}
    return {
        "id": root.id, "flow": root.flow, "source": SOURCE.get(root.flow, root.flow),
        "title": p.get("title") or p.get("url") or (p.get("path") or "").rsplit("/", 1)[-1]
        or (f"Dự án #{pid}" if pid else f"việc #{root.id}"),
        "url": p.get("url") or p.get("source_url"),
        "project_id": pid, "project_status": project.status if project else None,
        "created_at": root.created_at, "updated_at": max((t.finished_at or t.claimed_at or t.created_at) for t in chain),
        "state": state, "summary": summary, "current": chain[-1].stage, "steps": steps,
    }


def jobs(db: Session, *, ids: list[int] | None = None, now: float | None = None) -> dict:
    """
    ``ids``: chỉ các việc gốc này (trang «Lấy từ TikTok» theo dõi lô vừa gửi). Không có: việc đang chạy / chờ +
    việc xong / lỗi trong ``WINDOW_SEC`` qua (bỏ flow ``brand`` — nguyên liệu, không thành video).
    """
    now = time.time() if now is None else now
    q = db.query(StudioTask)
    if ids:
        roots = q.filter(StudioTask.id.in_(ids), StudioTask.parent_id.is_(None)).all()
    else:
        recent = q.filter(
            (StudioTask.created_at >= now - WINDOW_SEC)
            | StudioTask.status.in_([TaskStatus.QUEUED.value, TaskStatus.RUNNING.value])
        ).all()
        known = {t.id: t for t in recent}
        roots_by_id: dict[int, StudioTask] = {}
        for t in recent:
            while t.parent_id:
                parent = known.get(t.parent_id) or db.get(StudioTask, t.parent_id)
                if parent is None:
                    break
                known[parent.id] = t = parent
            if t.parent_id is None and t.flow != "brand":
                roots_by_id[t.id] = t
        roots = sorted(roots_by_id.values(), key=lambda r: r.id, reverse=True)[:MAX_JOBS]
    if not roots:
        return {"jobs": [], "active": 0, "now": int(now)}
    tasks = q.filter(StudioTask.id >= min(r.id for r in roots)).order_by(StudioTask.id).limit(MAX_TASKS).all()
    children: dict[int, StudioTask] = {}
    for t in tasks:
        if t.parent_id and t.parent_id not in children:
            children[t.parent_id] = t
    chains = {}
    for r in roots:
        chain = [r]
        while chain[-1].id in children and len(chain) < 50:
            chain.append(children[chain[-1].id])
        chains[r.id] = chain
    pids = {t.project_id for c in chains.values() for t in c if t.project_id}
    projects = {p.id: p for p in db.query(StudioProject).filter(StudioProject.id.in_(pids))} if pids else {}
    out = [_job(r, chains[r.id], projects) for r in sorted(roots, key=lambda r: r.id, reverse=True)]
    return {"jobs": out, "active": sum(j["state"] in ("running", "queued", "retry") for j in out), "now": int(now)}
