import os
import sys

sys.path.insert(0, os.path.abspath('.'))

from app.database.core import SessionLocal
from app.database.models import Account
from app.services.account import AccountService

def test():
    db = SessionLocal()
    account = db.query(Account).first()
    
    if not account:
        print("No account found")
        return
        
    print(f"Testing account: {account.name}")
    
    # Set sleep time to surround current time
    # e.g. "00:00" to "23:59"
    AccountService.update_limits(
        db, account.id, account.daily_limit, account.cooldown_seconds,
        sleep_start_time="00:00", sleep_end_time="23:59"
    )
    
    db.refresh(account)
    print(f"Sleep set to: {account.sleep_start_time} - {account.sleep_end_time}")
    print(f"Is sleeping right now? {account.is_sleeping}")
    
    # 2nd test: Not sleeping
    # Current time is 09:xx UTC. (Server time might be different if container sets TZ, but datetime.now() matches container)
    import datetime
    now_hour = datetime.datetime.now().hour
    
    awake_start = f"{(now_hour + 2) % 24:02d}:00"
    awake_end = f"{(now_hour + 4) % 24:02d}:00"
    
    AccountService.update_limits(
        db, account.id, account.daily_limit, account.cooldown_seconds,
        sleep_start_time=awake_start, sleep_end_time=awake_end
    )
    
    db.refresh(account)
    print(f"Sleep set to (Future): {account.sleep_start_time} - {account.sleep_end_time}")
    print(f"Is sleeping right now? {account.is_sleeping}")
    
    db.close()

if __name__ == "__main__":
    test()
