-- ADR-048: tỷ lệ chia admin áp dụng cho báo giá V1.2. Chỉ thêm dòng, tách khỏi reserve_policies.

CREATE TABLE IF NOT EXISTS share_policies (
    id INTEGER PRIMARY KEY,
    share_bps INTEGER NOT NULL CHECK (share_bps BETWEEN 0 AND 7000 AND share_bps % 100 = 0),
    effective_at TEXT NOT NULL,
    draft_id INTEGER,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_share_policies_effective ON share_policies (effective_at, id);

CREATE TABLE IF NOT EXISTS share_drafts (
    id INTEGER PRIMARY KEY,
    admin_user_id INTEGER NOT NULL,
    step TEXT NOT NULL,
    share_bps INTEGER,
    effective_at TEXT,
    nonce TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
