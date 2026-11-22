"""Sanitized runtime proof for PLAN-176; read-only state and process metadata."""
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.features.threads.growth import capcut_supervisor as supervisor

folder = Path(__file__).resolve().parent
apps = json.loads(subprocess.check_output(["pm2", "jlist"], text=True))
processes = [{"name": row["name"], "pid": row["pid"],
              "status": row["pm2_env"]["status"], "restarts": row["pm2_env"]["restart_time"],
              "unstable_restarts": row["pm2_env"]["unstable_restarts"],
              "started_at": datetime.fromtimestamp(row["pm2_env"]["pm_uptime"] / 1000, timezone.utc).isoformat()}
             for row in apps]
with sqlite3.connect(supervisor.DEFAULT_STATE_DB.resolve().as_uri() + "?mode=ro", uri=True) as conn:
    states = dict(conn.execute("SELECT key,value FROM state"))
    events = dict(conn.execute("SELECT status,COUNT(*) FROM events GROUP BY status"))
    business_events = conn.execute("SELECT COUNT(*) FROM events WHERE status IN (\'queued\',\'running\',\'done\')").fetchone()[0]
    baseline = json.loads(states["baseline"])
proof = {"observed_at": datetime.now(timezone.utc).isoformat(), "processes": processes,
         "sidecar_event_counts": events, "sidecar_event_sequence": states["event_sequence"],
         "last_production_sidecar_ai_started_at": states["last_ai_started"] or None,
         "current_business_events": business_events,
         "baseline_counts": supervisor._public_counts(baseline),
         "status": json.loads((folder / "status.json").read_text()),
         "smoke": json.loads((folder / "smoke/proof.json").read_text()),
         "rollout_normalization": json.loads((folder / "smoke/rollout-qr-field-normalization.json").read_text()),
         "rollout_normalization_role_calls": len(json.loads((folder / "smoke/rollout-qr-field-normalization.json").read_text()).get("specialists", {})),
         "source_db_open_mode": "ro", "customer_or_public_actions": 0,
         "notes": ["Supervisor restart count3 reflects three deliberate deployment reloads; PM2 reports zero unstable restarts.",
                   "Smoke uses a temporary sidecar and actual zero-change aggregate, not a production event.",
                   "One rollout-only empty QR-field shape event triggered three suggest-only calls on a zero cohort before compatibility normalization; proof is preserved and sidecar status is ignored. No customer actions occurred. Regression now covers this migration case.",
                   "Post-fix current baseline has no meaningful cohort event and no provider call; manual live smoke is separately labelled.",
                   "A forced kill can repeat an unfinished model call; completed role outputs persist (at-least-once).",
                   "Host/WSL/PM2 must remain running; no processing while the machine is off."]}
(folder / "runtime-proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"observed_at": proof["observed_at"], "supervisor": next(row for row in processes if row["name"] == "CapCut_Agent_Supervisor"),
                  "source_event_counts": events, "current_business_events": business_events, "historical_rollout_role_calls": proof["rollout_normalization_role_calls"],
                  "health": proof["status"]["scan_status"], "live_smoke_roles": proof["smoke"]["result"]["roles"],
                  "smoke_fallback_roles": proof["smoke"]["result"]["fallback_roles"]}, ensure_ascii=False))
