import threading
import logging
import time
import os
from app.services.telegram_command_handler import TelegramCommandHandler
from app.services.telegram_event_router import TelegramEventRouter

logger = logging.getLogger(__name__)

class TelegramPoller:
    LOCK_FILE = "/tmp/telegram_poller.lock"

    def __init__(self, bot_token: str, chat_id: str, poll_timeout: int = 30):
        from app.services.telegram_client import TelegramClient
        self.client = TelegramClient(bot_token, chat_id)
        self.authorized_chat_id = str(chat_id)
        self.poll_timeout = poll_timeout
        self._offset = 0
        self._running = False
        
        self.command_handler = TelegramCommandHandler(self.client)
        self.event_router = TelegramEventRouter(self.client, self.command_handler)

    def start(self):
        import fcntl
        self._running = True
        threading.Thread(target=self._poll_loop, daemon=True).start()
        logger.info("TelegramPoller started")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        while self._running:
            try:
                updates = self.client.get_updates(offset=self._offset, timeout=self.poll_timeout)
                if updates:
                    for u in updates:
                        self._process_update(u)
                        self._offset = u["update_id"] + 1
            except Exception as e:
                logger.error(f"Poller error: {e}")
                time.sleep(5)

    def _process_update(self, update: dict):
        if "message" in update:
            if str(update["message"].get("chat", {}).get("id")) != self.authorized_chat_id:
                return
        self.event_router.dispatch(update)
