# Badge

Bốn họ badge, đừng trộn lẫn:

1. **Badge job `.app-badge`** — 10px/700 uppercase, radius 8. Map trạng thái job: `.app-badge-green` DONE · `.app-badge-amber` DRAFT / PENDING / AWAITING_STYLE · `.app-badge-blue` RUNNING / AI_PROCESSING · `.app-badge-red` FAILED · `.app-badge-slate` CANCELLED.
   `<span class="app-badge app-badge-amber">Nháp</span>`
2. **Trạng thái material viral `.st`** — 12/500, không uppercase, radius 4: `.st-new` "Mới quét" (sky) · `.st-processing` "Đang xử lý" (torch, kèm `<span class="dot pulse"></span>` trước chữ) · `.st-drafted` "Đã tạo job" (moss) · `.st-ready` "Sẵn sàng đăng tay" (teal) · `.st-failed` "Lỗi" (danger; bên dưới thêm dòng lỗi 11px danger truncate) · `.st-boost` "Boost chờ duyệt".
3. **Pill nhỏ `.pill`** — 10px/700: `.pill-job` link "Job #12 · Nháp" (indigo) · `.pill-aff` "Aff" · `.pill-mega` "Mega" (rose, 9px uppercase, views ≥ ngưỡng) · `.pill-reup` "Reup" (emerald đặc, 8px/900 — góc thumbnail).
4. **Nền tảng `.pf`** — 11px/600: `.pf-youtube`, `.pf-tiktok` (có trong tool), `.pf-facebook`, `.pf-instagram` (đề xuất), mặc định xám.

Pill nguồn giá trị settings `.src` (9px uppercase): `default` xám; `.src-database`, `.src-override`, `.src-env`, `.src-restart` (hoặc `.src-torch`) tô torch-dim.

Chỉ báo Gemini trên header: `<span class="gemini"><span class="cave-dot cave-dot-torch"></span>Gemini: Hết hạn<span class="mode">COOKIE</span><span>Panel hệ thống</span></span>` — dot moss khi OK.

Primitive sẵn có khác: `.cave-badge` + `-torch/-moss/-danger`, `.cave-dot` + `-torch/-moss`.
