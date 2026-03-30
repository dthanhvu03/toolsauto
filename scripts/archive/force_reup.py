import logging
from app.database.core import SessionLocal
import workers.maintenance as m
logging.basicConfig(level=logging.INFO)
with SessionLocal() as db:
    m._process_viral_materials(db)
