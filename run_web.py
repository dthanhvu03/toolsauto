import uvicorn
from app.config import WORKER_TICK_SECONDS
from app.database.core import engine, Base

def start():
    # Only for dev, alembic should handle pro
    Base.metadata.create_all(bind=engine)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    start()
