# Architecture Decision Records (ADR)

Thư mục này lưu các quyết định kiến trúc và kỹ thuật quan trọng của dự án.

## Khi nào cần viết ADR?
- Chọn giữa 2+ phương án kỹ thuật quan trọng
- Thay đổi cấu trúc database hoặc schema lớn
- Quyết định về thư viện/framework sẽ dùng lâu dài
- Thay đổi luồng xử lý cốt lõi (core flow)
- Bất kỳ quyết định nào mà nếu đổi ý sau này sẽ tốn >1 ngày

## Format
Sử dụng `agents/templates/adr.template.md`
Tên file: `ADR-NNN-short-name.md`

## Quy trình
1. Viết ADR *trước* khi implement
2. Ghi rõ: bối cảnh → quyết định → lý do → hệ quả → các lựa chọn đã bỏ qua
3. Sau khi implement xong: cập nhật status → `Accepted`
4. Nếu quyết định bị thay thế sau này: cập nhật status → `Superseded by ADR-NNN`
