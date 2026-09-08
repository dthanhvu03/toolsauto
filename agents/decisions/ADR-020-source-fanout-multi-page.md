# ADR-020 — Một nguồn → nhiều Page: nhân bản video ra tất cả Page đã nối

- **Ngày**: 2026-09-08
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-08, sau khi được nêu rủi ro
  và vẫn chọn phương án "Nhân bản ra tất cả Page" + "Làm bây giờ"
- **Liên quan**: ADR-019 (bảng Nguồn), ADR-018 (READY), **PLAN-041/TASK-042 (cross-account
  media guard — ADR này nới chính sách đó)**, `docs/notes/2026-09-07-rate-limit-hai-tang.md`

## Bối cảnh

Owner hỏi "một URL nối được với nhiều tài khoản không". Hiện **không**, và bị chặn ở
**ba tầng**:

| Tầng | Ràng buộc | Hệ quả |
|---|---|---|
| `viral_sources.url` | UNIQUE | 1 kênh = 1 dòng = 1 `target_page` |
| `assert_media_not_blocked` (`app/core/media/content_hash.py`) | raise nếu material đã có job, hoặc hash media đã có job cùng platform | job thứ 2 bị chặn ở tầng code |
| DB: `idx_jobs_viral_material_active`, `idx_jobs_platform_content_hash_active` | **UNIQUE partial index** | chặn cứng ở tầng DB kể cả khi bỏ qua code |

Hai tầng dưới do **PLAN-041 (07/2026)** dựng, theo yêu cầu của chính Owner lúc đó:
*"video đã (sắp) đăng account A → account B không đăng lại"*. ADR này **lật lại** yêu cầu
đó trong phạm vi hẹp.

## Rủi ro đã nêu và Owner đã chấp nhận

Đăng **cùng một video** lên nhiều Page là dấu hiệu spam rõ với Facebook, nặng nhất với Page
mới (hạn mức BUC gần 0 — xem `docs/notes/2026-09-07-rate-limit-hai-tang.md`). Đã trình bày
kèm phương án thay thế "chia luân phiên" (mỗi video 1 Page, xoay vòng, không trùng nội dung);
Owner chọn **nhân bản**. Ghi lại để phiên sau không tưởng đây là sơ suất.

## Quyết định

1. **Một dòng nguồn, nhiều Page** — không nhân bản dòng nguồn:
   `viral_sources.target_pages` (TEXT, JSON list). `target_page` cũ giữ lại làm legacy, đọc
   theo thứ tự: `target_pages` nếu có, không thì `[target_page]` nếu có, không thì `[]`.
2. `viral_materials.target_pages` (TEXT, JSON list) — chép từ nguồn lúc quét. Material dán
   tay không có ⇒ đường đi cũ y nguyên.
3. **Tạo job theo vòng lặp**: material có `target_pages` ≥ 1 ⇒ mỗi Page một `Job`, cùng
   `media_path` / `content_hash` / `viral_material_id`, khác `target_page`. Xong hết mới
   `mat.status = DRAFTED`. Không có `target_pages` ⇒ **giữ nguyên** logic hiện tại (round-robin
   / keyword match / 1 job).
4. **Nới guard đúng một nấc — theo Page, không phải bỏ guard**:
   - `assert_media_not_blocked(..., sibling_material_id=<id>)`: bỏ qua các job **cùng
     `viral_material_id`** khi dò; mọi trường hợp khác vẫn chặn như cũ (upload tay trùng
     file, material khác cùng hash…).
   - Migration đổi 2 UNIQUE partial index sang **có `target_page`**:
     `(viral_material_id, COALESCE(target_page,''))` và
     `(platform, content_hash, COALESCE(target_page,''))`.
     `COALESCE` là bắt buộc: Postgres coi NULL là khác nhau, không có nó thì nhiều job
     `target_page=NULL` lọt hết.
   ⇒ Vẫn chặn được thứ guard sinh ra để chặn: **cùng một video hai lần trên cùng một Page**.
5. **Giãn giờ giữa các Page**: job thứ *n* cộng thêm `random(1800, 5400) × n` giây. Không
   thu hẹp phạm vi Owner yêu cầu, chỉ tránh N Page đăng trùng nội dung trong cùng một phút —
   thứ dễ bị đánh spam nhất. Giới hạn `posts_per_page_per_day` và `cooldown_seconds` vẫn áp.
6. **UI**: ô "Page đích" ở khối Nguồn tự động nhận **nhiều Page** (mỗi dòng một URL); bảng
   nguồn hiện số Page đã nối (`2 Page`) + tooltip liệt kê. Cảnh báo ngắn cạnh ô:
   *"Mỗi video sẽ đăng lên TẤT CẢ Page ở đây — nội dung trùng nhau, Facebook dễ đánh spam."*

## Phạm vi

| Việc | File |
|---|---|
| Cột mới | `app/core/database/models/viral.py` |
| Migration: 2 cột + đổi 2 unique index | `alembic/versions/<new>_source_fanout.py` (head hiện tại `k9f6a7b8c9d0`) |
| Guard nhận `sibling_material_id` | `app/core/media/content_hash.py` |
| Vòng lặp tạo job + giãn giờ | `app/features/viral_intake/processor.py` |
| Đọc/ghi danh sách Page | `app/features/viral_intake/sources.py` |
| Ô nhiều Page + cột số Page | `app/features/viral_intake/router.py`, `app/templates/fragments/viral_sources.html`, `app/templates/pages/app_viral.html` |
| Test | `tests/test_source_fanout.py` (mới), sửa test guard hiện có nếu cần |

## Ngoài phạm vi

- Không bỏ guard cho đường upload tay / job thủ công — chỉ nới cho fan-out từ một material.
- Không làm "chia luân phiên" (Owner đã chọn nhân bản).
- Không đụng `Account.competitor_urls` (kho kênh cũ).
- Không tự đăng — vẫn dừng ở `READY` khi chưa có account (ADR-018).

## Đường lùi

`downgrade()` trả 2 index về dạng cũ. Điều kiện: phải xoá bớt job trùng trước, nếu không
index cũ dựng lại sẽ lỗi — ghi rõ trong migration.

## Hết hiệu lực

Sau proof: 1 nguồn nối 2 Page → 1 video → **2 job**, khác `target_page`, lệch giờ hẹn;
và guard vẫn chặn khi cố tạo job thứ 2 cùng video trên **cùng một** Page.
