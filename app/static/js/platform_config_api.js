/**
 * Platform Config — API Layer & State Management
 *
 * This module contains all fetch() calls, state variables, and overview panel
 * rendering for the Platform Config admin dashboard.
 *
 * Dependencies (from global scope):
 *   - SVG (icon helpers, defined inline in template)
 *   - sourceTag() (badge helper, defined inline in template)
 *   - showToast() (toast notification, defined inline in template)
 *   - buildWarningsFromData() (from platform_config_warnings.js)
 *   - loadOverview (re-assigned at bottom of template for cache chain patch)
 *
 * Extracted from platform_config.html (Phase P0 Refactoring)
 */

// ─── Shared State ─────────────────────────────────────────────
let _runtimeData = null;
let _selectorData = null;
let _currentRequestId = 0;
let _currentPreviewId = 0;

// ─── Main Orchestrator ────────────────────────────────────────

async function loadOverview() {
  const existingModal = document.getElementById('preset-modal-overlay');
  if (existingModal) existingModal.remove();

  await loadRuntimeSnapshot();
  loadCacheState();
  loadPresetControl();
  loadStepResolution();
  loadSelectorHealth();
}

function refreshRuntimeSnapshot() {
  loadRuntimeSnapshot();
}

// ─── Card 2: Runtime Snapshot ─────────────────────────────────

async function loadRuntimeSnapshot() {
  const reqId = ++_currentRequestId;
  const body = document.getElementById('runtime-snapshot-body');
  const badge = document.getElementById('rc-cache-badge');
  const label = document.getElementById('rc-platform-label');
  try {
    const res = await fetch('/platform-config/runtime-config?platform=facebook&job_type=POST');
    const d = await res.json();
    if (reqId !== _currentRequestId) return;
    _runtimeData = d;
    label.textContent = 'facebook:POST';

    // Cache badge
    if (d.cache) {
      const age = d.cache.age_seconds;
      if (age === null) {
        badge.className = 'text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500';
        badge.textContent = 'no cache';
      } else if (age <= 30) {
        badge.className = 'text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700';
        badge.textContent = `${Math.round(age)}s ago`;
      } else if (age <= 60) {
        badge.className = 'text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700';
        badge.textContent = `${Math.round(age)}s ago`;
      } else {
        badge.className = 'text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700';
        badge.textContent = `stale ${Math.round(age)}s`;
      }
    }

    // Preset section
    let confidenceHtml = '';
    const age = d.cache ? d.cache.age_seconds : null;
    if (age !== null && age > 120) {
      confidenceHtml = `<span class="text-[10px] bg-yellow-50 text-yellow-600 px-2 py-0.5 rounded ml-2">Low confidence (Stale)</span>`;
    } else {
      confidenceHtml = `<span class="text-[10px] bg-green-50 text-green-600 px-2 py-0.5 rounded ml-2">High confidence</span>`;
    }

    const presetHtml = d.preset
      ? `<div class="flex items-center">
           <span class="text-sm font-semibold text-indigo-700 mr-2">${d.preset}</span>
           ${sourceTag(d.config_source ? d.config_source.preset : 'none')}
           ${confidenceHtml}
         </div>
         <p class="text-xs text-gray-400 mt-0.5">${d.preset_description || ''}</p>`
      : `<div class="flex items-center gap-2">
           <span class="text-sm text-gray-400">No active preset</span>
           ${sourceTag('none')}
         </div>
         <p class="text-xs text-gray-400 mt-0.5">Worker se dung config mac dinh.</p>`;

    // Steps section
    const sortedSteps = [...(d.step_resolution || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const stepsHtml = sortedSteps.map(s => {
      const icon = s.status === 'RUN' ? SVG.checkCircle : SVG.xCircle;
      const statusCls = s.status === 'RUN'
        ? 'bg-green-50 text-green-700'
        : 'bg-red-50 text-red-600';
      return `<tr class="border-t border-gray-50">
        <td class="py-1.5 pr-2">${icon}</td>
        <td class="py-1.5 pr-3 text-xs font-mono text-gray-700">${s.step}</td>
        <td class="py-1.5 pr-3"><span class="text-[10px] font-semibold px-1.5 py-0.5 rounded ${statusCls}">${s.status}</span></td>
        <td class="py-1.5 pr-2">${sourceTag(s.source)}</td>
        <td class="py-1.5 text-[10px] text-gray-400">${s.reason || ''}</td>
      </tr>`;
    }).join('');

    // Timing section
    const timingHuman = d.timing_human || {};
    const timingRaw = d.timing || {};
    const timingKeys = Object.keys(timingHuman);
    const timingHtml = timingKeys.length
      ? timingKeys.map(k => `<tr class="border-t border-gray-50">
          <td class="py-1 text-xs font-mono text-gray-600 pr-3">${k}</td>
          <td class="py-1 text-xs font-semibold text-gray-800 pr-3">${timingHuman[k]}</td>
          <td class="py-1 text-[10px] text-gray-400">${timingRaw[k]}ms</td>
        </tr>`).join('')
      : '<tr><td class="py-1 text-xs text-gray-400">Defaults</td></tr>';

    // CTA pool section
    const cta = d.cta_pool || {};
    const ctaHtml = `<div class="mt-0.5">
      <span class="text-xs text-gray-600">${cta.total || 0} templates <span class="text-gray-400">(${cta.locale || 'vi'})</span></span>
      ${cta.effective ? `<span class="text-[10px] bg-green-50 text-green-600 px-1.5 py-0.5 rounded ml-1">${cta.effective} effective</span>` : ''}
      ${cta.effective === 0 && cta.total > 0 ? `<span class="text-[10px] bg-orange-50 text-orange-600 px-1.5 py-0.5 rounded ml-1">no match</span>` : ''}
      ${cta.is_fallback ? `<span class="text-[10px] bg-orange-50 text-orange-600 px-1.5 py-0.5 rounded ml-1">fallback only</span>` : ''}
    </div>`;

    // Retry section
    const retry = d.retry || {};
    const retryHtml = retry.max_retries != null
      ? `max_retries: ${retry.max_retries}`
      : 'Defaults';

    body.innerHTML = `
      <!-- Preset -->
      <div>
        <div class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold mb-1">Preset</div>
        ${presetHtml}
      </div>

      <!-- Effective Steps -->
      <div>
        <div class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold mb-1">Effective Steps</div>
        <table class="w-full"><tbody>${stepsHtml || '<tr><td class="text-xs text-gray-400">No step data</td></tr>'}</tbody></table>
      </div>

      <!-- Timing -->
      <div>
        <div class="flex items-center gap-2 mb-1">
          <span class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Timing</span>
          ${sourceTag(d.config_source ? d.config_source.timing : 'none')}
        </div>
        <table class="w-full"><tbody>${timingHtml}</tbody></table>
      </div>

      <!-- CTA Pool + Retry -->
      <div class="flex flex-wrap gap-x-8 gap-y-2">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">CTA Pool</span>
            ${sourceTag(d.config_source ? d.config_source.cta : 'none')}
          </div>
          <div>${ctaHtml}</div>
        </div>
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Retry</span>
            ${sourceTag(d.config_source ? d.config_source.retry : 'none')}
          </div>
          <span class="text-xs font-mono text-gray-600">${retryHtml}</span>
        </div>
      </div>

      <!-- Copy JSON -->
      <div class="pt-2 border-t border-gray-100 flex justify-end">
        <button onclick="navigator.clipboard.writeText(JSON.stringify(_runtimeData,null,2)).then(()=>showToast('Copied to clipboard'))"
                class="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1 transition-colors">
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/></svg>
          Copy as JSON
        </button>
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="text-center py-6">
      ${SVG.xCircle}
      <p class="text-xs text-red-500 mt-2">Khong the tai runtime config</p>
      <p class="text-[10px] text-gray-400 mt-1">${e.message || 'Connection error'}</p>
      <button onclick="loadRuntimeSnapshot()" class="mt-2 text-xs text-indigo-600 hover:underline">Thu lai</button>
    </div>`;
  }
}

// ─── Card 3: Cache & Sync ─────────────────────────────────────

async function loadCacheState() {
  const body = document.getElementById('cache-sync-body');
  if (!_runtimeData || !_runtimeData.cache) {
    body.innerHTML = '<p class="text-xs text-gray-400">Waiting for runtime data...</p>';
    return;
  }
  const c = _runtimeData.cache;
  const age = c.age_seconds;

  let statusIcon, statusText, statusCls;
  if (age === null) {
    statusIcon = '<span class="w-2 h-2 rounded-full bg-gray-300 shrink-0"></span>';
    statusText = 'Not loaded';
    statusCls = 'text-gray-500';
  } else if (age <= 30) {
    statusIcon = '<span class="w-2 h-2 rounded-full bg-green-400 shrink-0"></span>';
    statusText = 'Fresh';
    statusCls = 'text-green-700';
  } else if (age <= 60) {
    statusIcon = '<span class="w-2 h-2 rounded-full bg-blue-400 shrink-0"></span>';
    statusText = 'OK';
    statusCls = 'text-blue-700';
  } else if (age <= 120) {
    statusIcon = '<span class="w-2 h-2 rounded-full bg-amber-400 shrink-0"></span>';
    statusText = 'Stale';
    statusCls = 'text-amber-700';
  } else {
    statusIcon = '<span class="w-2 h-2 rounded-full bg-red-400 shrink-0"></span>';
    statusText = 'Very stale';
    statusCls = 'text-red-600';
  }

  const lastReload = c.last_reload_ts
    ? new Date(c.last_reload_ts * 1000).toLocaleTimeString('vi-VN')
    : 'N/A';

  body.innerHTML = `
    <!-- Status -->
    <div class="space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs text-gray-500">Status</span>
        <div class="flex items-center gap-1.5">
          ${statusIcon}
          <span class="text-xs font-semibold ${statusCls}">${statusText}</span>
        </div>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-xs text-gray-500">Cache age</span>
        <span class="text-xs font-mono text-gray-700">${age != null ? Math.round(age) + 's' : '-'}</span>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-xs text-gray-500">TTL remaining</span>
        <span class="text-xs font-mono text-gray-700">${c.ttl_remaining != null ? Math.round(c.ttl_remaining) + 's' : '-'}</span>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-xs text-gray-500">Last reload</span>
        <span class="text-xs font-mono text-gray-700">${lastReload}</span>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-xs text-gray-500">Auto-refresh</span>
        <span class="text-xs text-gray-700">${c.ttl_total || 60}s</span>
      </div>
    </div>

    <!-- Reload button -->
    <button id="reload-cache-btn" onclick="reloadCache()"
            class="w-full mt-3 py-2 px-3 text-xs font-semibold rounded-lg border border-blue-200 text-blue-600 bg-blue-50 hover:bg-blue-100 transition-colors flex items-center justify-center gap-2">
      <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
      Reload Cache
    </button>

    <!-- Process info -->
    <div class="mt-3 p-2.5 bg-gray-50 rounded-lg border border-gray-100">
      <p class="text-[10px] text-gray-500 leading-relaxed flex items-start gap-1.5">
        ${SVG.infoCircle.replace('w-4 h-4','w-3.5 h-3.5 shrink-0 mt-0.5')}
        <span>Reload cache sẽ cập nhật web runtime cache.<br>Worker có thể vẫn dùng cache riêng cho đến khi nó tự refresh hoặc restart.</span>
      </p>
    </div>
  `;
}

async function reloadCache() {
  const btn = document.getElementById('reload-cache-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg> Reloading...';
  }
  try {
    const res = await fetch('/platform-config/cache/invalidate', {method: 'POST'});
    if (res.ok) {
      showToast('Cache da reload. Config moi co hieu luc.');
      await loadRuntimeSnapshot();
      loadCacheState();
      loadStepResolution();
      loadSelectorHealth();
    } else {
      showToast('Loi reload cache. Thu lai sau.');
    }
  } catch (e) {
    showToast('Loi reload cache. Thu lai sau.');
  }
  if (btn) btn.disabled = false;
}

// ─── Card 4: Preset Control ──────────────────────────────────

async function loadPresetControl() {
  const body = document.getElementById('preset-control-body');
  try {
    const [postRes, commentRes] = await Promise.all([
      fetch('/platform-config/presets?platform=facebook&job_type=POST'),
      fetch('/platform-config/presets?platform=facebook&job_type=COMMENT'),
    ]);
    const postPresets = await postRes.json();
    const commentPresets = await commentRes.json();

    const renderGroup = (label, presets) => {
      if (!presets.length) return '';
      return `
        <div class="mb-4">
          <p class="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">${label}</p>
          <div class="space-y-2">
            ${presets.map(p => {
              const isActive = !!p.is_active;
              return `
                <div class="p-2.5 rounded-lg border transition-all ${isActive ? 'bg-indigo-50/50 border-indigo-200' : 'bg-white border-gray-200 hover:border-gray-300'}">
                  <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2 min-w-0">
                      ${isActive ? '<span class="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0"></span>' : '<span class="w-1.5 h-1.5 rounded-full bg-gray-300 shrink-0"></span>'}
                      <span class="text-xs font-mono truncate ${isActive ? 'text-indigo-700 font-bold' : 'text-gray-600'}">${p.name}</span>
                    </div>
                    ${isActive
                      ? '<span class="text-[10px] px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-semibold shrink-0">Active</span>'
                      : `<button onclick="previewAndSwitch('${p.name}')"
                                class="text-[10px] px-2.5 py-1 rounded-lg border border-indigo-200 text-indigo-600 bg-white hover:bg-indigo-50 font-semibold shrink-0 transition-colors">
                           Preview &amp; Switch
                         </button>`}
                  </div>
                  <p class="text-[10px] text-gray-400 mt-1 ml-3.5">${p.description || ''}</p>
                </div>`;
            }).join('')}
          </div>
        </div>`;
    };

    body.innerHTML = renderGroup('POST Presets', postPresets)
                   + renderGroup('COMMENT Presets', commentPresets);
    if (!postPresets.length && !commentPresets.length) {
      body.innerHTML = '<p class="text-xs text-gray-400">Khong co preset nao. Tao preset moi trong tab Workflows.</p>';
    }
  } catch (e) {
    body.innerHTML = `<p class="text-xs text-red-500">Error loading presets</p>`;
  }
}

// ─── Preset Impact Preview Modal ──────────────────────────────

async function previewAndSwitch(toPreset) {
  const reqId = ++_currentPreviewId;
  const activePreset = _runtimeData?.preset;
  if (!activePreset) {
    showToast('Không có preset active để so sánh.');
    return;
  }

  const existing = document.getElementById('preset-modal-overlay');
  if (existing) existing.remove();

  // Create modal
  const modal = document.createElement('div');
  modal.id = 'preset-modal-overlay';
  modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm transition-opacity';
  modal.innerHTML = `
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] overflow-hidden flex flex-col">
      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <h3 class="text-base font-bold text-gray-800">Switch Preset?</h3>
        <button onclick="document.getElementById('preset-modal-overlay').remove()" class="p-1 rounded-lg hover:bg-gray-100 text-gray-400 focus:outline-none">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <div id="preset-modal-body" class="px-6 py-4 overflow-y-auto flex-1">
        <div class="flex flex-col items-center justify-center py-8">
          <svg class="w-6 h-6 animate-spin text-indigo-500 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          <span class="text-xs text-gray-500">Đang phân tích thay đổi...</span>
        </div>
      </div>
    </div>`;
  document.body.appendChild(modal);

  try {
    const res = await fetch(`/platform-config/presets/preview-switch?from_preset=${encodeURIComponent(activePreset)}&to_preset=${encodeURIComponent(toPreset)}&mode=cache`);
    const diff = await res.json();
    if (reqId !== _currentPreviewId) return;
    if (!document.getElementById('preset-modal-overlay')) return;

    if (diff.error) throw new Error(diff.error);

    const mbody = document.getElementById('preset-modal-body');

    // Step changes
    let stepsDiffHtml = '';
    if (diff.diff.steps_removed.length || diff.diff.steps_added.length) {
      stepsDiffHtml = `
        <div class="mb-3">
          <div class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold mb-1.5">Steps</div>
          ${diff.diff.steps_removed.map(s => `
            <div class="flex items-center gap-2 py-1">
              ${SVG.xCircle}
              <span class="text-xs font-mono text-gray-700">${s}</span>
              <span class="text-[10px] text-red-500 font-semibold bg-red-50 px-1 rounded">RUN -> SKIP</span>
            </div>`).join('')}
          ${diff.diff.steps_added.map(s => `
            <div class="flex items-center gap-2 py-1">
              ${SVG.checkCircle}
              <span class="text-xs font-mono text-gray-700">${s}</span>
              <span class="text-[10px] text-green-600 font-semibold bg-green-50 px-1 rounded">SKIP -> RUN</span>
            </div>`).join('')}
        </div>`;
    }

    // Timing changes
    let timingDiffHtml = '';
    if (diff.diff.timing_changed.length) {
      timingDiffHtml = `
        <div class="mb-3">
          <div class="text-[10px] uppercase tracking-wider text-gray-400 font-semibold mb-1.5">Timing</div>
          ${diff.diff.timing_changed.map(t => {
            const pctText = t.change_pct != null ? `${t.change_pct > 0 ? '+' : ''}${t.change_pct}%` : '';
            const pctCls = t.change_pct && t.change_pct < -30 ? 'text-red-500 font-bold bg-red-50 px-1 rounded' : 'text-gray-400';
            return `<div class="flex items-center gap-2 py-1 text-xs">
              <span class="font-mono text-gray-600 w-40 truncate">${t.key}</span>
              <span class="text-gray-400">${t.from != null ? t.from + 'ms' : '-'}</span>
              <svg class="w-3 h-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
              <span class="font-semibold text-gray-700">${t.to != null ? t.to + 'ms' : 'removed'}</span>
              <span class="text-[10px] ${pctCls}">${pctText}</span>
            </div>`;
          }).join('')}
        </div>`;
    }

    // Risk messages
    const riskHtml = diff.risk_messages.length ? `
      <div class="p-3 rounded-lg ${diff.risk_level === 'high' ? 'bg-red-50 border border-red-200' : 'bg-amber-50 border border-amber-200'} mb-3">
        ${diff.risk_messages.map(m => `
          <div class="flex items-start gap-2 text-xs ${diff.risk_level === 'high' ? 'text-red-700 font-semibold' : 'text-amber-700'} mb-1 last:mb-0">
            ${diff.risk_level === 'high' ? SVG.alertCritical.replace('text-red-600','text-red-500 mt-0.5') : SVG.alertTriangle.replace('text-amber-500','text-amber-600 mt-0.5')}
            <span>${m}</span>
          </div>`).join('')}
      </div>` : '';

    const noChanges = !diff.diff.steps_removed.length && !diff.diff.steps_added.length && !diff.diff.timing_changed.length;

    mbody.innerHTML = `
      <div class="flex items-center gap-3 mb-4 p-3 bg-gray-50 rounded-lg border border-gray-100">
        <div class="text-xs flex flex-col">
          <span class="text-[10px] uppercase text-gray-400 font-semibold mb-0.5">From</span>
          <span class="font-mono font-semibold text-gray-500 truncate max-w-[150px]">${diff.from.name}</span>
        </div>
        <svg class="w-5 h-5 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
        <div class="text-xs flex flex-col">
          <span class="text-[10px] uppercase text-indigo-400 font-semibold mb-0.5">To</span>
          <span class="font-mono font-bold text-indigo-700 truncate max-w-[150px]">${diff.to.name}</span>
        </div>
      </div>

      ${noChanges ? '<p class="text-xs text-gray-400 mb-3 bg-gray-50 p-2 rounded text-center">Không có thay đổi đáng kể giữa 2 preset này.</p>' : ''}

      <div class="${noChanges ? 'hidden' : 'mb-4'}">
        ${stepsDiffHtml}
        ${timingDiffHtml}
        ${!noChanges && !stepsDiffHtml && !timingDiffHtml ? '<p class="text-xs text-gray-400">Config giống nhau.</p>' : ''}
      </div>

      ${riskHtml}

      <div id="modal-error-msg" class="hidden text-xs text-red-600 mb-3 text-center bg-red-50 p-2 rounded border border-red-100 font-semibold"></div>
      <p class="text-[10px] text-gray-500 mb-4 bg-gray-50 p-1.5 rounded flex items-center justify-center gap-1.5">
          ${SVG.infoCircle.replace('w-4 h-4 text-blue-500','w-3.5 h-3.5 text-gray-400')}
          Thay đổi có hiệu lực với job tiếp theo.
      </p>

      <div class="flex items-center gap-3 justify-end pt-2 border-t border-gray-50 mt-auto">
        <button onclick="document.getElementById('preset-modal-overlay').remove()"
                class="px-4 py-2 text-xs font-semibold rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50">
          Cancel
        </button>
        <button onclick="confirmSwitch('${toPreset}', this)"
                ${noChanges ? 'disabled' : ''}
                class="min-w-[140px] px-4 py-2 text-xs font-semibold rounded-lg ${noChanges ? 'bg-gray-200 text-gray-400 cursor-not-allowed' : 'bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm'} flex items-center justify-center gap-1.5 disabled:opacity-75 disabled:cursor-wait">
          ${noChanges ? '' : '<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>'}
          <span>${noChanges ? 'No Effect' : 'Confirm Switch'}</span>
        </button>
      </div>`;
  } catch (e) {
    if (reqId !== _currentPreviewId) return;
    const mbody = document.getElementById('preset-modal-body');
    if (mbody) {
      mbody.innerHTML = `
        <div class="text-center py-8">
          <svg class="w-8 h-8 text-red-200 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          <p class="text-xs font-semibold text-red-600">Error loading preview</p>
          <p class="text-[10px] text-red-400 mt-1 max-w-[250px] mx-auto truncate">${e.message}</p>
          <button onclick="document.getElementById('preset-modal-overlay').remove()"
                  class="mt-4 px-4 py-1.5 rounded bg-gray-100 text-xs font-semibold text-gray-600 hover:bg-gray-200 transition-colors">Đóng</button>
        </div>`;
    }
  }
}

async function confirmSwitch(name, btn) {
  const modal = document.getElementById('preset-modal-overlay');
  const errorBox = document.getElementById('modal-error-msg');
  if (errorBox) errorBox.classList.add('hidden');

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<svg class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg> <span>Applying...</span>`;
  }

  try {
    const res = await fetch('/platform-config/presets/apply', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name})
    });
    const data = await res.json();
    if (data.success) {
      if (modal) modal.remove();
      showToast(`Preset '${name}' activated successfully.`);
      await loadOverview();
    } else {
      throw new Error(data.message || 'Error applying preset');
    }
  } catch (e) {
    if (errorBox) {
      errorBox.textContent = e.message;
      errorBox.classList.remove('hidden');
    } else {
      showToast(e.message);
    }
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg> <span>Confirm Switch</span>`;
    }
  }
}

// ─── Card 5: Step Resolution ──────────────────────────────────

async function loadStepResolution() {
  const body = document.getElementById('step-resolution-body');
  if (!_runtimeData || !_runtimeData.step_resolution) {
    // Wait for runtime data
    setTimeout(loadStepResolution, 500);
    return;
  }
  const steps = _runtimeData.step_resolution;
  if (!steps.length) {
    body.innerHTML = '<p class="text-xs text-gray-400">Khong co step data. Kiem tra tab Workflows.</p>';
    return;
  }

  body.innerHTML = `
    <table class="w-full">
      <tbody>
        ${steps.map(s => {
          const icon = s.status === 'RUN' ? SVG.checkCircle : SVG.xCircle;
          const statusCls = s.status === 'RUN'
            ? 'bg-green-50 text-green-700'
            : 'bg-red-50 text-red-600';
          return `<tr class="border-t border-gray-50">
            <td class="py-2 pr-2 w-6">${icon}</td>
            <td class="py-2 pr-3 text-xs font-mono text-gray-700">${s.step}</td>
            <td class="py-2 pr-3"><span class="text-[10px] font-semibold px-1.5 py-0.5 rounded ${statusCls}">${s.status}</span></td>
            <td class="py-2 pr-2">${sourceTag(s.source)}</td>
            <td class="py-2 text-[10px] text-gray-400">${s.reason || ''}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
    <p class="text-[10px] text-gray-400 mt-3 pt-2 border-t border-gray-100">
      Thay doi steps trong tab Workflows hoac switch preset.
    </p>`;
}

// ─── Card 6: Selector Health ──────────────────────────────────

async function loadSelectorHealth() {
  const body = document.getElementById('selector-health-body');
  try {
    const res = await fetch('/platform-config/selector-health');
    const data = await res.json();
    _selectorData = data;

    if (!data.total_tracked) {
      const uptime = data.server_uptime_seconds;
      const uptimeText = uptime < 60 ? `${uptime}s` : `${Math.floor(uptime/60)}m ${Math.round(uptime%60)}s`;
      body.innerHTML = `
        <div class="text-center py-4">
          <svg class="w-8 h-8 text-gray-200 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
          <p class="text-xs text-gray-500 font-medium">Chưa có dữ liệu selector health</p>
          <p class="text-[10px] text-gray-400 mt-1">Run a job to collect metrics.</p>
          <p class="text-[10px] text-gray-400 mt-1">Server start: ${uptimeText} trước</p>
        </div>`;
      buildWarningsFromData(_runtimeData, data);
      return;
    }

    const s = data.summary;
    // Summary counters
    const summaryHtml = `
      <div class="grid grid-cols-4 gap-2 mb-3">
        <div class="text-center p-2 bg-gray-50 rounded-lg">
          <div class="text-sm font-bold text-gray-700">${data.total_tracked}</div>
          <div class="text-[10px] text-gray-400">total</div>
        </div>
        <div class="text-center p-2 bg-green-50 rounded-lg">
          <div class="text-sm font-bold text-green-600">${s.healthy}</div>
          <div class="text-[10px] text-green-500">healthy</div>
        </div>
        <div class="text-center p-2 bg-amber-50 rounded-lg">
          <div class="text-sm font-bold text-amber-600">${s.warning}</div>
          <div class="text-[10px] text-amber-500">warning</div>
        </div>
        <div class="text-center p-2 bg-red-50 rounded-lg">
          <div class="text-sm font-bold text-red-600">${s.failing}</div>
          <div class="text-[10px] text-red-500">failing</div>
        </div>
      </div>`;

    // Items grouped by severity
    const failing = data.items.filter(i => i.severity === 'critical');
    const warning = data.items.filter(i => i.severity === 'warning');
    const healthy = data.items.filter(i => i.severity === 'healthy');

    const renderItem = (item, expanded) => {
      const barColor = item.severity === 'critical' ? 'bg-red-400' : item.severity === 'warning' ? 'bg-amber-400' : 'bg-green-400';
      const bgCls = item.severity === 'critical' ? 'bg-red-50 border border-red-100' : (item.severity === 'warning' ? 'bg-amber-50 border border-amber-100' : 'bg-white border border-gray-100');
      const agoText = item.last_attempt_ago != null ? `${item.last_attempt_ago}s ago` : '';

      let suggestionHtml = '';
      if (item.suggestion) {
        suggestionHtml = `
          <div class="mt-2 ml-6 p-2 bg-white/60 rounded flex flex-col gap-1">
            <div class="flex items-start gap-1.5">
              ${SVG.lightbulb.replace('w-3.5 h-3.5 mt-0.5', 'w-3.5 h-3.5 mt-0.5 text-amber-500 shrink-0')}
              <span class="text-[10px] text-gray-600 font-medium">${item.suggestion}</span>
            </div>
            <div class="flex items-start gap-1.5 ml-5">
              <span class="text-[10px] text-indigo-600 font-semibold">&rarr; Action:</span>
              <span class="text-[10px] text-gray-500">Mở tab Selectors và cập nhật giá trị mới.</span>
            </div>
          </div>`;
      }

      return `
        <div class="p-2.5 rounded-lg ${bgCls} ${expanded ? 'mb-2' : 'flex items-center gap-2 mb-1'}">
          ${expanded ? `
            <div class="flex items-center gap-2 mb-1.5">
              ${item.severity === 'critical' ? SVG.xCircle : item.severity === 'warning' ? SVG.alertTriangle : SVG.checkCircle}
              <span class="text-xs font-mono text-gray-800 font-bold flex-1 truncate">${item.key}</span>
              <span class="text-[10px] text-gray-400">${agoText}</span>
            </div>
            <div class="flex items-center gap-2 ml-6 mb-1.5">
              <span class="text-[10px] text-gray-500 bg-white px-1.5 py-0.5 rounded shadow-sm">${item.hit}/${item.total} hits</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded shadow-sm ${item.last_source === 'db' ? 'bg-blue-50 text-blue-600' : 'bg-orange-50 text-orange-600'}">${item.last_source}</span>
              <div class="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden shrink-0">
                <div class="h-full ${barColor} rounded-full" style="width:${item.rate}%"></div>
              </div>
              <span class="text-[10px] font-bold text-gray-700">${item.rate}%</span>
            </div>
            ${suggestionHtml}
          ` : `
            ${SVG.checkCircle}
            <span class="text-xs font-mono text-gray-600 flex-1 truncate">${item.key}</span>
            <div class="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden shrink-0">
              <div class="h-full ${barColor} rounded-full" style="width:${item.rate}%"></div>
            </div>
            <span class="text-[10px] text-gray-400 w-8 text-right">${item.hit}/${item.total}</span>
          `}
        </div>`;
    };

    let itemsHtml = '';
    if (failing.length) {
      itemsHtml += `<div class="mb-3"><div class="text-[10px] font-bold text-red-500 uppercase tracking-wider mb-2">Can xu ly (${failing.length})</div>
        <div>${failing.map(i => renderItem(i, true)).join('')}</div></div>`;
    }
    if (warning.length) {
      itemsHtml += `<div class="mb-3"><div class="text-[10px] font-bold text-amber-500 uppercase tracking-wider mb-2">Can theo doi (${warning.length})</div>
        <div>${warning.map(i => renderItem(i, true)).join('')}</div></div>`;
    }
    if (healthy.length) {
      itemsHtml += `<details class="group"><summary class="text-[10px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-600 mb-2 transition-colors">Healthy (${healthy.length}) <span class="text-[10px] text-gray-300 group-open:hidden ml-1">Show</span></summary>
        <div>${healthy.map(i => renderItem(i, false)).join('')}</div></details>`;
    }

    body.innerHTML = summaryHtml + itemsHtml;

    // Call warnings logic
    buildWarningsFromData(_runtimeData, data);
  } catch (e) {
    body.innerHTML = '<p class="text-xs text-red-500">Error loading selector health</p>';
  }
}

// ─── Card 1.5: Simulation & Debug Assistant ───────────────────

function handleSimulateJob() {
  const panel = document.getElementById('simulation-panel');
  if (!panel) return;
  panel.classList.remove('hidden');
  panel.innerHTML = '<div class="p-5 text-center text-xs text-gray-500">Đang phân tích...</div>';

  if (!_runtimeData || !_selectorData) {
    panel.innerHTML = '<div class="p-5 text-center text-xs text-red-500">Chưa tải xong dữ liệu để simulate.</div>';
    return;
  }

  const modeRadio = document.querySelector('input[name="simulation-mode"]:checked');
  const mode = modeRadio ? modeRadio.value : 'realistic';

  // Call pure simulation logic (from platform_config_simulation.js)
  const result = simulateJob(_runtimeData, _selectorData, { mode });
  renderSimulationResult(result);
}

function renderSimulationResult(result) {
  const panel = document.getElementById('simulation-panel');
  if (!panel) return;

  const bgCls = result.overall === 'FAIL' ? 'bg-red-50 border-red-200' 
              : (result.overall === 'RISK' ? 'bg-amber-50 border-amber-200' 
              : 'bg-green-50 border-green-200');
  
  const textTitleCls = result.overall === 'FAIL' ? 'text-red-700' 
              : (result.overall === 'RISK' ? 'text-amber-700' 
              : 'text-green-700');

  let stepsHtml = result.steps.map(s => {
    const sBg = s.execution_status === 'FAIL' ? 'bg-red-100 text-red-700'
              : (s.execution_status === 'RISK' ? 'bg-amber-100 text-amber-700'
              : (s.execution_status === 'SKIPPED' || s.execution_status === 'NOT_EXECUTED' ? 'bg-gray-100 text-gray-500' 
              : 'bg-green-100 text-green-700'));
    return `
      <div class="flex items-center justify-between text-[11px] py-1.5 border-b border-gray-50 last:border-0">
        <span class="font-mono text-gray-600 w-1/3 truncate">${s.step}</span>
        <span class="${sBg} px-1.5 py-0.5 rounded font-bold">${s.execution_status}</span>
        <span class="w-1/3 text-right text-gray-400 truncate" title="${s.reason}">${s.reason}</span>
      </div>
    `;
  }).join('');

  let firstFailureHtml = '';
  if (result.first_failure) {
    firstFailureHtml = `
      <div class="mt-3 p-2.5 bg-red-100 rounded-lg border border-red-200 text-red-800 text-[11px]">
        <strong>Điểm tịt dự đoán:</strong> ${result.first_failure.step} - do ${result.first_failure.reason}
        <br><strong class="text-red-600 mt-1 inline-block">&rarr; Action đề xuất:</strong> <span class="bg-white/60 px-1 py-0.5 rounded">${result.first_failure.action}</span>
      </div>
    `;
  }

  const html = `
    <div class="p-4 ${bgCls} border-b">
      <div class="flex justify-between items-center mb-1">
        <span class="font-bold uppercase tracking-wider text-[11px] ${textTitleCls}">Kết quả dự đoán: ${result.overall}</span>
        <span class="text-[10px] text-gray-500 bg-white px-2 py-0.5 rounded border border-gray-200 font-semibold shadow-sm">Mode: ${result.mode}</span>
      </div>
      <p class="text-xs ${textTitleCls} font-medium mt-1.5">${result.summary}</p>
      ${firstFailureHtml}
    </div>
    <div class="p-4 bg-gray-50 overflow-y-auto max-h-64">
      <h4 class="text-[10px] uppercase font-bold text-gray-400 tracking-wider mb-3">Chi tiết từng bước</h4>
      <div class="bg-white border rounded-lg px-3 py-1 shadow-sm">${stepsHtml}</div>
    </div>
  `;
  panel.innerHTML = html;
}

