-- 007 (BẢN NHÁP) — Bằng chứng tài chính cho khoá chi trả (Production Safety Hardening V1).
-- CHƯA ÁP DỤNG production. Không chạy file này bằng tay. Chỉ test dùng để dựng trạng thái "đã đủ bằng chứng".
-- Một PLAN đối soát riêng sẽ làm luồng nhập liệu có kiểm chứng (ai nhập, chứng từ gì, đối chiếu sao kê)
-- trước khi tạo hai bảng này trên production. Khi hai bảng chưa có, payout_gate và trigger trong db.SCHEMA
-- luôn khoá: không có khoản nào available, không tạo được yêu cầu rút, không xác nhận đã chuyển được.

-- Mỗi dòng là một lần Shopee đã thực trả hoa hồng cho kỳ `period` (YYYY-MM), có mã chứng từ.
CREATE TABLE IF NOT EXISTS shopee_settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL CHECK (length(period) = 7),
    amount_vnd INTEGER NOT NULL CHECK (amount_vnd > 0),
    evidence_ref TEXT NOT NULL CHECK (length(evidence_ref) > 0),
    recorded_by INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE (period, evidence_ref)
);

-- Quyết định thuế cho người nhận tiền hoàn đã được duyệt (tham chiếu ADR hoặc văn bản kế toán).
CREATE TABLE IF NOT EXISTS payout_tax_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_ref TEXT NOT NULL CHECK (length(policy_ref) > 0),
    approved_by INTEGER NOT NULL,
    approved_at TEXT NOT NULL
);
