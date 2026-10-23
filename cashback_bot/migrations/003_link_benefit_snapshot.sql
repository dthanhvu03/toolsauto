-- Chưa chạy trên data/cashback.sqlite.
-- Bản nháp cột snapshot. Không sửa estimated_cashback đã lưu.
-- Runner Python apply_snapshot_columns kiểm tra cột trước khi ALTER để chạy lại được.

ALTER TABLE link_requests ADD COLUMN membership_policy_id TEXT;
ALTER TABLE link_requests ADD COLUMN membership_rank TEXT;
ALTER TABLE link_requests ADD COLUMN share_bps INTEGER;
ALTER TABLE link_requests ADD COLUMN benefit_review TEXT;
