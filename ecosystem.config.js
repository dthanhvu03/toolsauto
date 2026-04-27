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
      script: "workers/publisher.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 600000,       // 10 minutes — allow in-flight Playwright job to finish
      listen_timeout: 10000,      // 10s to start
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "2G",
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "FB_Publisher_2",
      script: "workers/publisher.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 600000,       // 10 minutes
      listen_timeout: 10000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "2G",
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "AI_Generator_1",
      script: "workers/ai_generator.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 300000,       // 5 minutes
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "AI_Generator_2",
      script: "workers/ai_generator.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 300000,       // 5 minutes
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "Maintenance",
      script: "workers/maintenance.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,        // 1 minute
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      env: { PYTHONUNBUFFERED: "1" },
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
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "Threads_AutoReply",
      script: "workers/threads_auto_reply.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "Threads_NewsWorker",
      script: "workers/threads_news_worker.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 60000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "Threads_Publisher",
      script: "workers/threads_publisher.py",
      interpreter: VENV_PYTHON,
      cwd: PROJECT_ROOT,
      kill_timeout: 600000,
      listen_timeout: 10000,
      max_restarts: 10,
      min_uptime: 30000,
      restart_delay: 5000,
      autorestart: true,
      max_memory_restart: "1G",
      env: { PYTHONUNBUFFERED: "1" },
    },
  ],
};
