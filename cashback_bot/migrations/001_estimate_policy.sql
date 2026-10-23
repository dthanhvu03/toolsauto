-- Chưa chạy trên data/cashback.sqlite.
-- Chỉ chạy sau khi chủ bot duyệt chính sách hiển thị V1.2 và đã có bản sao SQLite.
ALTER TABLE link_requests ADD COLUMN estimate_policy TEXT;
