// ecosystem.config.js — PM2 process definitions
// All paths are dynamic via __dirname (no hardcoded absolute paths)
const path = require("path");
const childProcess = require("child_process");
const fs = require("fs");

const PROJECT_ROOT = path.resolve(__dirname);
const VENV_PYTHON = path.join(PROJECT_ROOT, "venv/bin/python");

let routerPath = "";
try {
  routerPath = childProcess.execSync("which 9router").toString().trim();
} catch (err) {
  // If which fails (e.g., local environment without 9router yet), use a fallback or keep it empty
  routerPath = "9router";
}

// 9Router v0.5: chạy thẳng server Next.js (bộ khởi động `9router` có menu + system tray, dưới PM2/WSL
// server con tự chết). Cần Node ≥ 20 (global File) → Node riêng /opt/node22, Node hệ thống (18) giữ nguyên.
// Cài riêng ở /opt/9router (npm của Node 22): bản global /usr/local/lib/node_modules kéo theo better-sqlite3
// build cho Node 18 hệ thống (libnode.so.109) → mở /dashboard là SIGSEGV.
const ROUTER_OPT = "/opt/9router/node_modules/9router";
const ROUTER_PKG = fs.existsSync(ROUTER_OPT)
  ? ROUTER_OPT
  : fs.existsSync(routerPath) ? path.dirname(fs.realpathSync(routerPath)) : "";
const ROUTER_APP = path.join(ROUTER_PKG, "app");
// server.js (không dùng custom-server.js: bản 0.5.112 trên Node 22/WSL bị SIGSEGV vài giây sau khi chạy)
const ROUTER_SERVER = path.join(ROUTER_APP, "server.js");
const ROUTER_NODE = fs.existsSync("/opt/node22/bin/node") ? "/opt/node22/bin/node" : "node";
const ROUTER_NODE_PATH = [
  path.join(process.env.HOME || "/root", ".9router/runtime/node_modules"),
  path.join(ROUTER_PKG, "node_modules"),
].join(path.delimiter);

module.exports = {
  apps: [
    {
      name: "FB_Publisher_1",
      script: "app/features/facebook/workers/publisher.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 600000,       // 10 minutes — allow in-flight Playwright job to finish

      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "2G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "FB_Publisher_2",
      script: "app/features/facebook/workers/publisher.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 600000,       // 10 minutes

      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "2G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "AI_Generator_1",
      script: "app/features/viral_intake/workers/ai_generator.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 300000,       // 5 minutes
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "AI_Generator_2",
      script: "app/features/viral_intake/workers/ai_generator.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 300000,       // 5 minutes
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "Maintenance",
      script: "app/features/system_panel/workers/maintenance.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,        // 1 minute
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      // CHI CHAY TREN VPS - may local khong dung PM2 (start.ps1 -Stack ->
      // local_supervisor.py). Lich backup o local dang ky bang Task Scheduler:
      //   scripts/register_backup_task.ps1
      // Backup Postgres hang ngay 03:00. autorestart:false + cron_restart => PM2
      // chi danh thuc dung gio roi de tien trinh thoat, khong chay lien tuc.
      // Truoc day khong co lich backup nao; lenh backup thu cong lai dump nham
      // file SQLite legacy nen thuc te he thong chua tung co ban luu nao dung.
      name: "DB_Backup",
      script: "manage.py",
      args: "db backup --keep 14",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      autorestart: false,
      cron_restart: "0 3 * * *",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "9Router_Gateway",
      script: ROUTER_SERVER,
      interpreter: ROUTER_NODE,
      node_args: "--dns-result-order=ipv4first",
      cwd: ROUTER_APP,
      env: { PORT: "20128", HOSTNAME: "0.0.0.0", NODE_PATH: ROUTER_NODE_PATH },
      max_restarts: 10,
      min_uptime: 5000,
      restart_delay: 3000,
      autorestart: true,
    },
    {
      name: "Web_Dashboard",
      script: "manage.py",
      args: "serve --no-reload",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 30000,        // 30 seconds
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 3000,
      autorestart: true,
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "Threads_AutoReply",
      script: "app/features/threads/workers/auto_reply.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      // PLAN-158: quét Threads theo từ khóa + tự reply kéo khách về bot (bật/tắt trên web: growth.enabled)
      name: "Threads_Growth",
      script: "app/features/threads/growth/worker.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 10000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "Threads_NewsWorker",
      script: "app/features/threads/workers/news_worker.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "Threads_Publisher",
      script: "app/features/threads/workers/publisher.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 600000,

      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    // ADR-061 Studio — chưa bật. Bật: pm2 start ecosystem.config.js --only Studio_Heavy,Studio_Light
    {
      name: "Studio_Heavy",
      script: "app/features/studio/worker.py",
      args: "--lanes heavy",         // analyze + render: ffmpeg / Whisper, 1 việc mỗi lần
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 900000,          // 15 phút — để render đang chạy xong
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "3G",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    {
      name: "Studio_Light",
      script: "app/features/studio/worker.py",
      args: "--lanes light",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "512M",
      env: { PYTHONUNBUFFERED: "1", PYTHONPATH: "." },
    },
    // Rút gọn s.shopee.vn qua CloakBrowser Windows (run_shopee_mcp.sh dọn chrome mồ côi khi PM2 restart).
    {
      name: "shopee-mcp",
      script: "run_shopee_mcp.sh",
      interpreter: "bash",
      cwd: PROJECT_ROOT,
      kill_timeout: 15000,
      max_restarts: 10,
      min_uptime: 10000,
      restart_delay: 5000,
      autorestart: true,
      env: {
        SHOPEE_DOMAIN: "shopee.vn",
        SHOPEE_PROFILE_DIR: "C:\\Users\\Admin\\.shopee-mcp\\chrome-profile",
        USERPROFILE: "C:\\Users\\Admin",
        HOMEDRIVE: "C:",
        HOMEPATH: "\\Users\\Admin",
      },
    },
    // PLAN-111 — giọng đọc VieNeu trên GPU cho bước dub. Venv riêng (torch CUDA); tắt thì dub tự về edge-tts.
    {
      name: "VieNeu_TTS",
      script: "app/features/studio/dub/vieneu_server.py",
      args: "--port 8790",
      interpreter: "/home/vu/venv-vieneu/bin/python",
      cwd: PROJECT_ROOT,
      kill_timeout: 10000,
      max_restarts: 5,
      min_uptime: 180000,            // nạp model mất 1–1,5 phút
      restart_delay: 30000,
      autorestart: true,
      max_memory_restart: "4G",
      // chỉ dùng model + code đã có trong cache HF — không tự tải bản mới (transformers trust_remote_code)
      env: { PYTHONUNBUFFERED: "1", HF_HUB_OFFLINE: "1", TRANSFORMERS_OFFLINE: "1" },
    },
  ],
};
