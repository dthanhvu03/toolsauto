
// ─── State ────────────────────────────────────────────────────
let platforms = [];
let workflows = [];
let selectors = [];
let ctaList = [];
let editingSelectorId = null;

// ─── Init ─────────────────────────────────────────────────────
async function init() {
  await loadPlatforms();
  loadWorkflows();
  loadOverview();
}
init();

// ─── Tab switching ────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('bg-white', 'shadow-sm', 'text-gray-800');
    btn.classList.add('text-gray-500');
  });
  document.querySelectorAll('[id^="tab-content-"]').forEach(el => {
    el.classList.add('hidden');
  });
  document.getElementById(`tab-${tab}`)
          .classList.add('bg-white', 'shadow-sm', 'text-gray-800');
  document.getElementById(`tab-content-${tab}`)
          .classList.remove('hidden');

  if (tab === 'selectors') loadSelectors();
  if (tab === 'cta') loadCTA();
  if (tab === 'overview') loadOverview();
}

// ─── Platforms ────────────────────────────────────────────────
async function loadPlatforms() {
  const res = await fetch('/platform-config/platforms');
  platforms = await res.json();

  // Populate filter dropdowns
  const filterSel = document.getElementById('platform-filter');
  const sPlatform = document.getElementById('s-platform');
  const ctaPlatform = document.getElementById('cta-platform');

  [filterSel, sPlatform, ctaPlatform].forEach(sel => {
    if (!sel) return;
    const current = sel.value;
    // Keep first option
    while (sel.options.length > 1) sel.remove(1);
    platforms.forEach(p => {
      const label = (p.display_name || p.platform || '').trim();
      sel.appendChild(new Option(label, p.platform));
    });
    if (current) sel.value = current;
  });

  // Populate platform-filter for selector tab
  const spf = document.getElementById('selector-platform-filter');
  if (spf) {
    while (spf.options.length > 1) spf.remove(1);
    platforms.forEach(p => {
      const label = (p.display_name || p.platform || '').trim();
      spf.appendChild(new Option(label, p.platform));
    });
  }

  // Render platform cards
  const grid = document.getElementById('platforms-grid');
  grid.innerHTML = platforms.map(p => `
    <div class="bg-white rounded-xl border p-4
                ${!p.is_active ? 'opacity-50' : ''}">
      <div class="flex items-center gap-2 mb-3">
        <div>
          <p class="font-semibold text-gray-800">
            ${p.display_name}
          </p>
          <p class="text-xs text-gray-400">${p.platform}</p>
        </div>
        <span class="ml-auto text-xs px-2 py-0.5 rounded-full
                     ${p.is_active
                       ? 'bg-green-100 text-green-700'
                       : 'bg-gray-100 text-gray-500'}">
          ${p.is_active ? 'Active' : 'Inactive'}
        </span>
      </div>
      <p class="text-xs text-gray-400 font-mono truncate mb-3">
        ${p.adapter_class}
      </p>
      <div class="flex gap-1 text-xs text-gray-500">
        <span class="bg-gray-50 px-2 py-0.5 rounded">
          ${(p.media_extensions || []).join(', ')}
        </span>
      </div>
    </div>
  `).join('');
}

// ─── Workflows ────────────────────────────────────────────────
async function loadWorkflows(platform = '') {
  const res = await fetch(
    `/platform-config/workflows${platform ? '?platform=' + platform : ''}`
  );
  workflows = await res.json();

  const container = document.getElementById('workflows-container');
  container.innerHTML = workflows.map(wf => `
    <div class="bg-white rounded-xl border overflow-hidden">
      <!-- Workflow Header -->
      <div class="flex items-center gap-3 p-4 border-b bg-gray-50">
        <div>
          <p class="font-semibold text-gray-800">${wf.name}</p>
          <p class="text-xs text-gray-400">
            ${wf.platform} · ${wf.job_type}
          </p>
        </div>
        <span class="ml-auto text-xs px-2 py-0.5 rounded-full
                     ${wf.is_active
                       ? 'bg-green-100 text-green-700'
                       : 'bg-gray-100 text-gray-500'}">
          ${wf.is_active ? '▶ Active' : 'Inactive'}
        </span>
        ${!wf.is_active
          ? `<button onclick="applyPreset('${wf.name}')"
                    class="text-xs px-2.5 py-1 rounded-lg
                           bg-indigo-50 text-indigo-600 border
                           border-indigo-200 hover:bg-indigo-100
                           font-medium ml-2">
               Activate
             </button>`
          : ''}
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-0
                  divide-x divide-gray-100">

        <!-- Steps — Drag-and-drop -->
        <div class="p-4">
          <p class="text-xs font-semibold text-gray-500 uppercase
                    tracking-wide mb-3">
            Workflow Steps
            <span class="text-gray-300 font-normal ml-1">
              (kéo để sắp xếp)
            </span>
          </p>
          <ul id="steps-${wf.id}"
              class="space-y-1.5 min-h-[100px]"
              data-workflow-id="${wf.id}">
            ${wf.steps.map((step, i) => `
              <li data-step="${step}"
                  class="flex items-center gap-2 bg-gray-50
                         border border-gray-200 rounded-lg
                         px-3 py-2 cursor-grab text-sm
                         select-none group">
                <span class="text-gray-400 font-mono text-xs select-none" title="Kéo">::</span>
                <span class="flex-1 font-mono text-xs text-gray-700">
                  ${step}
                </span>
                <span class="text-xs text-gray-300">${i + 1}</span>
              </li>
            `).join('')}
          </ul>
          <button onclick="saveSteps(${wf.id})"
                  class="mt-3 w-full text-xs text-indigo-600
                         border border-indigo-200 rounded-lg py-1.5
                         hover:bg-indigo-50">
            Lưu thứ tự
          </button>
        </div>

        <!-- Timing config -->
        <div class="p-4">
          <p class="text-xs font-semibold text-gray-500 uppercase
                    tracking-wide mb-3">Timing Config (ms)</p>
          <div class="space-y-2" id="timing-${wf.id}">
            ${Object.entries(wf.timing_config || {}).map(([k, v]) => `
              <div class="flex items-center gap-2">
                <label class="text-xs text-gray-500 flex-1
                              font-mono">${k}</label>
                <input type="number" value="${v}"
                       data-key="${k}"
                       onchange="markTimingDirty(${wf.id})"
                       class="w-24 border rounded px-2 py-1
                              text-xs text-right">
              </div>
            `).join('')}
          </div>
          <button onclick="saveTiming(${wf.id})"
                  id="save-timing-${wf.id}"
                  class="mt-3 w-full text-xs text-green-600
                         border border-green-200 rounded-lg py-1.5
                         hover:bg-green-50 hidden">
            Lưu timing
          </button>
        </div>
      </div>
    </div>
  `).join('');

  // Initialize SortableJS for each workflow's step list
  workflows.forEach(wf => {
    const el = document.getElementById(`steps-${wf.id}`);
    if (el) {
      Sortable.create(el, {
        animation: 150,
        ghostClass: 'bg-indigo-50',
        handle: 'li',
        onEnd: () => markStepsDirty(wf.id)
      });
    }
  });
}

function markStepsDirty(workflowId) {
  // Visual indicator that steps changed
  const btn = document.querySelector(
    `#steps-${workflowId} ~ button`
  );
}

function markTimingDirty(workflowId) {
  document.getElementById(`save-timing-${workflowId}`)
          ?.classList.remove('hidden');
}

async function saveSteps(workflowId) {
  const list = document.getElementById(`steps-${workflowId}`);
  const steps = [...list.querySelectorAll('li')]
    .map(li => li.dataset.step);

  const res = await fetch(
    `/platform-config/workflows/${workflowId}/steps`,
    {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({steps})
    }
  );
  if ((await res.json()).success) {
    showToast('Đã lưu thứ tự workflow');
  }
}

async function saveTiming(workflowId) {
  const container = document.getElementById(`timing-${workflowId}`);
  const timing_config = {};
  container.querySelectorAll('input[data-key]').forEach(input => {
    timing_config[input.dataset.key] = parseFloat(input.value);
  });

  const res = await fetch(
    `/platform-config/workflows/${workflowId}/timing`,
    {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({timing_config})
    }
  );
  if ((await res.json()).success) {
    document.getElementById(`save-timing-${workflowId}`)
            ?.classList.add('hidden');
    showToast('Đã lưu timing config');
  }
}

// ─── Selectors ────────────────────────────────────────────────
async function loadSelectors() {
  const platform = document.getElementById(
    'selector-platform-filter'
  )?.value || '';
  const category = document.getElementById(
    'selector-category-filter'
  )?.value || '';

  const params = new URLSearchParams();
  if (platform) params.set('platform', platform);
  if (category) params.set('category', category);

  const res = await fetch(
    `/platform-config/selectors?${params}`
  );
  selectors = await res.json();

  // Group by category
  const grouped = {};
  selectors.forEach(s => {
    const key = `${s.platform}:${s.category}`;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(s);
  });

  const container = document.getElementById(
    'selectors-by-category'
  );
  container.innerHTML = Object.entries(grouped).map(
    ([key, items]) => {
      const [plt, cat] = key.split(':');
      return `
        <div class="bg-white rounded-xl border overflow-hidden">
          <div class="flex items-center gap-3 px-4 py-3
                      bg-gray-50 border-b">
            <span class="text-xs font-semibold text-gray-500
                         uppercase tracking-wide">
              ${plt} · ${cat}
            </span>
            <span class="text-xs text-gray-400">
              ${items.length} selectors
            </span>
            <span class="text-xs text-gray-300 ml-auto">
              Kéo để ưu tiên
            </span>
          </div>
          <ul id="sel-${key.replace(':', '-')}"
              data-group="${key}"
              class="divide-y divide-gray-50 min-h-[50px]">
            ${items.map(s => `
              <li data-id="${s.id}"
                  class="flex items-center gap-3 px-4 py-2.5
                         cursor-grab hover:bg-gray-50
                         ${!s.is_active ? 'opacity-40' : ''}
                         select-none group">
                <span class="text-gray-400 font-mono text-xs select-none" title="Kéo">::</span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-xs px-1.5 py-0.5 rounded
                                 bg-blue-50 text-blue-600
                                 font-mono">
                      ${s.selector_type}
                    </span>
                    <span class="text-xs text-gray-500">
                      ${s.selector_name}
                    </span>
                    ${s.locale !== '*'
                      ? `<span class="text-xs px-1 py-0.5 rounded
                                      bg-yellow-50 text-yellow-600">
                           ${s.locale}
                         </span>`
                      : ''}
                  </div>
                  <p class="text-sm font-mono text-gray-700
                            truncate mt-0.5">
                    ${s.selector_value}
                  </p>
                  ${s.notes
                    ? `<p class="text-xs text-gray-400 mt-0.5">
                         ${s.notes}
                       </p>`
                    : ''}
                </div>
                <div class="flex gap-1 opacity-0
                            group-hover:opacity-100">
                  <button onclick="editSelector(${s.id})"
                          class="p-1.5 text-blue-600
                                 hover:bg-blue-50 rounded text-xs">
                    Sửa
                  </button>
                  <button onclick="toggleSelector(${s.id})"
                          class="p-1.5 text-gray-600
                                 hover:bg-gray-100 rounded text-xs">
                    ${s.is_active ? 'Tắt' : 'Bật'}
                  </button>
                  <button onclick="deleteSelector(${s.id})"
                          class="p-1.5 text-red-600
                                 hover:bg-red-50 rounded text-xs">
                    Xóa
                  </button>
                </div>
                <span class="text-xs text-gray-300 w-6 text-right">
                  ${s.priority}
                </span>
              </li>
            `).join('')}
          </ul>
          <div class="px-4 py-2 border-t bg-gray-50">
            <button onclick="saveSelectorsOrder('${key}')"
                    class="text-xs text-indigo-600
                           hover:underline">
              Lưu thứ tự
            </button>
          </div>
        </div>
      `;
    }
  ).join('');

  // Initialize SortableJS for each category group
  Object.keys(grouped).forEach(key => {
    const elId = `sel-${key.replace(':', '-')}`;
    const el = document.getElementById(elId);
    if (el) {
      Sortable.create(el, {
        animation: 150,
        ghostClass: 'bg-indigo-50',
        handle: 'li',
      });
    }
  });
}

async function saveSelectorsOrder(groupKey) {
  const elId = `sel-${groupKey.replace(':', '-')}`;
  const list = document.getElementById(elId);
  const items = [...list.querySelectorAll('li')]
    .map((li, i) => ({
      id: parseInt(li.dataset.id),
      priority: 100 - (i * 10)  // descending priority
    }));

  const res = await fetch('/platform-config/selectors/reorder', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({items})
  });
  if ((await res.json()).success) {
    showToast('Đã lưu thứ tự selector');
  }
}

async function editSelector(id) {
  const sel = selectors.find(s => s.id === id);
  if (!sel) return;
  editingSelectorId = id;

  document.getElementById('s-platform').value = sel.platform;
  document.getElementById('s-category').value = sel.category;
  document.getElementById('s-name').value = sel.selector_name;
  document.getElementById('s-type').value = sel.selector_type;
  document.getElementById('s-locale').value = sel.locale;
  document.getElementById('s-value').value = sel.selector_value;
  document.getElementById('s-notes').value = sel.notes || '';

  openSelectorModal();
}

async function toggleSelector(id) {
  const sel = selectors.find(s => s.id === id);
  if (!sel) return;
  await fetch(`/platform-config/selectors/${id}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({is_active: !sel.is_active})
  });
  loadSelectors();
}

async function deleteSelector(id) {
  if (!confirm('Xóa selector này?')) return;
  await fetch(`/platform-config/selectors/${id}`,
              {method: 'DELETE'});
  loadSelectors();
}

function openSelectorModal() {
  document.getElementById('selector-modal')
          .classList.remove('hidden');
}

function closeSelectorModal() {
  editingSelectorId = null;
  document.getElementById('selector-modal')
          .classList.add('hidden');
}

async function saveSelector() {
  const payload = {
    platform: document.getElementById('s-platform').value,
    category: document.getElementById('s-category').value,
    selector_name: document.getElementById('s-name').value,
    selector_type: document.getElementById('s-type').value,
    locale: document.getElementById('s-locale').value,
    selector_value: document.getElementById('s-value').value,
    notes: document.getElementById('s-notes').value,
  };

  if (editingSelectorId) {
    await fetch(
      `/platform-config/selectors/${editingSelectorId}`,
      {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      }
    );
  } else {
    await fetch('/platform-config/selectors', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
  }

  closeSelectorModal();
  loadSelectors();
}

// ─── CTA Templates ────────────────────────────────────────────
async function loadCTA() {
  const platform = document.getElementById(
    'platform-filter'
  )?.value || '';
  const params = platform ? `?platform=${platform}` : '';
  const res = await fetch(`/platform-config/cta${params}`);
  ctaList = await res.json();

  const list = document.getElementById('cta-list');
  list.innerHTML = ctaList.map(cta => `
    <div data-id="${cta.id}"
         class="flex items-start gap-3 p-3 border rounded-lg
                bg-gray-50 cursor-grab hover:bg-white
                hover:border-indigo-200 transition-all
                ${!cta.is_active ? 'opacity-40' : ''}
                select-none group">
      <span class="text-gray-400 font-mono text-xs mt-0.5 select-none" title="Kéo">::</span>
      <div class="flex-1 min-w-0">
        <pre class="text-sm text-gray-700 whitespace-pre-wrap
                    font-sans leading-relaxed">${cta.template}</pre>
        <div class="flex gap-2 mt-1.5">
          <span class="text-xs px-1.5 py-0.5 rounded
                       bg-blue-50 text-blue-600">
            ${cta.platform}
          </span>
          <span class="text-xs px-1.5 py-0.5 rounded
                       bg-gray-100 text-gray-500">
            ${cta.locale}
          </span>
          ${cta.page_url
            ? `<span class="text-xs px-1.5 py-0.5 rounded
                            bg-purple-50 text-purple-600 truncate
                            max-w-[200px]" title="${cta.page_url}">
                 URL: ${cta.page_url}
               </span>`
            : ''}
          ${cta.niche
            ? `<span class="text-xs px-1.5 py-0.5 rounded
                            bg-yellow-50 text-yellow-600">
                 Niche: ${cta.niche}
               </span>`
            : ''}
        </div>
      </div>
      <div class="flex gap-1 opacity-0 group-hover:opacity-100">
        <button onclick="deleteCTA(${cta.id})"
                class="p-1.5 text-red-600 hover:bg-red-50
                       rounded text-xs">
          Xóa
        </button>
      </div>
      <span class="text-xs text-gray-300">${cta.priority}</span>
    </div>
  `).join('');

  // SortableJS for CTA list
  Sortable.create(list, {
    animation: 150,
    ghostClass: 'bg-indigo-50 border-indigo-300',
    handle: 'div[data-id]',
    onEnd: saveCTAOrder
  });
}

async function saveCTAOrder() {
  const list = document.getElementById('cta-list');
  const items = [...list.querySelectorAll('[data-id]')]
    .map((el, i) => ({
      id: parseInt(el.dataset.id),
      priority: 100 - (i * 10)
    }));

  await fetch('/platform-config/cta/reorder', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({items})
  });
  showToast('Đã lưu thứ tự CTA');
}

function openCTAModal() {
  document.getElementById('cta-modal').classList.remove('hidden');
}

function closeCTAModal() {
  document.getElementById('cta-modal').classList.add('hidden');
}

async function saveCTA() {
  const payload = {
    platform: document.getElementById('cta-platform').value,
    template: document.getElementById('cta-template').value,
    locale: document.getElementById('cta-locale').value,
    page_url: document.getElementById('cta-page-url').value || null,
    niche: document.getElementById('cta-niche').value || null,
    priority: 0,
  };

  await fetch('/platform-config/cta', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });

  closeCTAModal();
  loadCTA();
}

async function deleteCTA(id) {
  if (!confirm('Xóa CTA template này?')) return;
  await fetch(`/platform-config/cta/${id}`, {method: 'DELETE'});
  loadCTA();
}

// ─── Cache control ────────────────────────────────────────────
async function invalidateCache() {
  await fetch('/platform-config/cache/invalidate',
              {method: 'POST'});
  showToast('Cache đã được reload');
}

// ─── Platform switching ───────────────────────────────────────
function switchPlatform(platform) {
  loadWorkflows(platform);
  loadSelectors();
  loadCTA();
}

// ─── Toast notification ───────────────────────────────────────
function showToast(msg) {
  const toast = document.createElement('div');
  toast.className = (
    'fixed bottom-4 right-4 bg-gray-800 text-white '
    + 'px-4 py-2 rounded-lg text-sm z-50 '
    + 'transition-opacity duration-300'
  );
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// ─── Overview Panel (Redesigned) ──────────────────────────────

// SVG icon helpers (no emoji)
const SVG = {
  checkCircle: '<svg class="w-4 h-4 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
  xCircle: '<svg class="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
  skipForward: '<svg class="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>',
  alertTriangle: '<svg class="w-4 h-4 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>',
  alertCritical: '<svg class="w-4 h-4 text-red-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
  infoCircle: '<svg class="w-4 h-4 text-blue-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
  lightbulb: '<svg class="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>',
};

function sourceTag(src) {
  const map = {
    preset:   'bg-indigo-50 text-indigo-600 border-indigo-200',
    database: 'bg-blue-50 text-blue-600 border-blue-200',
    default:  'bg-gray-100 text-gray-500 border-gray-200',
    fallback: 'bg-orange-50 text-orange-600 border-orange-200',
    none:     'bg-red-50 text-red-500 border-red-200',
  };
  const cls = map[src] || map.default;
  return `<span class="text-[10px] px-1.5 py-0.5 rounded border ${cls}">${src}</span>`;
}

// ─── State ───
let _runtimeData = null;
let _currentRequestId = 0;
let _currentPreviewId = 0;

// ─── Main loader ───
async function loadOverview() {
  const existingModal = document.getElementById('preset-modal-overlay');
  if (existingModal) existingModal.remove();

  await loadRuntimeSnapshot();
  loadCacheState();
  loadPresetControl();
  loadStepResolution();
  loadSelectorHealth();
  loadWarnings();
}

function refreshRuntimeSnapshot() {
  loadRuntimeSnapshot();
}

// ─── Card 2: Runtime Snapshot ───
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

// ─── Card 3: Cache & Sync ───
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
      loadWarnings();
    } else {
      showToast('Loi reload cache. Thu lai sau.');
    }
  } catch (e) {
    showToast('Loi reload cache. Thu lai sau.');
  }
  if (btn) btn.disabled = false;
}

// ─── Card 4: Preset Control ───
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
              re// ─── Preset Impact Preview Modal ───
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
  // Do not close when clicking overlay to force explicit action
  
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

// ─── Card 5: Step Resolution ───
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

// ─── Card 6: Selector Health ───
async function loadSelectorHealth() {
  const body = document.getElementById('selector-health-body');
  try {
    const res = await fetch('/platform-config/selector-health');
    const data = await res.json();

    if (!data.total_tracked) {
      const uptime = data.server_uptime_seconds;
      const uptimeText = uptime < 60 ? `${uptime}s` : `${Math.floor(uptime/60)}m ${Math.round(uptime%60)}s`;
      body.innerHTML = `
        <div class="text-center py-4">
          <svg class="w-8 h-8 text-gray-200 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
          <p class="text-xs text-gray-500 font-medium">Chua co du lieu selector health</p>
          <p class="text-[10px] text-gray-400 mt-1">Health stats duoc ghi nhan khi worker chay job.</p>
          <p class="text-[10px] text-gray-400">Server start: ${uptimeText} truoc</p>
        </div>`;
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
      const bgCls = item.severity === 'critical' ? 'bg-red-50' : '';
      const agoText = item.last_attempt_ago != null ? `${item.last_attempt_ago}s ago` : '';
      return `
        <div class="p-2 rounded-lg ${bgCls} ${expanded ? '' : 'flex items-center gap-2'}">
          ${expanded ? `
            <div class="flex items-center gap-2 mb-1.5">
              ${item.severity === 'critical' ? SVG.xCircle : item.severity === 'warning' ? SVG.alertTriangle : SVG.checkCircle}
              <span class="text-xs font-mono text-gray-700 flex-1 truncate">${item.key}</span>
              <span class="text-[10px] text-gray-400">${agoText}</span>
            </div>
            <div class="flex items-center gap-2 ml-6 mb-1.5">
              <span class="text-[10px] text-gray-500">${item.hit}/${item.total} hits</span>
              <span class="text-[10px] px-1 py-0.5 rounded ${item.last_source === 'db' ? 'bg-blue-50 text-blue-600' : 'bg-orange-50 text-orange-600'}">${item.last_source}</span>
              <div class="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div class="h-full ${barColor} rounded-full" style="width:${item.rate}%"></div>
              </div>
              <span class="text-[10px] font-semibold text-gray-600">${item.rate}%</span>
            </div>
            ${item.suggestion ? `<div class="flex items-start gap-1.5 ml-6 p-2 bg-amber-50/50 rounded">
              ${SVG.lightbulb}
              <span class="text-[10px] text-amber-700">${item.suggestion}</span>
            </div>` : ''}
          ` : `
            ${item.severity === 'healthy' ? SVG.checkCircle : SVG.alertTriangle}
            <span class="text-xs font-mono text-gray-600 flex-1 truncate">${item.key}</span>
            <div class="w-12 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div class="h-full ${barColor} rounded-full" style="width:${item.rate}%"></div>
            </div>
            <span class="text-[10px] text-gray-500">${item.hit}/${item.total}</span>
          `}
        </div>`;
    };

    let itemsHtml = '';
    if (failing.length) {
      itemsHtml += `<div class="mb-2"><div class="text-[10px] font-semibold text-red-500 uppercase tracking-wider mb-1">Can xu ly (${failing.length})</div>
        <div class="space-y-1.5">${failing.map(i => renderItem(i, true)).join('')}</div></div>`;
    }
    if (warning.length) {
      itemsHtml += `<div class="mb-2"><div class="text-[10px] font-semibold text-amber-500 uppercase tracking-wider mb-1">Can theo doi (${warning.length})</div>
        <div class="space-y-1">${warning.map(i => renderItem(i, true)).join('')}</div></div>`;
    }
    if (healthy.length) {
      itemsHtml += `<details class="group"><summary class="text-[10px] font-semibold text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-600 mb-1">Healthy (${healthy.length}) <span class="text-[10px] text-gray-300 group-open:hidden">Show</span></summary>
        <div class="space-y-0.5">${healthy.map(i => renderItem(i, false)).join('')}</div></details>`;
    }

    body.innerHTML = summaryHtml + itemsHtml;
  } catch (e) {
    body.innerHTML = '<p class="text-xs text-red-500">Error loading selector health</p>';
  }
}

// ─── Card 7: Operational Warnings ───
async function loadWarnings() {
  const body = document.getElementById('warnings-body');
  const banner = document.getElementById('overview-alert-banner');
  try {
    const res = await fetch('/platform-config/overview-warnings?platform=facebook&job_type=POST');
    const data = await res.json();

    // Alert banner
    if (data.has_critical) {
      const criticals = data.items.filter(w => w.severity === 'critical');
      banner.className = 'mb-4 p-3 rounded-xl bg-red-50 border border-red-200 flex items-start gap-3';
      banner.innerHTML = `
        ${SVG.alertCritical.replace('w-4 h-4','w-5 h-5')}
        <div class="flex-1">
          ${criticals.map(c => `<p class="text-xs text-red-700 font-medium">${c.text}</p>`).join('')}
        </div>`;
    } else if (data.has_warning) {
      const warns = data.items.filter(w => w.severity === 'warning').slice(0, 2);
      banner.className = 'mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3';
      banner.innerHTML = `
        ${SVG.alertTriangle.replace('w-4 h-4','w-5 h-5')}
        <div class="flex-1">
          ${warns.map(w => `<p class="text-xs text-amber-700">${w.text}</p>`).join('')}
        </div>`;
    } else {
      banner.className = 'hidden';
      banner.innerHTML = '';
    }

    // Warnings card body
    if (!data.items.length) {
      body.innerHTML = `
        <div class="flex items-center gap-2">
          ${SVG.checkCircle}
          <span class="text-xs text-green-600 font-medium">Khong co canh bao - he thong hoat dong binh thuong</span>
        </div>`;
      return;
    }

    const criticals = data.items.filter(w => w.severity === 'critical');
    const warnings = data.items.filter(w => w.severity === 'warning');
    const infos = data.items.filter(w => w.severity === 'info');

    let html = '';
    if (criticals.length) {
      html += `<div class="p-2.5 rounded-lg bg-red-50 border border-red-200 mb-2 space-y-1">
        ${criticals.map(c => `<div class="flex items-start gap-2 text-xs text-red-700">${SVG.alertCritical}<span>${c.text}</span></div>`).join('')}
      </div>`;
    }
    if (warnings.length) {
      html += `<div class="p-2.5 rounded-lg bg-amber-50 border border-amber-200 mb-2 space-y-1">
        ${warnings.map(w => `<div class="flex items-start gap-2 text-xs text-amber-700">${SVG.alertTriangle}<span>${w.text}</span></div>`).join('')}
      </div>`;
    }
    if (infos.length) {
      html += `<details class="group mt-1"><summary class="text-[10px] text-gray-400 cursor-pointer hover:text-gray-600">${infos.length} thong tin bo sung (info)</summary>
        <div class="mt-1 space-y-1">
          ${infos.map(i => `<div class="flex items-start gap-2 text-[10px] text-gray-500">${SVG.infoCircle.replace('w-4 h-4','w-3 h-3')}<span>${i.text}</span></div>`).join('')}
        </div></details>`;
    }

    body.innerHTML = html;
  } catch (e) {
    banner.className = 'hidden';
    body.innerHTML = '<p class="text-xs text-red-500">Error loading warnings</p>';
  }
}

// ─── Patch loadOverview to chain cache state ───
const _origLoadOverview = loadOverview;
loadOverview = async function() {
  await _origLoadOverview();
  // Cache state depends on _runtimeData being populated
  setTimeout(loadCacheState, 300);
};
