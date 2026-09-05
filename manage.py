#!/usr/bin/env python3
"""
Unified management CLI (Phase 2 SaaS Hardening).

Examples:
  python manage.py db backup
  python manage.py db upgrade
  python manage.py db stamp head          # existing DB already matches models — mark migrated without SQL
  python manage.py worker status
  python manage.py viral scan
  python manage.py serve

DB path: env DB_PATH or data/auto_publisher.db. Backup before first Alembic run on production data.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = typer.Typer(help="Auto Publisher — manage.py")
db_app = typer.Typer(help="Alembic database migrations")
worker_app = typer.Typer(help="Worker / PM2 helpers")
viral_app = typer.Typer(help="Viral scan & processing")
pages_app = typer.Typer(help="Facebook page tools (archived scripts)")
insights_app = typer.Typer(help="Insights scraping (archived script)")

app.add_typer(db_app, name="db")
app.add_typer(worker_app, name="worker")
app.add_typer(viral_app, name="viral")
app.add_typer(pages_app, name="pages")
app.add_typer(insights_app, name="insights")


def _env() -> dict:
    return {**os.environ, "PYTHONPATH": str(ROOT)}


def _alembic(args: list[str]) -> None:
    subprocess.check_call([sys.executable, "-m", "alembic", *args], cwd=str(ROOT), env=_env())


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head", help="Target revision (default: head)")) -> None:
    """Apply pending migrations.

    If the DB already has all tables from a pre-Alembic install, run `db stamp head` once instead of upgrade.
    """
    import sqlite3
    from app.config import DB_PATH
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_alembic_tmp_%'")
        for (tmp_table,) in cursor.fetchall():
            cursor.execute(f"DROP TABLE {tmp_table}")
            typer.echo(f"[cleanup] Dropped orphaned Alembic temp table: {tmp_table}")
        conn.commit()
        conn.close()
    except Exception as e:
        typer.echo(f"Warning: Failed to clean tmp tables: {e}")

    _alembic(["upgrade", revision])


@db_app.command("migrate")
def db_migrate() -> None:
    """Alias for `db upgrade head`."""
    _alembic(["upgrade", "head"])


@db_app.command("downgrade")
def db_downgrade(revision: str = typer.Argument(..., help="Target revision (e.g. -1 or revision id)")) -> None:
    """Revert migrations (use with care)."""
    _alembic(["downgrade", revision])


@db_app.command("history")
def db_history() -> None:
    _alembic(["history"])


@db_app.command("current")
def db_current() -> None:
    """Show current Alembic revision."""
    _alembic(["current"])


@db_app.command("stamp")
def db_stamp(revision: str = typer.Argument("head", help="Revision id to stamp")) -> None:
    """Mark DB at revision without running migration SQL (for existing DBs that already match models)."""
    _alembic(["stamp", revision])


@db_app.command("stamp-if-needed")
def stamp_if_needed() -> None:
    """Stamp head if DB has tables but no alembic_version."""
    import sqlite3
    from app.config import DB_PATH
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    conn.close()

    has_tables = len(tables) > 1  # có tables thực sự
    has_version = "alembic_version" in tables

    if has_tables and not has_version:
        print("DB exists without alembic_version -> stamping head...")
        _alembic(["stamp", "head"])
    else:
        print("alembic_version OK, skipping stamp.")


@db_app.command("revision")
def db_revision(
    message: str = typer.Option(..., "--message", "-m", help="Migration message"),
    autogenerate: bool = typer.Option(True, "--autogenerate/--empty", help="Autogenerate from models"),
) -> None:
    """Create a new migration (dev)."""
    if autogenerate:
        _alembic(["revision", "--autogenerate", "-m", message])
    else:
        _alembic(["revision", "-m", message])


def _parse_db_url(url: str) -> dict:
    """Tách DATABASE_URL kiểu SQLAlchemy thành tham số kết nối cho pg_dump."""
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url.replace("postgresql+psycopg2://", "postgresql://"))
    return {
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": (parsed.path or "/").lstrip("/") or "postgres",
    }


@db_app.command("backup")
def db_backup() -> None:
    """Dump database ra storage/db/backups/<db>_<timestamp>.sql.

    Postgres: dùng pg_dump trên PATH, nếu không có thì fallback `docker exec` vào
    container (tên lấy từ env POSTGRES_CONTAINER, mặc định toolsauto_postgres).
    SQLite legacy: copy file như cũ.

    Thất bại thì thoát khác 0. Trước đây lệnh này copy2(DB_PATH) — tức là backup
    file SQLite legacy chứ không phải Postgres đang chạy — mà vẫn in thành công.
    """
    from app.config import DATABASE_URL, DB_PATH

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not DATABASE_URL.startswith("postgres"):
        src = Path(DB_PATH)
        if not src.is_file():
            typer.echo(f"Database file not found: {src}", err=True)
            raise typer.Exit(code=1)
        dest = src.parent / f"{src.name}.bak.{ts}"
        shutil.copy2(src, dest)
        typer.echo(f"Backed up (sqlite): {dest}")
        return

    cfg = _parse_db_url(DATABASE_URL)
    backup_dir = Path("storage/db/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{cfg['dbname']}_{ts}.sql"

    env = os.environ.copy()
    if cfg["password"]:
        env["PGPASSWORD"] = cfg["password"]

    if shutil.which("pg_dump"):
        cmd = ["pg_dump", "-h", cfg["host"], "-p", cfg["port"],
               "-U", cfg["user"], "-d", cfg["dbname"], "--no-owner", "--no-acl"]
        how = "pg_dump"
    elif shutil.which("docker"):
        container = os.getenv("POSTGRES_CONTAINER", "toolsauto_postgres")
        cmd = ["docker", "exec"]
        if cfg["password"]:
            cmd += ["-e", f"PGPASSWORD={cfg['password']}"]
        cmd += [container, "pg_dump", "-U", cfg["user"], "-d", cfg["dbname"],
                "--no-owner", "--no-acl"]
        how = f"docker exec {container}"
    else:
        typer.echo("Không tìm thấy pg_dump lẫn docker — không thể backup Postgres.", err=True)
        raise typer.Exit(code=1)

    with open(dest, "wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=env, check=False)

    if proc.returncode != 0:
        dest.unlink(missing_ok=True)
        typer.echo(f"pg_dump thất bại ({how}): {proc.stderr.decode(errors='replace').strip()}", err=True)
        raise typer.Exit(code=1)

    size = dest.stat().st_size
    if size == 0:
        dest.unlink(missing_ok=True)
        typer.echo(f"pg_dump trả về file rỗng ({how}) — coi như thất bại.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Backed up ({how}): {dest} ({size:,} bytes)")


@worker_app.command("status")
def worker_status() -> None:
    """Print worker row from system_state (heartbeat, job, safe mode)."""
    import time

    from app.core.database.core import SessionLocal
    from app.core.queue.worker import WorkerService

    with SessionLocal() as db:
        state = WorkerService.get_or_create_state(db)
        now = int(time.time())
        hb_age = (now - state.heartbeat_at) if state.heartbeat_at else None
        uptime = (now - state.worker_started_at) if state.worker_started_at else None

        typer.echo(f"worker_status: {state.worker_status}")
        typer.echo(f"heartbeat_at: {state.heartbeat_at} (age_s: {hb_age})")
        typer.echo(f"current_job_id: {state.current_job_id}")
        typer.echo(f"safe_mode: {state.safe_mode}")
        typer.echo(f"pending_command: {state.pending_command}")
        if uptime is not None:
            typer.echo(f"uptime_s: {uptime}")


@worker_app.command("restart")
def worker_restart(
    name: str = typer.Argument(
        "all",
        help="PM2 process name or 'all' (override with env PM2_APP)",
    ),
) -> None:
    """Restart PM2 process(es). Uses `pm2 restart <name>`."""
    pm2 = shutil.which("pm2")
    if not pm2:
        typer.echo("pm2 not found on PATH. Restart workers manually.", err=True)
        raise typer.Exit(code=1)
    target = os.getenv("PM2_APP", name)
    subprocess.check_call([pm2, "restart", target], cwd=str(ROOT), env=_env())


@viral_app.command("scan")
def viral_scan() -> None:
    """TikTok competitor channel scan → new ViralMaterial rows."""
    from app.core.database.core import SessionLocal
    from app.features.viral_intake.scan import run_tiktok_competitor_scan

    with SessionLocal() as db:
        n, ch, sq, sm = run_tiktok_competitor_scan(db)
    typer.echo(f"new_videos={n} channels_scanned={ch} skipped_quota={sq} skipped_mega={sm}")


@viral_app.command("process")
def viral_process() -> None:
    """Download / queue viral materials (yt-dlp pipeline)."""
    from app.core.database.core import SessionLocal
    from app.features.viral_intake.processor import ViralProcessorService

    svc = ViralProcessorService()
    with SessionLocal() as db:
        svc.process_all(db)
    typer.echo("process_all finished.")


@viral_app.command("clean")
def viral_clean(
    force: bool = typer.Option(False, "--force", "-f", help="Bypass maintenance hourly throttle"),
) -> None:
    """Orphan target cleanup + stale NEW virals (same as maintenance helper)."""
    from app.core.database.core import SessionLocal
    from workers import maintenance as maint

    if force:
        maint._last_orphan_cleanup_ts = 0
    with SessionLocal() as db:
        maint._cleanup_orphaned_virals(db)
    typer.echo("clean done.")


def _run_archived_script(rel: str, extra: list[str]) -> None:
    script = ROOT / "scripts" / "archive" / rel
    if not script.is_file():
        typer.echo(f"Script not found: {script}", err=True)
        raise typer.Exit(code=1)
    subprocess.check_call([sys.executable, str(script), *extra], cwd=str(ROOT), env=_env())


@pages_app.command("scrape")
def pages_scrape(
    account: Optional[int] = typer.Option(None, "--account", "-a", help="Single account id"),
) -> None:
    """Run archived scrape_pages.py (managed Facebook pages)."""
    cmd: list[str] = []
    if account is not None:
        cmd.extend(["--account", str(account)])
    _run_archived_script("scrape_pages.py", cmd)


@insights_app.command("scrape")
def insights_scrape() -> None:
    """Run archived scrape_insights.py."""
    _run_archived_script("scrape_insights.py", [])


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Start uvicorn dev server (requires DB migrated)."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


@app.command("stack")
def stack(
    host: str = typer.Option("127.0.0.1", "--host", help="Web bind host"),
    port: int = typer.Option(0, "--port", help="Web port (0 = app.config.WEB_PORT)"),
    no_web: bool = typer.Option(False, "--no-web", help="Only maintenance + FB publisher"),
    reload_web: bool = typer.Option(
        False,
        "--reload-web/--no-reload-web",
        help="Pass --reload to web (creates extra process; off by default in stack)",
    ),
) -> None:
    """Local supervisor: keep 1 web + 1 maintenance + 1 FB publisher (PLAN-048)."""
    import app.config as config
    from app.platform.local_supervisor import StackConfig, run_stack

    resolved = port if port > 0 else int(getattr(config, "WEB_PORT", 8002) or 8002)
    raise SystemExit(
        run_stack(
            StackConfig(host=host, port=resolved, no_web=no_web, reload_web=reload_web)
        )
    )


if __name__ == "__main__":
    app()
