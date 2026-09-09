# ADR-029 — Chạy đúng yt-dlp đã ghim, và trang Sức khỏe phải báo đúng cái đang chạy

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-09 sau sự cố quét TikTok:
  *"oke em triển khai"*
- **Liên quan**: ADR-028 (quét TikTok), ADR-023 (bài học "nhãn nói dối"), ADR-012

## Bối cảnh

Sáng 2026-09-09 mất nhiều vòng chẩn đoán một lỗi hoá ra rất tầm thường. Máy Owner có **hai**
bản yt-dlp:

| Chỗ | Phiên bản |
|---|---|
| PATH → `…\Python312\Scripts\yt-dlp.exe` (cài toàn cục) | **2025.03.31** — cũ 17 tháng |
| `venv` của dự án, ghim trong `requirements.txt` | 2026.8.19 |

`yt_dlp_binary()` lấy **PATH trước** (`shutil.which("yt-dlp")`), nên tool chạy bản 2025 và
TikTok trả `Unable to extract webpage video data`. Trong khi đó trang **Sức khỏe hệ thống**
đọc phiên bản bằng `importlib.metadata.version("yt-dlp")` — tức **gói trong venv** — nên báo
"khớp bản ghim, ổn". Hai con số khác nhau, và cái hiện ra cho người dùng là cái **không được
dùng**.

Đây đúng loại **nhãn nói dối** mà ADR-023 phải đi sửa: ô cài đặt hứa một đằng, code làm một
nẻo. Lần này còn tệ hơn vì nó **chủ động dẫn người chẩn đoán đi sai hướng**.

Docstring của `yt_dlp_binary` ghi ý định là *"để subprocess chạy được khi venv không nằm trên
PATH (PM2 / Windows)"* — tức PATH chỉ nên là **phương án dự phòng**. Thứ tự hiện tại làm ngược
lại chính ý định đó.

## Quyết định

1. **Đảo thứ tự tìm yt-dlp** thành: (a) binary trong thư mục `Scripts`/`bin` cạnh
   `sys.executable` → (b) `[sys.executable, "-m", "yt_dlp"]` nếu import được → (c) PATH →
   (d) tên trần `yt-dlp`.
   Hai nấc đầu **luôn khớp bản ghim trong `requirements.txt`** vì chúng đi theo đúng trình
   thông dịch đang chạy tool. PATH tụt xuống hàng dự phòng — đúng ý định ban đầu của hàm.
   Chạy bằng python hệ thống (không venv) thì hai nấc đầu trỏ về chính bản hệ thống ⇒ **không
   hồi quy**, chỉ khác là không còn bốc nhầm một binary lạ khác trên PATH.
2. **Trang Sức khỏe báo đúng cái đang chạy**: chạy `--version` trên **chính argv mà
   `yt_dlp_cmd` sẽ dùng**, và hiện thêm **đường dẫn** binary đó. Đây mới là sự thật; phiên bản
   gói chỉ còn là số đối chiếu.
3. **Cảnh báo khi hai số lệch nhau** (`mismatch`): binary đang chạy khác gói trong venv nghĩa
   là có một bản yt-dlp lạ chen vào. Chính cái cảnh báo này, nếu có từ sáng, đã cắt ngắn buổi
   chẩn đoán còn một phút.
4. **Đo phiên bản có nhớ tạm 5 phút.** `get_system_health` được gọi bởi trang web, `/health/json`
   và cả lệnh Telegram — sinh một tiến trình con mỗi lượt gọi là phí. Phiên bản không đổi giữa
   hai lần khởi động, 5 phút là quá đủ.
5. **Đo phiên bản không bao giờ được làm hỏng trang Sức khỏe**: timeout 10 s, mọi lỗi ghi vào
   `error` rồi trả về, không ném.

## Kèm theo — hai hợp đồng "không ném lỗi" đang nói dối

Cùng họ với hai lỗi vừa vá ở ADR-030, tìm ra khi soi có hệ thống:

6. `ViralService.generate_caption_for_material` hứa *"KHÔNG BAO GIỜ raise"* nhưng `db.query`,
   `find_reup_path`, `ai_provider_ready(db)` và `db.commit()` ở nhánh thiếu key đều nằm **ngoài**
   mọi `try`. Hiện chưa nổ ra hậu quả **chỉ vì cả hai người gọi đều tự bọc** — đúng kiểu "đúng
   nhờ may mắn của người gọi". Bọc trọn thân hàm, lỗi ngoài dự kiến ⇒ `db.rollback()` + trả
   `(False, msg)`.
7. `offsite.copy_out` hứa *"KHÔNG BAO GIỜ ném lỗi ra ngoài"* nhưng chỉ bắt `OSError`. Đổi sang
   `Exception`.

**Không đụng `scan_source`** dù nó cũng hứa "không raise" và cũng có chỗ hở: `scan_all` đã bọc
sẵn `try/except` + `db.rollback()` cho từng nguồn, có ghi chú rõ ràng. Người viết trước đã
lường đúng — sửa thêm chỉ làm nhiễu.

## Phạm vi

| Việc | File |
|---|---|
| Đảo thứ tự tìm binary | `app/core/yt_dlp_path.py` |
| Đo binary thật + nhớ tạm + cảnh báo lệch | `app/core/observability/health.py` |
| Hiện đường dẫn + cảnh báo lệch | `app/templates/pages/health.html` |
| Bọc trọn thân hàm | `app/features/viral_intake/service.py` |
| `except Exception` | `app/core/storage/offsite.py` |
| Test | `tests/test_yt_dlp_path.py` (mới), `tests/test_health_ytdlp_version.py` |

## Ngoài phạm vi

- **Không tự cập nhật yt-dlp.** Trang Sức khỏe chỉ đọc và cảnh báo — tự chạy `pip install`
  trong tiến trình web là thứ không ai muốn nó tự làm.
- Không gỡ bản yt-dlp toàn cục trên máy Owner.
- Không gộp hai hàm làm sạch tiêu đề trùng nhau (nợ đã ghi ở ADR-030).
- Không đụng `scan_source` (lý do ở mục trên).

## Hết hiệu lực

Sau proof: có một `yt-dlp` cũ trên PATH và một bản mới trong venv ⇒ `yt_dlp_cmd` chọn **bản
venv**; trang Sức khỏe hiện phiên bản **của binary đang chạy** kèm đường dẫn, và cảnh báo khi
nó lệch với gói trong venv; `generate_caption_for_material` với DB hỏng ⇒ trả `(False, msg)`
chứ không ném.

## Proof (2026-09-09)

Trên máy dev, sau khi đảo thứ tự:

```
binary = D:\Zusem\toolsauto\venv\Scripts\yt-dlp.exe     ← bản của dự án, không phải PATH
bản    = 2026.08.19

_ytdlp_version_status() → {
  "installed": "2026.08.19",   ← của BINARY đang chạy
  "package":   "2026.8.19",    ← của gói trong venv, để đối chiếu
  "binary":    "D:\Zusem\toolsauto\venv\Scripts\yt-dlp.exe",
  "mismatch":  false, "outdated": false
}
```

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Có yt-dlp lạ trên PATH ⇒ vẫn chọn bản venv | `test_uu_tien_binary_trong_venv_hon_PATH` |
| Không có binary ⇒ `python -m yt_dlp` **trước** PATH | `test_khong_co_binary_thi_dung_python_m_yt_dlp_chu_chua_dung_PATH` |
| Không import được gói ⇒ mới lùi về PATH, rồi tên trần | 2 test |
| Bố cục Linux (`bin/yt-dlp`) vẫn nhận | `test_bo_cuc_linux_cung_duoc_nhan` |
| Sức khỏe báo phiên bản **của binary**, kèm đường dẫn | `test_installed_lay_tu_binary_chu_khong_phai_goi_trong_venv` |
| Binary lệch gói ⇒ `mismatch`, so theo **số** (`2026.08.19 == 2026.8.19`) | 2 test |
| Đo binary hỏng ⇒ lùi về số của gói, **không** kết luận là lệch | `test_do_binary_hong_thi_lui_ve_phien_ban_goi` |
| Đo phiên bản không bao giờ ném, có nhớ tạm (3 lượt gọi ⇒ **1** tiến trình con) | 2 test |
| Trang Sức khỏe render đủ: đường dẫn, "Đang gọi", cảnh báo "lạ chen vào" | render thật với dữ liệu lệch |
| `generate_caption_for_material` DB/đĩa hỏng ⇒ `(False, msg)`, có `rollback`, session còn dùng được | `test_j1`, `test_j2` |

**Toàn suite: 666 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ, 0 vi phạm.**

## Review sau khi làm — một lỗi trong chính bản vá này

Soi lại đúng đoạn vừa viết thì thấy: `mismatch` được tính **sau** lượt đọc `requirements.txt`,
mà đường đó có `return` sớm khi đọc hỏng. Nghĩa là cảnh báo *"có yt-dlp lạ chen vào"* — thứ
đáng giá nhất của cả ADR này — **biến mất đúng lúc có thứ khác cũng hỏng**. Trớ trêu: ADR sinh
ra để chống "nhãn nói dối" mà suýt tự đẻ ra một cái.

Đã đưa `_version_key` lên cấp module và tính `mismatch` **ngay sau khi đo**, trước mọi đường
`return` sớm. Khoá bằng `test_khong_doc_duoc_requirements_van_con_canh_bao_lech`.

## Ba test cũ phải sửa (ngữ nghĩa đổi có chủ ý)

`test_health_ytdlp_version.py` giả `importlib.metadata.version` rồi kỳ vọng `installed` đi
theo. Nay `installed` lấy từ **binary**, nên giả gói không còn đổi được nó — đúng ý ADR. Đã
đổi sang giả `_probe_ytdlp_binary`, và thêm fixture dọn nhớ tạm giữa các test (không dọn thì
test này ăn kết quả test kia).
