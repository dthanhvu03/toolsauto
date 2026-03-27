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
        # Runtime settings tables (used by workers too; create if missing)
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS runtime_settings (
                  id INTEGER PRIMARY KEY,
                  key VARCHAR NOT NULL UNIQUE,
                  value VARCHAR,
                  type VARCHAR NOT NULL,
                  updated_at INTEGER,
                  updated_by VARCHAR
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS runtime_settings_audit (
                  id INTEGER PRIMARY KEY,
                  ts INTEGER,
                  key VARCHAR NOT NULL,
                  old_value VARCHAR,
                  new_value VARCHAR,
                  action VARCHAR NOT NULL,
                  updated_by VARCHAR
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runtime_settings_key ON runtime_settings(key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runtime_settings_audit_key ON runtime_settings_audit(key)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_runtime_settings_audit_ts ON runtime_settings_audit(ts)"))

        # Page Insights table
        if "page_insights" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS page_insights (
                      id INTEGER PRIMARY KEY,
                      account_id INTEGER,
                      page_url VARCHAR NOT NULL,
                      page_name VARCHAR,
                      post_url VARCHAR NOT NULL,
                      caption VARCHAR,
                      published_date VARCHAR,
                      views INTEGER DEFAULT 0,
                      likes INTEGER DEFAULT 0,
                      comments INTEGER DEFAULT 0,
                      shares INTEGER DEFAULT 0,
                      recorded_at INTEGER,
                      FOREIGN KEY(account_id) REFERENCES accounts(id)
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_page_insights_account ON page_insights(account_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_page_insights_page_url ON page_insights(page_url)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_page_insights_post_url ON page_insights(post_url)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_page_insights_recorded ON page_insights(recorded_at)"))

        if "viral_materials" not in tables:
            # Nothing else to patch in fresh DB
            return

        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(viral_materials)")).fetchall()
        }
        if "last_error" not in columns:
            conn.execute(text("ALTER TABLE viral_materials ADD COLUMN last_error VARCHAR"))

        # system_state.viral_min_views (ngưỡng view quét TikTok)
        if "system_state" in tables:
            ss_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(system_state)")).fetchall()
            }
            if "viral_min_views" not in ss_cols:
                conn.execute(text("ALTER TABLE system_state ADD COLUMN viral_min_views INTEGER"))
            if "viral_max_videos_per_channel" not in ss_cols:
                conn.execute(text("ALTER TABLE system_state ADD COLUMN viral_max_videos_per_channel INTEGER"))

        # Page Insights platform column
        if "page_insights" in tables:
            pi_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(page_insights)")).fetchall()
            }
            if "platform" not in pi_cols:
                conn.execute(text("ALTER TABLE page_insights ADD COLUMN platform VARCHAR DEFAULT 'facebook'"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_page_insights_platform ON page_insights(platform)"))

        # Jobs V4: Visible Intelligence
        if "jobs" in tables:
            j_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
            }
            if "brain_used" not in j_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN brain_used VARCHAR"))
            if "ai_reasoning" not in j_cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_reasoning TEXT"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
