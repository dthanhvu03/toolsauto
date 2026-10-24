"""SQLite riêng cho tracking. Ví, payout và số dư nằm ở wallet.py (PLAN-066)."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot.commission_validation import (
    CONFIDENCE_INFERRED,
    FRAUD,
    NEEDS_REVIEW,
    REJECTED,
    SETTLEMENT_NOT_VERIFIED,
    SOURCE_REPORT,
    UNKNOWN,
    Assessment,
    assess_raw,
    is_regression,
    is_significant_drop,
)

logger = logging.getLogger("cashback_bot")

SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_users (
    telegram_user_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS link_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_update_id INTEGER UNIQUE,
    telegram_user_id INTEGER NOT NULL,
    sub_id TEXT UNIQUE,
    original_url TEXT NOT NULL,
    affiliate_url TEXT,
    item_id INTEGER,
    shop_id INTEGER,
    product_name TEXT,
    price_vnd INTEGER,
    estimated_commission INTEGER,
    estimated_cashback INTEGER,
    cashback_rate_percent INTEGER,
    api_status TEXT,
    data_source TEXT,
    product_last_update TEXT,
    link_status TEXT NOT NULL,
    reject_reason TEXT,
    delivery_status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (telegram_user_id) REFERENCES telegram_users(telegram_user_id)
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_update_id INTEGER UNIQUE,
    telegram_user_id INTEGER NOT NULL,
    body_html TEXT NOT NULL,
    button_url TEXT,
    edit_message_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS admin_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    message_html TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    last_attempt_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS shopee_cookies (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL DEFAULT 'disconnected',
    account_name TEXT,
    last_sync_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shopee_clicks (
    click_id TEXT PRIMARY KEY,
    sub_id TEXT,
    click_time TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shopee_conversions (
    conversion_id TEXT PRIMARY KEY,
    sub_id TEXT,
    order_sn TEXT,
    order_status TEXT,
    conversion_status TEXT,
    purchase_time TEXT,
    gross_commission_vnd INTEGER,
    net_commission_vnd INTEGER,
    matched_link_id INTEGER,
    telegram_user_id INTEGER,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shopee_sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL,
    clicks_synced INTEGER NOT NULL DEFAULT 0,
    conversions_synced INTEGER NOT NULL DEFAULT 0,
    new_orders_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

-- PLAN-066: sổ hoàn tiền. Mỗi đơn khớp link bot một dòng; số tiền đã chốt không tính lại.
CREATE TABLE IF NOT EXISTS cashback_entries (
    conversion_id TEXT PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL,
    link_id INTEGER,
    order_sn TEXT,
    item_name TEXT,
    commission_vnd INTEGER NOT NULL DEFAULT 0,
    cashback_vnd INTEGER NOT NULL DEFAULT 0,
    fee_vnd INTEGER NOT NULL DEFAULT 0,
    tax_vnd INTEGER NOT NULL DEFAULT 0,
    policy_label TEXT,
    status TEXT NOT NULL,
    purchase_time TEXT,
    completed_at TEXT,
    available_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cashback_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL,
    amount_vnd INTEGER NOT NULL,
    status TEXT NOT NULL,
    bank_code TEXT NOT NULL,
    account_no TEXT NOT NULL,
    account_name TEXT NOT NULL,
    transfer_note TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by INTEGER
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    telegram_user_id INTEGER PRIMARY KEY,
    bank_code TEXT NOT NULL,
    account_no TEXT NOT NULL,
    account_name TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Lịch sử thay đổi của từng đơn Shopee (PLAN-074). Chỉ thêm dòng, không sửa, không xoá.
CREATE TABLE IF NOT EXISTS shopee_conversion_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    significant INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    sync_run_id INTEGER,
    detected_at TEXT NOT NULL,
    UNIQUE (conversion_id, field, sync_run_id)
);
CREATE INDEX IF NOT EXISTS idx_conversion_changes_conv ON shopee_conversion_changes(conversion_id);

-- Đối soát thanh toán Shopee (PLAN-075, ADR-052). Tên bảng cố ý KHÁC `shopee_settlements` /
-- `payout_tax_policies` (điều kiện mở khoá của payout_gate, PLAN-078): nhập chứng từ hay đối soát
-- MATCHED không thể mở ví. Tiền là VND nguyên; NULL nghĩa là "chưa xác minh", không phải 0.
CREATE TABLE IF NOT EXISTS settlement_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL CHECK (length(period) = 7),
    shopee_payment_ref TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN
        ('DRAFT', 'EVIDENCE_PENDING', 'PARTIALLY_MATCHED', 'MATCHED', 'DISPUTED', 'REVERSED')),
    reported_commission_vnd INTEGER,
    adjustments_vnd INTEGER,
    fee_vnd INTEGER,
    fee_vat_vnd INTEGER,
    fee_includes_vat INTEGER,
    tax_withheld_vnd INTEGER,
    shopee_payout_vnd INTEGER,
    bank_received_vnd INTEGER,
    statement_evidence_id INTEGER,
    bank_evidence_id INTEGER,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_settlement_batch_ref
    ON settlement_batches(period, shopee_payment_ref) WHERE shopee_payment_ref IS NOT NULL;

-- Chứng cứ: chỉ thêm. Thay chứng từ = dòng mới + superseded_by, không sửa đè.
CREATE TABLE IF NOT EXISTS settlement_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES settlement_batches(id),
    kind TEXT NOT NULL CHECK (kind IN ('shopee_validation_report', 'shopee_payment_report', 'bank_statement')),
    source TEXT NOT NULL,
    document_ref TEXT NOT NULL CHECK (length(document_ref) > 0),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    stored_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    parser TEXT NOT NULL,
    verification TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (verification IN ('RECEIVED', 'VERIFIED', 'REJECTED', 'SUPERSEDED')),
    viewed_by INTEGER,
    viewed_at TEXT,
    superseded_by INTEGER,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (content_sha256),
    UNIQUE (kind, document_ref)
);

-- Khoản theo từng đơn trong một kỳ. conversion_id NULL: Shopee có trả nhưng bot không xác định được đơn.
CREATE TABLE IF NOT EXISTS settlement_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES settlement_batches(id),
    evidence_id INTEGER NOT NULL REFERENCES settlement_evidence(id),
    order_ref TEXT NOT NULL,
    conversion_id TEXT,
    is_bot INTEGER NOT NULL DEFAULT 0,
    telegram_user_id INTEGER,
    approved_vnd INTEGER,
    settled_vnd INTEGER,
    adjustment_vnd INTEGER,
    match_status TEXT NOT NULL CHECK (match_status IN
        ('MATCHED', 'NOT_BOT', 'UNKNOWN_ORDER', 'AMOUNT_MISMATCH', 'DUPLICATE', 'NEEDS_REVIEW')),
    created_at TEXT NOT NULL,
    UNIQUE (batch_id, evidence_id, order_ref)
);
CREATE INDEX IF NOT EXISTS idx_settlement_items_conv ON settlement_items(conversion_id);

-- Điều chỉnh hoa hồng sau khi đã vào một kỳ (giảm, thu hồi, gian lận về sau). Một sự kiện một dòng.
CREATE TABLE IF NOT EXISTS settlement_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_id TEXT NOT NULL,
    original_batch_id INTEGER,
    old_vnd INTEGER NOT NULL,
    new_vnd INTEGER NOT NULL,
    delta_vnd INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('conversion_change', 'settlement_item')),
    source_ref TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'DISPUTED')),
    detected_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    UNIQUE (source, source_ref)
);

-- Nhật ký đối soát: chỉ thêm. Trigger chặn sửa và xoá.
CREATE TABLE IF NOT EXISTS settlement_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS settlement_audit_no_update BEFORE UPDATE ON settlement_audit
BEGIN SELECT RAISE(ABORT, 'settlement_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS settlement_audit_no_delete BEFORE DELETE ON settlement_audit
BEGIN SELECT RAISE(ABORT, 'settlement_audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS settlement_evidence_no_delete BEFORE DELETE ON settlement_evidence
BEGIN SELECT RAISE(ABORT, 'settlement_evidence is append-only'); END;

-- Chính sách chốt cho từng link lúc báo giá (PLAN-076, ADR-053). Một link một dòng, chỉ thêm.
-- captured: ghi cùng lúc tạo link. backfilled: dựng lại từ link cũ và đã tính ra đúng số đã báo.
-- unresolved: link cũ không dựng lại được; cột chính sách để trống, không gán chính sách mới.
CREATE TABLE IF NOT EXISTS link_policy_snapshots (
    link_id INTEGER PRIMARY KEY REFERENCES link_requests(id),
    schema_version INTEGER NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('captured', 'backfilled', 'unresolved')),
    policy_label TEXT NOT NULL,
    pricing_version TEXT CHECK (pricing_version IN ('v1.1', 'v1.2')),
    formula TEXT,
    rounding TEXT,
    share_bps INTEGER,
    share_policy_id INTEGER,
    reserve_policy_id INTEGER,
    fee_bps INTEGER,
    tax_reserve_bps INTEGER,
    other_reserve_vnd INTEGER,
    rounding_unit INTEGER,
    resolved_at TEXT,
    quote_commission_vnd INTEGER,
    quote_cashback_vnd INTEGER,
    quote_source TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    CHECK (provenance = 'unresolved' OR (
        pricing_version IS NOT NULL AND formula IS NOT NULL AND rounding IS NOT NULL
        AND share_bps IS NOT NULL AND fee_bps IS NOT NULL AND tax_reserve_bps IS NOT NULL
        AND other_reserve_vnd IS NOT NULL AND rounding_unit IS NOT NULL AND resolved_at IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS link_policy_snapshots_no_update BEFORE UPDATE ON link_policy_snapshots
BEGIN SELECT RAISE(ABORT, 'link_policy_snapshots is append-only'); END;
CREATE TRIGGER IF NOT EXISTS link_policy_snapshots_no_delete BEFORE DELETE ON link_policy_snapshots
BEGIN SELECT RAISE(ABORT, 'link_policy_snapshots is append-only'); END;

-- Điều khoản khách theo phiên bản (PLAN-077, ADR-054). Nội dung chỉ sửa được khi còn DRAFT.
-- Trạng thái chỉ đi DRAFT → PUBLISHED → SUPERSEDED. Bản đã công bố không xoá được.
CREATE TABLE IF NOT EXISTS customer_terms_versions (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED')),
    effective_from TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_by TEXT,
    published_at TEXT,
    CHECK (status = 'DRAFT' OR (effective_from IS NOT NULL AND approved_by IS NOT NULL AND published_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_terms_one_published ON customer_terms_versions(status) WHERE status = 'PUBLISHED';
CREATE TRIGGER IF NOT EXISTS terms_content_frozen BEFORE UPDATE OF version, title, content, content_hash ON customer_terms_versions
WHEN OLD.status != 'DRAFT'
BEGIN SELECT RAISE(ABORT, 'published terms are immutable'); END;
CREATE TRIGGER IF NOT EXISTS terms_status_forward BEFORE UPDATE OF status ON customer_terms_versions
WHEN NOT ((OLD.status = 'DRAFT' AND NEW.status IN ('DRAFT', 'PUBLISHED'))
       OR (OLD.status = 'PUBLISHED' AND NEW.status IN ('PUBLISHED', 'SUPERSEDED'))
       OR (OLD.status = 'SUPERSEDED' AND NEW.status = 'SUPERSEDED'))
BEGIN SELECT RAISE(ABORT, 'terms status only moves forward'); END;
CREATE TRIGGER IF NOT EXISTS terms_publish_frozen BEFORE UPDATE OF effective_from, approved_by, published_at ON customer_terms_versions
WHEN OLD.status != 'DRAFT'
BEGIN SELECT RAISE(ABORT, 'published terms are immutable'); END;
CREATE TRIGGER IF NOT EXISTS terms_no_delete BEFORE DELETE ON customer_terms_versions
WHEN OLD.status != 'DRAFT'
BEGIN SELECT RAISE(ABORT, 'published terms are immutable'); END;

-- Chấp thuận điều khoản: chỉ ghi khi khách bấm đồng ý. Một khách một dòng mỗi phiên bản. Chỉ thêm.
CREATE TABLE IF NOT EXISTS customer_terms_acceptances (
    id INTEGER PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL,
    terms_version_id INTEGER NOT NULL REFERENCES customer_terms_versions(id),
    terms_hash TEXT NOT NULL,
    acceptance_source TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (telegram_user_id, terms_version_id)
);
CREATE TRIGGER IF NOT EXISTS terms_acceptances_no_update BEFORE UPDATE ON customer_terms_acceptances
BEGIN SELECT RAISE(ABORT, 'customer_terms_acceptances is append-only'); END;
CREATE TRIGGER IF NOT EXISTS terms_acceptances_no_delete BEFORE DELETE ON customer_terms_acceptances
BEGIN SELECT RAISE(ABORT, 'customer_terms_acceptances is append-only'); END;

-- Điều khoản đang công bố lúc tạo link, tách khỏi snapshot tiền (link_policy_snapshots). Link trước PLAN-077
-- không có dòng: LEGACY / NOT_RECORDED. terms_version_id NULL: lúc tạo link chưa có điều khoản công bố.
CREATE TABLE IF NOT EXISTS link_terms_context (
    link_id INTEGER PRIMARY KEY REFERENCES link_requests(id),
    terms_version_id INTEGER REFERENCES customer_terms_versions(id),
    acceptance_id INTEGER REFERENCES customer_terms_acceptances(id),
    recorded_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS link_terms_context_no_update BEFORE UPDATE ON link_terms_context
BEGIN SELECT RAISE(ABORT, 'link_terms_context is append-only'); END;
CREATE TRIGGER IF NOT EXISTS link_terms_context_no_delete BEFORE DELETE ON link_terms_context
BEGIN SELECT RAISE(ABORT, 'link_terms_context is append-only'); END;

-- Yêu cầu hỗ trợ / khiếu nại (PLAN-077). Ticket không chạm tiền: không có cột hay đường nào đổi hoa hồng,
-- trạng thái duyệt, sổ ví hay payout. source_update_id chặn tạo trùng khi Telegram gửi lại cùng update.
CREATE TABLE IF NOT EXISTS support_tickets (
    id INTEGER PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    link_id INTEGER REFERENCES link_requests(id),
    conversion_id TEXT,
    message TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'OPEN', 'IN_REVIEW', 'WAITING_CUSTOMER', 'WAITING_SHOPEE', 'RESOLVED', 'REJECTED', 'CLOSED')),
    assigned_to INTEGER,
    resolution TEXT,
    source_update_id INTEGER UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_support_tickets_user ON support_tickets(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);
CREATE TABLE IF NOT EXISTS support_ticket_events (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES support_tickets(id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    note TEXT,
    source_update_id INTEGER UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS support_ticket_events_no_update BEFORE UPDATE ON support_ticket_events
BEGIN SELECT RAISE(ABORT, 'support_ticket_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS support_ticket_events_no_delete BEFORE DELETE ON support_ticket_events
BEGIN SELECT RAISE(ABORT, 'support_ticket_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS support_tickets_no_delete BEFORE DELETE ON support_tickets
BEGIN SELECT RAISE(ABORT, 'support tickets are kept for audit'); END;

-- PLAN-078: vòng đời yêu cầu rút (ADR-055). cashback_payouts giữ làm bảng yêu cầu; thêm phân bổ, sự kiện,
-- lịch sử và xác minh tài khoản, quyết định chính sách, hạn mức. Mọi bảng mới chỉ thêm.
-- Mỗi đồng của một yêu cầu rút trỏ về một khoản sổ ví (conversion). Tổng phân bổ = số tiền yêu cầu.
CREATE TABLE IF NOT EXISTS payout_allocations (
    id INTEGER PRIMARY KEY,
    payout_id INTEGER NOT NULL REFERENCES cashback_payouts(id),
    conversion_id TEXT NOT NULL,
    amount_vnd INTEGER NOT NULL CHECK (amount_vnd > 0),
    created_at TEXT NOT NULL,
    UNIQUE (payout_id, conversion_id)
);
CREATE INDEX IF NOT EXISTS idx_payout_allocations_conv ON payout_allocations(conversion_id);
CREATE TRIGGER IF NOT EXISTS payout_allocations_no_update BEFORE UPDATE ON payout_allocations
BEGIN SELECT RAISE(ABORT, 'payout_allocations is append-only'); END;
CREATE TRIGGER IF NOT EXISTS payout_allocations_no_delete BEFORE DELETE ON payout_allocations
BEGIN SELECT RAISE(ABORT, 'payout_allocations is append-only'); END;

-- Mọi thay đổi trạng thái yêu cầu rút, kèm người làm, lý do, chứng từ. Chỉ thêm. idempotency_key chặn ghi lặp.
CREATE TABLE IF NOT EXISTS payout_events (
    id INTEGER PRIMARY KEY,
    payout_id INTEGER NOT NULL REFERENCES cashback_payouts(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    note TEXT,
    evidence_ref TEXT,
    version INTEGER NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payout_events_payout ON payout_events(payout_id);
CREATE TRIGGER IF NOT EXISTS payout_events_no_update BEFORE UPDATE ON payout_events
BEGIN SELECT RAISE(ABORT, 'payout_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS payout_events_no_delete BEFORE DELETE ON payout_events
BEGIN SELECT RAISE(ABORT, 'payout_events is append-only'); END;

-- Lịch sử tài khoản nhận tiền. Không lưu số đầy đủ: 4 số cuối + sha256 để nhận ra trùng / đổi.
CREATE TABLE IF NOT EXISTS bank_account_history (
    id INTEGER PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL,
    bank_code TEXT NOT NULL,
    account_last4 TEXT NOT NULL,
    account_sha TEXT NOT NULL,
    account_name TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('add', 'change')),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bank_history_sha ON bank_account_history(account_sha);
CREATE TRIGGER IF NOT EXISTS bank_account_history_no_update BEFORE UPDATE ON bank_account_history
BEGIN SELECT RAISE(ABORT, 'bank_account_history is append-only'); END;
CREATE TRIGGER IF NOT EXISTS bank_account_history_no_delete BEFORE DELETE ON bank_account_history
BEGIN SELECT RAISE(ABORT, 'bank_account_history is append-only'); END;

-- Xác minh thủ công có bằng chứng, gắn với đúng tài khoản (sha). Đổi tài khoản thì về UNVERIFIED.
-- Tạo được mã QR không phải là xác minh.
CREATE TABLE IF NOT EXISTS bank_account_verifications (
    id INTEGER PRIMARY KEY,
    telegram_user_id INTEGER NOT NULL,
    account_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED', 'REJECTED')),
    method TEXT NOT NULL,
    evidence_ref TEXT NOT NULL CHECK (length(evidence_ref) >= 4),
    decided_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS bank_account_verifications_no_update BEFORE UPDATE ON bank_account_verifications
BEGIN SELECT RAISE(ABORT, 'bank_account_verifications is append-only'); END;
CREATE TRIGGER IF NOT EXISTS bank_account_verifications_no_delete BEFORE DELETE ON bank_account_verifications
BEGIN SELECT RAISE(ABORT, 'bank_account_verifications is append-only'); END;

-- Quyết định chính sách cần trước khi chi (thuế, thu hồi, điều khoản chi trả, xác minh tài khoản, hạn mức,
-- quy trình chuyển khoản). Dòng mới nhất mỗi chủ đề có hiệu lực. Bot không có nút duyệt; APPROVED cần người
-- duyệt và tham chiếu. Không phải điều kiện mở khoá cũ: khoá shopee_settlements / payout_tax_policies vẫn đứng.
CREATE TABLE IF NOT EXISTS payout_policy_decisions (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL CHECK (topic IN
        ('tax', 'clawback', 'payout_terms', 'bank_verification', 'payment_limits', 'manual_payment')),
    status TEXT NOT NULL CHECK (status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED', 'REVOKED')),
    summary TEXT NOT NULL,
    reference TEXT,
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (status != 'APPROVED' OR (reference IS NOT NULL AND decided_by IS NOT NULL AND decided_at IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS payout_policy_decisions_no_update BEFORE UPDATE ON payout_policy_decisions
BEGIN SELECT RAISE(ABORT, 'payout_policy_decisions is append-only'); END;
CREATE TRIGGER IF NOT EXISTS payout_policy_decisions_no_delete BEFORE DELETE ON payout_policy_decisions
BEGIN SELECT RAISE(ABORT, 'payout_policy_decisions is append-only'); END;

-- Hạn mức rút. Dòng mới nhất có hiệu lực; chỉ ACTIVE có người duyệt mới được dùng. Mặc định không có dòng nào.
CREATE TABLE IF NOT EXISTS payout_limit_policies (
    id INTEGER PRIMARY KEY,
    min_vnd INTEGER NOT NULL CHECK (min_vnd > 0),
    max_per_request_vnd INTEGER NOT NULL CHECK (max_per_request_vnd >= min_vnd),
    daily_total_vnd INTEGER NOT NULL CHECK (daily_total_vnd >= max_per_request_vnd),
    monthly_total_vnd INTEGER NOT NULL CHECK (monthly_total_vnd >= daily_total_vnd),
    max_open_per_user INTEGER NOT NULL DEFAULT 1 CHECK (max_open_per_user = 1),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'PENDING_APPROVAL', 'ACTIVE', 'INACTIVE')),
    created_by TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (status != 'ACTIVE' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS payout_limit_policies_no_update BEFORE UPDATE ON payout_limit_policies
BEGIN SELECT RAISE(ABORT, 'payout_limit_policies is append-only'); END;
CREATE TRIGGER IF NOT EXISTS payout_limit_policies_no_delete BEFORE DELETE ON payout_limit_policies
BEGIN SELECT RAISE(ABORT, 'payout_limit_policies is append-only'); END;

-- Tuỳ chọn thông báo của từng khách (PLAN-079). Chưa có dòng = mặc định bật; cờ toàn cục vẫn quyết định
-- thông báo đơn hàng có được gửi hay không.
-- PLAN-080: lịch tự đồng bộ Shopee và khoá một lượt chạy (single flight). Một dòng id = 1.
-- Lease: lượt nào giữ lease_owner mới được gọi Shopee và ghi kết quả; hết lease_expires_at thì lượt khác thu hồi.
CREATE TABLE IF NOT EXISTS shopee_sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    interval_minutes INTEGER,
    paused INTEGER NOT NULL DEFAULT 0,
    paused_at TEXT,
    paused_by INTEGER,
    next_due_at TEXT,
    last_scheduled_at TEXT,
    last_started_at TEXT,
    last_finished_at TEXT,
    last_success_at TEXT,
    last_result TEXT,
    last_run_id INTEGER,
    last_error_category TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    needs_auth_since TEXT,
    last_success_window_start TEXT,
    last_success_window_end TEXT,
    lease_owner TEXT,
    lease_run_id INTEGER,
    lease_trigger TEXT,
    lease_started_at TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    updated_at TEXT NOT NULL
);

-- PLAN-080: sự cố đồng bộ (cookie, lỗi liên tiếp, định dạng Shopee đổi). Một sự cố mở một lần, báo admin một lần,
-- nhắc lại tối đa mỗi 24 giờ, báo khi phục hồi.
CREATE TABLE IF NOT EXISTS shopee_sync_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    resolved_at TEXT,
    failures INTEGER NOT NULL DEFAULT 1,
    last_alert_at TEXT,
    alerts INTEGER NOT NULL DEFAULT 0,
    first_run_id INTEGER,
    last_run_id INTEGER,
    summary TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_incident_open ON shopee_sync_incidents((1)) WHERE resolved_at IS NULL;

-- PLAN-081 (ADR-058): theo dõi đơn qua bot đang chờ xác minh khi ra khỏi khung đồng bộ 30 ngày.
-- Lớp riêng: KHÔNG thay validation_status / settlement_status / sổ ví; ví và payout không đọc bảng này.
CREATE TABLE IF NOT EXISTS conversion_reconciliation (
    conversion_id TEXT PRIMARY KEY REFERENCES shopee_conversions(conversion_id),
    tracking_status TEXT NOT NULL CHECK (tracking_status IN (
        'OBSERVED_RECENTLY', 'APPROACHING_WINDOW', 'OUTSIDE_WINDOW_UNVERIFIED', 'RECONCILIATION_REQUIRED', 'RECONCILED'
    )),
    reason TEXT,
    next_action TEXT,
    missed_runs INTEGER NOT NULL DEFAULT 0,
    last_run_id INTEGER,
    status_since TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversion_reconciliation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversion_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    reason TEXT,
    run_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS conversion_reconciliation_events_no_update
BEFORE UPDATE ON conversion_reconciliation_events
BEGIN SELECT RAISE(ABORT, 'conversion_reconciliation_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS conversion_reconciliation_events_no_delete
BEFORE DELETE ON conversion_reconciliation_events
BEGIN SELECT RAISE(ABORT, 'conversion_reconciliation_events is append-only'); END;

CREATE TABLE IF NOT EXISTS customer_notification_prefs (
    telegram_user_id INTEGER PRIMARY KEY,
    orders INTEGER NOT NULL DEFAULT 1,
    updates INTEGER NOT NULL DEFAULT 1,
    support INTEGER NOT NULL DEFAULT 1,
    wallet INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

-- PLAN-082: khách kênh khác Telegram mang ID nội bộ âm, đi qua cùng sổ link / ví / đối soát.
CREATE TABLE IF NOT EXISTS channel_identities (
    internal_user_id INTEGER PRIMARY KEY CHECK (internal_user_id < 0),
    channel TEXT NOT NULL,
    external_id TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (channel, external_id)
);

-- Tin Zalo đã nhận (chống xử lý trùng theo message_id). −id là update_id cho lõi. Không lưu nội dung khách gửi;
-- reply_json là câu trả lời của bot, để gửi lại khi lỗi mạng mà không chạy lại thao tác.
CREATE TABLE IF NOT EXISTS zalo_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    internal_user_id INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('received', 'replied', 'retry', 'failed')),
    reply_json TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_retry_at TEXT,
    received_at TEXT NOT NULL,
    replied_at TEXT
);

-- Update Telegram xử lý lỗi (hardening P0-4). Khoá chính là update_id: không ghi trùng.
-- retrying: còn thử lại, chưa tiến offset. quarantined: đã cách ly, offset đi tiếp, admin xem.
CREATE TABLE IF NOT EXISTS failed_updates (
    telegram_update_id INTEGER PRIMARY KEY,
    update_type TEXT NOT NULL,
    telegram_user_id INTEGER,
    category TEXT NOT NULL,
    error_code TEXT NOT NULL,
    error_detail TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('retrying', 'quarantined', 'resolved')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

-- Khoá tài chính ở tầng DB (Production Safety Hardening V1): chưa có bảng bằng chứng Shopee đã trả
-- và chính sách thuế người nhận thì không ghi được khoản 'available', yêu cầu rút mới hay trạng thái 'paid',
-- kể cả khi gọi SQL trực tiếp. Điều kiện chi tiết (có dòng, đủ quỹ, không gian lận) ở payout_gate.py.
CREATE TRIGGER IF NOT EXISTS financial_lock_entry_insert BEFORE INSERT ON cashback_entries
WHEN NEW.status = 'available' AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE TRIGGER IF NOT EXISTS financial_lock_entry_update BEFORE UPDATE OF status ON cashback_entries
WHEN NEW.status = 'available' AND OLD.status != 'available' AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE TRIGGER IF NOT EXISTS financial_lock_payout_insert BEFORE INSERT ON cashback_payouts
WHEN NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies')
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

CREATE TRIGGER IF NOT EXISTS financial_lock_payout_paid BEFORE UPDATE OF status ON cashback_payouts
WHEN NEW.status = 'paid' AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

-- PLAN-078: các trạng thái đưa tiền ra (duyệt chi, đang chuyển, đã gửi, đã trả) cũng bị khoá như 'paid'.
CREATE TRIGGER IF NOT EXISTS financial_lock_payout_progress BEFORE UPDATE OF status ON cashback_payouts
WHEN NEW.status IN ('approved_for_payment', 'processing', 'sent_unconfirmed', 'paid_confirmed') AND (
    NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'shopee_settlements')
    OR NOT EXISTS (SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payout_tax_policies'))
BEGIN SELECT RAISE(ABORT, 'financial_lock: no settlement evidence'); END;

-- Đã trả chỉ ghi được từ «đã gửi, chờ xác nhận» và khi đã có sự kiện kèm chứng từ ngân hàng.
CREATE TRIGGER IF NOT EXISTS payout_paid_needs_evidence BEFORE UPDATE OF status ON cashback_payouts
WHEN NEW.status = 'paid_confirmed' AND (OLD.status != 'sent_unconfirmed' OR NOT EXISTS (
    SELECT 1 FROM payout_events WHERE payout_id = NEW.id AND to_status = 'paid_confirmed'
    AND evidence_ref IS NOT NULL AND length(evidence_ref) >= 4))
BEGIN SELECT RAISE(ABORT, 'payout: paid needs bank evidence after sent'); END;

CREATE INDEX IF NOT EXISTS idx_cashback_entries_user ON cashback_entries(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_cashback_payouts_user ON cashback_payouts(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_shopee_conversions_sub_id ON shopee_conversions(sub_id);
CREATE INDEX IF NOT EXISTS idx_shopee_conversions_user_id ON shopee_conversions(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_shopee_clicks_sub_id ON shopee_clicks(sub_id);
"""


# Số liệu đối soát thêm (PLAN-066), theo các ô của Addlivetag. NULL: dòng kéo trước PLAN-066.
SHOPEE_CONVERSION_COLUMNS = (
    ("gmv_vnd", "INTEGER"),
    ("item_qty", "INTEGER"),
    ("item_name", "TEXT"),
    ("mcn_fee_vnd", "INTEGER"),
    ("complete_time", "TEXT"),
    ("validation_month", "TEXT"),
)

# Dữ liệu sản phẩm thêm cho thống kê (PLAN-064). Cho phép NULL: link cũ không có.
PRODUCT_INSIGHT_COLUMNS = (
    ("cat_name", "TEXT"),
    ("shop_name", "TEXT"),
    ("seller_commission_vnd", "INTEGER"),
    ("shopee_commission_vnd", "INTEGER"),
    ("commission_rate_bps", "INTEGER"),
    ("is_xtra", "INTEGER"),
    ("is_capped", "INTEGER"),
)


# Trạng thái duyệt hoa hồng (PLAN-074). Ba trạng thái tách cột: order_status / validation_status / settlement_status.
VALIDATION_COLUMNS = (
    ("first_commission_vnd", "INTEGER"),
    ("validation_status", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
    ("validation_reason", "TEXT"),
    ("fraud_flag", "INTEGER"),
    ("affiliate_item_status", "TEXT"),
    ("checkout_status", "TEXT"),
    ("settlement_status", f"TEXT NOT NULL DEFAULT '{SETTLEMENT_NOT_VERIFIED}'"),
    ("validation_source", "TEXT"),
    ("validation_confidence", "TEXT"),
    ("evidence_ref", "TEXT"),
    ("review_status", "TEXT NOT NULL DEFAULT 'none'"),
    ("reviewed_by", "INTEGER"),
    ("reviewed_at", "TEXT"),
)


@dataclass(frozen=True)
class ConversionChange:
    field: str
    old: str | None
    new: str | None
    significant: bool


@dataclass(frozen=True)
class ConversionResult:
    is_new: bool
    is_matched: bool
    matched_link_id: int | None
    telegram_user_id: int | None
    changes: tuple[ConversionChange, ...]
    validation_status: str


def _text(value) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(moment: datetime | None = None) -> str:
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _backfill_validation(conn: sqlite3.Connection) -> None:
    """Dòng có từ trước PLAN-074: chép hoa hồng hiện tại làm mốc đầu, đánh giá lại từ raw_json đã lưu.

    Không ghi lịch sử (đây là mốc, không phải thay đổi), không bao giờ ra APPROVED hay SETTLED.
    Chạy lại nhiều lần không đổi gì: chỉ đụng dòng còn UNKNOWN chưa có nguồn.
    """
    rows = conn.execute(
        "SELECT conversion_id, raw_json, net_commission_vnd, gross_commission_vnd FROM shopee_conversions "
        "WHERE validation_source IS NULL"
    ).fetchall()
    for row in rows:
        commission = row["net_commission_vnd"] if row["net_commission_vnd"] is not None else row["gross_commission_vnd"]
        found = assess_raw(row["raw_json"], commission)
        conn.execute(
            """
            UPDATE shopee_conversions SET
                first_commission_vnd = COALESCE(first_commission_vnd, net_commission_vnd),
                validation_status = ?, validation_reason = ?, fraud_flag = ?, affiliate_item_status = ?,
                checkout_status = ?, validation_source = ?, validation_confidence = ?,
                review_status = CASE WHEN ? = 'NEEDS_REVIEW' THEN 'needs_review' ELSE review_status END
            WHERE conversion_id = ?
            """,
            (
                found.status, found.reason, found.fraud_flag, found.item_statuses, found.checkout_status,
                SOURCE_REPORT, CONFIDENCE_INFERRED, found.status, row["conversion_id"],
            ),
        )


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


@dataclass(frozen=True)
class LinkRow:
    id: int
    telegram_update_id: int | None
    telegram_user_id: int
    sub_id: str | None
    affiliate_url: str | None
    item_id: int | None
    product_name: str | None
    price_vnd: int | None
    estimated_commission: int | None
    estimated_cashback: int | None
    cashback_rate_percent: int | None
    link_status: str
    reject_reason: str | None
    estimate_policy: str | None = None


def insert_snapshot(conn: sqlite3.Connection, link_id: int, snapshot: dict) -> None:
    row = {"link_id": link_id, **snapshot}
    names = ", ".join(row)
    conn.execute(
        f"INSERT INTO link_policy_snapshots ({names}) VALUES ({', '.join('?' for _ in row)})",
        list(row.values()),
    )


# Bảng huỷ lịch chính sách (PLAN-076). Admin cũng chạy file này khi mở kết nối, như 004–006.
CANCEL_SCHEMA_PATH = Path(__file__).resolve().parent / "migrations" / "008_policy_cancellations.sql"


# Cột thêm cho hàng đợi gửi (PLAN-079). status: pending, sending, sent, retry, failed, suppressed, unknown.
# PLAN-081: nguồn của last_seen_at khi ghi từ lượt đồng bộ (report/list, khung 30 ngày theo giờ mua) và khi tra
# khung hẹp quanh giờ mua của một đơn đã ra khung (Phương án A).
SEEN_SOURCE = "report_list_30d"
NARROW_SOURCE = "report_list_narrow"
SYNC_RUN_COLUMNS = (
    ("lease_owner", "TEXT"),
    ("error_category", "TEXT"),
    ("pages_fetched", "INTEGER NOT NULL DEFAULT 0"),
    ("pages_failed", "INTEGER NOT NULL DEFAULT 0"),
    ("conversions_new", "INTEGER NOT NULL DEFAULT 0"),
    ("conversions_changed", "INTEGER NOT NULL DEFAULT 0"),
    ("conversions_unchanged", "INTEGER NOT NULL DEFAULT 0"),
    ("invalid_records", "INTEGER NOT NULL DEFAULT 0"),
    ("notifications_queued", "INTEGER NOT NULL DEFAULT 0"),
    ("notifications_suppressed", "INTEGER NOT NULL DEFAULT 0"),
    ("window_start", "TEXT"),
    ("window_end", "TEXT"),
)
NOTIFICATION_COLUMNS = (
    ("audience", "TEXT NOT NULL DEFAULT 'admin'"),
    ("category", "TEXT"),
    ("next_retry_at", "TEXT"),
    ("telegram_message_id", "INTEGER"),
    ("reply_markup_json", "TEXT"),
    ("source_ref", "TEXT"),
)
# Tin gửi khách đã có trước PLAN-079 (đi chung bảng): đối tượng và loại để áp tuỳ chọn của khách.
CUSTOMER_EVENT_TYPES = {"WALLET_ENTRY": "wallet", "PAYOUT_DECIDED": "wallet", "SUPPORT_CUSTOMER": "support"}


def enqueue_event(
    conn: sqlite3.Connection,
    *,
    event_key: str,
    event_type: str,
    chat_id: int,
    message_html: str,
    audience: str = "admin",
    category: str | None = None,
    reply_markup_json: str | None = None,
    source_ref: str | None = None,
    suppressed_reason: str | None = None,
    now: str | None = None,
) -> bool:
    """Ghi một tin vào hàng đợi trong transaction của người gọi. Trùng event_key thì bỏ qua (False).

    suppressed_reason: ghi để theo dõi nhưng không bao giờ gửi (cờ tắt, khách tắt, đơn lịch sử…).
    """
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO admin_notifications
            (event_key, event_type, chat_id, message_html, status, attempt_count, last_error, created_at,
             audience, category, reply_markup_json, source_ref)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_key, event_type, chat_id, message_html,
            "suppressed" if suppressed_reason else "pending", suppressed_reason, now or _utc_now(),
            audience, category, reply_markup_json, source_ref,
        ),
    )
    return cursor.rowcount == 1


def _backfill_bank_history(conn: sqlite3.Connection) -> None:
    """Tài khoản khai trước PLAN-078 chưa có lịch sử: ghi một dòng 'add' (4 số cuối + sha), một lần."""
    rows = conn.execute(
        """
        SELECT b.* FROM bank_accounts b
        WHERE NOT EXISTS (SELECT 1 FROM bank_account_history h WHERE h.telegram_user_id = b.telegram_user_id)
        """
    ).fetchall()
    for row in rows:
        sha = hashlib.sha256(f"{row['bank_code']}:{row['account_no']}".encode()).hexdigest()
        conn.execute(
            """
            INSERT INTO bank_account_history (telegram_user_id, bank_code, account_last4, account_sha, account_name,
                action, created_at)
            VALUES (?, ?, ?, ?, ?, 'add', ?)
            """,
            (row["telegram_user_id"], row["bank_code"], str(row["account_no"])[-4:], sha, row["account_name"], row["updated_at"]),
        )


class TrackingRepository:
    def __init__(self, path: str):
        self.path = path
        # PLAN-079: hàm gọi trong transaction ghi đơn (sau khi ghi lịch sử thay đổi), để sinh sự kiện thông báo
        # cùng transaction. Lỗi trong hook không làm hỏng việc ghi đơn (SAVEPOINT).
        self.conversion_hooks: list = []

    def column_names(self, table: str) -> set[str]:
        with self.connect() as conn:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def connect(self) -> sqlite3.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        # PLAN-080: đồng bộ chạy ở luồng nền; chờ khoá ghi lâu hơn mặc định 5 giây thay vì báo lỗi ngay.
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executescript(CANCEL_SCHEMA_PATH.read_text(encoding="utf-8"))
            columns = {row[1] for row in conn.execute("PRAGMA table_info(link_requests)")}
            if "delivery_status" not in columns:
                conn.execute("ALTER TABLE link_requests ADD COLUMN delivery_status TEXT")
            _add_column(conn, "link_requests", "delivery_attempts", "INTEGER NOT NULL DEFAULT 0")
            _add_column(conn, "link_requests", "next_retry_at", "TEXT")
            _add_column(conn, "link_requests", "last_delivery_error", "TEXT")
            _add_column(conn, "telegram_users", "rate_window_start", "TEXT")
            _add_column(conn, "telegram_users", "rate_count", "INTEGER NOT NULL DEFAULT 0")
            _add_column(conn, "telegram_users", "cooldown_until", "TEXT")
            _add_column(conn, "outbound_messages", "edit_message_id", "INTEGER")
            _add_column(conn, "outbound_messages", "reply_markup_json", "TEXT")
            for column, ddl in PRODUCT_INSIGHT_COLUMNS:
                _add_column(conn, "link_requests", column, ddl)
            for column, ddl in SHOPEE_CONVERSION_COLUMNS:
                _add_column(conn, "shopee_conversions", column, ddl)
            for column, ddl in VALIDATION_COLUMNS:
                _add_column(conn, "shopee_conversions", column, ddl)
            _backfill_validation(conn)
            # Phần admin chịu trên từng đơn: phí và dự phòng thuế (admin còn = HH − hoàn − phí − thuế).
            _add_column(conn, "cashback_entries", "fee_vnd", "INTEGER NOT NULL DEFAULT 0")
            _add_column(conn, "cashback_entries", "tax_vnd", "INTEGER NOT NULL DEFAULT 0")
            # PLAN-078: số phiên bản (chống callback cũ), khoá chống gửi lặp, dấu tài khoản đã chụp.
            _add_column(conn, "cashback_payouts", "version", "INTEGER NOT NULL DEFAULT 1")
            _add_column(conn, "cashback_payouts", "idempotency_key", "TEXT")
            _add_column(conn, "cashback_payouts", "account_sha", "TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_payout_idempotency ON cashback_payouts(idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
            _backfill_bank_history(conn)
            # PLAN-079: admin_notifications là hàng đợi gửi chung cho admin và khách (ADR-056).
            for column, ddl in NOTIFICATION_COLUMNS:
                _add_column(conn, "admin_notifications", column, ddl)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_admin_notifications_due ON admin_notifications(status, next_retry_at)"
            )
            _add_column(conn, "telegram_users", "notify_blocked_at", "TEXT")
            # PLAN-080: số liệu từng lượt đồng bộ.
            for column, ddl in SYNC_RUN_COLUMNS:
                _add_column(conn, "shopee_sync_runs", column, ddl)
            # PLAN-081: lần cuối đơn có trong response của một lượt đồng bộ. Dòng cũ lấy từ updated_at (trước PLAN-081
            # updated_at chỉ được ghi khi lượt đồng bộ thấy đơn), có đánh dấu nguồn để không lẫn với giá trị thật.
            _add_column(conn, "shopee_conversions", "last_seen_at", "TEXT")
            _add_column(conn, "shopee_conversions", "last_seen_run_id", "INTEGER")
            _add_column(conn, "shopee_conversions", "last_seen_source", "TEXT")
            # Phương án A: lần tra khung hẹp gần nhất của đơn đang theo dõi.
            _add_column(conn, "conversion_reconciliation", "last_attempt_at", "TEXT")
            _add_column(conn, "conversion_reconciliation", "last_attempt_result", "TEXT")
            conn.execute(
                "UPDATE shopee_conversions SET last_seen_at = updated_at, last_seen_source = 'backfill_updated_at' "
                "WHERE last_seen_at IS NULL AND last_seen_source IS NULL AND updated_at IS NOT NULL"
            )
            # Mỗi khách tối đa một yêu cầu còn giữ tiền: chặn rút trùng ở tầng DB.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_payout_one_open ON cashback_payouts(telegram_user_id) "
                "WHERE status IN ('requested', 'under_review', 'approved_for_payment', 'processing', "
                "'sent_unconfirmed', 'needs_review')"
            )

    def upsert_user(self, telegram_user_id: int, username: str | None) -> bool:
        now = _utc_now()
        with self.connect() as conn:
            existed = conn.execute(
                "SELECT 1 FROM telegram_users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone() is not None
            conn.execute(
                """
                INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    username = excluded.username,
                    last_seen_at = excluded.last_seen_at
                """,
                (telegram_user_id, username, now, now),
            )
            # Khách nhắn lại bot: không còn bị coi là đã chặn bot (PLAN-079).
            if "notify_blocked_at" in {row[1] for row in conn.execute("PRAGMA table_info(telegram_users)")}:
                conn.execute(
                    "UPDATE telegram_users SET notify_blocked_at = NULL WHERE telegram_user_id = ? AND notify_blocked_at IS NOT NULL",
                    (telegram_user_id,),
                )
        return not existed

    def get_user(self, telegram_user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT telegram_user_id, username, created_at, last_seen_at FROM telegram_users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()

    def count_users(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM telegram_users").fetchone()[0])

    def get_by_update_id(self, update_id: int) -> LinkRow | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM link_requests WHERE telegram_update_id = ?",
                (update_id,),
            ).fetchone()
        return _row(row) if row else None

    def sub_id_exists(self, sub_id: str) -> bool:
        with self.connect() as conn:
            found = conn.execute(
                "SELECT 1 FROM link_requests WHERE sub_id = ?",
                (sub_id,),
            ).fetchone()
        return found is not None

    def insert_created(self, fields: dict, snapshot: dict | None = None, terms: dict | None = None) -> int:
        """snapshot: dòng link_policy_snapshots; terms: dòng link_terms_context (cả hai chưa có link_id).
        Ghi cùng transaction với link."""
        fields = dict(fields)
        fields["delivery_status"] = "pending"
        return self._insert(fields, snapshot, terms)

    def insert_rejected(self, fields: dict) -> int:
        fields = dict(fields)
        fields["link_status"] = "rejected"
        fields.setdefault("sub_id", None)
        fields.setdefault("affiliate_url", None)
        return self._insert(fields)

    def _insert(self, fields: dict, snapshot: dict | None = None, terms: dict | None = None) -> int:
        columns = [
            "telegram_update_id",
            "telegram_user_id",
            "sub_id",
            "original_url",
            "affiliate_url",
            "item_id",
            "shop_id",
            "product_name",
            "price_vnd",
            "estimated_commission",
            "estimated_cashback",
            "cashback_rate_percent",
            "api_status",
            "data_source",
            "product_last_update",
            "link_status",
            "reject_reason",
            "delivery_status",
            "created_at",
        ]
        existing = self.column_names("link_requests")
        if fields.get("estimate_policy") and "estimate_policy" in existing:
            columns.append("estimate_policy")
        columns += [name for name, _ddl in PRODUCT_INSIGHT_COLUMNS if name in existing and name in fields]
        payload = {key: fields.get(key) for key in columns}
        payload["created_at"] = payload["created_at"] or _utc_now()
        placeholders = ", ".join("?" for _ in columns)
        with self.connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO link_requests ({', '.join(columns)}) VALUES ({placeholders})",
                [payload[key] for key in columns],
            )
            link_id = int(cursor.lastrowid)
            if snapshot is not None:
                insert_snapshot(conn, link_id, snapshot)
            if terms is not None:
                row = {"link_id": link_id, **terms}
                conn.execute(
                    f"INSERT INTO link_terms_context ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                    list(row.values()),
                )
            return link_id

    def get_offset(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM bot_state WHERE key = 'update_offset'"
            ).fetchone()
        return int(row["value"]) if row else 0

    def mark_delivered(self, update_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE link_requests
                SET delivery_status = 'sent',
                    next_retry_at = NULL,
                    last_delivery_error = NULL
                WHERE telegram_update_id = ? AND link_status = 'created'
                """,
                (update_id,),
            )

    def mark_link_delivery(
        self,
        update_id: int,
        status: str,
        attempts: int,
        next_retry_at: str | None,
        error_kind: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE link_requests
                SET delivery_status = ?,
                    delivery_attempts = ?,
                    next_retry_at = ?,
                    last_delivery_error = ?
                WHERE telegram_update_id = ?
                """,
                (status, attempts, next_retry_at, error_kind, update_id),
            )

    def consume_link_attempt(
        self,
        telegram_user_id: int,
        now: datetime,
        limit: int,
        window_sec: int,
        cooldown_sec: int,
    ) -> bool:
        """True nếu còn lượt. False thì không tạo link. limit <= 0 là tắt giới hạn."""
        if limit <= 0:
            return True
        moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        moment = moment.astimezone(timezone.utc)
        now_text = _stamp(moment)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT rate_window_start, rate_count, cooldown_until
                FROM telegram_users WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
            if row is None:
                return True
            cooldown_until = row["cooldown_until"]
            if cooldown_until and cooldown_until > now_text:
                return False
            window_start = row["rate_window_start"]
            count = int(row["rate_count"] or 0)
            expired = True
            if window_start:
                started = datetime.strptime(window_start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                expired = (moment - started).total_seconds() >= window_sec
            if expired or (cooldown_until and cooldown_until <= now_text):
                conn.execute(
                    """
                    UPDATE telegram_users
                    SET rate_window_start = ?, rate_count = 1, cooldown_until = NULL
                    WHERE telegram_user_id = ?
                    """,
                    (now_text, telegram_user_id),
                )
                return True
            if count >= limit:
                until = _stamp(moment + timedelta(seconds=cooldown_sec))
                conn.execute(
                    """
                    UPDATE telegram_users
                    SET cooldown_until = ?
                    WHERE telegram_user_id = ?
                    """,
                    (until, telegram_user_id),
                )
                return False
            conn.execute(
                """
                UPDATE telegram_users
                SET rate_count = ?
                WHERE telegram_user_id = ?
                """,
                (count + 1, telegram_user_id),
            )
            return True

    def enqueue_outbound(
        self,
        update_id: int,
        telegram_user_id: int,
        body_html: str,
        button_url: str | None,
        edit_message_id: int | None = None,
        reply_markup_json: str | None = None,
    ) -> sqlite3.Row:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO outbound_messages (
                    telegram_update_id, telegram_user_id, body_html, button_url, edit_message_id,
                    reply_markup_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(telegram_update_id) DO NOTHING
                """,
                (update_id, telegram_user_id, body_html, button_url, edit_message_id, reply_markup_json, _utc_now()),
            )
            return conn.execute(
                "SELECT * FROM outbound_messages WHERE telegram_update_id = ?",
                (update_id,),
            ).fetchone()

    def get_outbound(self, update_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM outbound_messages WHERE telegram_update_id = ?",
                (update_id,),
            ).fetchone()

    def list_due_outbound(self, now: datetime, limit: int) -> list[sqlite3.Row]:
        now_text = _stamp(now)
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT * FROM outbound_messages
                WHERE status IN ('pending', 'retry', 'ambiguous', 'sending')
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (now_text, limit),
            ).fetchall()

    def mark_outbound_sending(self, outbound_id: int) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_messages
                SET status = 'sending',
                    attempt_count = attempt_count + 1,
                    next_retry_at = NULL
                WHERE id = ?
                """,
                (outbound_id,),
            )
            row = conn.execute(
                "SELECT attempt_count FROM outbound_messages WHERE id = ?",
                (outbound_id,),
            ).fetchone()
        return int(row["attempt_count"])

    def mark_outbound_sent(self, outbound_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_messages
                SET status = 'sent', sent_at = ?, last_error = NULL, next_retry_at = NULL
                WHERE id = ?
                """,
                (_utc_now(), outbound_id),
            )

    def schedule_outbound(
        self,
        outbound_id: int,
        status: str,
        next_retry_at: str | None,
        error_kind: str,
        attempts: int,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbound_messages
                SET status = ?, next_retry_at = ?, last_error = ?, attempt_count = ?
                WHERE id = ?
                """,
                (status, next_retry_at, error_kind[:40], attempts, outbound_id),
            )

    def enqueue_admin_event(self, event_key: str, event_type: str, chat_id: int, message_html: str) -> bool:
        """Tin vào hàng đợi chung. Loại tin gửi khách có sẵn (ví, chi trả, hỗ trợ) được gắn audience=customer."""
        category = CUSTOMER_EVENT_TYPES.get(event_type)
        with self.connect() as conn:
            return enqueue_event(
                conn, event_key=event_key, event_type=event_type, chat_id=chat_id, message_html=message_html,
                audience="customer" if category else "admin", category=category,
            )

    def list_pending_admin_events(self, limit: int = 10, max_attempts: int = 5, now: str | None = None,
                                  audiences: tuple[str, ...] = ("admin", "customer"),
                                  channel: str = "telegram") -> list[sqlite3.Row]:
        """Tin tới lượt gửi: pending, hoặc retry đã tới giờ. Không lấy sending / unknown / failed / suppressed.

        PLAN-082: Telegram lấy tin admin và tin khách ID dương; Zalo chỉ lấy tin khách ID âm.
        """
        marks = ", ".join("?" for _ in audiences)
        scope = "audience = 'customer' AND chat_id < 0" if channel == "zalo" else "(audience = 'admin' OR chat_id > 0)"
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM admin_notifications
                WHERE status IN ('pending', 'retry') AND attempt_count < ? AND audience IN ({marks})
                  AND {scope}
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY id ASC
                LIMIT ?
                """,
                (max_attempts, *audiences, now or _utc_now(), limit),
            ).fetchall()

    def claim_admin_event(self, event_id: int) -> bool:
        """Đánh dấu đang gửi trước khi gọi Telegram. Restart giữa chừng thì dòng ở 'sending' → recover_sending."""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE admin_notifications SET status = 'sending', attempt_count = attempt_count + 1, last_attempt_at = ?
                WHERE id = ? AND status IN ('pending', 'retry')
                """,
                (_utc_now(), event_id),
            )
            return cursor.rowcount == 1

    def finish_admin_event(self, event_id: int, status: str, error: str | None = None,
                           next_retry_at: str | None = None, message_id: int | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE admin_notifications
                SET status = ?, last_error = ?, next_retry_at = ?, telegram_message_id = COALESCE(?, telegram_message_id),
                    sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END
                WHERE id = ?
                """,
                (status, None if error is None else error[:120], next_retry_at, message_id, status, _utc_now(), event_id),
            )

    def suppress_admin_event(self, event_id: int, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE admin_notifications SET status = 'suppressed', last_error = ? WHERE id = ? AND status IN ('pending', 'retry')",
                (reason[:120], event_id),
            )

    def notification_mark(self) -> int:
        """Mã dòng lớn nhất của hàng đợi: mốc để đếm tin một lượt đồng bộ sinh ra (PLAN-080)."""
        with self.connect() as conn:
            return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM admin_notifications").fetchone()[0])

    def order_events_after(self, mark: int) -> tuple[int, int]:
        """(chờ gửi, bỏ qua) của tin đơn hàng ghi sau mốc mark: đúng phần của lượt đồng bộ, không lẫn lượt trước."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(status IN ('pending', 'retry', 'sending', 'sent')), 0),
                       COALESCE(SUM(status = 'suppressed'), 0)
                FROM admin_notifications
                WHERE audience = 'customer' AND id > ? AND source_ref LIKE 'conversion:%'
                """,
                (mark,),
            ).fetchone()
        return int(row[0]), int(row[1])

    def recover_sending(self) -> int:
        """Lúc khởi động: tin kẹt ở 'sending' (bot dừng giữa lúc gửi) thành 'unknown'.

        Không tự gửi lại: Telegram có thể đã nhận tin. Admin xem và chủ động gửi lại ở 🔔 Thông báo khách.
        """
        with self.connect() as conn:
            return conn.execute(
                "UPDATE admin_notifications SET status = 'unknown', last_error = 'interrupted_while_sending' "
                "WHERE status = 'sending'"
            ).rowcount

    def mark_admin_event_sent(self, event_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE admin_notifications
                SET status = 'sent',
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    sent_at = ?,
                    last_error = NULL
                WHERE id = ?
                """,
                (_utc_now(), _utc_now(), event_id),
            )

    def mark_admin_event_failed(self, event_id: int, error_code: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE admin_notifications
                SET status = 'pending',
                    attempt_count = attempt_count + 1,
                    last_attempt_at = ?,
                    last_error = ?
                WHERE id = ?
                """,
                (_utc_now(), error_code[:80], event_id),
            )

    def record_update_failure(
        self,
        update_id: int,
        update_type: str,
        telegram_user_id: int | None,
        category: str,
        error_code: str,
        error_detail: str,
    ) -> int:
        """Ghi một lần xử lý lỗi, trả số lần đã lỗi. Lỗi ghi DB thì ném ra: caller không được tiến offset."""
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO failed_updates (
                    telegram_update_id, update_type, telegram_user_id, category, error_code, error_detail,
                    attempt_count, status, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 'retrying', ?, ?)
                ON CONFLICT(telegram_update_id) DO UPDATE SET
                    category = excluded.category,
                    error_code = excluded.error_code,
                    error_detail = excluded.error_detail,
                    attempt_count = failed_updates.attempt_count + 1,
                    status = CASE WHEN failed_updates.status = 'quarantined' THEN 'quarantined' ELSE 'retrying' END,
                    last_seen_at = excluded.last_seen_at
                """,
                (update_id, update_type, telegram_user_id, category, error_code, error_detail, now, now),
            )
            row = conn.execute(
                "SELECT attempt_count FROM failed_updates WHERE telegram_update_id = ?", (update_id,)
            ).fetchone()
        return int(row["attempt_count"])

    def quarantine_update(self, update_id: int) -> None:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE failed_updates SET status = 'quarantined', last_seen_at = ? WHERE telegram_update_id = ?",
                (_utc_now(), update_id),
            )
            if cursor.rowcount != 1:
                raise sqlite3.OperationalError("failed_updates row missing")

    def resolve_update_failure(self, update_id: int) -> None:
        """Update từng lỗi tạm rồi xử lý được: đánh dấu resolved, giữ lịch sử."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE failed_updates SET status = 'resolved', last_seen_at = ? "
                "WHERE telegram_update_id = ? AND status = 'retrying'",
                (_utc_now(), update_id),
            )

    def update_failure(self, update_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM failed_updates WHERE telegram_update_id = ?", (update_id,)).fetchone()

    def count_quarantined_updates(self) -> int:
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM failed_updates WHERE status = 'quarantined'").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row[0])

    def get_state(self, key: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def set_offset(self, offset: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value) VALUES ('update_offset', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(offset),),
            )

    def get_shopee_cookie_status(self) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM shopee_cookies WHERE id = 1").fetchone()
            if row is None:
                return {
                    "status": "disconnected",
                    "account_name": None,
                    "last_sync_at": None,
                    "last_error": None,
                    "updated_at": None,
                }
            return dict(row)

    def update_shopee_cookie_status(
        self,
        status: str,
        account_name: str | None = None,
        last_error: str | None = None,
        last_sync_at: str | None = None,
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO shopee_cookies (id, status, account_name, last_sync_at, last_error, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    account_name = COALESCE(excluded.account_name, shopee_cookies.account_name),
                    last_sync_at = COALESCE(excluded.last_sync_at, shopee_cookies.last_sync_at),
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (status, account_name, last_sync_at, last_error, now),
            )

    def record_shopee_click(
        self,
        click_id: str,
        sub_id: str | None,
        click_time: str | None,
        raw_json: str | None = None,
    ) -> bool:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO shopee_clicks (click_id, sub_id, click_time, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(click_id) DO NOTHING
                """,
                (click_id, sub_id, click_time, raw_json, now),
            )
            return cursor.rowcount > 0

    def record_shopee_conversion(
        self,
        conversion_id: str,
        sub_id: str | None,
        order_sn: str | None,
        order_status: str | None,
        conversion_status: str | None,
        purchase_time: str | None,
        gross_commission_vnd: int | None,
        net_commission_vnd: int | None,
        raw_json: str | None = None,
        details: dict | None = None,
    ) -> tuple[bool, bool, int | None, int | None]:
        """Lưu đơn hàng và đối soát sub_id. Trả về (is_new, is_matched, matched_link_id, telegram_user_id).

        Bản rút gọn của record_conversion_snapshot (giữ cho code và test cũ). Có raw_json thì đánh giá
        trạng thái hoa hồng từ đó.
        """
        assessment = assess_raw(raw_json, net_commission_vnd if net_commission_vnd is not None else gross_commission_vnd) if raw_json else None
        result = self.record_conversion_snapshot(
            conversion_id=conversion_id,
            sub_id=sub_id,
            order_sn=order_sn,
            order_status=order_status,
            conversion_status=conversion_status,
            purchase_time=purchase_time,
            gross_commission_vnd=gross_commission_vnd,
            net_commission_vnd=net_commission_vnd,
            raw_json=raw_json,
            details=details,
            assessment=assessment,
        )
        return result.is_new, result.is_matched, result.matched_link_id, result.telegram_user_id

    def record_conversion_snapshot(
        self,
        conversion_id: str,
        sub_id: str | None,
        order_sn: str | None,
        order_status: str | None,
        conversion_status: str | None,
        purchase_time: str | None,
        gross_commission_vnd: int | None,
        net_commission_vnd: int | None,
        raw_json: str | None = None,
        details: dict | None = None,
        assessment: Assessment | None = None,
        sync_run_id: int | None = None,
        seen_source: str = SEEN_SOURCE,
    ) -> ConversionResult:
        """Ghi một lần Shopee báo về đơn (PLAN-074), trong một transaction.

        - Người thụ hưởng giữ theo lần gắn đầu tiên; Sub ID lần sau trỏ link khác → ghi lịch sử, cần kiểm tra.
        - Giá trị thiếu (None) không ghi đè giá trị đã có; hoa hồng không bị đưa về 0 vì response thiếu field.
        - Chỉ ghi lịch sử khi giá trị thật sự đổi; đồng bộ lại y hệt không tạo dòng.
        - Không bao giờ gán APPROVED hay SETTLED ở đây.
        """
        extra = {name: (details or {}).get(name) for name, _ddl in SHOPEE_CONVERSION_COLUMNS}
        now = _utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prev = conn.execute("SELECT * FROM shopee_conversions WHERE conversion_id = ?", (conversion_id,)).fetchone()
            found_link, found_user = None, None
            if sub_id:
                link = conn.execute(
                    "SELECT id, telegram_user_id FROM link_requests WHERE sub_id = ? ORDER BY id DESC LIMIT 1",
                    (sub_id,),
                ).fetchone()
                if link is not None:
                    found_link, found_user = int(link["id"]), int(link["telegram_user_id"])

            def keep(column: str, new):
                return new if new is not None else (None if prev is None else prev[column])

            changes: list[ConversionChange] = []
            review = "none" if prev is None else (prev["review_status"] or "none")
            matched_link_id, telegram_user_id = found_link, found_user
            if prev is not None and prev["matched_link_id"] is not None:
                matched_link_id, telegram_user_id = prev["matched_link_id"], prev["telegram_user_id"]
                if found_link is not None and found_link != prev["matched_link_id"]:
                    changes.append(ConversionChange("attribution", str(prev["matched_link_id"]), str(found_link), True))

            net = keep("net_commission_vnd", net_commission_vnd)
            gross = keep("gross_commission_vnd", gross_commission_vnd)
            status = keep("order_status", order_status or None)
            if assessment is not None and assessment.complete:
                validation, reason = assessment.status, assessment.reason
                fraud_flag, item_statuses = assessment.fraud_flag, assessment.item_statuses
                checkout = assessment.checkout_status
                if prev is not None and is_regression(prev["validation_status"], validation):
                    validation, reason = NEEDS_REVIEW, "status_regression"
            elif prev is not None:
                validation, reason = prev["validation_status"], prev["validation_reason"]
                fraud_flag, item_statuses, checkout = prev["fraud_flag"], prev["affiliate_item_status"], prev["checkout_status"]
            else:
                validation = UNKNOWN if assessment is None else assessment.status
                reason = None if assessment is None else assessment.reason
                fraud_flag = None if assessment is None else assessment.fraud_flag
                item_statuses = None if assessment is None else assessment.item_statuses
                checkout = None if assessment is None else assessment.checkout_status

            if prev is not None:
                old_net = prev["net_commission_vnd"]
                if net_commission_vnd is not None and net_commission_vnd != old_net:
                    changes.append(
                        ConversionChange("net_commission_vnd", _text(old_net), _text(net), is_significant_drop(old_net, net))
                    )
                if order_status and order_status != prev["order_status"]:
                    changes.append(
                        ConversionChange("order_status", prev["order_status"], order_status, "CANCEL" in order_status.upper())
                    )
                if validation != prev["validation_status"]:
                    significant = validation in (FRAUD, REJECTED, NEEDS_REVIEW)
                    changes.append(ConversionChange("validation_status", prev["validation_status"], validation, significant))
                if fraud_flag is not None and fraud_flag != prev["fraud_flag"] and prev["fraud_flag"] is not None:
                    changes.append(ConversionChange("fraud_flag", _text(prev["fraud_flag"]), _text(fraud_flag), fraud_flag == 1))
            if any(change.significant for change in changes) or (validation == NEEDS_REVIEW and (prev is None or prev["validation_status"] != NEEDS_REVIEW)):
                review = "needs_review"

            values = {
                "sub_id": keep("sub_id", sub_id),
                "order_sn": keep("order_sn", order_sn),
                "order_status": status,
                "conversion_status": keep("conversion_status", conversion_status),
                "purchase_time": keep("purchase_time", purchase_time),
                "gross_commission_vnd": gross,
                "net_commission_vnd": net,
                "matched_link_id": matched_link_id,
                "telegram_user_id": telegram_user_id,
                "raw_json": keep("raw_json", raw_json),
                "updated_at": now,
                **{name: keep(name, value) for name, value in extra.items()},
                "first_commission_vnd": net if prev is None or prev["first_commission_vnd"] is None else prev["first_commission_vnd"],
                "validation_status": validation,
                "validation_reason": reason,
                "fraud_flag": fraud_flag,
                "affiliate_item_status": item_statuses,
                "checkout_status": checkout,
                "validation_source": SOURCE_REPORT,
                "validation_confidence": CONFIDENCE_INFERRED,
                "evidence_ref": f"sync_run:{sync_run_id}" if sync_run_id else (None if prev is None else prev["evidence_ref"]),
                # PLAN-081: chỉ đường đồng bộ (có mã lượt) mới là «thấy trong nguồn».
                **({"last_seen_at": now, "last_seen_run_id": sync_run_id, "last_seen_source": seen_source}
                   if sync_run_id else {}),
                "review_status": review,
            }
            if prev is None:
                columns = ["conversion_id", "created_at", *values]
                conn.execute(
                    f"INSERT INTO shopee_conversions ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                    (conversion_id, now, *values.values()),
                )
            else:
                conn.execute(
                    f"UPDATE shopee_conversions SET {', '.join(f'{name} = ?' for name in values)} WHERE conversion_id = ?",
                    (*values.values(), conversion_id),
                )
            recorded: list[tuple[ConversionChange, int]] = []
            for change in changes:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO shopee_conversion_changes
                    (conversion_id, field, old_value, new_value, significant, source, sync_run_id, detected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (conversion_id, change.field, change.old, change.new, int(change.significant), SOURCE_REPORT, sync_run_id, now),
                )
                if cursor.rowcount == 1:
                    recorded.append((change, int(cursor.lastrowid)))
            for hook in self.conversion_hooks:
                conn.execute("SAVEPOINT conversion_hook")
                try:
                    hook(conn, conversion_id, prev, values, recorded, now)
                    conn.execute("RELEASE conversion_hook")
                except Exception:
                    conn.execute("ROLLBACK TO conversion_hook")
                    conn.execute("RELEASE conversion_hook")
                    logger.exception("[Cashback] sinh sự kiện thông báo đơn lỗi conversion=%s", conversion_id[-6:])
        return ConversionResult(
            is_new=prev is None,
            is_matched=matched_link_id is not None,
            matched_link_id=matched_link_id,
            telegram_user_id=telegram_user_id,
            changes=tuple(changes),
            validation_status=validation,
        )

    def conversion_changes(self, conversion_id: str | None = None, limit: int = 10) -> list[sqlite3.Row]:
        where, args = ("WHERE conversion_id = ?", (conversion_id,)) if conversion_id else ("", ())
        with self.connect() as conn:
            return conn.execute(
                f"SELECT * FROM shopee_conversion_changes {where} ORDER BY id DESC LIMIT ?", (*args, limit)
            ).fetchall()

    def mark_conversion_reviewed(self, conversion_id: str, admin_id: int, now: str | None = None) -> bool:
        """Admin đã xem cảnh báo. Không đổi hoa hồng, trạng thái duyệt hay quyền rút."""
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE shopee_conversions SET review_status = 'reviewed', reviewed_by = ?, reviewed_at = ?
                WHERE conversion_id = ? AND review_status = 'needs_review'
                """,
                (admin_id, now or _utc_now(), conversion_id),
            )
            return cursor.rowcount == 1

    def record_shopee_sync_run(self, trigger_type: str = "manual") -> int:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO shopee_sync_runs (trigger_type, status, started_at)
                VALUES (?, 'running', ?)
                """,
                (trigger_type, now),
            )
            return int(cursor.lastrowid)

    def complete_shopee_sync_run(
        self,
        run_id: int,
        status: str,
        clicks: int,
        conversions: int,
        new_orders: int,
        error: str | None = None,
        category: str | None = None,
        stats: dict | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Đóng một lượt. PLAN-080: thêm loại lỗi và số liệu (trang, đơn mới / đổi / không đổi, tin khách).

        conn: transaction của bên giữ khoá (sync_scheduler), để kiểm tra khoá và đóng lượt trong cùng transaction.
        """
        now = _utc_now()
        stats = stats or {}
        values = [stats.get(column) if column not in ("pages_fetched", "pages_failed") else int(stats.get(column) or 0)
                  for column, _ddl in SYNC_RUN_COLUMNS if column != "lease_owner" and column != "error_category"]
        names = [column for column, _ddl in SYNC_RUN_COLUMNS if column not in ("lease_owner", "error_category")]
        sets = ", ".join(f"{name} = COALESCE(?, {name})" for name in names)
        params = (status, clicks, conversions, new_orders, error, now, category, *values, run_id)
        sql = f"""
            UPDATE shopee_sync_runs
            SET status = ?, clicks_synced = ?, conversions_synced = ?,
                new_orders_count = ?, error_message = ?, completed_at = ?, error_category = ?, {sets}
            WHERE id = ?
        """
        if conn is not None:
            conn.execute(sql, params)
            return
        with self.connect() as own:
            own.execute(sql, params)

    def get_last_sync_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM shopee_sync_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return None if row is None else dict(row)


def _row(row: sqlite3.Row) -> LinkRow:
    return LinkRow(
        id=row["id"],
        telegram_update_id=row["telegram_update_id"],
        telegram_user_id=row["telegram_user_id"],
        sub_id=row["sub_id"],
        affiliate_url=row["affiliate_url"],
        item_id=row["item_id"],
        product_name=row["product_name"],
        price_vnd=row["price_vnd"],
        estimated_commission=row["estimated_commission"],
        estimated_cashback=row["estimated_cashback"],
        cashback_rate_percent=row["cashback_rate_percent"],
        link_status=row["link_status"],
        reject_reason=row["reject_reason"],
        estimate_policy=row["estimate_policy"] if "estimate_policy" in row.keys() else None,
    )
