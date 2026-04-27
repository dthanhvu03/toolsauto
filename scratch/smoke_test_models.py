import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import app.database.models as m
    from app.database.core import Base
    print(f"Tables registered: {len(Base.metadata.tables)}")
    print(f"Job class: {m.Job}")
    print(f"Account class: {m.Account}")
    print(f"IncidentLog class: {m.IncidentLog}")
    print("SUCCESS: All imports and metadata checks passed.")
except Exception as e:
    print(f"FAILURE: {e}")
    sys.exit(1)
