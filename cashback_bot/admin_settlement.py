import sys
from cashback_bot.admin.handlers import settlement as _impl

sys.modules[__name__] = _impl
