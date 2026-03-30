import sys
from app.database.core import SessionLocal
from app.database.models import Account

db = SessionLocal()
acc = db.query(Account).filter(Account.id == 3).first()
print(f"Managed Pages for {acc.name}:")
for p in acc.managed_pages_list:
    print(p)
