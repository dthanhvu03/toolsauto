from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={
        "check_same_thread": False,
        "timeout": 30.0  # Increased timeout for multiprocess concurrency
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_runtime_schema():
    """Apply lightweight SQLite schema fixes required by the current code."""
    if not DATABASE_URL.startswith("sqlite:///"):
        return

    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "viral_materials" not in tables:
            return

        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(viral_materials)")).fetchall()
        }
        if "last_error" not in columns:
            conn.execute(text("ALTER TABLE viral_materials ADD COLUMN last_error VARCHAR"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
