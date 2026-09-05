"""partial unique index: 1 job RUNNING moi (account_id, platform)

ADR-011 / AUDIT-001 P0-1B. Bat bien nay truoc gio chi duoc canh bang `NOT EXISTS
... status='RUNNING'` trong cau claim, ma dieu kien do doc theo snapshot: hai worker
chay dong thoi deu thay account "ranh" roi cung claim hai job khac nhau cua cung mot
(account, platform). Ban va outer predicate cua P0-1A KHONG che duoc truong hop nay
vi hai worker cham hai dong khac nhau nen khong he co xung dot khoa.

Index bat buoc bat bien o tang DB, la noi duy nhat thay duoc moi transaction.
`claim_next_job` bat IntegrityError va tra None; worker thu lai o nhip sau.

Truy van live 2026-08-21 va 2026-09-04 deu cho 0 job RUNNING va khong cap
(account_id, platform) nao >1 RUNNING, nen index tao duoc ngay, khong can don du lieu.

Revision ID: j8e5f6a7b8c9
Revises: i7d4e5f6a7b8
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j8e5f6a7b8c9"
down_revision: Union[str, None] = "i7d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_jobs_one_running_per_account_platform"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "jobs",
        ["account_id", "platform"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="jobs")
