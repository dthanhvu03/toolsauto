"""SQLAlchemy ORM models — re-exported here for backward compatibility.

Historical layout had a single `app/database/models.py` file. After the
TASK-022 split, models live in domain submodules. Every previous import path
of the form `from app.database.models import X` continues to work because
each class is re-exported below.

When adding a new model:
1. Create the class in the domain file (or a new domain file).
2. Add it to the import block AND `__all__` below.
"""

from app.database.models.base import Base, now_ts

# Domain models — order chosen for human readability, not import dependency.
# SQLAlchemy resolves cross-table relationships via string names, so import
# order does not matter for ORM correctness.
from app.database.models.accounts import Account
from app.database.models.jobs import Job, JobEvent
from app.database.models.viral import (
    AffiliateLink,
    CompetitorReel,
    DiscoveredChannel,
    PageInsight,
    ViralMaterial,
)
from app.database.models.incidents import IncidentGroup, IncidentLog
from app.database.models.threads import NewsArticle, ThreadsInteraction
from app.database.models.settings import (
    AuditLog,
    CtaTemplate,
    PlatformConfig,
    PlatformSelector,
    RuntimeSetting,
    RuntimeSettingAudit,
    SystemState,
    WorkflowDefinition,
)
from app.database.models.compliance import (
    ComplianceAllowlist,
    ComplianceRegexRule,
    KeywordBlacklist,
    ViolationLog,
)

__all__ = [
    "Base",
    "now_ts",
    # accounts
    "Account",
    # jobs
    "Job",
    "JobEvent",
    # viral / discovery / affiliate / insights
    "ViralMaterial",
    "DiscoveredChannel",
    "CompetitorReel",
    "PageInsight",
    "AffiliateLink",
    # incidents
    "IncidentLog",
    "IncidentGroup",
    # threads
    "NewsArticle",
    "ThreadsInteraction",
    # settings / system / audit / platform
    "SystemState",
    "RuntimeSetting",
    "RuntimeSettingAudit",
    "AuditLog",
    "PlatformConfig",
    "WorkflowDefinition",
    "PlatformSelector",
    "CtaTemplate",
    # compliance
    "KeywordBlacklist",
    "ComplianceAllowlist",
    "ComplianceRegexRule",
    "ViolationLog",
]
