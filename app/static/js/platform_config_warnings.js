/**
 * Platform Config — Warnings Engine (Business Rules + Rendering)
 *
 * This module evaluates runtime config + selector health data to produce
 * operational warnings for the admin dashboard.
 *
 * Dependencies (from global scope):
 *   - SVG (icon helpers, defined inline in template)
 *
 * Extracted from platform_config.html (Phase P0 Refactoring)
 *
 * BUG FIXES applied during extraction:
 *   - Fixed `hardFailing` referenced outside its scope (was inside if-block on line 1812)
 *   - Removed duplicate warning push for "no preset active" (was pushed twice)
 */

// ─── Warning Builder (Business Rules) ─────────────────────────

function buildWarningsFromData(runtime, selectorData) {
  const alerts = { criticals: [], warnings: [], infos: [] };

  // Guard: no runtime data
  if (!runtime || !runtime.step_resolution) {
    alerts.criticals.push({
      text: "Runtime snapshot lỗi hoặc không tải được.",
      action: "Reload lại trang."
    });
    renderWarnings(alerts);
    return;
  }

  // ── Pre-compute selector classifications ──
  let hardFailing = [];
  let warns = [];
  let lowConfFailing = [];

  if (selectorData && selectorData.items) {
    hardFailing = selectorData.items.filter(i => i.severity === 'critical' && i.confidence !== 'low');
    warns = selectorData.items.filter(i => i.severity === 'warning');
    lowConfFailing = selectorData.items.filter(i => i.severity === 'critical' && i.confidence === 'low');
  }

  // ── Critical Rules ──

  // 1. Hard-failing selectors (high confidence)
  if (hardFailing.length > 0) {
    alerts.criticals.push({
      text: `Có ${hardFailing.length} selector fail liên tục (Mức độ tin cậy: cao). Job có thể bị block / thất bại hoàn toàn.`,
      action: "Mở tab Selectors để cập nhật giá trị query DOM mới."
    });
  }

  // 2. No active preset
  if (!runtime.preset || runtime.preset === "default") {
    alerts.criticals.push({
      text: "Không có preset active. Worker đang chạy config cứng mặc định, rủi ro tương thích cao.",
      action: "Vui lòng Active một Preset có sẵn."
    });
  }

  // ── Warning Rules ──

  // 3. Unstable selectors
  if (warns.length > 0) {
    alerts.warnings.push({
      text: `Có ${warns.length} selector không ổn định.`,
      action: "Kiểm tra layout."
    });
  }

  // 4. Low-confidence failing selectors
  if (lowConfFailing.length > 0) {
    alerts.warnings.push({
      text: `Có ${lowConfFailing.length} selector fail (Low Confidence).`,
      action: "Chờ thêm logs."
    });
  }

  // 5. Stale cache
  if (runtime.cache) {
    const { age_seconds, ttl_total } = runtime.cache;
    if (age_seconds !== null && ttl_total !== null && age_seconds > ttl_total) {
      alerts.warnings.push({
        text: "Cache đã stale.",
        action: "Reload Cache."
      });
    }
  }

  // 6. CTA mismatch
  if (runtime.cta_pool) {
    if (runtime.cta_pool.total > 0 && runtime.cta_pool.effective === 0) {
      alerts.warnings.push({
        text: "CTA templates không match locale.",
        action: "Chỉnh sửa target."
      });
    } else if (runtime.cta_pool.is_fallback) {
      alerts.warnings.push({
        text: "Worker đang dùng fallback tĩnh.",
        action: "Thiết lập CTA."
      });
    }
  }

  // ── Info Rules ──

  // 7. Cache just reloaded
  if (runtime.cache && runtime.cache.age_seconds !== null && runtime.cache.age_seconds < 10) {
    alerts.infos.push({ text: "Cache vừa được reload." });
  }

  renderWarnings(alerts);
}

// ─── Warning Renderer ─────────────────────────────────────────

function renderWarnings(w) {
  const body = document.getElementById('warnings-body');
  if (!body) return;
  let html = '';

  // Critical section
  if (w.criticals.length > 0) {
    html += `<div class="p-3 rounded-lg bg-red-50 border border-red-200 mb-3 space-y-3 shadow-sm">
      <div class="text-[10px] font-bold text-red-500 uppercase tracking-wider">Critical Issues</div>
      ${w.criticals.map(c => `
        <div class="flex items-start gap-2.5">
          ${SVG.alertCritical.replace('w-4 h-4', 'w-4 h-4 mt-0.5 bg-white rounded-full')}
          <div class="flex flex-col gap-1.5">
            <span class="text-xs font-bold text-red-700 leading-tight">${c.text}</span>
            ${c.action ? `<span class="text-[10px] font-semibold text-red-600 bg-white/70 w-fit px-2 py-0.5 rounded flex items-center gap-1.5">&rarr; Action: ${c.action}</span>` : ''}
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  // Warning section
  if (w.warnings.length > 0) {
    html += `<div class="p-3 rounded-lg bg-amber-50 border border-amber-200 mb-3 space-y-3 shadow-sm">
      <div class="text-[10px] font-bold text-amber-500 uppercase tracking-wider">Warnings &amp; Risks</div>
      ${w.warnings.map(warn => `
        <div class="flex items-start gap-2.5">
          ${SVG.alertTriangle.replace('w-4 h-4', 'w-4 h-4 mt-0.5 bg-white rounded-full')}
          <div class="flex flex-col gap-1.5">
            <span class="text-xs font-semibold text-amber-800 leading-tight">${warn.text}</span>
            ${warn.action ? `<span class="text-[10px] font-semibold text-amber-600 bg-white/70 w-fit px-2 py-0.5 rounded flex items-center gap-1.5">&rarr; Action: ${warn.action}</span>` : ''}
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  // Info section (collapsible)
  if (w.infos.length > 0) {
    html += `<details class="group mt-2">
      <summary class="text-[10px] text-gray-400 cursor-pointer hover:text-gray-600 transition-colors bg-gray-50 p-1.5 rounded inline-block">
        + ${w.infos.length} thông tin ngữ cảnh (Info)
      </summary>
      <div class="mt-2 space-y-1.5 pl-1 my-2">
        ${w.infos.map(i => `
          <div class="flex items-start gap-2 text-[10px] text-gray-500">
             ${SVG.infoCircle.replace('w-4 h-4', 'w-3.5 h-3.5 text-gray-400 mt-0.5')}
             <span class="leading-relaxed">${i.text}</span>
          </div>
        `).join('')}
      </div>
    </details>`;
  }

  body.innerHTML = html;
}
