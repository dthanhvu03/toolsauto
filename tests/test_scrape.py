import sys
import os
import logging
from app.core.database.core import SessionLocal
from scripts.scrape_insights import scrape_insights_for_page
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)

with SessionLocal() as db:
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir="/home/vu/toolsauto/data/Hoang Khoa",
            headless=True,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled", "--no-first-run", "--disable-infobars"]
        )
        page = context.new_page()
        scrape_insights_for_page(page, db, 3, "https://www.facebook.com/kids0810", platform="facebook")
        context.close()
