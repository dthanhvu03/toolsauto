"""chong trung noi dung o tang material: content_hash + phash (ADR-024)

Truoc ADR-024 tool chi chan trung o hai tang: URL (unique) va job (sha256 + unique index).
Cung mot video xuat hien o hai kenh nguon => hai material, tai hai lan, chay ffmpeg hai lan.

  - content_hash  VARCHAR  sha256 file NGUON vua tai (co index — do sanh truoc, re va chac chan)
  - phash         TEXT     JSON {"1.23s": "hex", ...} pHash 5 khung (doc qua `ViralMaterial.phash_map`)

Ca hai deu nullable => khong dong dai lieu cu, khong can backfill; material cu (content_hash
NULL) chi don gian khong tham gia so trung.

Revision ID: n2c9d0e1f2a3
Revises: m1b8c9d0e1f2
Create Date: 2026-09-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "n2c9d0e1f2a3"
down_revision: Union[str, None] = "m1b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("content_hash", sa.String(), nullable=True))
    op.add_column("viral_materials", sa.Column("phash", sa.Text(), nullable=True))
    op.create_index(
        "ix_viral_materials_content_hash", "viral_materials", ["content_hash"], unique=False
    )


def downgrade() -> None:
    """Mat toan bo dau van tay noi dung — chi co o 2 cot nay, phai tinh lai bang cach tai lai video."""
    op.drop_index("ix_viral_materials_content_hash", table_name="viral_materials")
    op.drop_column("viral_materials", "phash")
    op.drop_column("viral_materials", "content_hash")
