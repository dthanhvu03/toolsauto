import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("xe_tet.server.app:app", host=os.getenv("XE_TET_HOST", "127.0.0.1"),
                port=int(os.getenv("XE_TET_PORT", "8810")), log_level="info",
                access_log=False)  # log truy cập ghi cả ?token=… → tắt; lỗi vẫn ghi
