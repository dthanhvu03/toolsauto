import sys
from cashback_bot.admin.notify import customer_notify as _impl

sys.modules[__name__] = _impl
