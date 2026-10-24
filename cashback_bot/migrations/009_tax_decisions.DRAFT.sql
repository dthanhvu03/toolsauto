-- BẢN NHÁP, KHÔNG CHẠY TRÊN DB NÀO (PLAN-077). Sổ quyết định thuế cho khoản chi cho người nhận.
-- Cố ý KHÔNG đặt tên payout_tax_policies (điều kiện mở khoá của payout_gate, ADR-050): có dòng ở đây
-- không mở được ví. Nối vào khoá tài chính là việc của PLAN sau, khi chủ bot và kế toán đã duyệt.
CREATE TABLE IF NOT EXISTS tax_policy_decisions (
    id INTEGER PRIMARY KEY,
    policy_version TEXT NOT NULL,
    recipient_kind TEXT NOT NULL,          -- ví dụ: INDIVIDUAL_NO_BUSINESS, HOUSEHOLD_BUSINESS
    payout_kind TEXT NOT NULL,             -- ví dụ: CASHBACK_SHARE
    treatment TEXT NOT NULL,               -- cách xử lý thuế đã được tư vấn (mô tả, không phải số tự chọn)
    legal_basis TEXT NOT NULL,             -- số văn bản, điều, khoản; ngày hiệu lực
    advisor TEXT,                          -- kế toán / tư vấn xác nhận
    document_handling TEXT,                -- chứng từ phải lưu cho mỗi lần chi
    effective_from TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')),
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (status != 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND advisor IS NOT NULL))
);
CREATE TRIGGER IF NOT EXISTS tax_policy_decisions_no_delete BEFORE DELETE ON tax_policy_decisions
BEGIN SELECT RAISE(ABORT, 'tax_policy_decisions is append-only'); END;
