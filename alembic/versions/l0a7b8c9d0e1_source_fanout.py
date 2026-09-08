"""mot nguon -> nhieu Page: target_pages + 2 unique index theo target_page (ADR-020)

Truoc ADR-020, 1 video chi len duoc 1 Page vi hai UNIQUE partial index tren `jobs`
(`idx_jobs_viral_material_active`, `idx_jobs_platform_content_hash_active`) khong co
`target_page` trong khoa. Migration nay:

  1. them `viral_sources.target_pages` + `viral_materials.target_pages` (TEXT, JSON list);
  2. dung lai hai index do voi `COALESCE(target_page, '')` trong khoa.

`COALESCE` la bat buoc: Postgres coi NULL khac nhau, khong co no thi moi job
`target_page IS NULL` deu lot qua unique. Menh de WHERE giu nguyen danh sach status cu
(doc bang `SELECT indexdef FROM pg_indexes WHERE tablename='jobs'` truoc khi viet).

Revision ID: l0a7b8c9d0e1
Revises: k9f6a7b8c9d0
Create Date: 2026-09-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "l0a7b8c9d0e1"
down_revision: Union[str, None] = "k9f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Giong `_BLOCKING` trong f4a1b2c3d4e5 va `BLOCKING_JOB_STATUSES` trong content_hash.py
_BLOCKING = (
    "PENDING",
    "RUNNING",
    "DONE",
    "DRAFT",
    "AI_PROCESSING",
    "AWAITING_STYLE",
)
_STATUS_IN = ", ".join(f"'{s}'" for s in _BLOCKING)


def upgrade() -> None:
    op.add_column("viral_sources", sa.Column("target_pages", sa.Text(), nullable=True))
    op.add_column("viral_materials", sa.Column("target_pages", sa.Text(), nullable=True))

    op.execute("DROP INDEX IF EXISTS idx_jobs_viral_material_active")
    op.execute("DROP INDEX IF EXISTS idx_jobs_platform_content_hash_active")
    op.execute(
        f"""
        CREATE UNIQUE INDEX idx_jobs_viral_material_active
        ON jobs (viral_material_id, COALESCE(target_page, ''))
        WHERE viral_material_id IS NOT NULL
          AND status IN ({_STATUS_IN})
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX idx_jobs_platform_content_hash_active
        ON jobs (platform, content_hash, COALESCE(target_page, ''))
        WHERE content_hash IS NOT NULL
          AND status IN ({_STATUS_IN})
        """
    )


def downgrade() -> None:
    """
    CANH BAO: index cu khong co `target_page` trong khoa. Neu da fan-out (1 material ->
    nhieu job khac Page) thi phai XOA BOT job trung truoc, neu khong CREATE UNIQUE INDEX
    se loi `could not create unique index ... Key ... is duplicated`. Cau kiem tra:

        SELECT viral_material_id, COUNT(*) FROM jobs
        WHERE viral_material_id IS NOT NULL
          AND status IN ('PENDING','RUNNING','DONE','DRAFT','AI_PROCESSING','AWAITING_STYLE')
        GROUP BY 1 HAVING COUNT(*) > 1;
    """
    op.execute("DROP INDEX IF EXISTS idx_jobs_viral_material_active")
    op.execute("DROP INDEX IF EXISTS idx_jobs_platform_content_hash_active")
    op.execute(
        f"""
        CREATE UNIQUE INDEX idx_jobs_platform_content_hash_active
        ON jobs (platform, content_hash)
        WHERE content_hash IS NOT NULL
          AND status IN ({_STATUS_IN})
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX idx_jobs_viral_material_active
        ON jobs (viral_material_id)
        WHERE viral_material_id IS NOT NULL
          AND status IN ({_STATUS_IN})
        """
    )
    op.drop_column("viral_materials", "target_pages")
    op.drop_column("viral_sources", "target_pages")
