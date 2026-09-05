// ecosystem.config.js — PM2 process definitions
// All paths are dynamic via __dirname (no hardcoded absolute paths)
const path = require("path");
const childProcess = require("child_process");

const PROJECT_ROOT = path.resolve(__dirname);
const VENV_PYTHON = path.join(PROJECT_ROOT, "venv/bin/python");

let routerPath = "";
try {
  routerPath = childProcess.execSync("which 9router").toString().trim();
} catch (err) {
  // If which fails (e.g., local environment without 9router yet), use a fallback or keep it empty
  routerPath = "9router"; 
}

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
      script: routerPath,
      interpreter: "node",
      cwd: PROJECT_ROOT,
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
  ],
};
