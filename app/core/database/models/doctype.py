"""
PLAN-109 — DocType kiểu Frappe: định nghĩa loại dữ liệu trên web, bản ghi lưu JSON (không migration cho từng loại).

``doctypes.fields``: danh sách trường ``{"fieldname", "label", "fieldtype", "options", "required", "default",
"unique", "in_list_view", "read_only", "description"}``. Bảng con (``fieldtype: table``) lưu trong ``data`` của bản
ghi cha. Engine kiểm dữ liệu ở ``app/core/doctype/``.
"""
from sqlalchemy import JSON, Boolean, Column, Integer, String, Text, UniqueConstraint

from app.core.database.models.base import Base, now_ts


class DocType(Base):
    __tablename__ = "doctypes"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)  # slug: chữ thường, số, gạch dưới
    label = Column(String(120), nullable=False)
    module = Column(String(64), nullable=True)  # nhóm hiển thị, vd "Studio"
    description = Column(Text, nullable=True)
    fields = Column(JSON, nullable=False, default=list)
    is_child = Column(Boolean, nullable=False, default=False)  # chỉ dùng làm dòng của trường ``table``
    title_field = Column(String(64), nullable=True)
    naming = Column(String(80), nullable=False, default="autoincrement")  # autoincrement | field:<fieldname>
    created_at = Column(Integer, nullable=False, default=now_ts)
    modified_at = Column(Integer, nullable=False, default=now_ts, onupdate=now_ts)


class DocRecord(Base):
    __tablename__ = "doc_records"
    __table_args__ = (UniqueConstraint("doctype", "name", name="uq_doc_records_doctype_name"),)

    id = Column(Integer, primary_key=True)
    doctype = Column(String(64), nullable=False, index=True)
    name = Column(String(140), nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(Integer, nullable=False, default=now_ts)
    modified_at = Column(Integer, nullable=False, default=now_ts, onupdate=now_ts)
