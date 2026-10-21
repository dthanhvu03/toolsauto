/**
 * Live activity — job Buffer (poll) + log worker (SSE nếu đã đăng nhập).
 * Sự kiện mới làm sáng đúng đường trên đồ thị 3D.
 */

const MAX_LINES = 80;
const MAX_WORKER_LINES = 40;
const POLL_IDLE_MS = 8000;
const POLL_BUSY_MS = 3000;

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusClass(status, httpStatus) {
  const s = String(status || '').toUpperCase();
  if (s === 'DONE' || httpStatus === 200) return 'ok';
  if (s === 'FAILED' || httpStatus >= 400) return 'err';
  if (s === 'RUNNING' || httpStatus === 102) return 'run';
  return 'wait';
}

function statusLabel(status, httpStatus) {
  const s = String(status || '').toUpperCase();
  if (s === 'DONE') return 'DONE';
  if (s === 'FAILED') return httpStatus === 429 ? '429' : 'FAIL';
  if (s === 'RUNNING') return 'RUN';
  return 'WAIT';
}

function looksSensitive(line) {
  return /bearer\s|api[_-]?key|password|cookie|secret|token=/i.test(line);
}

function formatLine(evt, freshIds) {
  const cls = statusClass(evt.status, evt.httpStatus);
  const tag = statusLabel(evt.status, evt.httpStatus);
  const svc = String(evt.service || 'buffer').toUpperCase();
  const ch = escapeHtml(evt.channelName || evt.channelId || '—');
  const msg = escapeHtml((evt.message || '').slice(0, 160));
  const time = escapeHtml(evt.timeIct || '--:--');
  const jobId = evt.jobId != null ? evt.jobId : '?';
  const acc = evt.accountIndex != null ? evt.accountIndex : '';
  const fresh = freshIds && freshIds.has(String(jobId)) ? ' is-fresh' : '';

  return (
    `<div class="dispatch-line st-${cls}${fresh}" data-job="${jobId}" data-acc="${acc}">` +
    `<span class="dl-time">${time}</span>` +
    `<span class="dl-tag">${tag}</span>` +
    `<span class="dl-job">JOB #${jobId}</span>` +
    `<span class="dl-svc">${svc}</span>` +
    `<span class="dl-acc">#${acc}</span>` +
    `<span class="dl-ch">${ch}</span>` +
    `<span class="dl-msg">${msg}</span>` +
    `</div>`
  );
}

function formatWorkerLine(row) {
  const fresh = row.fresh ? ' is-fresh' : '';
  return (
    `<div class="dispatch-line st-sys${fresh}">` +
    `<span class="dl-time">${escapeHtml(row.time)}</span>` +
    `<span class="dl-tag">LOG</span>` +
    `<span class="dl-job">${escapeHtml(row.proc)}</span>` +
    `<span class="dl-svc"></span>` +
    `<span class="dl-acc"></span>` +
    `<span class="dl-ch"></span>` +
    `<span class="dl-msg">${escapeHtml(row.msg)}</span>` +
    `</div>`
  );
}

export class DispatchFeedTerminal {
  constructor() {
    this.panel = document.getElementById('dispatch-terminal');
    this.body = document.getElementById('dispatch-feed-body');
    this.meta = document.getElementById('dispatch-feed-meta');
    this.nowEl = document.getElementById('dispatch-now');
    this.toggleBtn = document.getElementById('btn-toggle-terminal');
    this.collapsed = false;
    this.timer = null;
    this.pollMs = 0;
    this.graph = null;
    this.lastEvents = [];
    this.prevStatus = null;
    this.freshIds = new Set();
    this.workerLines = [];
    this.workerState = 'off';
    this.workerStarted = false;
    this.workerSource = null;
    this.selectedJobId = null;
    this.initToggle();
    this.initLineClick();
  }

  attachGraph(graph) {
    this.graph = graph;
  }

  initToggle() {
    if (!this.toggleBtn || !this.panel) return;
    this.toggleBtn.addEventListener('click', () => {
      this.collapsed = !this.collapsed;
      this.panel.classList.toggle('collapsed', this.collapsed);
      this.toggleBtn.textContent = this.collapsed ? 'Hiện log' : 'Thu gọn';
      this.toggleBtn.setAttribute('aria-expanded', String(!this.collapsed));
    });
  }

  initLineClick() {
    if (!this.body) return;
    this.body.addEventListener('click', (e) => {
      const line = e.target.closest('.dispatch-line[data-job]');
      if (!line) return;
      const evt = (this.lastEvents || []).find((item) => String(item.jobId) === line.dataset.job);
      if (!evt) return;
      this.showJobDetail(evt);
      const index = Number(evt.accountIndex);
      if (Number.isFinite(index)) {
        this.graph?.pulseActivity?.({
          accountIndex: index,
          status: evt.status,
          httpStatus: evt.httpStatus,
          channelId: evt.channelId,
        });
      }
    });

    const closeBtn = document.getElementById('job-detail-close');
    const overlay = document.getElementById('job-detail');
    if (closeBtn) closeBtn.addEventListener('click', () => this.hideJobDetail());
    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) this.hideJobDetail();
      });
    }
  }

  start(intervalMs = POLL_IDLE_MS) {
    this.fetchFeed();
    this._arm(intervalMs);
    this.attachWorkerStream();
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (this.workerSource) {
      this.workerSource.close();
      this.workerSource = null;
    }
  }

  _arm(ms) {
    if (this.pollMs === ms && this.timer) return;
    this.pollMs = ms;
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => this.fetchFeed(true), ms);
  }

  replayPulses() {
    const running = (this.lastEvents || []).filter(
      (e) => String(e.status || '').toUpperCase() === 'RUNNING'
    );
    running.forEach((evt) => this.graph?.pulseActivity?.(evt));
  }

  async fetchFeed(silent = false) {
    if (this.panel) this.panel.classList.toggle('polling', !silent);

    try {
      const res = await fetch('/api/buffer/dispatch-feed?limit=40');
      const json = await res.json();
      if (!json || !json.ok) {
        this._setMeta('Không lấy được việc Buffer');
        return;
      }
      this.render(json.events || []);
    } catch (err) {
      console.warn('[DispatchFeed] fetch failed:', err);
      this._setMeta('Mất kết nối feed');
    } finally {
      if (this.panel) this.panel.classList.remove('polling');
    }
  }

  async attachWorkerStream() {
    if (this.workerStarted) return;
    this.workerStarted = true;
    try {
      const res = await fetch(
        '/app/logs/tail?proc=ALL&kind=out&lines=12&category=user',
        { credentials: 'same-origin' }
      );
      if (res.status === 401) {
        this.workerState = 'auth';
        this._paintNow(this.lastEvents || []);
        return;
      }
      if (!res.ok) {
        this.workerState = 'off';
        return;
      }
      const text = await res.text();
      if (/Không tìm thấy file PM2|Không có dòng log/i.test(text)) {
        this.workerState = 'off';
        this._paintNow(this.lastEvents || []);
        return;
      }
      text.split('\n').forEach((line) => this._pushWorkerLine(line, false));
      this.workerState = 'live';
      this.render(this.lastEvents || []);

      const src = new EventSource('/app/logs/stream?proc=ALL&kind=out&category=user');
      this.workerSource = src;
      src.onmessage = (ev) => {
        if (!this._pushWorkerLine(ev.data, true)) return;
        this.render(this.lastEvents || []);
      };
      src.onerror = () => {
        if (this.workerState === 'live') this.workerState = 'off';
        this._paintNow(this.lastEvents || []);
      };
    } catch (err) {
      console.warn('[DispatchFeed] worker log unavailable:', err);
      this.workerState = 'off';
    }
  }

  _pushWorkerLine(raw, isNew) {
    const line = String(raw || '').replace(/\s+/g, ' ').trim();
    if (!line || line.startsWith(':')) return false;
    if (looksSensitive(line)) return false;
    if (/\[missing\]|Local Windows|không dùng PM2|Không có dòng log|Không tìm thấy file PM2/i.test(line)) {
      return false;
    }
    const matched = line.match(/^\[([^\]]+)\]\s*(.*)$/);
    const proc = matched ? matched[1] : 'worker';
    const msg = (matched ? matched[2] : line).slice(0, 180);
    if (!msg || msg.length < 2) return false;
    const clock = line.match(/\b(\d{2}:\d{2}:\d{2})\b/);
    const time = clock
      ? clock[1]
      : new Date().toLocaleTimeString('en-GB', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          timeZone: 'Asia/Ho_Chi_Minh',
        });
    this.workerLines.push({ proc, msg, time, fresh: Boolean(isNew) });
    if (this.workerLines.length > MAX_WORKER_LINES) this.workerLines.shift();
    return true;
  }

  render(events) {
    if (!this.body) return;

    const list = Array.isArray(events) ? events.slice(0, MAX_LINES) : [];
    this.lastEvents = list;
    const counts = { DONE: 0, FAILED: 0, RUNNING: 0, PENDING: 0 };
    const nextStatus = new Map();
    const freshIds = new Set();

    list.forEach((e) => {
      const s = String(e.status || 'PENDING').toUpperCase();
      if (counts[s] != null) counts[s] += 1;
      else counts.PENDING += 1;
      const id = String(e.jobId);
      const sig = `${s}:${e.httpStatus}`;
      nextStatus.set(id, sig);
      if (this.prevStatus && this.prevStatus.get(id) !== sig) {
        freshIds.add(id);
        this.graph?.pulseActivity?.(e);
      }
    });

    if (!this.prevStatus) {
      list
        .filter((e) => String(e.status || '').toUpperCase() === 'RUNNING')
        .forEach((e) => this.graph?.pulseActivity?.(e));
    }
    this.prevStatus = nextStatus;
    this.freshIds = freshIds;

    const chronological = list.slice().reverse();
    const jobHtml = chronological.map((evt) => formatLine(evt, freshIds)).join('');
    const workerHtml = this.workerLines.map(formatWorkerLine).join('');
    const split = workerHtml
      ? `<div class="dispatch-split">Log worker</div>${workerHtml}`
      : '';

    if (!list.length && !workerHtml) {
      this.body.innerHTML = `<div class="dispatch-empty">Chưa có việc Buffer gần đây — hàng đợi đang trống.</div>`;
    } else if (!list.length) {
      this.body.innerHTML = `<div class="dispatch-empty">Hàng đợi Buffer đang trống.</div>${split}`;
    } else {
      this.body.innerHTML = jobHtml + split;
    }

    if (freshIds.size || this.workerLines.some((row) => row.fresh)) {
      this.body.scrollTop = this.body.scrollHeight;
      window.setTimeout(() => {
        this.workerLines.forEach((row) => {
          row.fresh = false;
        });
      }, 1600);
    }

    if (this.selectedJobId != null) {
      const fresh = list.find((item) => String(item.jobId) === String(this.selectedJobId));
      if (fresh) this.showJobDetail(fresh);
      else this.hideJobDetail();
    } else {
      this._markSelected();
    }

    const busy = counts.RUNNING > 0;
    this._arm(busy ? POLL_BUSY_MS : POLL_IDLE_MS);

    const workerNote = this.workerState === 'live'
      ? ' · worker live'
      : (this.workerState === 'auth' ? ' · worker cần đăng nhập' : '');
    this._setMeta(
      `RUN ${counts.RUNNING} · WAIT ${counts.PENDING} · OK ${counts.DONE} · FAIL ${counts.FAILED} · ${this.pollMs / 1000}s${workerNote}`
    );
    this._paintNow(list);

    const liveDot = document.getElementById('dispatch-live-dot');
    if (liveDot) {
      liveDot.classList.toggle('active', busy || this.workerState === 'live');
      liveDot.title = busy ? `${counts.RUNNING} job đang chạy` : 'Đang theo dõi';
    }
  }

  showJobDetail(evt) {
    const overlay = document.getElementById('job-detail');
    const title = document.getElementById('job-detail-title');
    const body = document.getElementById('job-detail-body');
    if (!overlay || !body || !evt) return;

    this.selectedJobId = evt.jobId;
    const tag = statusLabel(evt.status, evt.httpStatus);
    const cls = statusClass(evt.status, evt.httpStatus);
    if (title) title.textContent = `Job #${evt.jobId} · ${tag}`;

    const rows = [
      ['Trạng thái', `${tag} · HTTP ${evt.httpStatus ?? '—'}`],
      ['Thời gian', evt.timeIct || '—'],
      ['Kênh', evt.channelName || evt.channelId || '—'],
      ['Nền tảng', String(evt.service || 'buffer')],
      ['Tài khoản', evt.accountIndex != null ? `#${evt.accountIndex}` : '—'],
      ['Đang làm gì', evt.message || '—'],
    ];
    let html = rows.map(([label, value]) => (
      `<div class="job-detail-row"><div class="job-detail-k">${escapeHtml(label)}</div>` +
      `<div class="job-detail-v">${escapeHtml(value)}</div></div>`
    )).join('');

    const caption = String(evt.caption || '').trim();
    if (caption) {
      html += `<div class="job-detail-row"><div class="job-detail-k">Caption</div>` +
        `<div class="job-detail-v job-detail-caption">${escapeHtml(caption)}</div></div>`;
    }
    const postUrl = String(evt.postUrl || '').trim();
    if (postUrl) {
      const safe = escapeHtml(postUrl);
      html += `<div class="job-detail-row"><div class="job-detail-k">Link bài</div>` +
        `<div class="job-detail-v"><a href="${safe}" target="_blank" rel="noopener">${safe}</a></div></div>`;
    }

    body.innerHTML = `<div class="job-detail-status st-${cls}"></div>${html}`;
    overlay.hidden = false;
    overlay.classList.add('open');
    this._markSelected();
  }

  hideJobDetail() {
    const overlay = document.getElementById('job-detail');
    if (overlay) {
      overlay.classList.remove('open');
      overlay.hidden = true;
    }
    this.selectedJobId = null;
    this._markSelected();
  }

  _markSelected() {
    if (!this.body) return;
    this.body.querySelectorAll('.dispatch-line.is-selected').forEach((el) => el.classList.remove('is-selected'));
    if (this.selectedJobId == null) return;
    const line = this.body.querySelector(`.dispatch-line[data-job="${this.selectedJobId}"]`);
    if (line) line.classList.add('is-selected');
  }

  _paintNow(list) {
    if (!this.nowEl) return;
    const running = list.filter((e) => String(e.status || '').toUpperCase() === 'RUNNING');
    let text = 'Hệ thống đang chờ việc mới.';
    let tone = 'wait';
    if (running.length) {
      const e = running[0];
      const extra = running.length > 1 ? ` (+${running.length - 1})` : '';
      text = `Đang gửi job #${e.jobId} → ${e.channelName || e.channelId || 'kênh'} · tài khoản #${e.accountIndex}${extra}`;
      tone = 'run';
    } else if (list.length) {
      const e = list[0];
      const tag = statusLabel(e.status, e.httpStatus);
      text = `Mới nhất: job #${e.jobId} ${tag} · ${e.channelName || e.channelId || 'kênh'} · ${e.message || ''}`;
      tone = statusClass(e.status, e.httpStatus);
    }
    if (this.workerState === 'auth') {
      text += ' · Log worker cần đăng nhập, đang theo job Buffer.';
    }
    this.nowEl.textContent = text;
    this.nowEl.className = `dispatch-now tone-${tone}`;
  }

  _setMeta(text) {
    if (this.meta) this.meta.textContent = text;
  }
}
