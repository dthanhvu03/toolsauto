import re

with open('app/adapters/facebook/adapter.py', 'r') as f:
    content = f.read()

# 1. Add _safe_goto after _ensure_authenticated_context
safe_goto_func = '''
    def _safe_goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 60000, retries: int = 3) -> bool:
        if not self.page: return False
        for attempt in range(retries):
            try:
                self.logger.info("FacebookAdapter: Navigating to %s (Attempt %d/%d)...", url, attempt + 1, retries)
                self.page.goto(url, wait_until=wait_until, timeout=timeout)
                return True
            except Exception as e:
                self.logger.warning("FacebookAdapter: Navigation to %s failed on attempt %d: %s", url, attempt + 1, e)
                if attempt < retries - 1:
                    self.logger.info("FacebookAdapter: Waiting 5s before retry...")
                    try:
                        self.page.wait_for_timeout(5000)
                    except Exception:
                        pass
                else:
                    raise e
        return False
'''

if '_safe_goto' not in content:
    # insert before _ensure_authenticated_context
    content = content.replace('    def _ensure_authenticated_context(self) -> bool:', safe_goto_func + '\n    def _ensure_authenticated_context(self) -> bool:')

# 2. Replace self.page.goto with self._safe_goto EXCEPT inside _safe_goto itself
# First replace all
content = content.replace('self.page.goto(', 'self._safe_goto(')
# Then fix the one inside _safe_goto
content = content.replace('self._safe_goto(url, wait_until=wait_until, timeout=timeout)', 'self.page.goto(url, wait_until=wait_until, timeout=timeout)')

with open('app/adapters/facebook/adapter.py', 'w') as f:
    f.write(content)

print('Patched successfully!')
