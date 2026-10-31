"""
PLAN-109 — DocType kiểu Frappe: kiểm định nghĩa, dữ liệu, link, bảng con, unique, đặt tên, luật giữ dữ liệu, API.
SQLite tạm, chỉ 2 bảng doctypes / doc_records. Không mạng.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.core import get_db
from app.core.database.models import Base, DocRecord, DocType
from app.core.doctype import service
from app.core.doctype.schema import DocTypeError, DocValidationError, coerce, normalize_fields, validate_data
from app.platform.doctype_api.router import router


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dt.sqlite'}")
    Base.metadata.create_all(engine, tables=[DocType.__table__, DocRecord.__table__])
    factory = sessionmaker(bind=engine)
    session = factory()
    session.factory = factory
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def api(db):
    app = FastAPI()
    app.include_router(router)

    def _db():
        s = db.factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _setup(db):
    """Kênh (đặt tên theo trường) ← Thư viện hook (link kênh + bảng con biến thể chữ)."""
    service.save_doctype(db, {"name": "kenh", "label": "Kênh", "naming": "field:ma", "title_field": "ten", "fields": [
        {"fieldname": "ma", "fieldtype": "data", "required": True},
        {"fieldname": "ten", "fieldtype": "data", "required": True, "in_list_view": True},
    ]})
    service.save_doctype(db, {"name": "hook_dong", "label": "Dòng hook", "is_child": True, "fields": [
        {"fieldname": "chu", "fieldtype": "data", "required": True},
        {"fieldname": "giay", "fieldtype": "float", "default": 3},
    ]})
    return service.save_doctype(db, {"name": "hook", "label": "Thư viện hook", "module": "Studio", "title_field": "ten",
                                     "fields": [
        {"fieldname": "ten", "fieldtype": "data", "required": True, "unique": True},
        {"fieldname": "kenh", "fieldtype": "link", "options": "kenh"},
        {"fieldname": "loai", "fieldtype": "select", "options": "Mở đầu\nKết", "default": "Mở đầu"},
        {"fieldname": "bat", "fieldtype": "check", "default": True},
        {"fieldname": "ngay", "fieldtype": "date"},
        {"fieldname": "dong", "fieldtype": "table", "options": "hook_dong"},
        {"fieldname": "them", "fieldtype": "json"},
    ]})


# ── schema thuần ──


def test_dinh_nghia_truong_chuan_hoa_va_chan_sai():
    f = normalize_fields([{"fieldname": "loai", "fieldtype": "select", "options": "A\n B \n"}])[0]
    assert f["options"] == ["A", "B"] and f["label"] == "loai" and f["required"] is False
    for bad, msg in [
        ([{"fieldname": "Ten"}], "không hợp lệ"), ([{"fieldname": "name"}], "không hợp lệ"),
        ([{"fieldname": "a1"}, {"fieldname": "a1"}], "trùng"), ([{"fieldname": "x1", "fieldtype": "video"}], "không có"),
        ([{"fieldname": "x1", "fieldtype": "select"}], "options"), ([{"fieldname": "x1", "fieldtype": "link"}], "options"),
        ([{"fieldname": "x1", "la": 1}], "khoá lạ"), ([{"fieldname": "x1", "fieldtype": "int", "default": "abc"}], "default sai"),
    ]:
        with pytest.raises(DocTypeError, match=msg):
            normalize_fields(bad)


@pytest.mark.parametrize("ft,value,expect", [
    ("int", "42", 42), ("float", "1.5", 1.5), ("check", "có", True), ("check", "0", False),
    ("date", "2026-10-31T09:00", "2026-10-31"), ("datetime", "2026-10-31T09:00:00", "2026-10-31T09:00:00"),
    ("json", '{"a": 1}', {"a": 1}), ("data", "  x  ", "x"),
])
def test_ep_kieu(ft, value, expect):
    assert coerce({"fieldtype": ft}, value) == expect


@pytest.mark.parametrize("ft,value", [("int", "1.5"), ("int", True), ("float", "x"), ("date", "31/10"),
                                      ("check", "có lẽ"), ("data", "x" * 141), ("json", "{sai")])
def test_ep_kieu_sai(ft, value):
    with pytest.raises(DocTypeError):
        coerce({"fieldtype": ft}, value)


def test_kiem_du_lieu_bat_buoc_default_truong_la():
    fields = normalize_fields([{"fieldname": "ten", "required": True}, {"fieldname": "so", "fieldtype": "int", "default": 2}])
    assert validate_data(fields, {"ten": "a"}) == {"ten": "a", "so": 2}
    with pytest.raises(DocValidationError) as exc:
        validate_data(fields, {"so": "x", "la": 1})
    assert exc.value.errors == {"la": "trường không có trong DocType", "so": "sai kiểu int", "ten": "bắt buộc"}


# ── service ──


def test_tao_ban_ghi_co_link_bang_con_default_va_dat_ten(db):
    _setup(db)
    service.save_record(db, "kenh", {"ma": "uyen_nhi", "ten": "Uyển Nhi"})
    rec = service.save_record(db, "hook", {"ten": "Mẹo 3 giây", "kenh": "uyen_nhi", "ngay": "2026-10-31",
                                           "dong": [{"chu": "Xem tới cuối"}, {"chu": "Đừng lướt", "giay": "2.5"}]})
    assert rec.name == "1"
    assert rec.data == {"ten": "Mẹo 3 giây", "kenh": "uyen_nhi", "loai": "Mở đầu", "bat": True, "ngay": "2026-10-31",
                        "dong": [{"chu": "Xem tới cuối", "giay": 3.0}, {"chu": "Đừng lướt", "giay": 2.5}], "them": None}
    assert service.save_record(db, "hook", {"ten": "Hook 2"}).name == "2"
    rows, total = service.list_records(db, "hook", q="mẹo")
    assert total == 1 and rows[0]["title"] == "Mẹo 3 giây"
    assert service.list_records(db, "kenh")[0][0]["title"] == "Uyển Nhi"


def test_loi_link_bang_con_unique_va_ten(db):
    _setup(db)
    with pytest.raises(DocValidationError) as exc:
        service.save_record(db, "hook", {"ten": "A", "kenh": "khong_co", "dong": [{"giay": 1}], "loai": "Giữa"})
    assert set(exc.value.errors) == {"loai", "dong[1].chu"}, "lỗi kiểu + bảng con báo cùng lúc; link kiểm sau"
    with pytest.raises(DocValidationError) as exc:
        service.save_record(db, "hook", {"ten": "A", "kenh": "khong_co", "dong": [{"giay": 1}]})
    assert exc.value.errors == {"kenh": "không có «khong_co» trong kenh", "dong[1].chu": "bắt buộc"}
    service.save_record(db, "hook", {"ten": "A"})
    with pytest.raises(DocValidationError, match="trùng"):
        service.save_record(db, "hook", {"ten": "A"})
    service.save_record(db, "kenh", {"ma": "k1", "ten": "K"})
    with pytest.raises(DocValidationError, match="đã có"):
        service.save_record(db, "kenh", {"ma": "k1", "ten": "K2"})
    with pytest.raises(DocValidationError, match="không đổi được"):
        service.save_record(db, "kenh", {"ma": "k2", "ten": "K"}, name="k1")
    with pytest.raises(DocTypeError, match="DocType con"):
        service.save_record(db, "hook_dong", {"chu": "x"})


def test_sua_ban_ghi_giu_ten_va_unique_khong_tu_va_vao_chinh_no(db):
    _setup(db)
    rec = service.save_record(db, "hook", {"ten": "A"})
    again = service.save_record(db, "hook", {"ten": "A", "loai": "Kết"}, name=rec.name)
    assert again.name == rec.name and again.data["loai"] == "Kết"


def test_dinh_nghia_link_table_phai_hop_le(db):
    _setup(db)
    with pytest.raises(DocTypeError, match="không có DocType"):
        service.save_doctype(db, {"name": "x_a", "fields": [{"fieldname": "k", "fieldtype": "link", "options": "khong_co"}]})
    with pytest.raises(DocTypeError, match="phải là DocType con"):
        service.save_doctype(db, {"name": "x_b", "fields": [{"fieldname": "k", "fieldtype": "table", "options": "kenh"}]})
    with pytest.raises(DocTypeError, match="không link tới DocType con"):
        service.save_doctype(db, {"name": "x_c", "fields": [{"fieldname": "k", "fieldtype": "link", "options": "hook_dong"}]})
    with pytest.raises(DocTypeError, match="đã có"):
        service.save_doctype(db, {"name": "hook", "fields": []})
    with pytest.raises(DocTypeError, match="naming"):
        service.save_doctype(db, {"name": "x_d", "naming": "field:khong", "fields": [{"fieldname": "a1"}]})
    with pytest.raises(DocTypeError, match="đổi tên"):
        service.save_doctype(db, {"name": "hook_moi", "fields": []}, name="hook")
    ok = service.save_doctype(db, {"name": "tu_lien", "fields": [{"fieldname": "cha", "fieldtype": "link", "options": "tu_lien"}]})
    assert ok.fields[0]["options"] == "tu_lien", "link tới chính nó (cây cha / con) được"


def test_them_bot_truong_khong_mat_du_lieu(db):
    _setup(db)
    rec = service.save_record(db, "kenh", {"ma": "k1", "ten": "K"})
    service.save_doctype(db, {"name": "kenh", "label": "Kênh", "naming": "field:ma", "fields": [
        {"fieldname": "ma", "fieldtype": "data", "required": True},
        {"fieldname": "mau", "fieldtype": "select", "options": "Đỏ\nXanh", "default": "Đỏ"},
    ]}, name="kenh")
    db.refresh(rec)
    assert rec.data == {"ma": "k1", "ten": "K"}, "bỏ trường «ten» không xoá dữ liệu cũ"
    assert service.save_record(db, "kenh", {"ma": "k1"}, name="k1").data == {"ma": "k1", "mau": "Đỏ"}


def test_xoa_bi_chan_khi_con_du_lieu_hoac_dang_bi_link(db):
    _setup(db)
    service.save_record(db, "kenh", {"ma": "k1", "ten": "K"})
    service.save_doctype(db, {"name": "dong_link", "is_child": True, "fields": [{"fieldname": "k", "fieldtype": "link", "options": "kenh"}]})
    service.save_doctype(db, {"name": "lich", "fields": [{"fieldname": "rows", "fieldtype": "table", "options": "dong_link"}]})
    service.save_record(db, "lich", {"rows": [{"k": "k1"}]})
    with pytest.raises(DocTypeError, match="link tới «k1».*lich/1"):
        service.delete_record(db, "kenh", "k1")
    with pytest.raises(DocTypeError, match="còn bản ghi"):
        service.delete_doctype(db, "kenh")
    with pytest.raises(DocTypeError, match="đang trỏ tới"):
        service.delete_doctype(db, "dong_link")
    service.delete_record(db, "lich", "1")
    service.delete_record(db, "kenh", "k1")
    service.delete_doctype(db, "lich")
    service.delete_doctype(db, "dong_link")
    assert [d["name"] for d in service.list_doctypes(db)] == ["hook_dong", "kenh", "hook"]


# ── API ──


def test_api_dinh_nghia_va_ban_ghi(api):
    r = api.post("/api/doctypes", json={"name": "kieu_caption", "label": "Kiểu caption", "title_field": "ten", "fields": [
        {"fieldname": "ten", "fieldtype": "data", "required": True, "in_list_view": True},
        {"fieldname": "giong", "fieldtype": "select", "options": ["Hài", "Tâm sự"]},
    ]})
    assert r.status_code == 200 and r.json()["fields"][1]["options"] == ["Hài", "Tâm sự"]
    listed = api.get("/api/doctypes").json()
    assert listed["doctypes"][0]["records"] == 0 and "table" in listed["fieldtypes"]
    bad = api.post("/api/doc/kieu_caption", json={"giong": "Nghiêm"})
    assert bad.status_code == 422 and bad.json()["errors"] == {"giong": "phải là một trong ['Hài', 'Tâm sự']", "ten": "bắt buộc"}
    rec = api.post("/api/doc/kieu_caption", json={"ten": "Vui", "giong": "Hài"}).json()
    assert rec["name"] == "1"
    assert api.put("/api/doc/kieu_caption/1", json={"ten": "Vui vẻ", "giong": "Hài"}).json()["data"]["ten"] == "Vui vẻ"
    page = api.get("/api/doc/kieu_caption?q=vui").json()
    assert page["total"] == 1 and page["doctype"]["label"] == "Kiểu caption"
    assert api.get("/api/doc/kieu_caption/options").json()["options"] == [{"name": "1", "title": "Vui vẻ"}]
    assert api.get("/api/doc/kieu_caption/9").status_code == 404
    assert api.get("/api/doc/khong_co").status_code == 404
    assert api.delete("/api/doctypes/kieu_caption").status_code == 400
    assert api.delete("/api/doc/kieu_caption/1").json() == {"ok": True}
    assert api.delete("/api/doctypes/kieu_caption").json() == {"ok": True}


def test_loi_truong_chinh_va_bang_con_bao_cung_luc(db):
    _setup(db)
    with pytest.raises(DocValidationError) as exc:
        service.save_record(db, "hook", {"dong": [{"giay": "x"}]})
    assert exc.value.errors == {"ten": "bắt buộc", "dong[1].chu": "bắt buộc", "dong[1].giay": "sai kiểu float"}
