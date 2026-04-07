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

from sqlalchemy import event

@event.listens_for(engine, "connect")
def pragma_on_connect(dbapi_con, con_record):
    cursor = dbapi_con.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
