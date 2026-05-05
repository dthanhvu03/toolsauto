from app.core.database.core import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("UPDATE platform_configs SET adapter_class='app.features.facebook.adapter.FacebookAdapter' WHERE platform='facebook'"))
db.commit()
print("Updated platform_configs in database")
