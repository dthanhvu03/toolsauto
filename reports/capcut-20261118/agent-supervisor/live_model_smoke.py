"""One bounded live-model verification; no production event or customer is created."""
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.features.threads.growth import capcut_supervisor as supervisor

root = Path(__file__).resolve().parents[3]
folder = root / "reports/capcut-20261118/agent-supervisor/smoke"
folder.mkdir(parents=True, exist_ok=True)
store_path, admins, _ = supervisor._environment()
now = datetime.now(timezone.utc)
actual = supervisor.snapshot(store_path, admins, supervisor._published_since(), now)
proof = {"mode": "manual_model_smoke_not_business_event", "started_at": now.isoformat(),
         "actual_aggregate_counts": supervisor._public_counts(actual),
         "customer_or_public_actions": 0, "production_event_inserted": False,
         "generator_calls_requested": 3}
with tempfile.TemporaryDirectory(prefix="capcut-model-smoke-") as temporary:
    state = Path(temporary) / "state.sqlite"
    supervisor.initialize(state)
    observed = (now - timedelta(seconds=11)).isoformat()
    with sqlite3.connect(state) as conn:
        conn.execute("INSERT INTO events(event_key,observed_at,current_json,previous_json,changed_json) VALUES(?,?,?,?,?)",
                     ("manual-model-smoke", observed, json.dumps(actual), json.dumps(actual), json.dumps(["manual_model_smoke"])))
    supervisor.REPORT_DIR = folder
    result = supervisor.dispatch_once(state, now, cooldown=0)
    with sqlite3.connect(state) as conn:
        outputs = json.loads(conn.execute("SELECT specialist_json FROM events").fetchone()[0])
    proof.update(result=result, role_outputs=outputs, finished_at=datetime.now(timezone.utc).isoformat())
(folder / "proof.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"mode": proof["mode"], "result": result,
                  "roles": {role: value["status"] for role, value in outputs.items()}}, ensure_ascii=False))
