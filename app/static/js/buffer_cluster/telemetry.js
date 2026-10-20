/**
 * Module Telemetry: Xử lý polling dữ liệu từ API `/api/buffer/cluster-status`,
 * quản lý state và cập nhật các thành phần DOM HUD (Header, Left Cards).
 */

export class TelemetryService {
  constructor(onDataLoaded) {
    this.onDataLoaded = onDataLoaded;
    this.data = null;
  }

  async fetchStatus() {
    const btn = document.getElementById('btn-refresh');
    if (btn) btn.innerHTML = 'Đang tải...';

    try {
      const res = await fetch('/api/buffer/cluster-status');
      const json = await res.json();
      if (json && json.ok) {
        this.data = json;
        this.updateHeaderStats(json.summary);
        this.renderAccountCards(json);
        if (this.onDataLoaded) {
          this.onDataLoaded(json);
        }
      }
    } catch (err) {
      console.error('[Telemetry] Error loading cluster status:', err);
    } finally {
      if (btn) {
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg> Làm mới`;
      }
    }
  }

  updateHeaderStats(summary) {
    if (!summary) return;
    document.getElementById('stat-accounts').textContent = summary.totalAccounts || 0;
    document.getElementById('stat-active').textContent = summary.activeAccounts || 0;
    document.getElementById('stat-cooldown').textContent = summary.cooldownAccounts || 0;
    document.getElementById('stat-channels').textContent = summary.totalChannels || 0;
    document.getElementById('stat-queue').textContent = summary.totalQueuedPosts || 0;

    const orb = document.getElementById('cluster-orb');
    if (orb) {
      if (summary.activeAccounts > 0) {
        orb.style.background = 'var(--accent-green)';
        orb.style.boxShadow = '0 0 14px var(--accent-green)';
      } else {
        orb.style.background = 'var(--accent-amber)';
        orb.style.boxShadow = '0 0 14px var(--accent-amber)';
      }
    }
  }

  renderAccountCards(data) {
    const container = document.getElementById('account-cards-container');
    if (!container) return;
    container.innerHTML = '';

    (data.accounts || []).forEach(acc => {
      const isCooldown = acc.status === 'COOLDOWN';
      const stateClass = isCooldown ? 'cooldown-state' : 'active-state';

      const card = document.createElement('div');
      card.className = `account-card glass-panel ${stateClass}`;
      card.id = `card-acc-${acc.index}`;

      const channelPills = (acc.channels || []).map(ch => {
        const isTT = (ch.service || '').toLowerCase().includes('tiktok');
        const typeClass = isTT ? 'tt' : 'fb';
        const icon = isTT ? '🎵' : '📘';
        return `<span class="chan-pill ${typeClass}">${icon} ${ch.name} (${ch.pendingCount})</span>`;
      }).join('');

      card.innerHTML = `
        <div class="account-card-header">
          <div class="acc-index">
            <span>#${acc.index}</span>
            <span>${acc.name}</span>
          </div>
          <span class="acc-status-tag ${isCooldown ? 'tag-cooldown' : 'tag-active'}">
            ${isCooldown ? 'COOLDOWN (429)' : 'ACTIVE'}
          </span>
        </div>
        <div class="acc-email">${acc.email}</div>
        <div class="acc-meta">
          <span>Key: <code style="color: #38bdf8">${acc.maskedKey}</code></span>
          <span>Kênh: <b>${acc.channelCount}/3</b></span>
        </div>
        <div class="channels-pill-row">${channelPills || '<span style="color: #64748b; font-size: 10px;">Chưa có kênh</span>'}</div>
      `;

      let touchStartX = 0;
      let touchStartY = 0;
      let touchMoved = false;

      card.addEventListener('touchstart', (e) => {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchMoved = false;
      }, { passive: true });

      card.addEventListener('touchmove', (e) => {
        const dx = Math.abs(e.touches[0].clientX - touchStartX);
        const dy = Math.abs(e.touches[0].clientY - touchStartY);
        if (dx > 10 || dy > 10) {
          touchMoved = true;
        }
      }, { passive: true });

      card.addEventListener('touchend', () => {
        if (!touchMoved) {
          window.dispatchEvent(new CustomEvent('cluster:select-account', { detail: { index: acc.index, account: acc } }));
        }
      });

      card.addEventListener('click', (e) => {
        if (e.pointerType === 'mouse' || !('ontouchstart' in window)) {
          window.dispatchEvent(new CustomEvent('cluster:select-account', { detail: { index: acc.index, account: acc } }));
        }
      });

      container.appendChild(card);
    });
  }
}
