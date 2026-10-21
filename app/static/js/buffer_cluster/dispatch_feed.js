/**
 * Live Dispatch Terminal — poll /api/buffer/dispatch-feed, hiển thị log điều phối Buffer.
 */

const MAX_LINES = 80;
const POLL_MS = 8000;

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

function formatLine(evt) {
  const cls = statusClass(evt.status, evt.httpStatus);
  const tag = statusLabel(evt.status, evt.httpStatus);
  const svc = String(evt.service || 'buffer').toUpperCase();
  const ch = escapeHtml(evt.channelName || evt.channelId || '—');
  const msg = escapeHtml((evt.message || '').slice(0, 160));
  const time = escapeHtml(evt.timeIct || '--:--');
  const jobId = evt.jobId != null ? evt.jobId : '?';
  const acc = evt.accountIndex != null ? `#${evt.accountIndex}` : '';

  return (
    `<div class="dispatch-line st-${cls}" data-job="${jobId}">` +
    `<span class="dl-time">${time}</span>` +
    `<span class="dl-tag">${tag}</span>` +
    `<span class="dl-job">JOB #${jobId}</span>` +
    `<span class="dl-svc">${svc}</span>` +
    `<span class="dl-acc">${acc}</span>` +
    `<span class="dl-ch">${ch}</span>` +
    `<span class="dl-msg">${msg}</span>` +
    `</div>`
  );
}

export class DispatchFeedTerminal {
  constructor() {
    this.panel = document.getElementById('dispatch-terminal');
    this.body = document.getElementById('dispatch-feed-body');
    this.meta = document.getElementById('dispatch-feed-meta');
    this.toggleBtn = document.getElementById('btn-toggle-terminal');
    this.collapsed = false;
    this.timer = null;
    this.lastFingerprint = '';
    this.initToggle();
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

  start(intervalMs = POLL_MS) {
    this.fetchFeed();
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => this.fetchFeed(true), intervalMs);
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  async fetchFeed(silent = false) {
    if (this.panel) this.panel.classList.toggle('polling', !silent);

    try {
      const res = await fetch('/api/buffer/dispatch-feed?limit=40');
      const json = await res.json();
      if (!json || !json.ok) {
        this._setMeta('⚠️ Không lấy được feed điều phối');
        return;
      }
      this.render(json.events || []);
    } catch (err) {
      console.warn('[DispatchFeed] fetch failed:', err);
      this._setMeta('⚠️ Mất kết nối feed');
    } finally {
      if (this.panel) this.panel.classList.remove('polling');
    }
  }

  render(events) {
    if (!this.body) return;

    const list = Array.isArray(events) ? events.slice(0, MAX_LINES) : [];
    const counts = { DONE: 0, FAILED: 0, RUNNING: 0, PENDING: 0 };
    list.forEach((e) => {
      const s = String(e.status || 'PENDING').toUpperCase();
      if (counts[s] != null) counts[s] += 1;
      else counts.PENDING += 1;
    });

    const fingerprint = list.map((e) => `${e.jobId}:${e.status}:${e.httpStatus}`).join('|');
    const changed = fingerprint !== this.lastFingerprint;
    this.lastFingerprint = fingerprint;

    if (!list.length) {
      this.body.innerHTML = `<div class="dispatch-empty">Chưa có job Buffer gần đây — hàng đợi đang trống.</div>`;
      this._setMeta('0 sự kiện · live');
      return;
    }

    // API trả mới→cũ; hiển thị cũ→mới (log đọc từ trên xuống như terminal)
    const chronological = list.slice().reverse();
    this.body.innerHTML = chronological.map(formatLine).join('');

    if (changed) {
      this.body.scrollTop = this.body.scrollHeight;
    }

    this._setMeta(
      `RUN ${counts.RUNNING} · WAIT ${counts.PENDING} · OK ${counts.DONE} · FAIL ${counts.FAILED} · live ${POLL_MS / 1000}s`
    );

    // Badge trên footer nếu có RUNNING
    const liveDot = document.getElementById('dispatch-live-dot');
    if (liveDot) {
      liveDot.classList.toggle('active', counts.RUNNING > 0);
      liveDot.title = counts.RUNNING > 0 ? `${counts.RUNNING} job đang chạy` : 'Không có job RUNNING';
    }
  }

  _setMeta(text) {
    if (this.meta) this.meta.textContent = text;
  }
}
