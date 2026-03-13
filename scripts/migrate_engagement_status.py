#!/usr/bin/env python3
"""
Migration: Add engagement_status and engagement_detail columns to system_state table.
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "auto_publisher.db"

if not DB_PATH.exists():
    print(f"[ERROR] Database not found at {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Check existing columns
cursor.execute("PRAGMA table_info(system_state)")
existing = {row[1] for row in cursor.fetchall()}

added = []
for col in ["engagement_status", "engagement_detail"]:
    if col not in existing:
        cursor.execute(f"ALTER TABLE system_state ADD COLUMN {col} TEXT")
        added.append(col)
        print(f"[OK] Added column '{col}'")
    else:
        print(f"[SKIP] Column '{col}' already exists")

conn.commit()
conn.close()

if added:
    print(f"[OK] Migration complete: {len(added)} column(s) added.")
else:
    print("[OK] No changes needed.")
