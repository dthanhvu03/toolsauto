// ecosystem.config.js — PM2 process definitions
// All paths are dynamic via __dirname (no hardcoded absolute paths)
const path = require("path");
const PROJECT_ROOT = __dirname;
const VENV_PYTHON = path.join(PROJECT_ROOT, "venv/bin/python");

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
  ],
};
