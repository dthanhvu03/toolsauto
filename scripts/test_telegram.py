"""
Test script to verify Telegram connection via NotifierService.
"""
import sys
import os
import asyncio
from dotenv import load_dotenv

# Ensure we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables
load_dotenv()

from app.services.notifier import NotifierService
import app.config as config

def main():
    print("Testing Telegram Connection...")
    
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID
    
    if not token or not chat_id:
        print("❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing from app.config.")
        return

    print(f"Bot Token: {token[:10]}... (len: {len(token)})")
    print(f"Chat ID: {chat_id}")
    
    # NotifierService uses TelegramClient internally which operates synchronously or using asyncio loop
    try:
        # A simple broadcast message
        test_message = "🤖 *Ping!* Test kết nối Telegram từ hệ thống Auto Publisher thành công! ✅"
        print("Sending test message...")
        
        # We need to initialize the channels if they aren't manually.
        # However, NotifierService auto-registers Telegram if env vars are present during import in some apps.
        # Let's explicitly register it just to be safe if it's not already.
        from app.services.notifier import TelegramNotifier
        
        # Check if already registered (the module might do it globally)
        if hasattr(NotifierService, '_channels') and not NotifierService._channels:
            print("Manually registering TelegramNotifier...")
            telegram_notifier = TelegramNotifier(token, chat_id)
            NotifierService.register(telegram_notifier)
            
        NotifierService._broadcast(test_message)
        
        print("✅ Message broadcast attempted. Please check your Telegram chat.")
        
    except Exception as e:
        print(f"❌ Failed to send message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
