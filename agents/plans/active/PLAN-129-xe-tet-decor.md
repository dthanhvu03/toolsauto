# PLAN-129 — Xe Tết: hoa mai, hoa đào và đồ Tết dọc đường

- Status: In progress
- Executor: Claude Code (anh yêu cầu 01/11: «thiếu hoa mai, hoa đào, và các chi tiết liên quan đến Tết»)
- Phạm vi: chỉ overlay (`xe_tet/overlay/src/`), không đổi server → không cần khởi động lại 8810, F5 trang là thấy.

## Đã có trước
Cánh hoa bay (mai / đào theo vùng), câu đối + cành đào trên xe, chậu quất + đèn lồng ở bến / trạm / nhà, mâm ngũ quả,
nồi bánh chưng, một cây đào / mai ở sân nhà. Dọc đường thì gần như không có gì Tết: chỉ miền Bắc có đào (40 % số cây).

## Làm
- `src/tet.ts` (mới): chậu mai / đào, chậu cúc vàng, cờ đỏ sao vàng, băng rôn «CHÚC MỪNG NĂM MỚI · XUÂN <năm âm lịch>»
  (tự tính can chi theo năm Tết sắp tới), cây nêu, dưa hấu bổ đôi, chồng bánh chưng, đèn lồng treo. Vật liệu / texture dùng
  chung, dựng một lần (không rò bộ nhớ GPU suốt buổi live).
- Dọc đường: cờ trên trụ điện; nhà ống treo cờ + đèn lồng, trước cửa chậu mai / đào / quất; băng rôn chúc Tết thỉnh thoảng;
  cây mai vàng xen vào cây ven đường miền Trung / Tây Nguyên / Nam, miền Bắc thêm đào.
- Bến xe: băng rôn chúc Tết, chậu mai + đào hai bên, cúc vàng. Trạm dừng: chậu mai, cúc. Nhà: cây nêu, dưa hấu, bánh chưng,
  cúc hai bên cửa, cờ trên cổng.

## Verify
- `npx tsc --noEmit`, `npm run build`.
- Chụp màn hình trên máy chủ thử 8811 (không đụng 8810): đường các vùng, bến, trạm, nhà; `?fps=1` so số draw call trước / sau.
