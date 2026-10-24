"""PLAN-076: một công thức tiền, snapshot chính sách bất biến cho từng link, mô phỏng admin dùng đúng engine."""

from __future__ import annotations

import inspect
import sqlite3
from dataclasses import replace
from datetime import timedelta

import pytest

from cashback_bot import admin_policy, service as service_module
from cashback_bot.admin_reserve import effective_from, resolve_policy, stamp
from cashback_bot.calculator import CalculationError
from cashback_bot.messages import DIEUKIEN, HOME, HUONGDAN, how_to_calc
from cashback_bot.pricing import V11, V12, PolicyResolution, cashback_for, quote_displayed_vnd
from cashback_bot.ranks import MEMBERSHIP_CUTOVER
from cashback_bot.wallet import PayoutBlocked
from tests.test_cashback_bot import FakeClient, payload, repo, service
from tests.test_cashback_reserve import ADMIN, LINK, NOW, _bot, _data, _rows, _wizard
from tests.test_cashback_share import _share
from tests.test_cashback_wallet import _order

V12_DEFAULT = PolicyResolution(V12, 7_000, 98, 1_000)
V11_DEFAULT = PolicyResolution(V11, 7_000, 98, 1_000)
BUYER = 111


def _snapshots(tmp_path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM link_policy_snapshots ORDER BY link_id").fetchall()


def _sub(tmp_path, update_id: int) -> str:
    return _rows(tmp_path, f"SELECT sub_id FROM link_requests WHERE telegram_update_id = {update_id}")[0][0]


def _entry(tmp_path, cid: str = "o1") -> tuple:
    return _rows(tmp_path, f"SELECT cashback_vnd, fee_vnd, tax_vnd, policy_label, status FROM cashback_entries WHERE conversion_id = '{cid}'")[0]


def _restart(tmp_path, v12: bool = True, **overrides):
    """Process mới trên cùng DB, như sau khi chủ bot restart."""
    client = FakeClient(payload(last_update="2026-10-23 08:30:00"))
    return service(
        tmp_path, client, estimate_policy="v1.2" if v12 else "v1.1", admin_user_ids=frozenset({ADMIN}), **overrides
    )


def _counts(tmp_path) -> dict[str, int]:
    tables = (
        "link_requests", "link_policy_snapshots", "share_policies", "reserve_policies", "policy_versions",
        "admin_drafts", "admin_change_audit", "cashback_entries", "cashback_payouts", "shopee_conversions",
        "settlement_batches", "settlement_items", "settlement_adjustments", "bot_state",
    )
    return {name: _rows(tmp_path, f"SELECT COUNT(*) FROM {name}")[0][0] for name in tables}


def _legacy_link(tmp_path, *, label, rate, commission, cashback, created_at="2026-10-23T08:00:00Z", update_id=900):
    """Link tạo trước PLAN-076: không có snapshot."""
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    cursor = conn.execute(
        """
        INSERT INTO link_requests (telegram_update_id, telegram_user_id, sub_id, original_url, affiliate_url,
            product_name, price_vnd, estimated_commission, estimated_cashback, cashback_rate_percent,
            link_status, delivery_status, created_at, estimate_policy)
        VALUES (?, ?, ?, ?, 'https://s.shopee.vn/x', 'Áo', 250000, ?, ?, ?, 'created', 'sent', ?, ?)
        """,
        (update_id, BUYER, f"legacy{update_id}", LINK, commission, cashback, rate, created_at, label),
    )
    conn.commit()
    return int(cursor.lastrowid)


# --- A. Pricing -------------------------------------------------------------


def test_01_v11_giu_cong_thuc_cu_moi_ty_le_va_hoa_hong():
    assert cashback_for(17_368, V11_DEFAULT).cashback_vnd == 12_157
    for rate in (0, 1, 33, 60, 65, 69, 70):
        policy = replace(V11_DEFAULT, share_bps=rate * 100)
        for commission in (0, 1, 7, 99, 1_663, 17_368, 30_510, 999_999, 123_456_789):
            assert cashback_for(commission, policy).cashback_vnd == quote_displayed_vnd(commission, rate)


def test_02_v12_dung_vi_du_plan():
    quote = cashback_for(100_000, V12_DEFAULT)
    assert (quote.fee_reserve_vnd, quote.tax_reserve_vnd, quote.distributable_vnd) == (980, 10_000, 89_020)
    assert (quote.cashback_vnd, quote.remainder_vnd) == (62_314, 26_706)


def test_03_mo_phong_bang_bao_gia_that_cung_dau_vao(tmp_path):
    bot = _bot(tmp_path)
    card = bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    stored = _rows(tmp_path, "SELECT estimated_commission, estimated_cashback FROM link_requests")[0]
    live = bot.admin_panel.resolve_policy(NOW)
    assert cashback_for(stored[0], live).cashback_vnd == stored[1] == 12_462
    assert "<b>12.462đ</b>" in card.text
    for amount in admin_policy.SIM_AMOUNTS:
        sim = bot.admin_panel.handle_callback(ADMIN, f"c:sim:{amount}", "private", NOW)
        expected = cashback_for(amount, live).cashback_vnd
        assert f"Khách nhận {_cell(expected)}" in " ".join(sim.text.split())


def _cell(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def test_04_05_du_phong_bang_0_va_phi_bang_0():
    none = replace(V12_DEFAULT, fee_bps=0, tax_reserve_bps=0)
    assert cashback_for(100_000, none).cashback_vnd == 70_000
    no_fee = replace(V12_DEFAULT, fee_bps=0)
    assert cashback_for(100_000, no_fee).cashback_vnd == 63_000


def test_06_07_hoa_hong_0_va_rat_nho_khong_am():
    zero = cashback_for(0, V12_DEFAULT)
    assert (zero.cashback_vnd, zero.fee_reserve_vnd, zero.tax_reserve_vnd, zero.remainder_vnd) == (0, 0, 0, 0)
    for commission in (1, 2, 9, 11):
        quote = cashback_for(commission, V12_DEFAULT)
        assert quote.cashback_vnd >= 0
        assert quote.distributable_vnd >= 0


def test_08_gia_tri_lon_chinh_xac_so_nguyen():
    quote = cashback_for(10_000_000_000, V12_DEFAULT)
    assert quote.fee_reserve_vnd == 98_000_000
    assert quote.tax_reserve_vnd == 1_000_000_000
    assert quote.cashback_vnd == (10_000_000_000 - 98_000_000 - 1_000_000_000) * 7_000 // 10_000


def test_09_lam_tron_phi_thue_len_khach_xuong_va_don_vi():
    quote = cashback_for(1_001, V12_DEFAULT)
    assert quote.fee_reserve_vnd == 10  # ceil(9,8098)
    assert quote.tax_reserve_vnd == 101  # ceil(100,1)
    assert quote.cashback_vnd == (1_001 - 10 - 101) * 7 // 10
    rounded = cashback_for(100_000, replace(V12_DEFAULT, rounding_unit=1_000))
    assert rounded.cashback_vnd == 62_000


def test_10_tu_choi_so_thuc_va_gia_tri_sai():
    with pytest.raises(CalculationError):
        cashback_for(100_000.0, V12_DEFAULT)  # type: ignore[arg-type]
    with pytest.raises(CalculationError):
        PolicyResolution(V12, 7_100, 98, 1_000)
    with pytest.raises(CalculationError):
        PolicyResolution("v9", 7_000, 98, 1_000)
    with pytest.raises(CalculationError):
        PolicyResolution(V12, 7_000, 98.0, 1_000)  # type: ignore[arg-type]


def test_nhan_chinh_sach_giu_dang_cu():
    assert V11_DEFAULT.label == "v1.1:70"
    assert V12_DEFAULT.label == "v1.2-reserve-2026-10-23"
    assert replace(V12_DEFAULT, reserve_policy_id=1, share_policy_id=2).label == "v1.2-reserve-2026-10-23+r1+s2"


# --- B. Snapshot -------------------------------------------------------------


def test_11_link_moi_ghi_snapshot_cung_luc(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    (snap,) = _snapshots(tmp_path)
    link = _rows(tmp_path, "SELECT id, estimated_commission, estimated_cashback, estimate_policy, cashback_rate_percent FROM link_requests")[0]
    assert snap["link_id"] == link[0]
    assert snap["provenance"] == "captured"
    assert (snap["pricing_version"], snap["share_bps"], snap["fee_bps"], snap["tax_reserve_bps"]) == ("v1.2", 7_000, 98, 1_000)
    assert (snap["other_reserve_vnd"], snap["rounding_unit"]) == (0, 1)
    assert snap["formula"] == "reserve_ceil_then_share_floor"
    assert snap["rounding"] == "reserve_ceil_vnd_share_floor_vnd"
    assert (snap["quote_commission_vnd"], snap["quote_cashback_vnd"]) == (link[1], link[2])
    assert snap["policy_label"] == link[3]
    assert snap["resolved_at"] == stamp(NOW)
    assert snap["quote_source"] == "product_data"


def test_12_15_doi_ty_le_sau_khi_tao_link_khong_doi_tien_link_cu(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    _order(bot, _sub(tmp_path, 1), commission=10_000)
    bot.refresh_wallet(NOW + timedelta(hours=1))
    before = _entry(tmp_path)
    assert before[0] == 6_231
    preview = _share(bot, NOW + timedelta(minutes=1))
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW + timedelta(minutes=1))
    assert _rows(tmp_path, "SELECT share_bps FROM share_policies") == [(6_500,)]
    bot.refresh_wallet(NOW + timedelta(hours=2))
    assert _entry(tmp_path) == before
    assert _snapshots(tmp_path)[0]["share_bps"] == 7_000


def test_16_doi_phi_thue_sau_khi_tao_link_khong_doi_tien_link_cu(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    _order(bot, _sub(tmp_path, 1), commission=10_000)
    bot.refresh_wallet(NOW + timedelta(hours=1))
    before = _entry(tmp_path)
    preview = _wizard(bot, NOW + timedelta(minutes=1), tax="1,5")
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW + timedelta(minutes=1))
    bot.refresh_wallet(NOW + timedelta(hours=2))
    assert _entry(tmp_path) == before
    newer = bot.handle_text(BUYER, "buyer", LINK, update_id=2, now=NOW + timedelta(minutes=2))
    assert "<b>13.652đ</b>" in newer.text, "link mới dùng mức mới"


def test_13_link_v11_khong_thanh_v12_khi_bat_v12(tmp_path):
    old = _bot(tmp_path, v12=False)
    old.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    with old.repo.connect() as conn:
        conn.execute("ALTER TABLE link_requests ADD COLUMN estimate_policy TEXT")
    bot = _restart(tmp_path, v12=True)
    _order(bot, _sub(tmp_path, 1), commission=17_368)
    bot.refresh_wallet(NOW + timedelta(hours=1))
    assert _entry(tmp_path)[:4] == (12_157, 171, 1_737, "v1.1:70")
    assert _snapshots(tmp_path)[0]["pricing_version"] == "v1.1"
    new = bot.handle_text(BUYER, "buyer", LINK, update_id=2, now=NOW)
    assert "<b>12.462đ</b>" in new.text
    assert [row["pricing_version"] for row in _snapshots(tmp_path)] == ["v1.1", "v1.2"]


def test_14_link_v12_cu_doc_dung_r_id_khong_tra_theo_gio(tmp_path):
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.execute(
        "INSERT INTO reserve_policies (account_kind, fee_bps, tax_reserve_bps, effective_at, created_by, created_at) "
        "VALUES ('PERSONAL', 98, 1000, '2026-10-23T07:00:00Z', 1, 'x')"
    )
    # r2 hiệu lực trước giờ ghi link, nhưng báo giá đã chốt r1 (link tạo sát mốc).
    conn.execute(
        "INSERT INTO reserve_policies (account_kind, fee_bps, tax_reserve_bps, effective_at, created_by, created_at) "
        "VALUES ('HOUSEHOLD_BUSINESS', 98, 150, '2026-10-23T07:59:59Z', 1, 'x')"
    )
    conn.commit()
    link_id = _legacy_link(tmp_path, label="v1.2-reserve-2026-10-23+r1", rate=70, commission=20_000, cashback=12_462)
    bot = _restart(tmp_path)
    snap = [row for row in _snapshots(tmp_path) if row["link_id"] == link_id][0]
    assert (snap["provenance"], snap["reserve_policy_id"], snap["tax_reserve_bps"]) == ("backfilled", 1, 1_000)
    _order(bot, "legacy900", commission=10_000)
    bot.refresh_wallet(NOW + timedelta(hours=1))
    assert _entry(tmp_path)[:4] == (6_231, 98, 1_000, "v1.2-reserve-2026-10-23+r1")


def test_17_link_cu_thieu_du_lieu_unresolved_khong_gan_chinh_sach_moi(tmp_path):
    bot = _bot(tmp_path)
    bad = _legacy_link(tmp_path, label="v1.2-reserve-2026-10-23", rate=70, commission=20_000, cashback=15_000)
    missing = _legacy_link(tmp_path, label=None, rate=70, commission=None, cashback=None, update_id=901)
    unknown = _legacy_link(tmp_path, label="v0-la", rate=70, commission=20_000, cashback=14_000, update_id=902)
    _restart(tmp_path)
    rows = {row["link_id"]: row for row in _snapshots(tmp_path)}
    for link_id in (bad, missing, unknown):
        assert rows[link_id]["provenance"] == "unresolved"
        assert rows[link_id]["share_bps"] is None and rows[link_id]["fee_bps"] is None
        assert rows[link_id]["note"]
    assert _rows(tmp_path, f"SELECT estimated_cashback FROM link_requests WHERE id = {bad}") == [(15_000,)]
    hist = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW)
    assert "Link đã chốt chính sách</b>: 0 · chưa xác định: 3" in hist.text


def test_backfill_dung_mau_production_v11_va_v12(tmp_path):
    """Hai dạng link thật trên production: V1.1 (70%) trước r1 và V1.2 +r1."""
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.execute(
        "INSERT INTO reserve_policies (account_kind, fee_bps, tax_reserve_bps, effective_at, created_by, created_at) "
        "VALUES ('PERSONAL', 98, 1000, '2026-10-23T09:55:51Z', 1, '2026-10-23T09:55:51Z')"
    )
    conn.commit()
    v11 = _legacy_link(tmp_path, label=None, rate=70, commission=30_510, cashback=21_357, created_at="2026-10-23T03:18:39Z")
    v12 = _legacy_link(
        tmp_path, label="v1.2-reserve-2026-10-23+r1", rate=70, commission=20_000, cashback=12_462,
        created_at="2026-10-24T01:16:42Z", update_id=901,
    )
    _restart(tmp_path)
    rows = {row["link_id"]: row for row in _snapshots(tmp_path)}
    assert (rows[v11]["provenance"], rows[v11]["policy_label"], rows[v11]["reserve_policy_id"]) == ("backfilled", "v1.1:70", None)
    assert (rows[v12]["provenance"], rows[v12]["reserve_policy_id"], rows[v12]["share_policy_id"]) == ("backfilled", 1, None)


def test_18_restart_khong_doi_snapshot_va_khong_ghi_them(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    _legacy_link(tmp_path, label=None, rate=70, commission=1_663, cashback=1_164)
    _restart(tmp_path)
    first = [tuple(row) for row in _snapshots(tmp_path)]
    _restart(tmp_path)
    _restart(tmp_path, v12=False)
    assert [tuple(row) for row in _snapshots(tmp_path)] == first
    assert len(first) == 2


def test_19_telegram_gui_lai_cung_update_khong_tao_snapshot_khac(tmp_path):
    bot = _bot(tmp_path)
    first = bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    preview = _share(bot, NOW)
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    again = bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW + timedelta(minutes=5))
    assert again.text == first.text
    assert len(_snapshots(tmp_path)) == 1
    assert _rows(tmp_path, "SELECT COUNT(*) FROM link_requests") == [(1,)]


def test_20_don_ve_sau_nhieu_ngay_van_dung_chinh_sach_link_goc(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    preview = _share(bot, NOW + timedelta(minutes=1), typed="60")
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW + timedelta(minutes=1))
    _order(bot, _sub(tmp_path, 1), commission=10_000)
    bot.refresh_wallet(NOW + timedelta(days=40))
    assert _entry(tmp_path)[0] == 6_231


def test_snapshot_chi_them_khong_sua_khong_xoa(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE link_policy_snapshots SET share_bps = 6000")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM link_policy_snapshots")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO link_policy_snapshots (link_id, schema_version, provenance, policy_label, created_at) VALUES (1, 1, 'captured', 'x', 'x')")


def test_bang_chinh_sach_chi_them(tmp_path):
    bot = _bot(tmp_path)
    preview = _share(bot, NOW)
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    preview = _wizard(bot, NOW)
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    for table, column in (("share_policies", "share_bps"), ("reserve_policies", "fee_bps")):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute(f"UPDATE {table} SET {column} = 0")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute(f"DELETE FROM {table}")


def test_ghi_snapshot_loi_thi_khong_luu_link(tmp_path):
    store = repo(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_created(
            {"telegram_update_id": 5, "telegram_user_id": BUYER, "sub_id": "s5", "original_url": LINK, "link_status": "created"},
            snapshot={"schema_version": 1, "provenance": "khac", "policy_label": "x", "created_at": "x"},
        )
    assert _rows(tmp_path, "SELECT COUNT(*) FROM link_requests") == [(0,)]


# --- C. Effective time ------------------------------------------------------


def _insert_share(tmp_path, share_bps: int, effective_at: str) -> int:
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    cursor = conn.execute(
        "INSERT INTO share_policies (share_bps, effective_at, created_by, created_at) VALUES (?, ?, 1, 'x')",
        (share_bps, effective_at),
    )
    conn.commit()
    return int(cursor.lastrowid)


def test_21_22_chua_toi_gio_va_dung_gio_hieu_luc(tmp_path):
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    share_id = _insert_share(tmp_path, 6_500, stamp(NOW + timedelta(hours=1)))
    assert bot.admin_panel.resolve_policy(NOW + timedelta(minutes=59, seconds=59)).share_bps == 7_000
    at = bot.admin_panel.resolve_policy(NOW + timedelta(hours=1))
    assert (at.share_bps, at.share_policy_id) == (6_500, share_id)


def test_23_hai_chinh_sach_cung_moc_dong_sau_thang_va_ghi_dung_id(tmp_path):
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    _insert_share(tmp_path, 6_500, stamp(NOW))
    later = _insert_share(tmp_path, 6_000, stamp(NOW))
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    snap = _snapshots(tmp_path)[0]
    assert (snap["share_bps"], snap["share_policy_id"]) == (6_000, later)
    assert snap["policy_label"].endswith(f"+s{later}")


def test_24_moc_da_qua_luc_bam_ap_dung_khong_hoi_to(tmp_path):
    bot = _bot(tmp_path)
    preview = _share(bot, NOW, typed="65", when="23/10 16:05")
    assert "16:05 23/10/2026" in preview.text
    late = NOW + timedelta(minutes=8)
    done = bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", late)
    assert _rows(tmp_path, "SELECT effective_at FROM share_policies") == [(stamp(late),)]
    assert "hiệu lực ngay bây giờ" in done.text
    assert effective_from("2026-10-23T08:59:30Z", NOW) == stamp(NOW)
    assert effective_from(None, NOW) == stamp(NOW)
    assert effective_from("2026-10-24T00:00:00Z", NOW) == "2026-10-24T00:00:00Z"


def test_dat_moc_du_phong_da_qua_cung_khong_hoi_to(tmp_path):
    bot = _bot(tmp_path)
    preview = _wizard(bot, NOW, when="23/10 16:05")
    late = NOW + timedelta(minutes=9)
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", late)
    assert _rows(tmp_path, "SELECT effective_at FROM reserve_policies") == [(stamp(late),)]


def test_25_26_link_sat_moc_chuyen_quote_va_snapshot_cung_mot_lan_chon(tmp_path):
    """Báo giá lúc 16:00:00 theo 70%. Tỷ lệ 65% hiệu lực 16:00:01, trước giờ ghi link. Tiền vẫn theo 70%."""
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    _insert_share(tmp_path, 6_500, stamp(NOW + timedelta(seconds=1)))
    card = bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    link = _rows(tmp_path, "SELECT estimated_cashback, estimate_policy, cashback_rate_percent, created_at FROM link_requests")[0]
    assert link[3] > stamp(NOW + timedelta(seconds=1)), "giờ ghi link sau mốc hiệu lực"
    snap = _snapshots(tmp_path)[0]
    assert "<b>12.462đ</b>" in card.text
    assert (link[0], link[1], link[2]) == (snap["quote_cashback_vnd"], snap["policy_label"], snap["share_bps"] // 100)
    _order(bot, _sub(tmp_path, 1), commission=10_000)
    bot.refresh_wallet(NOW + timedelta(hours=1))
    assert _entry(tmp_path)[0] == 6_231, "không lấy 65% theo giờ ghi link"


def test_26_moi_link_quote_va_snapshot_khop(tmp_path):
    bot = _bot(tmp_path)
    moments = [NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=2), NOW + timedelta(minutes=3)]
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=moments[0])
    preview = _share(bot, moments[1], typed="60")
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", moments[1])
    bot.handle_text(BUYER, "buyer", LINK, update_id=2, now=moments[2])
    preview = _wizard(bot, moments[2], tax="2")
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", moments[2])
    bot.handle_text(BUYER, "buyer", LINK, update_id=3, now=moments[3])
    links = _rows(tmp_path, "SELECT id, estimated_commission, estimated_cashback, estimate_policy FROM link_requests ORDER BY id")
    snaps = {row["link_id"]: row for row in _snapshots(tmp_path)}
    for link_id, commission, cashback, label in links:
        snap = snaps[link_id]
        assert (snap["quote_cashback_vnd"], snap["policy_label"]) == (cashback, label)
        resolution = PolicyResolution(
            snap["pricing_version"], snap["share_bps"], snap["fee_bps"], snap["tax_reserve_bps"],
            snap["other_reserve_vnd"], snap["rounding_unit"],
        )
        assert cashback_for(commission, resolution).cashback_vnd == cashback
    assert [row["share_bps"] for row in snaps.values()] == [7_000, 6_000, 6_000]
    assert [row["tax_reserve_bps"] for row in snaps.values()] == [1_000, 1_000, 200]


def test_27_restart_khi_co_lich_hen(tmp_path):
    bot = _bot(tmp_path)
    preview = _share(bot, NOW, typed="65", when="w:tmr")
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    bot = _restart(tmp_path, product_max_age_hours=48)
    before = bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW + timedelta(hours=1))
    after = bot.handle_text(BUYER, "buyer", LINK, update_id=2, now=NOW + timedelta(days=1))
    assert "<b>12.462đ</b>" in before.text
    assert "<b>11.572đ</b>" in after.text
    assert [row["share_bps"] for row in _snapshots(tmp_path)] == [7_000, 6_500]


def test_resolve_policy_doc_trong_mot_transaction(tmp_path):
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.row_factory = sqlite3.Row
    result = resolve_policy(conn, NOW, v12=True, default_share_bps=7_000, fee_default=98, tax_default=1_000)
    assert not conn.in_transaction
    assert (result.pricing_version, result.resolved_at) == ("v1.2", stamp(NOW))
    v11 = resolve_policy(conn, NOW, v12=False, default_share_bps=7_000, fee_default=98, tax_default=1_000, other_reserve_vnd=500)
    assert (v11.pricing_version, v11.other_reserve_vnd) == ("v1.1", 0)


# --- D. Admin ---------------------------------------------------------------


def test_28_man_admin_khong_co_cong_thuc_rieng():
    source = inspect.getsource(admin_policy)
    assert "estimate_cashback(" not in source
    assert "share_cashback(" not in source
    assert "quote_displayed_vnd(" not in source
    svc = inspect.getsource(service_module.CashbackService._real_cashback)
    assert "active_share" not in svc and "active_reserve" not in svc


def test_29_mo_phong_chi_doc_khong_bat_gi(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    bot.admin_panel.menu(ADMIN, NOW)
    before = _counts(tmp_path)
    for data in ["c:menu:sim", *(f"c:sim:{amount}" for amount in admin_policy.SIM_AMOUNTS)]:
        reply = bot.admin_panel.handle_callback(ADMIN, data, "private", NOW)
        assert all(d == "c:menu:home" or d.startswith("c:sim:") for row in reply.inline_keyboard for _l, d in row)
    assert _counts(tmp_path) == before
    assert bot.admin_panel.resolve_policy(NOW) == bot.admin_panel.resolve_policy(NOW)
    assert "<b>12.462đ</b>" in bot.handle_text(BUYER, "buyer", LINK, update_id=2, now=NOW).text


def test_30_so_sanh_v11_v12_cung_dau_vao(tmp_path):
    bot = _bot(tmp_path)
    sim = bot.admin_panel.handle_callback(ADMIN, "c:sim:100000", "private", NOW)
    flat = " ".join(sim.text.split())
    assert "V1.2 V1.1" in flat
    assert "Khách nhận 62.314 70.000" in flat
    assert "Quỹ chia 89.020 —" in flat
    assert "Còn lại 26.706 19.020" in flat
    assert "Khách nhận V1.2 so với V1.1: -7.686đ" in sim.text
    assert "không bật công thức nào" in sim.text
    v11 = _bot(tmp_path / "v11", v12=False)
    sim11 = v11.admin_panel.handle_callback(ADMIN, "c:sim:100000", "private", NOW)
    assert "V1.1 V1.2" in " ".join(sim11.text.split())
    assert "Khách nhận V1.1 so với V1.2: +7.686đ" in sim11.text


def test_mo_phong_hien_lich_hen(tmp_path):
    bot = _bot(tmp_path)
    preview = _share(bot, NOW, typed="65", when="w:tmr")
    bot.admin_panel.handle_callback(ADMIN, _data(preview, ":ok"), "private", NOW)
    sim = bot.admin_panel.handle_callback(ADMIN, "c:menu:sim", "private", NOW)
    assert "ĐÃ HẸN GIỜ" in sim.text
    assert "Từ 00:00 24/10/2026: chia 65%, phí 0,98%, thuế 10% → khách 57.863đ" in sim.text
    assert "Khách nhận 62.314" in " ".join(sim.text.split()), "cột hiện hành chưa đổi trước mốc"


def test_31_32_ban_nhap_hang_khong_thanh_dang_ap_dung(tmp_path):
    bot = _bot(tmp_path)
    bot.admin_panel.handle_callback(ADMIN, "c:tier:BRONZE", "private", NOW)
    preview = bot.handle_text(ADMIN, "owner", "55", update_id=20, now=NOW)
    confirm = [d for row in preview.inline_keyboard for _l, d in row if d.startswith("c:ok:")][0]
    bot.admin_panel.handle_callback(ADMIN, confirm, "private", NOW)
    assert _rows(tmp_path, "SELECT customer_effect FROM policy_versions") == [("none",)]
    sim = bot.admin_panel.handle_callback(ADMIN, "c:menu:sim", "private", NOW)
    assert "HẠNG THÀNH VIÊN</b> · bản nháp, chưa bật" in sim.text
    assert "Đồng 55%" in sim.text
    assert MEMBERSHIP_CUTOVER is False
    assert "Hạng thành viên: Chưa bật" in bot.admin_panel.menu(ADMIN, NOW).text
    assert "<b>12.462đ</b>" in bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW).text
    assert _snapshots(tmp_path)[0]["share_bps"] == 7_000


def test_33_lich_su_hien_phien_ban_that(tmp_path):
    bot = _bot(tmp_path)
    first = _share(bot, NOW, typed="65")
    bot.admin_panel.handle_callback(ADMIN, _data(first, ":ok"), "private", NOW)
    second = _share(bot, NOW + timedelta(minutes=1), typed="60", when="w:tmr")
    bot.admin_panel.handle_callback(ADMIN, _data(second, ":ok"), "private", NOW + timedelta(minutes=1))
    hist = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW + timedelta(minutes=2))
    assert "#2 60% từ 00:00 24/10/2026 · 🗓️ ĐÃ HẸN GIỜ" in hist.text
    assert "#1 65% từ 16:00 23/10/2026 · 🟢 ĐANG ÁP DỤNG" in hist.text
    assert "Mặc định cấu hình phí 0,98%, thuế 10% · 🟢 ĐANG ÁP DỤNG" in hist.text
    later = bot.admin_panel.handle_callback(ADMIN, "c:menu:hist", "private", NOW + timedelta(days=1))
    assert "#2 60% từ 00:00 24/10/2026 · 🟢 ĐANG ÁP DỤNG" in later.text
    assert "#1 65% từ 16:00 23/10/2026 · ⚪ ĐÃ THAY" in later.text


def test_34_callback_mo_phong_trai_quyen_bi_tu_choi(tmp_path):
    bot = _bot(tmp_path)
    for user, chat in ((BUYER, "private"), (ADMIN, "group")):
        reply = bot.admin_panel.handle_callback(user, "c:sim:100000", chat, NOW)
        assert "chỉ dành cho quản trị" in reply.text
    for data in ("c:sim:123", "c:sim:100000:x", "c:sim:-1", "c:sim:9999999"):
        assert bot.admin_panel.handle_callback(ADMIN, data, "private", NOW).text == "Nút này không còn hiệu lực."


def test_man_hang_va_xem_truoc_dung_engine(tmp_path):
    bot = _bot(tmp_path)
    rank = bot.admin_panel.handle_callback(ADMIN, "c:menu:rank", "private", NOW)
    assert "Đồng 60%: hoàn 53.412đ · còn 35.608đ" in rank.text
    assert "Vàng 70%: hoàn 62.314đ · còn 26.706đ" in rank.text
    bot.admin_panel.handle_callback(ADMIN, "c:tier:SILVER", "private", NOW)
    preview = bot.admin_panel.consume_text(ADMIN, "66", NOW)
    assert "Trước: hoàn 57.863đ, phần còn 31.157đ" in preview.text


# --- E. Customer messaging --------------------------------------------------


def test_35_36_cachtinh_theo_calculator_dang_chay(tmp_path):
    v12 = _bot(tmp_path)
    text12 = v12.handle_text(BUYER, "buyer", "/cachtinh", update_id=1, now=NOW).text
    assert "đã trừ trước dự phòng phí và thuế" in text12
    v11 = _bot(tmp_path / "v11", v12=False)
    text11 = v11.handle_text(BUYER, "buyer", "/cachtinh", update_id=1, now=NOW).text
    assert "chưa trừ thuế và phí" in text11
    assert "dự phòng" not in text11
    for text in (text11, text12):
        assert "Mỗi link giữ cách tính lúc bot tạo link" in text
        assert "%" not in text


def test_37_the_link_hien_dung_quote_da_chot(tmp_path):
    bot = _bot(tmp_path)
    card = bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    snap = _snapshots(tmp_path)[0]
    assert f"<b>{_cell(snap['quote_cashback_vnd'])}đ</b>" in card.text
    assert "khoảng" in card.text and "dự kiến" in card.text


def test_38_39_40_khong_hua_khong_goi_du_phong_la_thue_khong_goi_quote_la_so_du():
    pages = [HOME, HUONGDAN, DIEUKIEN, how_to_calc(False), how_to_calc(True)]
    for text in pages:
        lowered = text.lower()
        assert "chắc chắn" not in lowered and "cam kết hoàn" not in lowered
        assert "số dư" not in lowered
    calc = how_to_calc(True)
    assert "không phải số thuế bạn phải nộp" in calc
    assert "chưa phải tiền đã duyệt hay có thể rút" in calc
    assert "Ví hoàn tiền chưa mở" in calc and "Ví hoàn tiền chưa mở" in HOME
    assert "chưa theo dõi đơn" not in HOME


# --- F. Financial safety ----------------------------------------------------


def test_41_47_khong_mo_vi_khong_chi_khong_doi_trang_thai(tmp_path):
    bot = _bot(tmp_path)
    bot.handle_text(BUYER, "buyer", LINK, update_id=1, now=NOW)
    _order(bot, _sub(tmp_path, 1), commission=10_000, status="COMPLETED", complete="2026-10-01T00:00:00Z")
    _legacy_link(tmp_path, label=None, rate=70, commission=1_663, cashback=1_164)
    statuses = _rows(tmp_path, "SELECT validation_status, settlement_status, net_commission_vnd FROM shopee_conversions")
    bot.refresh_wallet(NOW + timedelta(days=60))
    _restart(tmp_path)
    for data in ("c:menu:sim", "c:sim:500000", "c:menu:hist", "c:menu:policy", "c:menu:rank", "c:menu:fee"):
        bot.admin_panel.handle_callback(ADMIN, data, "private", NOW)
    assert bot.wallet.settings().enabled is False
    with pytest.raises(PayoutBlocked):
        bot.wallet.set_enabled(True)
    assert _rows(tmp_path, "SELECT COUNT(*) FROM cashback_entries WHERE status = 'available'") == [(0,)]
    assert _rows(tmp_path, "SELECT COUNT(*) FROM cashback_payouts") == [(0,)]
    triggers = {row[0] for row in _rows(tmp_path, "SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {"financial_lock_entry_insert", "financial_lock_entry_update", "financial_lock_payout_insert", "financial_lock_payout_paid"} <= triggers
    assert _rows(tmp_path, "SELECT validation_status, settlement_status, net_commission_vnd FROM shopee_conversions") == statuses
    assert statuses[0][0] != "APPROVED" and statuses[0][1] != "SETTLED"
    assert _rows(tmp_path, "SELECT COUNT(*) FROM settlement_batches") == [(0,)]


def test_47_khoan_pending_cu_giu_nguyen_so_sau_backfill(tmp_path):
    """Đúng hai khoản pending thật: V1.1 70%, HH 17.368 → 12.157 (phí 171, thuế 1.737) và 1.372 → 960 (14, 138)."""
    bot = _bot(tmp_path)
    bot.admin_panel.menu(ADMIN, NOW)
    conn = sqlite3.connect(tmp_path / "cashback.sqlite")
    conn.execute(
        "INSERT INTO reserve_policies (account_kind, fee_bps, tax_reserve_bps, effective_at, created_by, created_at) "
        "VALUES ('PERSONAL', 98, 1000, '2026-10-23T09:55:51Z', 1, '2026-10-23T09:55:51Z')"
    )
    conn.commit()
    _legacy_link(tmp_path, label=None, rate=70, commission=30_510, cashback=21_357, created_at="2026-10-23T03:18:39Z")
    _legacy_link(tmp_path, label=None, rate=70, commission=1_663, cashback=1_164, created_at="2026-10-22T14:20:27Z", update_id=901)
    bot = _restart(tmp_path)
    assert [row["provenance"] for row in _snapshots(tmp_path)] == ["backfilled", "backfilled"]
    _order(bot, "legacy900", commission=17_368)
    _order(bot, "legacy901", commission=1_372, cid="o2")
    bot.refresh_wallet(NOW + timedelta(hours=1))
    assert _entry(tmp_path, "o1") == (12_157, 171, 1_737, "v1.1:70", "pending")
    assert _entry(tmp_path, "o2") == (960, 14, 138, "v1.1:70", "pending")
    _restart(tmp_path).refresh_wallet(NOW + timedelta(hours=2))
    assert _entry(tmp_path, "o1") == (12_157, 171, 1_737, "v1.1:70", "pending")


def test_link_cu_chua_co_snapshot_duoc_dung_lai_khi_tinh_vi(tmp_path):
    """Link chưa có dòng snapshot lúc tính ví (backfill khởi động chưa chạy): dựng tạm, không ghi giữa
    transaction sổ ví; số vẫn đúng. Lần khởi động sau mới ghi dòng."""
    bot = _bot(tmp_path)
    _legacy_link(tmp_path, label=None, rate=70, commission=30_510, cashback=21_357)
    _legacy_link(tmp_path, label=None, rate=70, commission=1_663, cashback=1_164, update_id=901)
    _order(bot, "legacy900", commission=17_368)
    _order(bot, "legacy901", commission=1_372, cid="o2")
    bot.refresh_wallet(NOW + timedelta(hours=1))
    assert _entry(tmp_path)[:4] == (12_157, 171, 1_737, "v1.1:70")
    assert _entry(tmp_path, "o2")[:4] == (960, 14, 138, "v1.1:70")
    assert _snapshots(tmp_path) == []
    _restart(tmp_path)
    assert [row["provenance"] for row in _snapshots(tmp_path)] == ["backfilled", "backfilled"]
