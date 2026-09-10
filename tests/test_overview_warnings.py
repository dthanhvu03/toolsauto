"""
ADR-040 — test cho `overview_warnings_api` trong `app/core/config_service.py`
(1041 dòng, trước bản này KHÔNG có test nào).

Đây là cái quyết định băng cảnh báo đỏ/vàng trên trang Tổng quan — tức thứ Owner nhìn để tin
là hệ thống đang ổn. Nó im lặng sai thì đúng họ "nhãn nói dối" của cả tuần.

Khẳng định theo CẤU TRÚC (mức độ, chỗ dẫn tới, số lượng), không bám câu chữ: câu chữ còn sửa,
ngưỡng thì không được đổi lặng lẽ.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config_service import overview_warnings_api


@pytest.fixture
def env(monkeypatch):
    """Dựng một hệ thống HOÀN TOÀN LÀNH, rồi từng test chỉ bẻ đúng một thứ."""
    from app.core import workflow_registry as wr
    from app.core.observability import runtime_events as re_mod

    state = {
        "health": {"summary": {"failing": 0, "warning": 0}, "items": []},
        "cache": {"is_stale": False, "age_seconds": 0},
        "workflow": SimpleNamespace(name="default", timing={}),
        "steps": [],
        "cta": ["Xem thêm: {link}"],
    }

    monkeypatch.setattr(re_mod, "get_enriched_selector_health", lambda: state["health"])
    monkeypatch.setattr(wr, "get_cache_status", lambda: state["cache"])
    monkeypatch.setattr(wr.WorkflowRegistry, "get_workflow", staticmethod(lambda p, j: state["workflow"]))
    monkeypatch.setattr(wr.WorkflowRegistry, "get_step_resolution", staticmethod(lambda p, j: state["steps"]))
    monkeypatch.setattr(wr.WorkflowRegistry, "get_cta_templates", staticmethod(lambda p, locale="vi": state["cta"]))
    return state


def _links(res, severity=None):
    return [w["link"] for w in res["items"] if severity is None or w["severity"] == severity]


def test_he_thong_lanh_thi_KHONG_canh_bao_gi(env):
    """Băng cảnh báo phải im khi mọi thứ ổn — kêu vặt thì lần đỏ thật Owner cũng bỏ qua."""
    res = overview_warnings_api()

    assert res == {"has_critical": False, "has_warning": False, "total": 0, "items": []}


# ── selector ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("failing,severity", [(1, "warning"), (2, "warning"), (3, "critical"), (9, "critical")])
def test_tu_ba_selector_chet_tro_len_moi_len_muc_do(env, failing, severity):
    """Dưới ba cái là chuyện thường; từ ba trở lên nghĩa là worker có thể không xong job."""
    env["health"]["summary"]["failing"] = failing

    res = overview_warnings_api()

    assert _links(res, severity) == ["selector-health"]
    assert str(failing) in res["items"][0]["text"]


def test_hit_rate_thap_bao_rieng(env):
    env["health"]["summary"]["warning"] = 4

    res = overview_warnings_api()

    assert res["total"] == 1 and res["items"][0]["severity"] == "warning"


@pytest.mark.parametrize("n,expect", [(1, 0), (2, 1), (5, 1)])
def test_tu_hai_selector_dung_ban_du_phong_moi_bao(env, n, expect):
    env["health"]["items"] = [{"last_source": "static_fallback"}] * n + [{"last_source": "dom"}]

    assert overview_warnings_api()["total"] == expect


# ── cache ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("age,severity", [(0, "warning"), (300, "warning"), (301, "critical"), (9999, "critical")])
def test_cache_cu_qua_nam_phut_moi_len_do(env, age, severity):
    env["cache"] = {"is_stale": True, "age_seconds": age}

    res = overview_warnings_api()

    assert _links(res, severity) == ["cache"]


def test_cache_khong_stale_thi_khong_bao_du_tuoi_lon(env):
    env["cache"] = {"is_stale": False, "age_seconds": 99999}

    assert overview_warnings_api()["total"] == 0


# ── preset ──────────────────────────────────────────────────────────────────


def test_khong_co_preset_la_muc_do_do(env):
    """Không preset ⇒ worker chạy config mặc định — Owner phải biết ngay."""
    env["workflow"] = None

    res = overview_warnings_api()

    assert _links(res, "critical") == ["preset"]
    assert "facebook" in res["items"][0]["text"] and "POST" in res["items"][0]["text"]


def test_khong_co_preset_thi_KHONG_bao_them_ve_timing(env):
    """Không có workflow thì không có timing để soi — không được đoán bừa."""
    env["workflow"] = None

    assert overview_warnings_api()["total"] == 1


def test_preset_fast_co_buoc_bi_bo_thi_bao(env):
    env["workflow"] = SimpleNamespace(name="fb_fast", timing={})
    env["steps"] = [{"status": "SKIP"}, {"status": "RUN"}, {"status": "SKIP"}]

    res = overview_warnings_api()

    assert _links(res, "warning") == ["preset"]
    assert "2" in res["items"][0]["text"]


def test_preset_fast_khong_bo_buoc_nao_thi_im(env):
    env["workflow"] = SimpleNamespace(name="fb_fast", timing={})
    env["steps"] = [{"status": "RUN"}]

    assert overview_warnings_api()["total"] == 0


def test_preset_stealth_chi_la_thong_tin(env):
    env["workflow"] = SimpleNamespace(name="fb_stealth", timing={})

    res = overview_warnings_api()

    assert res["items"][0]["severity"] == "info"
    assert res["has_critical"] is False and res["has_warning"] is False


# ── timing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("timing,total", [
    ({"browse_delay_ms": 999}, 1),
    ({"browse_delay_ms": 1000}, 0),
    ({"settle_ms": 1999}, 1),
    ({"settle_ms": 2000}, 0),
    ({"browse_delay_ms": 500, "settle_ms": 500}, 2),
])
def test_nguong_timing(env, timing, total):
    """Hai ngưỡng khác nhau: browse 1000ms, settle 2000ms. Đổi lặng lẽ là hỏng."""
    env["workflow"] = SimpleNamespace(name="default", timing=timing)

    assert overview_warnings_api()["total"] == total


def test_timing_khong_phai_so_thi_bo_qua_chu_khong_no(env):
    env["workflow"] = SimpleNamespace(name="default", timing={"browse_delay_ms": "nhanh", "settle_ms": None})

    assert overview_warnings_api()["total"] == 0


# ── CTA ─────────────────────────────────────────────────────────────────────


def test_cta_dang_dung_ban_du_phong_thi_bao_thong_tin(env):
    env["cta"] = ["{link}"]

    res = overview_warnings_api()

    assert _links(res, "info") == ["cta"]


def test_cta_no_thi_KHONG_lam_chet_ca_bang_canh_bao(env, monkeypatch):
    """Cảnh báo CTA là phần phụ — hỏng ở đây không được nuốt mất cảnh báo đỏ phía trên."""
    from app.core import workflow_registry as wr

    def _no(p, locale="vi"):
        raise RuntimeError("x")

    env["workflow"] = None
    monkeypatch.setattr(wr.WorkflowRegistry, "get_cta_templates", staticmethod(_no))

    res = overview_warnings_api()

    assert _links(res, "critical") == ["preset"]


# ── xếp thứ tự ──────────────────────────────────────────────────────────────


def test_do_len_dau_vang_giua_thong_tin_cuoi(env):
    """Owner đọc từ trên xuống — cái nguy nhất phải nằm trên."""
    env["health"]["summary"] = {"failing": 5, "warning": 2}
    env["cta"] = ["{link}"]

    res = overview_warnings_api()

    assert [w["severity"] for w in res["items"]] == ["critical", "warning", "info"]
    assert res["has_critical"] is True and res["has_warning"] is True
