import sys
from app.core.database.core import SessionLocal
from app.core.database.models import Account

db = SessionLocal()
acc = db.query(Account).filter(Account.id == 3).first()
print(f"Managed Pages for {acc.name}:")
for p in acc.managed_pages_list:
    print(p)
