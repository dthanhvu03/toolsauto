# PLAN-120: Ngắt dòng phụ đề chuẩn — theo cụm từ / dấu câu, dòng cân, không chữ lẻ, thời gian theo độ dài

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-120 |
| **Status** | Approved — anh nhận xét 31/10 («cách ngắt dòng chưa chuẩn em nhỉ») |
| **Executor** | Claude Code (vai UX; ngoại lệ ADR-061 Studio) |
| **Created** | 2026-10-31 |

---

## Vấn đề (ASS dựng lại từ dự án #12)
`render/subtitles._wrap` nhồi chữ đầy dòng 22 ký tự. Cứ 2 dòng thành một lượt hiện chữ, thời gian chia đều cho các lượt. Hậu quả:
- **chẻ từ ghép**: «Ấn ⏎ tượng», «được thành ⏎ lập», «Tee ⏎ box 1»;
- **chữ lẻ thành một lượt riêng**: «Anh.», «1», «box 1», «chúng ta tới»;
- **thời gian đều nhau**: «Anh.» hiện 1,2 s bằng lượt 2 dòng đầy chữ;
- **bỏ qua dấu câu, dòng lệch**: dòng trên đầy, dòng dưới vài chữ.

## Thiết kế (chuẩn phụ đề phổ biến: ≤ 2 dòng, ngắt theo cụm, dòng cân, không chữ mồ côi)
1. **Chia lượt:** câu dài hơn 2 dòng → tách thành nhiều lượt. Chọn chỗ tách ưu tiên:
   - sau dấu kết câu `. ! ? …`, rồi sau `, ; :`;
   - các lượt dài gần bằng nhau;
   - không để lượt chỉ 1–2 chữ.
2. **Ngắt 2 dòng trong một lượt:** chọn chỗ ngắt có điểm phạt thấp nhất:
   - lệch độ dài hai dòng;
   - quá `max_chars` (phạt rất nặng);
   - ngắt ngay sau dấu câu được thưởng;
   - ngắt **trước** từ nối / giới từ («và, nhưng, thì, là, của, ở, từ, với, cho, khi, vì, nên, mà, để…») được thưởng;
   - dòng kết thúc bằng từ nối / giới từ, hoặc dòng chỉ 1 chữ → phạt.
   - Câu vừa 1 dòng thì giữ 1 dòng.
3. **Thời gian mỗi lượt theo số ký tự** (tỉ lệ), tối thiểu 0,7 s nếu đủ chỗ.
- Không đổi kiểu chữ / cỡ / vị trí. `max_chars` vẫn theo spec (22).

## Scope
`app/features/studio/render/subtitles.py` (+ test). Áp cho mọi bản render từ nay; dự án cũ đổi khi render lại / lồng lại.

## Out of Scope
- Tách từ tiếng Việt bằng thư viện NLP (pyvi / underthesea): chưa cài; dùng luật cụm từ ở trên.
- Đổi cỡ chữ / số ký tự mỗi dòng.

## Validation
- pytest các câu thật của #12: không chẻ «ấn tượng» / «thành lập» / «tee box»; không lượt 1 chữ; thời gian liên tục, tỉ lệ theo độ dài.
- Dựng ASS của #12 so trước / sau.
- Render 1 khung có phụ đề để nhìn.

---

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — cần restart Studio_Heavy (render) để áp; video cũ đổi khi render / lồng lại.**
  - `render/subtitles.py`:
    - `_Measure`: đo bằng Pillow với font thật × `LIBASS_SCALE = 0.65`. libass hiểu Fontsize là chiều cao dòng; đo trên khung
      thật 600/921 px và 557/857 px. Giới hạn `min(bề ngang khung, READ_CAP = 32)` ký tự trung bình; không có font thì `max_chars`.
    - `_sentences`: mỗi câu một lượt; mẩu < 3 chữ chỉ gộp khi gộp xong vẫn vừa và ngắt sạch (`_clean`).
    - `split_caption` / `_rows`: chọn chỗ ngắt theo điểm phạt (lệch dòng, quá khung, thưởng sau dấu câu / trước từ nối,
      phạt dòng treo ở từ nối, phạt tách tên riêng, phạt dòng 1 chữ).
    - `_timed`: thời gian theo số ký tự, tối thiểu 0,7 s, liền mạch.
  - `render/graph.py` truyền `font_file` vào `build_ass`.
  - Còn ngoài tầm: từ ghép tiếng Việt không có dấu hiệu («mùa ⏎ hè») — cần thư viện tách từ (pyvi / underthesea).

**Verification Proof**:
```
# ASS dự án #12 (câu dịch cũ):
#   trước: 41+ lượt, «Ấn ⏎ tượng», «được thành ⏎ lập», lượt lẻ «Anh.», «1», «box 1», chia thời gian đều
#   sau: 37 lượt, 0 lượt 1 chữ, «John Allen» / «Royal North Devon» nguyên, «Rất giàu lịch sử.» / «Ấn tượng đầu rất tốt.»
#        thành 2 lượt riêng; lượt ngắn nhất 0,84 s
# Render khung thật (ffmpeg ass, 1080×1920): chữ nằm gọn, dòng 28 ký tự ≈ 600 px
$ unshare -n pytest tests/test_studio_subtitles.py (5) + 11 file Studio → 176 passed; ruff ok
```
