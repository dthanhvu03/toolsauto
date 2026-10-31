import sys
from cashback_bot.admin.handlers import stats as _impl

sys.modules[__name__] = _impl
