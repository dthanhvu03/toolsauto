-- PLAN-076: huỷ chính sách đã hẹn giờ. Không xoá dòng share_policies / reserve_policies (chỉ thêm);
-- ghi một dòng huỷ. Chỉ huỷ được trước mốc hiệu lực: chính sách chưa từng áp cho link nào, không hồi tố.
CREATE TABLE IF NOT EXISTS policy_cancellations (
    id INTEGER PRIMARY KEY,
    policy_kind TEXT NOT NULL CHECK (policy_kind IN ('share', 'reserve')),
    policy_id INTEGER NOT NULL,
    effective_at TEXT NOT NULL,
    cancelled_by INTEGER NOT NULL,
    cancelled_at TEXT NOT NULL,
    CHECK (cancelled_at < effective_at),
    UNIQUE (policy_kind, policy_id)
);
CREATE TRIGGER IF NOT EXISTS policy_cancellations_no_update BEFORE UPDATE ON policy_cancellations
BEGIN SELECT RAISE(ABORT, 'policy_cancellations is append-only'); END;
CREATE TRIGGER IF NOT EXISTS policy_cancellations_no_delete BEFORE DELETE ON policy_cancellations
BEGIN SELECT RAISE(ABORT, 'policy_cancellations is append-only'); END;
