from app.database.database import SessionLocal
from app.database.models import Job

db = SessionLocal()
job = Job(
    command="/reup",
    post_text="https://vt.tiktok.com/ZSuByd8BC/",
    target_account="Nguyen Ngoc Vi",
    status="PENDING"
)
db.add(job)
db.commit()
print(f"Inserted Job ID: {job.id}")
