"""Persistent read-only watcher and suggest-only specialist dispatcher for CapCut."""
from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import logging
import os
import random
import signal
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values

from app.config import RUNTIME_CONFIG_DIR
from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.threads.growth.config import CAPCUT_TRIAL_SOURCE
from app.features.threads.growth import strategy_review
from cashback_bot import store_campaign

logger = logging.getLogger("capcut_supervisor")
ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = ROOT / "reports" / "capcut-20261118" / "agent-supervisor"
DEFAULT_STATE_DB = RUNTIME_CONFIG_DIR / "capcut_supervisor.sqlite"
POLL_SECONDS = max(1, int(os.getenv("CAPCUT_SUPERVISOR_POLL_SECONDS", "5")))
AI_COOLDOWN_SECONDS = max(0, int(os.getenv("CAPCUT_SUPERVISOR_AI_COOLDOWN_SECONDS", "60")))
BURST_COALESCE_SECONDS = max(0, int(os.getenv("CAPCUT_SUPERVISOR_BURST_COALESCE_SECONDS", "10")))
STOP = False

ROLES = {
    "measurement": (
        "Bạn là chuyên viên số liệu. Tóm tắt số aggregate về khách mới, bước đã ghi nhận, QR, nạp, đơn đã giao, hoàn "
        "và doanh thu sau hoàn. Đơn pending không phải đơn giao. Tỷ lệ 24h chỉ hợp lệ với khách đủ 24h; mẫu số rỗng ghi "
        "chưa có dữ liệu. Phân biệt fact với điều chưa đo được. Không suy nguyên nhân từ số 0."
    ),
    "conversion": (
        "Bạn là chuyên viên chuyển đổi. Chỉ nêu bước thay đổi có bằng chứng aggregate. Marker product/confirm chỉ lưu "
        "lần đầu; thiếu marker không chứng minh khách bỏ bước. Tách fact khỏi giả thuyết. Đưa tối đa hai câu hỏi hoặc "
        "đề xuất chỉ đọc; không đề xuất sửa code, gọi khách hoặc thay đổi vận hành."
    ),
    "content": (
        "Bạn là cộng tác viên nội dung. Từ aggregate signal, chỉ chuẩn bị một gợi ý nháp hoặc nói chưa cần viết mới. "
        "Không đăng/gửi. Không tuyên bố bảo hành, official, giảm giá, testimonial, bảo đảm tính năng, giá/tồn hiện hành "
        "hay hiệu quả nếu evidence đầu vào không có. Không giả lời người mua."
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _environment() -> tuple[Path, tuple[int, ...], dict]:
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    raw_admins = values.get("STORE_ADMIN_IDS")
    if not raw_admins:
        raise RuntimeError("STORE_ADMIN_IDS unavailable; refusing an unfiltered report")
    admins = tuple(int(part.strip()) for part in raw_admins.replace(";", ",").split(",") if part.strip())
    if not admins:
        raise RuntimeError("STORE_ADMIN_IDS empty; refusing an unfiltered report")
    raw_path = values.get("STORE_DB_PATH") or "./data/store.sqlite"
    store_path = Path(raw_path)
    if not store_path.is_absolute():
        store_path = ROOT / store_path
    state_path = Path(values.get("CAPCUT_SUPERVISOR_STATE") or DEFAULT_STATE_DB)
    if not state_path.is_absolute():
        state_path = ROOT / state_path
    if state_path.resolve() == store_path.resolve():
        raise RuntimeError("Supervisor sidecar must not be the Store database")
    return store_path.resolve(), admins, {"state_path": state_path.resolve()}


def initialize(state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(state_path, timeout=5)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_key TEXT PRIMARY KEY,
                observed_at TEXT NOT NULL,
                current_json TEXT NOT NULL,
                previous_json TEXT NOT NULL,
                changed_json TEXT NOT NULL,
                specialist_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'queued',
                retry_at TEXT NOT NULL DEFAULT ''
            );
        """)
        conn.execute("INSERT OR IGNORE INTO state(key,value) VALUES('baseline','')")
        conn.execute("INSERT OR IGNORE INTO state(key,value) VALUES('last_ai_started','')")
        conn.execute("INSERT OR IGNORE INTO state(key,value) VALUES('event_sequence','0')")
        conn.commit()


def _published_since() -> datetime:
    path = ROOT / "reports" / "capcut-20261118" / "trial-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "posted" or manifest.get("source") != CAPCUT_TRIAL_SOURCE:
        raise RuntimeError("Verified CapCut trial manifest is unavailable")
    return datetime.fromisoformat(manifest["published_at"].replace("Z", "+00:00"))


def snapshot(store_path: Path, admins: tuple[int, ...], since: datetime,
             now: datetime | None = None) -> dict:
    """Build exact-source, all-time trial aggregates from a single bounded report window."""
    until = now or _now()
    report = store_campaign.report(since, 2, until, store_path,
                                   source_prefix=CAPCUT_TRIAL_SOURCE,
                                   exclude_user_ids=admins, source_exact=True)
    if report["errors"] or report["cohort"] is None:
        raise RuntimeError("Store aggregate unavailable; suppressing zero report")
    cohort = report["cohort"]
    selected = cohort["selected_product"]
    delivered = selected["delivered_orders"]
    catalog = report["product"] or {}
    return {
        "observed_at": until.isoformat(),
        "since": since.isoformat(),
        "source": CAPCUT_TRIAL_SOURCE,
        "product_id": 2,
        "new_users": cohort["customers"],
        "not_yet_24h": cohort["not_yet_24h"],
        "product_markers": selected["stages"]["product"],
        "confirm_markers": selected["stages"]["confirm"],
        "qr_customers": selected["stages"]["qr"],
        "qr_requests_by_current_status": selected["qr_requests_by_current_status"],
        "paid_topup_customers": selected["stages"]["paid"],
        "delivered_order_customers": selected["stages"]["order"],
        "delivered_orders": delivered,
        "revenue_after_refunds": selected["revenue_after_refunds"],
        "mature_24h": selected["mature_24h"],
        "converted_24h": selected["converted_24h"],
        "conversion_24h_pct": selected["conversion_24h_pct"],
        "product": {
            key: value for key, value in {
                "id": catalog.get("id"),
                "name": catalog.get("name"),
                "price": catalog.get("price"),
                "description": catalog.get("description"),
                "active": catalog.get("active"),
                "upstream_available": catalog.get("upstream_available"),
                "recorded_catalog_unit_cost": catalog.get("upstream_cost"),
            }.items() if value is not None
        },
        "limitations": report["notes"],
        "identifiers_exported": False,
    }


def _fingerprint(snapshot_data: dict) -> str:
    stable = _semantic(snapshot_data)
    encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _semantic(data: dict) -> dict:
    stable = {key: value for key, value in data.items()
              if key not in {"observed_at", "limitations"}}
    # Older baselines had no status breakdown for an empty QR cohort.
    stable.setdefault("qr_requests_by_current_status", {})
    product = data.get("product") or {}
    stable["product"] = {key: product.get(key) for key in
                         ("id", "name", "price", "description", "active", "upstream_available")
                         if key in product}
    catalog_cost = product.get("recorded_catalog_unit_cost", product.get("upstream_cost"))
    if catalog_cost is not None:
        stable["product"]["recorded_catalog_unit_cost"] = catalog_cost
    return stable


def _changed(previous: dict, current: dict) -> list[str]:
    old, new = _semantic(previous), _semantic(current)
    return [key for key in new if new.get(key) != old.get(key)]


def detect_once(store_path: Path, state_path: Path, admins: tuple[int, ...],
                since: datetime, now: datetime | None = None) -> dict:
    current = snapshot(store_path, admins, since, now)
    with closing(sqlite3.connect(state_path, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        raw = conn.execute("SELECT value FROM state WHERE key='baseline'").fetchone()[0]
        previous = json.loads(raw) if raw else None
        if previous is None:
            conn.execute("UPDATE state SET value=? WHERE key='baseline'",
                         (json.dumps(current, sort_keys=True),))
            conn.commit()
            return {"status": "baseline", **_public_counts(current)}
        fingerprint = _fingerprint(current)
        if fingerprint == _fingerprint(previous):
            conn.rollback()
            return {"status": "unchanged", "observed_at": current["observed_at"]}
        fields = _changed(previous, current)
        if not fields:
            conn.rollback()
            return {"status": "unchanged", "observed_at": current["observed_at"]}
        sequence = int(conn.execute("SELECT value FROM state WHERE key='event_sequence'").fetchone()[0]) + 1
        event_key = f"{sequence}-{hashlib.sha256((_fingerprint(previous) + fingerprint).encode()).hexdigest()}"
        conn.execute("UPDATE state SET value=? WHERE key='event_sequence'", (str(sequence),))
        conn.execute("INSERT INTO events(event_key,observed_at,current_json,previous_json,changed_json) "
                     "VALUES(?,?,?,?,?)", (event_key, current["observed_at"],
                                             json.dumps(current, sort_keys=True),
                                             json.dumps(previous, sort_keys=True),
                                             json.dumps(fields)))
        conn.execute("UPDATE state SET value=? WHERE key='baseline'",
                     (json.dumps(current, sort_keys=True),))
        conn.commit()
    return {"status": "event", "event_key": event_key,
            **_public_counts(current), "changed": fields,
            "current": current, "previous": previous}


def _public_counts(current: dict) -> dict:
    keys = ("observed_at", "new_users", "not_yet_24h", "product_markers", "confirm_markers",
            "qr_customers", "paid_topup_customers", "delivered_orders", "revenue_after_refunds",
            "mature_24h", "converted_24h", "conversion_24h_pct")
    return {key: current[key] for key in keys}


def _call_specialist(role: str, current: dict, previous: dict,
                     generator: Callable = AIUseCases.generate_text) -> dict:
    evidence = {"current": current, "previous": previous,
                "changed": _changed(previous, current)}
    prompt = (ROLES[role] + "\n\nChỉ dùng evidence sau. Facts và hypotheses phải tách biệt; nếu chưa biết, nói chưa biết. "
              "Trả tiếng Việt tối đa 140 từ, không nêu bất kỳ ID/tên cá nhân nào. Không thực thi hành động.\n\n"
              + json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    text, meta = generator(prompt, purpose=AIPurpose.STRATEGIC_ADVICE)
    if not text or not meta.get("ok"):
        return {"status": "fallback", "text": "Chưa có phân tích AI; dùng aggregate metrics đính kèm."}
    return {"status": "suggestion", "text": str(text)[:1800],
            "model": str(meta.get("model") or "unknown")[:80]}


def dispatch_once(state_path: Path, now: datetime | None = None,
                  generator: Callable = AIUseCases.generate_text,
                  cooldown: int = AI_COOLDOWN_SECONDS) -> dict:
    lock_path = state_path.with_suffix(".dispatch.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "busy"}
        return _dispatch_locked(state_path, now, generator, cooldown)


def _dispatch_locked(state_path: Path, now: datetime | None,
                     generator: Callable, cooldown: int) -> dict:
    stamp = now or _now()
    with closing(sqlite3.connect(state_path, timeout=5)) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT value FROM state WHERE key='last_ai_started'").fetchone()
        last = datetime.fromisoformat(row[0]) if row and row[0] else None
        if last and stamp - last < timedelta(seconds=cooldown):
            conn.rollback()
            return {"status": "cooldown"}
        events = conn.execute("SELECT event_key,observed_at,current_json,previous_json,changed_json,specialist_json,status "
                              "FROM events WHERE status IN ('queued','running') ORDER BY observed_at").fetchall()
        if not events:
            conn.rollback()
            return {"status": "idle"}
        first = events[0]
        first_time = datetime.fromisoformat(first[1])
        if first[6] == "queued" and stamp - first_time < timedelta(seconds=BURST_COALESCE_SECONDS):
            conn.rollback()
            return {"status": "debouncing"}
        batch = [event for event in events if event[6] == first[6]
                 and datetime.fromisoformat(event[1]) <= first_time + timedelta(seconds=BURST_COALESCE_SECONDS)]
        event_keys = [event[0] for event in batch]
        previous_json = batch[0][3]
        current_json = batch[-1][2]
        completed = {}
        for event in batch:
            completed.update(json.loads(event[5] or "{}"))
        changed_fields = sorted({field for event in batch for field in json.loads(event[4])})
        event_key = hashlib.sha256("|".join(event_keys).encode()).hexdigest()
        event_key = "batch-" + event_key
        observed_at = batch[0][1]
        running_rows = [event for event in batch if event[6] == "running"]
        if running_rows and len(running_rows) == len(batch):
            completed = json.loads(batch[0][5] or "{}")
        if any(event[6] == "queued" for event in batch):
            placeholders = ",".join("?" for _ in event_keys)
            conn.execute(f"UPDATE events SET status='running' WHERE event_key IN ({placeholders})", event_keys)
            conn.execute("UPDATE state SET value=? WHERE key='last_ai_started'", (stamp.isoformat(),))
        conn.commit()
    current, previous, changed = json.loads(current_json), json.loads(previous_json), changed_fields
    roles = completed
    errors = {}
    for role in ROLES:
        if role in roles:
            continue
        try:
            roles[role] = _call_specialist(role, current, previous, generator)
        except Exception as exc:
            roles[role] = {"status": "fallback", "text": "Chưa có phân tích AI; dùng aggregate metrics đính kèm."}
            errors[role] = type(exc).__name__
        with closing(sqlite3.connect(state_path, timeout=5)) as conn:
            placeholders = ",".join("?" for _ in event_keys)
            conn.execute(f"UPDATE events SET specialist_json=? WHERE event_key IN ({placeholders})",
                         (json.dumps(roles, ensure_ascii=False), *event_keys))
            conn.commit()
    output = {
        "event_key": event_key,
        "coalesced_event_count": len(event_keys),
        "source_event_keys": event_keys,
        "observed_at": observed_at,
        "analyzed_at": stamp.isoformat(),
        "changed": changed,
        "current": current,
        "specialists": roles,
        "specialist_errors": errors,
        "suggest_only": True,
        "identifiers_exported": False,
        "customer_or_public_actions": 0,
    }
    encoded = json.dumps(output, ensure_ascii=False, indent=2)
    filename = f"{observed_at.replace(':', '').replace('-', '')}-{event_key[:12]}.json"
    destination = REPORT_DIR / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(encoded + "\n", encoding="utf-8")
    temporary.replace(destination)
    with closing(sqlite3.connect(state_path, timeout=5)) as conn:
        placeholders = ",".join("?" for _ in event_keys)
        conn.execute(f"UPDATE events SET specialist_json=?,status='done' WHERE event_key IN ({placeholders})",
                     (json.dumps(roles, ensure_ascii=False), *event_keys))
        conn.commit()
    return {"status": "done", "event_key": event_key, "coalesced_event_count": len(event_keys),
            "roles": list(roles),
            "fallback_roles": [role for role, output in roles.items() if output["status"] == "fallback"]}


def advance_without_ai(state_path: Path) -> None:
    """Coalesce baseline/availability events that carry no customer/order change."""
    with closing(sqlite3.connect(state_path, timeout=5)) as conn:
        events = conn.execute("SELECT event_key,current_json,previous_json FROM events "
                              "WHERE status='queued' ORDER BY observed_at").fetchall()
        for event_key, current_json, previous_json in events:
            current, previous = json.loads(current_json), json.loads(previous_json)
            customer_fields = {"new_users", "product_markers", "confirm_markers", "qr_customers",
                               "qr_requests_by_current_status",
                               "paid_topup_customers", "delivered_order_customers", "delivered_orders",
                               "revenue_after_refunds", "mature_24h", "converted_24h"}
            if not any(current.get(key) != previous.get(key) for key in customer_fields):
                conn.execute("UPDATE events SET status='ignored',specialist_json=? WHERE event_key=?",
                             (json.dumps({"status": "no_customer_signal"}), event_key))
        conn.commit()


def write_status(state_path: Path, scan_status: str, error_type: str | None = None) -> None:
    with closing(sqlite3.connect(state_path, timeout=5)) as conn:
        raw = conn.execute("SELECT value FROM state WHERE key='baseline'").fetchone()[0]
        counts = {status: count for status, count in
                  conn.execute("SELECT status,COUNT(*) FROM events GROUP BY status")}
        last_ai = conn.execute("SELECT value FROM state WHERE key='last_ai_started'").fetchone()[0]
    current = json.loads(raw) if raw else None
    status = {"heartbeat_at": _now().isoformat(), "worker_pid": os.getpid(),
              "scan_status": scan_status, "last_error_type": error_type,
              "poll_seconds": POLL_SECONDS, "event_counts": counts,
              "last_ai_started": last_ai or None,
              "baseline_counts": _public_counts(current) if current else None,
              "exact_source": CAPCUT_TRIAL_SOURCE, "source_db_mode": "ro",
              "specialist_roles": list(ROLES), "customer_or_public_actions": 0,
              "chat_delivery_interval_minutes": 15}
    status["strategy_plan"] = "PLAN-179"
    status["strategy_review_interval_hours"] = 6
    status["strategy_review_path"] = "reports/customer-agents/strategy/latest.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = REPORT_DIR / "status.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def tick(store_path: Path, state_path: Path, admins: tuple[int, ...],
         since: datetime, now: datetime | None = None,
         generator: Callable = AIUseCases.generate_text) -> dict:
    detected = detect_once(store_path, state_path, admins, since, now)
    advance_without_ai(state_path)
    result = dispatch_once(state_path, now, generator)
    return {**detected, "dispatch": result}


def _stop(signum, frame):  # noqa: ARG001
    global STOP
    STOP = True


def _background_work(state_path: Path) -> dict:
    """Periodic strategy work is separate from genuine cohort events and fingerprints."""
    try:
        event = dispatch_once(state_path)
    except Exception as exc:
        event = {"status": "unavailable", "error_type": type(exc).__name__}
    try:
        review = strategy_review.review_due()
    except Exception as exc:
        logger.warning("strategy review unavailable (%s)", type(exc).__name__)
        review = {"status": "unavailable", "error_type": type(exc).__name__}
    return {**event, "strategy_review": review}


def serve() -> None:
    global STOP
    STOP = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    store_path, admins, paths = _environment()
    state_path = paths["state_path"]
    initialize(state_path)
    since = _published_since()
    logger.info("started poll_seconds=%s source=%s", POLL_SECONDS, CAPCUT_TRIAL_SOURCE)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="capcut-specialists") as executor:
        pending = None
        while not STOP:
            try:
                if pending is None or pending.done():
                    if pending is not None:
                        try:
                            dispatch_result = pending.result()
                            if dispatch_result.get("status") not in {"idle", "cooldown"}:
                                logger.info("specialist dispatch=%s", dispatch_result.get("status"))
                        except Exception as exc:
                            logger.warning("specialist dispatch failed (%s)", type(exc).__name__)
                    advance_without_ai(state_path)
                    pending = executor.submit(_background_work, state_path)
                result = detect_once(store_path, state_path, admins, since)
                if result["status"] == "event":
                    logger.info("aggregate event=%s changed=%s", result["event_key"][:12], result["changed"])
                write_status(state_path, result["status"])
                time.sleep(POLL_SECONDS + random.uniform(0, min(0.25, POLL_SECONDS / 10)))
            except Exception as exc:
                logger.warning("scan unavailable (%s); preserving last aggregate", type(exc).__name__)
                try:
                    write_status(state_path, "unavailable", type(exc).__name__)
                except Exception:
                    logger.warning("cannot update supervisor health artifact")
                time.sleep(max(5, POLL_SECONDS))
        if pending is not None:
            pending.cancel()
    logger.info("stopped")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run one read-only tick and exit")
    args = parser.parse_args(argv)
    store_path, admins, paths = _environment()
    state_path = paths["state_path"]
    initialize(state_path)
    since = _published_since()
    if args.once:
        print(json.dumps(tick(store_path, state_path, admins, since), ensure_ascii=False))
    else:
        serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
