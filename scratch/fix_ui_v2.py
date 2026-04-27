
import os

file_path = "app/templates/pages/platform_config.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = """// ─── Platform switching ───────────────────────────────────────
function switchPlatform(platform) {
  loadWorkflows(platform);
  loadSelectors();
  loadCTA();
}"""

replacement = """// ─── Platform switching ───────────────────────────────────────
function switchPlatform(platform) {
  loadWorkflows(platform);
  loadSelectors();
  loadCTA();
}

async function applyPreset(name) {
  if (!confirm(`Kích hoạt workflow "${name}"?`)) return;
  try {
    const res = await fetch('/platform-config/presets/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || `Đã kích hoạt ${name}`);
      loadWorkflows();
      if (typeof loadOverview === 'function') loadOverview();
    } else {
      showToast(data.message || data.error || 'Lỗi khi kích hoạt');
    }
  } catch (e) {
    showToast('Lỗi kết nối: ' + e.message);
  }
}"""

if target in content:
    new_content = content.replace(target, replacement)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Success: applyPreset function added.")
else:
    print("Error: Target content not found.")
