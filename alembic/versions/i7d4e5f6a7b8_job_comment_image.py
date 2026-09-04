"""jobs.comment_image_path

PLAN-055: ảnh đính kèm vào comment tự động (link aff + ảnh + tiêu đề dạng link nhóm).
Cột nullable nên job cũ không đổi hành vi.

Revision ID: i7d4e5f6a7b8
Revises: h6c3d4e5f6a7
Create Date: 2026-08-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i7d4e5f6a7b8"
down_revision: Union[str, None] = "h6c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("comment_image_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "comment_image_path")
