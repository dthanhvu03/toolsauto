# ADR-036 — Chọn cả hai đầu đoạn cắt, và cho phép không cắt

- **Ngày**: 2026-09-10
- **Trạng thái**: **ĐÃ DUYỆT** — Owner hỏi *"sao lại cắt em nhỉ, người xem xem không hiểu đầu
  đuôi như nào"* rồi giao *"em triển khai đi em"*
- **Liên quan**: **ADR-031 (mốc cắt — ADR này bổ sung đầu còn lại)**, ADR-032, ADR-035

## Bối cảnh — kiểm chứng lại giả định cũ

`MAX_REELS_DURATION = 90` đặt theo giới hạn Facebook Reels. Kiểm lại 2026-09-10:
**tháng 6/2025 Meta đã bỏ giới hạn đó** — mọi video đăng lên Facebook đều thành Reels và
*"không còn giới hạn độ dài hay định dạng"*. Nên câu "phải cắt vì Reels chỉ cho 90 giây"
**không còn đúng**. ADR-031 giữ nguyên con số này mà không kiểm lại.

Nhưng **bỏ cắt cũng không phải lời giải**: Facebook xếp hạng Reels theo **tỷ lệ xem hết**,
không phải tổng thời gian xem. Vlog 9,5 phút thì tỷ lệ xem hết gần 0, và nền tảng đọc đó là
nội dung dở rồi dìm cả Page. Khoảng hiệu quả được ghi nhận là 15 giây – 1 phút.

**Vấn đề thật là cắt ẩu, không phải cắt.** Clip hiện tại bắt đầu ở chỗ vô nghĩa (móc mồi) và
kết thúc giữa chừng. Một clip 60 giây **tự nó trọn vẹn** — thả câu → cần cong → kéo lên → con
cá — thì người xem hiểu ngay. Muốn vậy phải chọn được **cả hai đầu**, mà ADR-031 chỉ cho chọn
điểm bắt đầu; độ dài là một con số chung cho mọi video.

## Quyết định

1. **`viral_materials.clip_length_sec`** (Integer, nullable) — độ dài riêng cho từng video.
   Thứ tự ưu tiên: **độ dài riêng của video** → `max_duration` của preset (`reels_short` = 45)
   → ô `reup.max_duration_sec` → hằng số trong code.
2. **`reup.max_duration_sec = 0` nghĩa là KHÔNG CẮT.** Chặn cứng một lựa chọn mà nền tảng đã
   mở là sai; để Owner tự quyết. Ô hạ `min` từ 10 xuống 0.
3. **Không truyền số 0 xuống ffmpeg — đổi thành một số rất lớn (`NO_CUT_DURATION`).**
   Đây là điểm kỹ thuật quan trọng: `max_duration` không chỉ dùng để cắt, nó còn là **cổng
   kiểm chất lượng** (`in_duration > max_duration and out_duration > max_duration + 1` ⇒ loại
   bản xuất) và là điều kiện của nhánh dự phòng. Truyền 0 vào đó thì **mọi bản xuất đều bị
   loại**. Đổi ở đúng một chỗ (`_configured_max_duration`) thì 8 chỗ dùng còn lại không phải
   sửa và không thể sai.
4. **Mô tả ô phải nói thẳng cái giá.** Đặt 0 ⇒ nhắc rằng Facebook xếp hạng theo tỷ lệ xem hết,
   video dài thường bị dìm. Cho phép ≠ khuyến khích; nhãn phải nói đúng hậu quả (ADR-023).
5. **UI: ô "dài (giây)" đặt ngay cạnh ô "bắt đầu từ giây"** trong khối "✂️ Chọn đoạn cắt" —
   hai đầu của cùng một quyết định thì phải nằm cạnh nhau.

## Phạm vi

| Việc | File |
|---|---|
| Cột + migration | `app/core/database/models/viral.py`, `alembic/versions/` |
| `clip_length` + `NO_CUT_DURATION` | `app/features/viral_intake/reup_processor.py` |
| Truyền độ dài riêng | `app/features/viral_intake/processor.py` |
| Ô cho phép 0 | `app/core/settings.py` |
| Nhận độ dài khi đặt mốc | `app/features/viral_intake/service.py`, `router.py` |
| Ô nhập | `app/templates/fragments/viral_row.html` |
| Test | `tests/test_clip_start.py` (thêm mục) |

## Ngoài phạm vi

- Không tự tìm điểm kết "trọn vẹn" — ADR-031 đã đo và chứng minh không có tín hiệu để dò.
- Không đổi mặc định 90 giây: đổi mặc định là đổi hành vi của mọi video cũ.
- Không đụng dải khung hình, Drive, caption, Telegram.

## Hết hiệu lực

Sau proof: đặt `clip_length_sec = 50` ⇒ file ra dài 50 giây bất kể ô chung; đặt
`reup.max_duration_sec = 0` ⇒ **không cắt**, file dài bằng bản gốc và **vẫn qua cổng kiểm
chất lượng**; bỏ trống ⇒ y như trước.

## Proof (2026-09-10)

**Chạy ffmpeg thật** trên video 300 giây:

```
độ dài riêng 50s từ giây 60  ->  success=True  dài=50.0s
KHÔNG CẮT (ô Thiết lập = 0)  ->  success=True  dài=300.0s   ← nguyên bản
```

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Độ dài riêng thắng preset và ô chung | chạy thật: 50.0s; `test_do_dai_rieng_cua_video_thang_moi_thu_khac` |
| Đặt 0 ⇒ không cắt, **vẫn qua cổng kiểm chất lượng** | chạy thật: 300.0s, `success=True` |
| 0 **không** được truyền xuống mà đổi thành `NO_CUT_DURATION` | `test_dat_0_thi_KHONG_truyen_0_xuong_ma_doi_thanh_so_rat_lon` |
| Không cổng nào loại bản xuất ở chế độ không cắt (kể cả video 24 tiếng) | 4 ca parametrize |
| Đặt cả mốc lẫn độ dài; bỏ trống độ dài ⇒ dùng số chung | 2 test |
| Độ dài sai (chữ / âm / dưới 5 giây) ⇒ từ chối, **không đổi status** | 3 ca |
| Số dương ở ô Thiết lập vẫn được tôn trọng | `test_so_duong_van_duoc_ton_trong` |

**Toàn suite: 774 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ. Alembic: 1 head.**

## Lỗi thật chỉ lộ khi chạy thật — lần thứ ba trong hai ngày

Chạy chế độ không cắt lần đầu: `success=False`, nhưng **file vẫn ra đủ 300 giây**. Truy ra:
`_fast_trim_fallback` có chốt `duration <= max_duration ⇒ "Fallback not needed"`. Chốt đó đúng
khi **mọi video dài đều bị cắt**, nhưng ở chế độ không cắt thì `duration` **không bao giờ**
vượt ngưỡng ⇒ lượt mã hoá chính hỏng là **hỏng hẳn**: material bị đánh `FAILED` và file tải về
bị xoá.

Trước ADR này lỗ đó không lộ được, vì video dài luôn có đường rơi vào dự phòng. Chính tính
năng mới mở ra đường đi không có lưới.

Đã sửa: dự phòng chạy được **cả hai chế độ** — chỉ thêm `-t` khi thật sự phải cắt, không thì
chép nguyên; và **cả bốn** nhánh hỏng (lỗi ffmpeg, file rỗng, quá giờ, ngoại lệ) đều thử dự
phòng thay vì chỉ hai nhánh như trước.

**Một lỗi phụ tự tạo rồi tự bắt:** viết `_fast_trim_fallback() or ReupResult(...)` — mà
`ReupResult` **luôn truthy** nên nhánh sau không bao giờ chạy, và **lỗi gốc bị nuốt** thành
"Both … failed", vô dụng khi chẩn đoán. Đổi sang xét `.success`, giữ nguyên lỗi gốc.

## Ghi chú về máy dev

Lượt chạy thật báo lỗi `psycopg2 … port 5434 Connection refused` — Postgres máy dev đang tắt,
**không liên quan** ADR này. Nó vô tình có ích: chính vì lượt mã hoá chính hỏng mà lỗ "không
có lưới ở chế độ không cắt" mới lộ ra.
