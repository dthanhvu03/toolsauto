"""Read-only follow-up for the single published trial; no bot messages or vendor calls."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from cashback_bot import store_campaign

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
manifest = json.loads((FOLDER / "trial-manifest.json").read_text())
if manifest["status"] != "posted":
    raise SystemExit("No verified published trial in manifest")
env = {**dotenv_values(ROOT / ".env"), **os.environ}
admins = tuple(int(x.strip()) for x in env["STORE_ADMIN_IDS"].replace(";", ",").split(",") if x.strip())
store_path = Path(env.get("STORE_DB_PATH") or "./data/store.sqlite")
if not store_path.is_absolute():
    store_path = ROOT / store_path
since = datetime.fromisoformat(manifest["published_at"].replace("Z", "+00:00"))
now = datetime.now(timezone.utc)
report = store_campaign.report(since, 2, now, store_path, source_prefix=manifest["source"], exclude_user_ids=admins, source_exact=True)
proof = {"observed_at": now.isoformat(), "post_url": manifest["post_url"], "source": manifest["source"],
         "since_is_attempt_start_not_exact_publish_time": bool(manifest.get("publish_time_is_attempt_start")),
         "report": report, "notes": ["The source was used only for this trial; existing customers are not reattributed.",
                                     "A fresh post with no mature 24h cohort is not evidence of success or failure.",
                                     "No link clicks/impressions are available before Telegram Start."]}
(FOLDER / "trial-measurement.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"observed_at": now.isoformat(), "errors": report["errors"], "cohort": report["cohort"]}, ensure_ascii=False))
