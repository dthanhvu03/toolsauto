import sys
import json
from app.database.core import SessionLocal
from app.database.models import ViralMaterial, Account, Job

db = SessionLocal()
materials = db.query(ViralMaterial).order_by(ViralMaterial.id.desc()).limit(10).all()
print("--- LATEST VIRAL MATERIALS ---")
for m in materials:
    print(f"ID:{m.id} | Account_ID:{m.scraped_by_account_id} | TargetPage:{m.target_page} | URL:{m.url}")

accounts = db.query(Account).filter(Account.is_active == True).all()
print("\n--- ACTIVE ACCOUNTS ---")
for a in accounts:
    print(f"ID:{a.id} | Name:{a.name} | CompetitorURLs:{a.competitor_urls}")
