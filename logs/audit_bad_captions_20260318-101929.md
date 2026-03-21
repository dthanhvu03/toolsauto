# Audit caption lỗi (DB)

- DB: `/home/vu/toolsauto/data/auto_publisher.db`
- Scanned jobs: **403**
- Suspect captions (has flags): **8**

## Status breakdown

- **DONE**: 209
- **DRAFT**: 81
- **CANCELLED**: 39
- **FAILED**: 39
- **PENDING**: 35

## Error breakdown (jobs.last_error classifier)

- **auth_cookie**: 34
- **other**: 23
- **infra_timeout**: 12
- **empty_result**: 10
- **content_policy**: 1

## Top suspect jobs (max 50)

### Job #351 (facebook)
- status: **DRAFT**
- created_at: `2026-03-17 06:02:22`
- caption_flags: `assistant_prose`
- caption_preview: `Chào Vũ, tôi đã xem qua bộ ảnh collage của bạn. Với phong cách ảnh "thư ký văn phòng" (office lady) theo style Hàn Quốc/Y2K gợi cảm và hiện đại như thế này, chúng ta sẽ đánh mạnh vào tệp khách hàng nam giới hoặc những người quan tâm đến thời trang công sở phá cách.\n\n#Fashion #OfficeLady #OOTD #Shope`

### Job #243 (facebook)
- status: **DONE**
- created_at: `2026-03-16 10:28:37`
- finished_at: `2026-03-17 00:21:01`
- caption_flags: `options_vi`
- caption_preview: `Thiết kế áo kiểu cổ điển pha lẫn nét hiện đại, cực kỳ sang chảnh và thanh lịch.\nChất liệu tơ mềm mại cùng chi tiết nút thắt tỉ mỉ tạo điểm nhấn tinh tế.\nLựa chọn hoàn hảo để nâng tầm phong cách mỗi ngày.\n👉 Sắm ngay thiết kế này tại link bên dưới!\n\n#aokieunu #aokieuxinh #thoitrangnu #thoitrangthietke`

### Job #217 (facebook)
- status: **DONE**
- created_at: `2026-03-12 01:52:29`
- finished_at: `2026-03-12 02:06:01`
- caption_flags: `options_vi`
- caption_preview: `[ CHÚT LẦM LỠ GÂY THƯƠNG NHỚ ]\n\nXinh lung linh dù chỉ ở nhà! Set đồ mặc nhà mỏng nhẹ, mát mẻ, giúp vóc dáng thon gọn cực kỳ. 💖\n\n- Chất vải mướt mịn, siêu co giãn, thoải mái vận động.\n- Tone hồng ngọt ngào, trẻ trung, lên hình là slay.\n- Lựa chọn hoàn hảo để mặc nhà, đi ngủ hay quay clip đu trend.\n\n🔥`

### Job #198 (facebook)
- status: **DONE**
- created_at: `2026-03-10 05:20:50`
- finished_at: `2026-03-10 05:48:27`
- caption_flags: `options_vi`
- caption_preview: `✨ LẦN ĐẦU THẤY KEM DƯỠNG MÀ NHƯ BÁNH MOCHI LUÔN NÈ! ✨\n\nTeam da dầu mụn bơi hết vào đây xem siêu phẩm mới từ Garnier nha. Texture độc lạ chạm vào là tan, mướt mịn y hệt bánh Mochi, không hề bết rít hay bóng nhờn luôn.\n\n- Kiềm dầu đỉnh cao suốt 8 tiếng.\n- Thành phần Salicylic Acid giúp sạch lỗ chân lô`

### Job #176 (facebook)
- status: **DONE**
- created_at: `2026-03-05 01:46:05`
- finished_at: `2026-03-09 07:46:19`
- caption_flags: `options_vi`
- caption_preview: `⚠️ ĐỪNG ĐỂ LÁ GAN PHẢI KÊU CỨU VÌ KHÓI THUỐC!\n\nBạn có biết lá gan sẽ trông như thế nào sau 20 năm tiếp nạp độc tố mỗi ngày? Đen xỉn, chai cứng và chạm ngưỡng cửa tử là kịch bản có thật nếu không thay đổi ngay hôm nay.\n\n- Thanh lọc cơ thể, hỗ trợ đào thải độc tố tích tụ.\n- Bảo vệ tế bào gan trước các`

### Job #65 (facebook)
- status: **DONE**
- created_at: `2026-02-25 16:26:16`
- finished_at: `2026-02-25 16:30:59`
- caption_flags: `empty`
- caption_preview: ``

### Job #204 (facebook)
- status: **CANCELLED**
- error_class: **other**
- last_error: `Unexpected Playwright Error: [Errno 2] No such file or directory: '/home/vu/toolsauto/content/processed/viral_23_7316121500128496914_reup_processed.mp4'`
- created_at: `2026-03-11 03:16:39`
- finished_at: `2026-03-11 07:00:47`
- caption_flags: `options_vi`
- caption_preview: `[ TÂM AN YÊN - DIỆN PHÁP PHỤC XINH ]\n\nĐi chùa hay vãn cảnh, một bộ pháp phục thanh lịch luôn là lựa chọn hoàn hảo. Chất vải đũi mềm mát, thiết kế suông nhẹ cùng họa tiết hoa sen thêu tỉ mỉ tạo nên vẻ tao nhã, vô cùng thoải mái khi vận động.\n\nSẵn đủ tone màu be, xám, nâu nhã nhặn và cực kỳ tôn da.\n\n🔥`

### Job #132 (facebook)
- status: **CANCELLED**
- error_class: **empty_result**
- last_error: `AI Generation returned empty result`
- created_at: `2026-03-04 16:02:25`
- caption_flags: `options_vi`
- caption_preview: `⚠️ MẸ CÓ BIẾT: DA BÉ MỎNG HƠN DA NGƯỜI LỚN GẤP 5 LẦN? ⚠️\n\nLựa chọn nước giặt không phù hợp dễ khiến bé bị kích ứng, mẩn đỏ. Đó là lý do OMO Matic cho Quần Áo Bé Yêu luôn là chân ái của mẹ Bill bấy lâu nay! \n\n✨ Tại sao mẹ nên chọn dòng này cho bé?\n- Thành phần tự nhiên: Chiết xuất từ Tràm trà & Nha đ`
