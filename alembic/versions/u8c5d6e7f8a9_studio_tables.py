"""ADR-061 — bảng Studio: assets, analysis, templates, channels, projects, tasks.

Chỉ thêm bảng mới, không đụng bảng cũ.

Revision ID: u8c5d6e7f8a9
Revises: t7b4c5d6e7f8
"""
from alembic import op
import sqlalchemy as sa

revision = "u8c5d6e7f8a9"
down_revision = "t7b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("credit", sa.String(255), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("has_audio", sa.Boolean(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True, unique=True),
        sa.Column("viral_material_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_studio_assets_viral_material_id", "studio_assets", ["viral_material_id"])

    op.create_table(
        "studio_analysis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("studio_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("asset_id", "kind", name="uq_studio_analysis_asset_kind"),
    )

    op.create_table(
        "studio_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )

    op.create_table(
        "studio_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buffer_channel_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("studio_templates.id"), nullable=True),
        sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("show_credit", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("slot_hours", sa.JSON(), nullable=True),
        sa.Column("intro_asset_id", sa.Integer(), sa.ForeignKey("studio_assets.id"), nullable=True),
        sa.Column("outro_asset_id", sa.Integer(), sa.ForeignKey("studio_assets.id"), nullable=True),
        sa.Column("logo_asset_id", sa.Integer(), sa.ForeignKey("studio_assets.id"), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("take_reup", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )

    op.create_table(
        "studio_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("studio_channels.id"), nullable=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("studio_templates.id"), nullable=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("studio_assets.id"), nullable=True),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", sa.JSON(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.Column("rendered_at", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.Integer(), nullable=True),
        sa.Column("viral_material_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_studio_projects_status", "studio_projects", ["status"])
    op.create_index("ix_studio_projects_viral_material_id", "studio_projects", ["viral_material_id"])

    op.create_table(
        "studio_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("flow", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("lane", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("studio_assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(64), nullable=True),
        sa.Column("claimed_at", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.Integer(), nullable=True),
    )
    op.create_index("ix_studio_tasks_claim", "studio_tasks", ["status", "lane", "run_after"])
    op.create_index("ix_studio_tasks_parent_id", "studio_tasks", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_studio_tasks_parent_id", table_name="studio_tasks")
    op.drop_index("ix_studio_tasks_claim", table_name="studio_tasks")
    op.drop_table("studio_tasks")
    op.drop_index("ix_studio_projects_viral_material_id", table_name="studio_projects")
    op.drop_index("ix_studio_projects_status", table_name="studio_projects")
    op.drop_table("studio_projects")
    op.drop_table("studio_channels")
    op.drop_table("studio_templates")
    op.drop_table("studio_analysis")
    op.drop_index("ix_studio_assets_viral_material_id", table_name="studio_assets")
    op.drop_table("studio_assets")
