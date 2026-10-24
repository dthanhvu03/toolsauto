"""Tự đồng bộ Shopee theo lịch và khoá một lượt chạy chung cho thủ công / tự động (PLAN-080, ADR-057).

- Dùng lại nguyên pipeline của ShopeeSyncEngine (snapshot đơn → lịch sử thay đổi → sự kiện PLAN-079 → hàng đợi).
  Không có đường đồng bộ hay đường thông báo thứ hai.
- Chạy ở một luồng nền duy nhất (SyncWorker), nên Telegram vẫn nhận và trả lời trong lúc gọi Shopee. Không giữ
  transaction SQLite trong lúc gọi HTTP: mỗi đơn ghi trong transaction riêng như trước.
- Khoá một lượt (single flight) nằm trong DB (shopee_sync_state.lease_*): lấy khoá, gia hạn sau mỗi trang, đóng lượt
  và nhả khoá trong cùng transaction có kiểm tra chủ khoá. Lượt mất khoá không ghi kết quả. Khoá quá hạn hoặc của
  tiến trình đã chết thì được thu hồi, lượt cũ ghi «interrupted».
- Lịch bền: next_due_at lưu trong DB, giờ UTC. Restart không chạy lại lượt vừa xong; bot tắt lâu chỉ chạy bù một lượt.
- Cờ SHOPEE_AUTO_SYNC_ENABLED (mặc định tắt) là công tắc chính. Nút admin chỉ tạm dừng / tiếp tục khi cờ đã bật.
- Lỗi phiên (AUTH_EXPIRED / ACCESS_DENIED / CHALLENGE): dừng tự đồng bộ (NEEDS_AUTH), báo admin một lần, tự chạy lại
  khi admin kết nối lại cookie hoặc đồng bộ tay thành công. Lỗi tạm, 429, PARTIAL: lùi lịch có giãn cách.
"""

from __future__ import annotations

import html
import json
import logging
import os
import queue
import socket
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from cashback_bot import reconciliation
from cashback_bot.config import AutoSyncConfig
from cashback_bot.db import TrackingRepository, enqueue_event
from cashback_bot.shopee_client import NEEDS_AUTH_CATEGORIES, PARSE_ERROR, RATE_LIMITED
from cashback_bot.shopee_sync import SYNC_REQUEST_KEY, ShopeeSyncEngine, SyncResult

logger = logging.getLogger("cashback_bot")

# Bật cờ lần đầu: lượt tự động đầu tiên sau 5 phút, để chủ bot kịp mở màn theo dõi.
FIRST_RUN_DELAY = timedelta(minutes=5)
# Lỗi tạm: lùi 15, 30, 60… phút, không quá một chu kỳ.
RETRY_BASE = timedelta(minutes=15)
REMIND_EVERY = timedelta(hours=24)
WORKER_TICK_SECONDS = 30
WAKE = threading.Event()


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _owner_alive(owner: str | None) -> bool:
    """Chủ khoá còn sống? Chỉ biết chắc với tiến trình cùng máy; máy khác coi như còn sống tới khi khoá quá hạn."""
    try:
        host, pid, _token = str(owner).split(":")
        if host != socket.gethostname():
            return True
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (ValueError, PermissionError):
        return True
    return True


def _state(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM shopee_sync_state WHERE id = 1").fetchone()
    if row is None:
        conn.execute("INSERT OR IGNORE INTO shopee_sync_state (id, updated_at) VALUES (1, ?)", (_stamp(_utcnow()),))
        row = conn.execute("SELECT * FROM shopee_sync_state WHERE id = 1").fetchone()
    return row


def busy(repo: TrackingRepository, now: datetime | None = None) -> tuple[int, str] | None:
    """Lượt đang giữ khoá (mã lượt, thủ công / tự động), hoặc None."""
    moment = now or _utcnow()
    with repo.connect() as conn:
        row = _state(conn)
    expires = _parse(row["lease_expires_at"])
    if row["lease_owner"] and expires is not None and expires > moment:
        return int(row["lease_run_id"] or 0), str(row["lease_trigger"] or "")
    return None


def request_manual(repo: TrackingRepository, now: datetime | None = None) -> tuple[int, str] | None:
    """Admin bấm 🔄. Đang có lượt chạy thì trả lượt đó, không xếp lượt thứ hai; không thì xếp và đánh thức luồng nền."""
    current = busy(repo, now)
    if current is not None:
        return current
    repo.set_state(SYNC_REQUEST_KEY, "1")
    WAKE.set()
    return None


def derived_status(row, cfg: AutoSyncConfig, now: datetime) -> str:
    expires = _parse(row["lease_expires_at"])
    if row["lease_owner"] and expires is not None and expires > now:
        return "RUNNING"
    if not cfg.enabled:
        return "DISABLED"
    if row["paused"]:
        return "PAUSED"
    if row["needs_auth_since"]:
        return "NEEDS_AUTH"
    failures = int(row["consecutive_failures"] or 0)
    if failures >= cfg.failure_threshold:
        return "FAILED"
    if failures:
        return "RETRY_WAIT"
    return "SCHEDULED"


class SyncCoordinator:
    def __init__(
        self,
        repo: TrackingRepository,
        admin_notifier=None,
        cfg: AutoSyncConfig = AutoSyncConfig(),
        engine_factory: Callable[..., ShopeeSyncEngine] = ShopeeSyncEngine,
        clock: Callable[[], datetime] = _utcnow,
        owner: str | None = None,
        client_factory: Callable[[], object] | None = None,
    ):
        self.repo = repo
        self.admin_notifier = admin_notifier
        self.cfg = cfg
        self.engine_factory = engine_factory
        self.clock = clock
        self.owner_prefix = owner
        self.client_factory = client_factory
        # Lượt xong chờ luồng chính làm tiếp (làm mới ví, tin kết quả cho admin, gửi hàng đợi).
        self.completed: queue.Queue[tuple[str, SyncResult]] = queue.Queue()

    # --- Trạng thái và lịch ----------------------------------------------------------------------

    def start(self) -> None:
        """Lúc khởi động: áp cấu hình vào lịch, thu hồi khoá của tiến trình đã chết."""
        now = self.clock()
        with self.repo.connect() as conn:
            row = _state(conn)
            updates: dict = {}
            if bool(row["enabled"]) != self.cfg.enabled:
                updates["enabled"] = int(self.cfg.enabled)
                if self.cfg.enabled:
                    updates["next_due_at"] = _stamp(now + FIRST_RUN_DELAY)
                    updates["last_scheduled_at"] = _stamp(now)
                else:
                    updates["next_due_at"] = None
            if row["interval_minutes"] != self.cfg.interval_minutes:
                updates["interval_minutes"] = self.cfg.interval_minutes
                last = _parse(row["last_finished_at"])
                if self.cfg.enabled and bool(row["enabled"]) and last is not None:
                    updates["next_due_at"] = _stamp(max(now, last + self.cfg.interval))
            if row["lease_owner"]:
                expires = _parse(row["lease_expires_at"])
                if expires is None or expires <= now or not _owner_alive(row["lease_owner"]):
                    self._interrupt(conn, row, now, "bot dừng giữa lượt")
            if updates:
                updates["updated_at"] = _stamp(now)
                sets = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(f"UPDATE shopee_sync_state SET {sets} WHERE id = 1", tuple(updates.values()))
        if updates:
            logger.info("[ShopeeAutoSync] cấu hình: bật=%s chu kỳ=%s phút", self.cfg.enabled, self.cfg.interval_minutes)

    def _interrupt(self, conn: sqlite3.Connection, row, now: datetime, reason: str) -> None:
        if row["lease_run_id"]:
            conn.execute(
                "UPDATE shopee_sync_runs SET status = 'interrupted', error_category = 'INTERRUPTED', error_message = ?, "
                "completed_at = ? WHERE id = ? AND status = 'running'",
                (reason, _stamp(now), row["lease_run_id"]),
            )
        conn.execute(
            "UPDATE shopee_sync_state SET lease_owner = NULL, lease_run_id = NULL, lease_trigger = NULL, "
            "lease_started_at = NULL, lease_expires_at = NULL, last_result = 'interrupted', updated_at = ? WHERE id = 1",
            (_stamp(now),),
        )

    def set_paused(self, admin_id: int, paused: bool) -> bool:
        """Tạm dừng / tiếp tục (lưu bền). Chỉ có tác dụng khi cờ đã bật; trả True khi có thay đổi."""
        now = self.clock()
        with self.repo.connect() as conn:
            row = _state(conn)
            if bool(row["paused"]) == paused:
                return False
            due = None if paused else _stamp(now + FIRST_RUN_DELAY)
            conn.execute(
                "UPDATE shopee_sync_state SET paused = ?, paused_at = ?, paused_by = ?, next_due_at = ?, updated_at = ? "
                "WHERE id = 1",
                (int(paused), _stamp(now) if paused else None, admin_id if paused else None, due, _stamp(now)),
            )
        return True

    def _auth_recovered(self, conn: sqlite3.Connection, row) -> bool:
        cookie = conn.execute("SELECT status, updated_at FROM shopee_cookies WHERE id = 1").fetchone()
        return (
            cookie is not None and cookie["status"] == "connected"
            and (cookie["updated_at"] or "") > (row["needs_auth_since"] or "")
        )

    def next_job(self, now: datetime | None = None) -> str | None:
        """'manual' khi admin vừa bấm 🔄; 'auto' khi tới giờ; None khi chưa có việc."""
        moment = now or self.clock()
        if self.repo.get_state(SYNC_REQUEST_KEY) == "1":
            return "manual"
        if not self.cfg.enabled:
            return None
        with self.repo.connect() as conn:
            row = _state(conn)
            if row["paused"]:
                return None
            if row["needs_auth_since"]:
                if not self._auth_recovered(conn, row):
                    return None
                # Admin đã kết nối lại cookie: thử lại ngay.
                conn.execute(
                    "UPDATE shopee_sync_state SET needs_auth_since = NULL, next_due_at = ?, updated_at = ? WHERE id = 1",
                    (_stamp(moment), _stamp(moment)),
                )
                return "auto"
            due = _parse(row["next_due_at"])
        if due is None or moment >= due:
            return "auto"
        return None

    # --- Khoá một lượt -----------------------------------------------------------------------------

    def _acquire(self, trigger: str, now: datetime) -> tuple[str | None, int | None, tuple[int, str] | None]:
        """(chủ khoá, mã lượt, None) khi lấy được; (None, None, lượt đang chạy) khi bận. Một transaction."""
        owner = f"{self.owner_prefix}:{uuid.uuid4().hex[:8]}" if self.owner_prefix else new_owner()
        ttl = now + timedelta(seconds=self.cfg.max_runtime_seconds)
        conn = self.repo.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = _state(conn)
            expires = _parse(row["lease_expires_at"])
            if row["lease_owner"]:
                if expires is not None and expires > now and _owner_alive(row["lease_owner"]):
                    conn.rollback()
                    return None, None, (int(row["lease_run_id"] or 0), str(row["lease_trigger"] or ""))
                self._interrupt(conn, row, now, "khoá quá hạn, lượt khác thu hồi")
            cursor = conn.execute(
                "INSERT INTO shopee_sync_runs (trigger_type, status, started_at, lease_owner) VALUES (?, 'running', ?, ?)",
                (trigger, _stamp(now), owner),
            )
            run_id = int(cursor.lastrowid)
            conn.execute(
                "UPDATE shopee_sync_state SET lease_owner = ?, lease_run_id = ?, lease_trigger = ?, lease_started_at = ?, "
                "lease_expires_at = ?, heartbeat_at = ?, last_started_at = ?, updated_at = ? WHERE id = 1",
                (owner, run_id, trigger, _stamp(now), _stamp(ttl), _stamp(now), _stamp(now), _stamp(now)),
            )
            conn.commit()
            return owner, run_id, None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _heartbeat(self, owner: str, run_id: int) -> bool:
        """Gia hạn khoá sau mỗi trang. False: đã mất khoá, hoặc lượt quá thời gian tối đa (dừng, không ghi tiếp)."""
        now = self.clock()
        with self.repo.connect() as conn:
            row = _state(conn)
            started = _parse(row["lease_started_at"])
            if row["lease_owner"] != owner or row["lease_run_id"] != run_id or started is None:
                return False
            if now - started > timedelta(seconds=self.cfg.max_runtime_seconds):
                return False
            cursor = conn.execute(
                "UPDATE shopee_sync_state SET lease_expires_at = ?, heartbeat_at = ? "
                "WHERE id = 1 AND lease_owner = ? AND lease_run_id = ?",
                (_stamp(now + timedelta(seconds=self.cfg.max_runtime_seconds)), _stamp(now), owner, run_id),
            )
            return cursor.rowcount == 1

    # --- Một lượt -----------------------------------------------------------------------------------

    def run(self, trigger: str) -> SyncResult | None:
        """Chạy một lượt có khoá. Bận thì không chạy (lượt thủ công trùng: báo admin mã lượt đang chạy)."""
        now = self.clock()
        if trigger == "manual":
            self.repo.set_state(SYNC_REQUEST_KEY, "0")
        owner, run_id, current = self._acquire(trigger, now)
        if owner is None:
            if trigger == "manual" and current is not None:
                self._notify_busy(current)
            return None
        engine = self.engine_factory(self.repo, admin_notifier=self.admin_notifier)
        kwargs = {"trigger": trigger, "run_id": run_id, "heartbeat": lambda: self._heartbeat(owner, run_id),
                  "alert_auth": False}
        if self.client_factory is not None:
            kwargs["client"] = self.client_factory()
        if self.cfg.reconcile_lookup:
            # PLAN-081 Phương án A: cùng lượt, cùng khoá; có trần số đơn mỗi lượt và 1 lần / đơn / ngày.
            targets = reconciliation.lookup_targets(self.repo, now, self.cfg.reconcile_lookup_max)
            if targets:
                kwargs["lookups"] = targets
        try:
            result = engine.sync(**kwargs)
        except Exception as exc:
            logger.exception("[ShopeeAutoSync] lượt %s lỗi ngoài dự kiến", run_id)
            result = SyncResult(ok=False, message=f"Lỗi đồng bộ: {type(exc).__name__}", status="failed",
                                category="UNKNOWN_ERROR", run_id=run_id)
        if not self._finish(owner, run_id, trigger, result):
            logger.warning("[ShopeeAutoSync] lượt %s mất khoá, không ghi kết quả", run_id)
            return result
        self._incident(run_id, result)
        try:
            # PLAN-081: nhãn theo dõi đơn đang chờ; chỉ đọc DB, lỗi ở đây không làm hỏng lượt đồng bộ.
            reconciliation.evaluate(
                self.repo, self.clock(), run_id=run_id, window_start=(result.stats or {}).get("window_start"),
                run_success=result.status == "success", admin_notifier=self.admin_notifier,
            )
        except Exception:
            logger.exception("[ShopeeAutoSync] cập nhật theo dõi đối soát sau lượt %s lỗi", run_id)
        self.completed.put((trigger, result))
        return result

    def _next_due(self, row, result: SyncResult, failures: int, now: datetime) -> str | None:
        if not self.cfg.enabled or row["paused"] or result.category in NEEDS_AUTH_CATEGORIES:
            return None
        if result.status == "success":
            return _stamp(now + self.cfg.interval)
        backoff = min(self.cfg.interval, RETRY_BASE * (2 ** max(0, failures - 1)))
        if result.category == RATE_LIMITED and result.retry_after:
            backoff = max(backoff, timedelta(seconds=int(result.retry_after)))
        return _stamp(now + backoff)

    def _finish(self, owner: str, run_id: int, trigger: str, result: SyncResult) -> bool:
        """Đóng lượt, cập nhật lịch, nhả khoá: một transaction, chỉ khi còn giữ khoá."""
        now = self.clock()
        conn = self.repo.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = _state(conn)
            if row["lease_owner"] != owner or row["lease_run_id"] != run_id:
                conn.rollback()
                return False
            status = result.status if result.status in ("success", "partial", "failed") else "failed"
            stats = dict(result.stats or {})
            self.repo.complete_shopee_sync_run(
                run_id=run_id, status=status, clicks=result.clicks_synced, conversions=result.conversions_synced,
                new_orders=result.new_matched_orders, error=None if status == "success" else result.message[:200],
                category=result.category, stats=stats, conn=conn,
            )
            failures = 0 if status == "success" else int(row["consecutive_failures"] or 0) + 1
            needs_auth = row["needs_auth_since"]
            if status == "success":
                needs_auth = None
            elif result.category in NEEDS_AUTH_CATEGORIES and not needs_auth:
                needs_auth = _stamp(now)
            values = {
                "last_finished_at": _stamp(now),
                "last_result": status,
                "last_run_id": run_id,
                "last_error_category": None if status == "success" else result.category,
                "consecutive_failures": failures,
                "needs_auth_since": needs_auth,
                "next_due_at": self._next_due(row, result, failures, now),
                "lease_owner": None, "lease_run_id": None, "lease_trigger": None, "lease_started_at": None,
                "lease_expires_at": None,
                "updated_at": _stamp(now),
            }
            if status == "success":
                values["last_success_at"] = _stamp(now)
                values["last_success_window_start"] = stats.get("window_start")
                values["last_success_window_end"] = stats.get("window_end")
            sets = ", ".join(f"{key} = ?" for key in values)
            conn.execute(f"UPDATE shopee_sync_state SET {sets} WHERE id = 1", tuple(values.values()))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Sự cố và cảnh báo admin --------------------------------------------------------------------

    def _incident(self, run_id: int, result: SyncResult) -> None:
        now = self.clock()
        stamp = _stamp(now)
        with self.repo.connect() as conn:
            row = _state(conn)
            open_row = conn.execute("SELECT * FROM shopee_sync_incidents WHERE resolved_at IS NULL").fetchone()
            if result.status == "success":
                if open_row is not None:
                    conn.execute("UPDATE shopee_sync_incidents SET resolved_at = ?, last_run_id = ? WHERE id = ?",
                                 (stamp, run_id, open_row["id"]))
                    self._alert(conn, f"sync_incident:{open_row['id']}:resolved", self._recovered_text(open_row, now))
                return
            if result.category in NEEDS_AUTH_CATEGORIES:
                category = "NEEDS_AUTH"
            elif result.category == PARSE_ERROR:
                category = "SOURCE_FORMAT"
            elif result.status == "partial":
                category = "PARTIAL_SYNC"
            else:
                category = "SYNC_FAILING"
            failures = int(row["consecutive_failures"] or 0)
            summary = f"{result.category or '-'}: {html.escape(result.message[:160])}"
            if open_row is None:
                urgent = category in ("NEEDS_AUTH", "SOURCE_FORMAT")
                if not urgent and failures < self.cfg.failure_threshold:
                    return
                cursor = conn.execute(
                    "INSERT INTO shopee_sync_incidents (category, opened_at, last_seen_at, failures, first_run_id, "
                    "last_run_id, summary, last_alert_at, alerts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (category, stamp, stamp, failures, run_id, run_id, summary, stamp),
                )
                incident = int(cursor.lastrowid)
                self._alert(conn, f"sync_incident:{incident}:open", self._incident_text(incident, category, summary, failures))
                return
            escalated = open_row["category"] != category and category == "NEEDS_AUTH"
            last_alert = _parse(open_row["last_alert_at"])
            remind = last_alert is None or now - last_alert >= REMIND_EVERY
            conn.execute(
                "UPDATE shopee_sync_incidents SET last_seen_at = ?, failures = ?, last_run_id = ?, summary = ?, category = ? "
                "WHERE id = ?",
                (stamp, failures, run_id, summary, category if escalated else open_row["category"], open_row["id"]),
            )
            if escalated or remind:
                alerts = int(open_row["alerts"] or 0) + 1
                conn.execute("UPDATE shopee_sync_incidents SET last_alert_at = ?, alerts = ? WHERE id = ?",
                             (stamp, alerts, open_row["id"]))
                kind = "escalated" if escalated else f"remind:{alerts}"
                self._alert(conn, f"sync_incident:{open_row['id']}:{kind}",
                            self._incident_text(int(open_row["id"]), category if escalated else open_row["category"],
                                                summary, failures, again=True))

    def _alert(self, conn: sqlite3.Connection, key: str, body: str) -> None:
        notifier = self.admin_notifier
        if notifier is None or not getattr(notifier, "enabled", False) or getattr(notifier, "chat_id", None) is None:
            return
        enqueue_event(conn, event_key=key, event_type="SYNC_INCIDENT", chat_id=int(notifier.chat_id), message_html=body,
                      now=_stamp(self.clock()))

    def _incident_text(self, incident: int, category: str, summary: str, failures: int, again: bool = False) -> str:
        titles = {
            "NEEDS_AUTH": "🔑 <b>Shopee cần kiểm tra phiên đăng nhập</b>",
            "SOURCE_FORMAT": "🧩 <b>Dữ liệu Shopee đổi định dạng</b>",
            "PARTIAL_SYNC": "⚠️ <b>Đồng bộ Shopee chưa đọc đủ dữ liệu</b>",
            "SYNC_FAILING": "⚠️ <b>Đồng bộ Shopee lỗi liên tiếp</b>",
        }
        hint = {
            "NEEDS_AUTH": "Tự đồng bộ đã dừng. Vào /admin → 🔗 Shopee Affiliate → 🔑 Cập nhật Cookie. Bot không tự đăng nhập "
                          "hay vượt bước xác minh. Kết nối lại xong, bot tự chạy lại.",
            "SOURCE_FORMAT": "Bot không đọc được cấu trúc trả về; đơn cũ giữ nguyên. Cần kiểm tra code đồng bộ.",
            "PARTIAL_SYNC": "Phần đã đọc được đã ghi; phần còn lại giữ số cũ. Bot sẽ thử lại theo lịch.",
            "SYNC_FAILING": "Bot sẽ thử lại với giãn cách. Đồng bộ tay 🔄 vẫn dùng được.",
        }
        return (
            f"{titles.get(category, '⚠️ <b>Sự cố đồng bộ Shopee</b>')}{' (nhắc lại)' if again else ''}\n\n"
            f"Sự cố #{incident} · lỗi liên tiếp: {failures}\n"
            f"Lỗi gần nhất: <i>{summary}</i>\n\n"
            f"👉 {hint.get(category, '')}\n"
            "Xem /admin → 🔗 Shopee Affiliate → ⏱ Tự động đồng bộ."
        )

    def _recovered_text(self, incident, now: datetime) -> str:
        opened = _parse(incident["opened_at"])
        minutes = int((now - opened).total_seconds() // 60) if opened else 0
        return (
            f"✅ <b>Đồng bộ Shopee đã hoạt động lại</b>\n\nSự cố #{incident['id']} kết thúc sau khoảng {minutes} phút. "
            "Lịch tự đồng bộ trở lại bình thường."
        )

    def _notify_busy(self, current: tuple[int, str]) -> None:
        notifier = self.admin_notifier
        if notifier is None or not getattr(notifier, "enabled", False) or getattr(notifier, "chat_id", None) is None:
            return
        run_id, trigger = current
        label = "tự động" if trigger == "auto" else "thủ công"
        with self.repo.connect() as conn:
            self._alert(conn, f"sync_busy:{run_id}", (
                f"🔄 Shopee đang được đồng bộ {label}. Mã lượt: #{run_id}. Không chạy thêm lượt thứ hai; "
                "kết quả có ở màn ⏱ Tự động đồng bộ."
            ))


class SyncWorker(threading.Thread):
    """Luồng nền duy nhất chạy đồng bộ. Không bao giờ dừng vì lỗi một lượt."""

    def __init__(self, coordinator: SyncCoordinator, tick_seconds: float = WORKER_TICK_SECONDS):
        super().__init__(name="shopee-sync", daemon=True)
        self.coordinator = coordinator
        self.tick_seconds = tick_seconds
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.coordinator.next_job()
                if job is not None:
                    self.coordinator.run(job)
                    continue
            except Exception:
                logger.exception("[ShopeeAutoSync] vòng lập lịch lỗi")
            WAKE.wait(self.tick_seconds)
            WAKE.clear()

    def stop(self) -> None:
        self.stop_event.set()
        WAKE.set()


def history(repo: TrackingRepository, limit: int = 15) -> list[sqlite3.Row]:
    with repo.connect() as conn:
        return conn.execute("SELECT * FROM shopee_sync_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def snapshot(repo: TrackingRepository) -> dict:
    """Trạng thái lịch cho màn admin và báo cáo (chỉ đọc)."""
    with repo.connect() as conn:
        row = dict(_state(conn))
        incident = conn.execute("SELECT * FROM shopee_sync_incidents WHERE resolved_at IS NULL").fetchone()
    row["open_incident"] = dict(incident) if incident else None
    return json.loads(json.dumps(row))
