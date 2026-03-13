import sys, os, time
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.abspath('.'))

import logging
logging.basicConfig(level=logging.INFO)

from app.adapters.facebook.adapter import FacebookAdapter
from app.adapters.facebook.engagement import FacebookEngagementTask

def run_test():
    account_profile = '/home/vu/toolsauto/content/profiles/facebook_4'
    print(f'Testing engagement on profile: {account_profile}')

    adapter = FacebookAdapter()
    if adapter.open_session(account_profile):
        task = FacebookEngagementTask(adapter.page)
        print('Running watch_reels test for 45 seconds to fetch niche videos...')
        
        # Override to force watch Reels via keyword
        task._action_watch_reels(45, 'thời trang')
        
        print('\n=========================================')
        print('[RESULT URLs EXTRACTED]:', list(task.interacted_urls))
        print('=========================================')
        adapter.close_session()
    else:
        print('Failed to open session')

if __name__ == '__main__':
    run_test()
