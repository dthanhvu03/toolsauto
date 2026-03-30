import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.core import SessionLocal
from app.database.models import Account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_garbage(name, url=""):
    name_lower = name.lower()
    url_lower = url.lower()
    if "chưa đọc" in name_lower or "unread" in name_lower:
        return True
    if "bạn đang hoàn thành" in name_lower or "tin nhắn" in name_lower:
        return True
    if "video ngắn" in name_lower or "bình luận" in name_lower:
        return True
    if len(name) > 60:
        return True
    if any(x in url_lower for x in ["/videos/", "/posts/", "/reel/", "/photo/", "/groups/"]):
        return True
    return False

def fix_accounts():
    with SessionLocal() as db:
        accounts = db.query(Account).all()
        fixed = 0
        for acc in accounts:
            changed = False
            
            # Fix managed pages
            if acc.managed_pages:
                try:
                    pages = json.loads(acc.managed_pages)
                except:
                    pages = []
                
                good_pages = [p for p in pages if not is_garbage(p.get("name", ""), p.get("url", ""))]
                if len(good_pages) != len(pages):
                    logger.info(f"Account {acc.id}: Removed {len(pages) - len(good_pages)} garbage pages")
                    acc.managed_pages_list = good_pages
                    changed = True

            # Fix target pages
            if acc.target_pages:
                try:
                    targets = json.loads(acc.target_pages)
                except:
                    targets = []
                
                # Check if targets have garbage urls
                good_targets = [t for t in targets if not is_garbage("", t)]
                if len(good_targets) != len(targets):
                    acc.target_pages_list = good_targets
                    changed = True

            # Fix page_niches map
            if acc.page_niches:
                try:
                    niches_map = json.loads(acc.page_niches)
                except:
                    niches_map = {}
                
                if isinstance(niches_map, dict):
                    good_niches_map = {k: v for k, v in niches_map.items() if not is_garbage("", k)}
                    if len(good_niches_map) != len(niches_map):
                        acc.page_niches_map = good_niches_map
                        changed = True

            if changed:
                db.commit()
                fixed += 1
                
        logger.info(f"Fixed {fixed} accounts.")

if __name__ == "__main__":
    fix_accounts()
