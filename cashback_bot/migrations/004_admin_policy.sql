-- Bản nháp. Không được chạy trên data/cashback.sqlite trong task này.
-- policy đã confirmed là bất biến. customer_effect luôn là none cho tới khi có quyết định bật riêng.

CREATE TABLE IF NOT EXISTS policy_versions (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status = 'confirmed'),
    config_json TEXT NOT NULL,
    effective_at TEXT,
    customer_effect TEXT NOT NULL CHECK (customer_effect = 'none'),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (domain, version)
);

CREATE TABLE IF NOT EXISTS admin_drafts (
    id INTEGER PRIMARY KEY,
    admin_user_id INTEGER NOT NULL,
    domain TEXT NOT NULL,
    tier TEXT,
    proposed_bps INTEGER,
    base_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    nonce TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_change_audit (
    id INTEGER PRIMARY KEY,
    admin_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    draft_id INTEGER,
    before_json TEXT,
    after_json TEXT,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
