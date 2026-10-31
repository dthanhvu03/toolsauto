import sys
from cashback_bot.admin.notify import admin_notify as _impl

sys.modules[__name__] = _impl
