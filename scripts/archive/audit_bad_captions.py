import argparse
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class JobRow:
    id: int
    platform: str | None
    account_id: int | None
    status: str | None
    caption: str | None
    last_error: str | None
    created_at: int | None
    finished_at: int | None


def _db_path() -> Path:
    base = Path(__file__).resolve().parent.parent.parent
    env = os.getenv("DB_PATH")
    if env:
        return Path(env)
    return base / "data" / "auto_publisher.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_jobs(conn: sqlite3.Connection, limit: int | None = None) -> list[JobRow]:
    sql = """
    SELECT
      id, platform, account_id, status, caption, last_error, created_at, finished_at
    FROM jobs
    ORDER BY id DESC
    """
    if limit:
        sql += " LIMIT ?"
        rows = conn.execute(sql, (int(limit),)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()
    out: list[JobRow] = []
    for r in rows:
        out.append(
            JobRow(
                id=int(r["id"]),
                platform=r["platform"],
                account_id=r["account_id"],
                status=r["status"],
                caption=r["caption"],
                last_error=r["last_error"],
                created_at=r["created_at"],
                finished_at=r["finished_at"],
            )
        )
    return out


def _classify_caption(caption: str | None) -> dict:
    text = (caption or "").strip()
    lowered = text.lower()
    flags: list[str] = []

    if not text:
        flags.append("empty")
        return {"flags": flags, "preview": ""}

    # Option/prose patterns commonly returned by Gemini
    if re.search(r"\boption\s*1\b", lowered) or re.search(r"\boption\s*2\b", lowered) or re.search(r"\boption\s*3\b", lowered):
        flags.append("options_block")
    if re.search(r"\bphương\s+án\b", lowered) or re.search(r"\blựa\s+chọn\b", lowered):
        flags.append("options_vi")
    if "```" in text:
        flags.append("code_fence")

    # Heuristic: looks like a whole chat/prose
    if len(text) >= 1200:
        flags.append("very_long")
    if text.count("\n") >= 25:
        flags.append("many_lines")

    # If it begins with an assistant-style greeting and is long-ish, often a prose failure mode
    if lowered.startswith(("chào", "xin chào", "okay", "ok", "tất nhiên", "dưới đây", "mình có thể")) and len(text) >= 300:
        flags.append("assistant_prose")

    preview = text[:300].replace("\n", "\\n")
    return {"flags": flags, "preview": preview}


def _classify_error(last_error: str | None) -> str | None:
    if not last_error:
        return None
    msg = str(last_error)
    low = msg.lower()
    if "cookies expired" in low or "signin" in low or "servicelogin" in low or "captcha" in low:
        return "auth_cookie"
    if "content policy" in low or "safety" in low or "unsafe" in low or "can't help" in low or "refuse" in low:
        return "content_policy"
    if "read timed out" in low or "httpconnectionpool" in low or "cannot connect to chrome" in low or "unexpectedly exited" in low:
        return "infra_timeout"
    if "output contract violation" in low:
        return "output_contract"
    if "returned empty" in low or "empty result" in low:
        return "empty_result"
    return "other"


def _ts(ts: int | None) -> str:
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ts)))
    except Exception:
        return str(ts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Limit number of latest jobs to scan (0 = all)")
    ap.add_argument("--out-dir", default="/home/vu/toolsauto/logs", help="Directory to write report files")
    args = ap.parse_args()

    db_path = _db_path()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    try:
        jobs = _fetch_jobs(conn, limit=args.limit or None)
    finally:
        conn.close()

    total = len(jobs)
    error_counts = Counter()
    status_counts = Counter()
    suspect: list[dict] = []

    for j in jobs:
        status_counts[j.status or ""] += 1
        err_cls = _classify_error(j.last_error)
        if err_cls:
            error_counts[err_cls] += 1

        cap_info = _classify_caption(j.caption)
        if cap_info["flags"]:
            suspect.append(
                {
                    "id": j.id,
                    "platform": j.platform,
                    "account_id": j.account_id,
                    "status": j.status,
                    "created_at": j.created_at,
                    "finished_at": j.finished_at,
                    "last_error": j.last_error,
                    "error_class": err_cls,
                    "caption_flags": cap_info["flags"],
                    "caption_preview": cap_info["preview"],
                }
            )

    # Top suspects: prioritize DONE/DRAFT with bad flags, then most recent
    suspect_sorted = sorted(
        suspect,
        key=lambda r: (
            0 if (r.get("status") in ("DONE", "DRAFT")) else 1,
            -int(r.get("id") or 0),
        ),
    )

    summary = {
        "db_path": str(db_path),
        "scanned_jobs": total,
        "status_counts": dict(status_counts),
        "error_counts": dict(error_counts),
        "suspect_count": len(suspect),
        "suspect_top": suspect_sorted[:200],
        "generated_at": int(time.time()),
    }

    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    json_path = out_dir / f"audit_bad_captions_{stamp}.json"
    md_path = out_dir / f"audit_bad_captions_{stamp}.md"

    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown report
    lines: list[str] = []
    lines.append("# Audit caption lỗi (DB)\n")
    lines.append(f"- DB: `{db_path}`")
    lines.append(f"- Scanned jobs: **{total}**")
    lines.append(f"- Suspect captions (has flags): **{len(suspect)}**\n")

    lines.append("## Status breakdown\n")
    for k, v in status_counts.most_common():
        lines.append(f"- **{k or '(empty)'}**: {v}")
    lines.append("")

    lines.append("## Error breakdown (jobs.last_error classifier)\n")
    if error_counts:
        for k, v in error_counts.most_common():
            lines.append(f"- **{k}**: {v}")
    else:
        lines.append("- (no last_error found)")
    lines.append("")

    lines.append("## Top suspect jobs (max 50)\n")
    for r in suspect_sorted[:50]:
        lines.append(f"### Job #{r['id']} ({r.get('platform')})")
        lines.append(f"- status: **{r.get('status')}**")
        if r.get("error_class"):
            lines.append(f"- error_class: **{r.get('error_class')}**")
        if r.get("last_error"):
            le = str(r.get("last_error"))
            lines.append(f"- last_error: `{le[:240]}`")
        lines.append(f"- created_at: `{_ts(r.get('created_at'))}`")
        if r.get("finished_at"):
            lines.append(f"- finished_at: `{_ts(r.get('finished_at'))}`")
        lines.append(f"- caption_flags: `{', '.join(r.get('caption_flags') or [])}`")
        lines.append(f"- caption_preview: `{r.get('caption_preview')}`\n")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("Wrote:")
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()

