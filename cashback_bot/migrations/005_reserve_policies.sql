-- ADR-047: phí và thuế dự phòng admin áp dụng cho báo giá V1.2.
-- reserve_policies chỉ thêm dòng. Không sửa policy_versions.

CREATE TABLE IF NOT EXISTS reserve_policies (
    id INTEGER PRIMARY KEY,
    account_kind TEXT NOT NULL CHECK (account_kind IN ('PERSONAL', 'INDIVIDUAL_BUSINESS', 'HOUSEHOLD_BUSINESS')),
    fee_bps INTEGER NOT NULL CHECK (fee_bps BETWEEN 0 AND 5000),
    tax_reserve_bps INTEGER NOT NULL CHECK (tax_reserve_bps BETWEEN 0 AND 5000),
    effective_at TEXT NOT NULL,
    draft_id INTEGER,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reserve_policies_effective ON reserve_policies (effective_at, id);

CREATE TABLE IF NOT EXISTS reserve_drafts (
    id INTEGER PRIMARY KEY,
    admin_user_id INTEGER NOT NULL,
    step TEXT NOT NULL,
    account_kind TEXT,
    fee_bps INTEGER,
    tax_reserve_bps INTEGER,
    effective_at TEXT,
    nonce TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
