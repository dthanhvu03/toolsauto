import sys
from cashback_bot.admin.handlers import deals as _impl

sys.modules[__name__] = _impl
