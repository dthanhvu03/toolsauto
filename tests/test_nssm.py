import time
import sys
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [NSSM_MOCK] - %(message)s")

def run():
    logging.info("🔥 Worker Mock bắt đầu chạy (PID: %s)", os.getpid())
    logging.info("Đang xử lý job... (mô phỏng 5 giây rớt)")
    time.sleep(5)
    logging.error("💀 FATAL ERROR: Worker Crash Mô Phỏng! Tự động kill process.")
    sys.exit(1)

if __name__ == "__main__":
    run()
