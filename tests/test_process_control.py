"""
PLAN-115 — bảng tiến trình PM2 trên web: đọc trạng thái, bật / tắt / khởi động lại đúng app trong danh sách.
``pm2`` giả (jlist cố định), lệnh bật / tắt chỉ ghi lại — không đụng PM2 thật.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import process_control as pc
from app.core.pm2_apps import APP_INFO, PM2_SAFE_NAMES
from app.platform.admin_api.processes import router

NOW = 1_800_000_000
JLIST = [
    {"name": "Web_Dashboard", "pid": 11, "monit": {"cpu": 2.5, "memory": 170 * 1048576},
     "pm2_env": {"status": "online", "pm_uptime": (NOW - 60) * 1000, "restart_time": 3}},
    {"name": "VieNeu_TTS", "pid": 12, "monit": {"cpu": 0.1, "memory": 1375 * 1048576},
     "pm2_env": {"status": "online", "pm_uptime": (NOW - 3600) * 1000, "restart_time": 0}},
    {"name": "DB_Backup", "pid": 0, "monit": {"cpu": 0, "memory": 0}, "pm2_env": {"status": "stopped", "restart_time": 0}},
    {"name": "la_lam", "pid": 13, "monit": {"cpu": 0, "memory": 10 * 1048576}, "pm2_env": {"status": "online"}},
]


@pytest.fixture
def pm2(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(pc.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "pm2" else None)
    monkeypatch.setattr(pc, "_pm2", lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(JLIST), ""))
    monkeypatch.setattr(pc, "_spawn", sent.append)
    return sent


def test_ecosystem_va_danh_sach_dieu_khien_khop():
    names = set(re.findall(r'name:\s*"([^"]+)"', Path("ecosystem.config.js").read_text(encoding="utf-8")))
    assert {"Studio_Heavy", "Studio_Light", "VieNeu_TTS", "DB_Backup"} <= names
    assert names <= PM2_SAFE_NAMES, names - PM2_SAFE_NAMES
    assert set(APP_INFO) <= names


def test_snapshot_dung_so_va_quyen_bat_tat(pm2):
    s = pc.snapshot(now=NOW)
    assert s["error"] is None and s["machine"]["mem_total_mb"] > 0
    apps = {a["name"]: a for a in s["apps"]}
    assert [a["name"] for a in s["apps"]][:2] == ["VieNeu_TTS", "Web_Dashboard"]  # đang chạy, RAM lớn trước
    vn = apps["VieNeu_TTS"]
    assert (vn["mem_mb"], vn["uptime_s"], vn["label"]) == (1375, 3600, "Giọng đọc VieNeu (GPU)")
    assert (vn["can_start"], vn["can_stop"], vn["can_restart"]) == (False, True, True)
    web = apps["Web_Dashboard"]
    assert (web["can_stop"], web["can_restart"], web["restarts"]) == (False, True, 3)  # không tự tắt mình
    backup = apps["DB_Backup"]
    assert (backup["can_start"], backup["can_stop"], backup["uptime_s"]) == (True, False, None)
    other = apps["la_lam"]
    assert not (other["can_start"] or other["can_stop"] or other["can_restart"])  # app ngoài danh sách: chỉ xem


def test_pm2_hong_van_tra_phan_may(monkeypatch):
    monkeypatch.setattr(pc.shutil, "which", lambda name: None)
    s = pc.snapshot(now=NOW)
    assert s["apps"] == [] and "pm2" in s["error"] and s["machine"]["cpus"] > 0


def test_act_gui_lenh_tach_khoi_web_va_luu(pm2):
    assert pc.act("VieNeu_TTS", "stop") == "Đang tắt Giọng đọc VieNeu (GPU)…"
    assert pm2 == ["/usr/bin/pm2 stop VieNeu_TTS; /usr/bin/pm2 save"]
    assert "mất kết nối" in pc.act("Web_Dashboard", "restart")
    assert "render" in pc.act("Studio_Heavy", "stop")


@pytest.mark.parametrize(("name", "action", "why"), [
    ("la_lam", "stop", "không điều khiển"),
    ("VieNeu_TTS; rm -rf /", "stop", "không điều khiển"),
    ("VieNeu_TTS", "delete", "không có hành động"),
    ("Web_Dashboard", "stop", "chỉ khởi động lại"),
])
def test_act_chan(pm2, name, action, why):
    with pytest.raises(pc.ProcessError, match=why):
        pc.act(name, action)
    assert pm2 == []


def test_api(pm2):
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")
    api = TestClient(app)
    assert {a["name"] for a in api.get("/api/admin/processes").json()["apps"]} >= {"VieNeu_TTS", "DB_Backup"}
    r = api.post("/api/admin/processes/DB_Backup/start")
    assert r.json() == {"ok": True, "message": "Đang bật Sao lưu DB…"}
    r = api.post("/api/admin/processes/Web_Dashboard/stop")
    assert r.status_code == 400 and "chỉ khởi động lại" in r.json()["detail"]
