# Ghi chú re-sync — ToolsAuto Cave

- **Off-script.** Thư viện là HTML + CSS tĩnh, không React/Storybook → KHÔNG chạy
  `package-build.mjs`/`resync.mjs`. Bộ sinh là `.design-sync/build.mjs`; validate bằng
  `.ds-sync/package-validate.mjs` (stage script skill vào `.ds-sync/` như bình thường).
- `_ds_bundle.js` là namespace rỗng (`window.ToolsAutoCave = {}`), header `components: []` để
  validate bỏ qua smoke-check export. `componentCount` trong `.ds-build-meta.json` = số card.
- `_ds_sync.json` do build.mjs sinh bằng đúng `lib/sync-hashes.mjs` của skill (styleSha,
  renderHashes, auxSha, bundleSha12). Không có `sourceKeys` → remote-diff rơi về renderHashes:
  card nào đổi html/prompt thì re-verify, còn lại skip. 12 card tĩnh — re-verify toàn bộ cũng rẻ.
- Re-sync: sửa card nguồn → `node .design-sync/build.mjs` → validate → chụp/đối chiếu
  (`shoot.py` kiểu Playwright, viewport theo marker) → upload theo đường atomic (projectId đã pin).
- Render check của validate cần Node `playwright` (đã `npm i playwright` trong `.ds-sync/`) và
  Chromium: đặt `DS_CHROMIUM_PATH` tới `%LOCALAPPDATA%\ms-playwright\chromium-<n>\chrome-win64\chrome.exe`
  (Python Playwright của venv đòi headless-shell bản khác, không dùng được trực tiếp).
- Font Figtree/Syne nạp từ Google Fonts qua `@import` trong `styles.css` (`[FONT_REMOTE]` là
  thông tin, không phải lỗi). Không ship woff2.
- `components.css` được tách từ `<style>` của từng card (phiên 2026-09-07); các class demo
  (`.section`, `.row`, `.spec`, `.cap`, `.grid2`) vẫn nằm local trong card — cố ý, không phải vốn class.

## Rủi ro khi re-sync

- `tokens.css` là bản TRÍCH thủ công từ `app/static/cave-tokens.css` + `app.css` (commit 8bcd75d,
  2026-07-23). Nếu tool đổi token thì phải trích lại tay — không có bước tự động.
- Tên card tiếng Việt nằm trong marker `name=`; tên thư mục ASCII lấy từ `config.componentNames`.
  Đổi tên thư mục = card mới với anchor (renderHashes theo tên) → re-verify + orphan cần xoá.
- Google Fonts là tài nguyên mạng: máy không có mạng thì render check báo font thiếu.
