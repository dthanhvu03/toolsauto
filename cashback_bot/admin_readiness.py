import sys
from cashback_bot.admin.handlers import readiness as _impl

sys.modules[__name__] = _impl
