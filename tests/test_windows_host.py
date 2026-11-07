"""
Khung «Máy Windows» trên Panel hệ thống: số liệu powershell giả — không gọi Windows thật.
"""
from __future__ import annotations

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import windows_host as wh
from app.platform.admin_api.processes import router

NOW = 1_800_000_000.0
RAW = {
    "t": 8 * 1024 * 1024, "f": 1024 * 1024, "c": 37, "n": " Intel i5 ", "k": 8,
    "b": "2027-01-15T08:00:00.5000000+07:00",
    "d": ["C:", "Acer", 300_000_000_000, 27_000_000_000, "D:", "?", 16_000_000_000, 15_500_000_000],
    "p": ["vmmemWSL", 1300 * 1048576, 5.0,
          "chrome", 100 * 1048576, 10.0, "chrome", 50 * 1048576, 6.0,
          "Cursor#8", 200 * 1048576, 1.0, "Idle", 8192, 999.0],
}


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(wh, "_cache", None)
    monkeypatch.setattr(wh, "_cache_at", 0.0)
    monkeypatch.setattr(wh, "_prev_cpu", {})
    monkeypatch.setattr(wh, "_prev_at", 0.0)


def test_build_gop_theo_ten_va_doi_don_vi():
    data, totals = wh.build(RAW, {}, 0, NOW)
    assert data["mem_total_mb"] == 8192 and data["mem_used_mb"] == 7168
    assert data["cpu_pct"] == 37 and data["cpus"] == 8 and data["cpu_name"] == "Intel i5"
    assert data["disks"] == [
        {"drive": "C:", "label": "Acer", "total_gb": 300.0, "used_gb": 273.0, "free_gb": 27.0},
        {"drive": "D:", "label": "", "total_gb": 16.0, "used_gb": 0.5, "free_gb": 15.5},
    ]
    names = [r["name"] for r in data["top"]]
    assert names == ["vmmemWSL", "Cursor", "chrome"]  # theo RAM giảm dần, bỏ Idle, «Cursor#8» → «Cursor»
    chrome = data["top"][2]
    assert chrome["count"] == 2 and chrome["mem_mb"] == 150 and chrome["label"] == "Chrome"
    assert chrome["cpu_pct"] is None  # lần đọc đầu chưa có mốc
    assert data["wsl_mem_mb"] == 1300 and data["process_count"] == 4
    assert totals["chrome"] == 16.0
    assert data["uptime_s"] is not None and data["uptime_s"] > 0


def test_cpu_tung_chuong_trinh_tinh_tu_chenh_lech():
    _, totals = wh.build(RAW, {}, 0, NOW)
    raw2 = {**RAW, "p": ["chrome", 100 * 1048576, 16.0 + 8.0]}  # +8 giây CPU trong 10 giây, 8 luồng → 10%
    data, _ = wh.build(raw2, totals, 10.0, NOW + 10)
    assert data["top"][0]["cpu_pct"] == 10.0


def test_snapshot_giu_ket_qua_va_tinh_cpu(monkeypatch):
    calls = []
    monkeypatch.setattr(wh, "_powershell", lambda: "/x/powershell.exe")
    monkeypatch.setattr(wh, "_query", lambda exe: calls.append(exe) or RAW)
    first = wh.snapshot(NOW)
    assert first["available"] and first["age_s"] == 0
    again = wh.snapshot(NOW + 3)
    assert len(calls) == 1 and again["age_s"] == 3  # trong CACHE_SEC không gọi lại powershell
    wh.snapshot(NOW + wh.CACHE_SEC + 1)
    assert len(calls) == 2


def test_khong_co_powershell_hoac_loi_khong_raise(monkeypatch):
    monkeypatch.setattr(wh, "_powershell", lambda: None)
    out = wh.snapshot(NOW)
    assert out["available"] is False and "powershell" in out["error"]

    def boom(exe):
        raise subprocess.TimeoutExpired(exe, 20)

    monkeypatch.setattr(wh, "_powershell", lambda: "/x/powershell.exe")
    monkeypatch.setattr(wh, "_query", boom)
    out = wh.snapshot(NOW)
    assert out["available"] is False and "Không đọc được" in out["error"]


def test_api(monkeypatch):
    monkeypatch.setattr(wh, "_powershell", lambda: "/x/powershell.exe")
    monkeypatch.setattr(wh, "_query", lambda exe: RAW)
    app = FastAPI()
    app.include_router(router)
    body = TestClient(app).get("/processes/windows").json()
    assert body["available"] and body["top"][0]["label"].startswith("WSL")
