"""caption AI luu tren material READY: 4 cot ai_caption* (ADR-021)

AI viet caption hien gan vao `Job`, ma job chi sinh khi co tai khoan Facebook. 0 tai khoan
=> material dung o READY => khong bao gio co caption. ADR-021 chuyen cho luu caption ve
thang `viral_materials`, doc lap voi job:

  - ai_caption        TEXT     caption AI vua viet
  - ai_hashtags       TEXT     JSON list hashtag (doc qua `ViralMaterial.ai_hashtags_list`)
  - ai_caption_at     INTEGER  epoch giay — lan chay AI gan nhat, ghi CA khi that bai
  - ai_caption_error  TEXT     ly do lan chay gan nhat that bai; NULL = lan cuoi OK

Ca 4 deu nullable => khong dong dai lieu cu, khong can backfill.

Revision ID: m1b8c9d0e1f2
Revises: l0a7b8c9d0e1
Create Date: 2026-09-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m1b8c9d0e1f2"
down_revision: Union[str, None] = "l0a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("viral_materials", sa.Column("ai_caption", sa.Text(), nullable=True))
    op.add_column("viral_materials", sa.Column("ai_hashtags", sa.Text(), nullable=True))
    op.add_column("viral_materials", sa.Column("ai_caption_at", sa.Integer(), nullable=True))
    op.add_column("viral_materials", sa.Column("ai_caption_error", sa.Text(), nullable=True))


def downgrade() -> None:
    """Mat toan bo caption AI da viet (chi co o 4 cot nay, khong cho nao khac giu ban sao)."""
    op.drop_column("viral_materials", "ai_caption_error")
    op.drop_column("viral_materials", "ai_caption_at")
    op.drop_column("viral_materials", "ai_hashtags")
    op.drop_column("viral_materials", "ai_caption")
