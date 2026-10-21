/**
 * Module Telemetry: Polling dữ liệu /api/buffer/cluster-status (30s),
 * thực thi Ping Key, quản lý đếm ngược 429 ICT (1s), và lọc tìm kiếm DOM tức thì.
 */
import { copyToClipboard } from './controls.js';

export class TelemetryService {
  constructor(onDataLoaded, onAccountUpdated, onFilterApplied) {
    this.onDataLoaded = onDataLoaded;
    this.onAccountUpdated = onAccountUpdated;
    this.onFilterApplied = onFilterApplied;
    this.data = null;
    this.pollTimer = null;
    this.countdownTimer = null;
    this.activeFilter = { query: '', platform: 'all' };
    this.pingingAccounts = new Set();

    this.initFilterEvents();
    this.startCountdownLoop();
  }

  /**
   * Khởi động polling chu kỳ 30 giây
   */
  startPolling(intervalMs = 30000) {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => {
      this.fetchStatus(true);
    }, intervalMs);
  }

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  /**
   * Tải trạng thái cụm tài khoản từ backend API
   */
  async fetchStatus(silent = false) {
    const btn = document.getElementById('btn-refresh');
    if (btn && !silent) btn.innerHTML = 'Đang tải...';

    try {
      const res = await fetch('/api/buffer/cluster-status');
      const json = await res.json();
      if (json && json.ok) {
        this.data = json;
        this.updateHeaderStats(json.summary);
        this.renderAccountCards(json);
        this.applyFilter(this.activeFilter);
        if (this.onDataLoaded) {
          this.onDataLoaded(json);
        }
      }
    } catch (err) {
      console.error('[Telemetry] Lỗi tải cluster status:', err);
      if (window.showToast && !silent) {
        window.showToast('⚠️ Không thể kết nối tới máy chủ');
      }
    } finally {
      if (btn && !silent) {
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg> Làm mới`;
      }
    }
  }

  /**
   * Cập nhật các badge số liệu trên Header bar
   */
  updateHeaderStats(summary) {
    if (!summary) return;
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val ?? 0;
    };
    setVal('stat-accounts', summary.totalAccounts);
    setVal('stat-active', summary.activeAccounts);
    setVal('stat-cooldown', summary.cooldownAccounts);
    setVal('stat-channels', summary.totalChannels);
    setVal('stat-queue', summary.totalQueuedPosts);

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

  /**
   * Ping kiểm tra độ trễ và hạn mức token theo account_index
   */
  async pingKey(accountIndex, triggerBtn = null) {
    if (this.pingingAccounts.has(accountIndex)) return;
    this.pingingAccounts.add(accountIndex);

    let origHtml = '';
    if (triggerBtn) {
      origHtml = triggerBtn.innerHTML;
      triggerBtn.disabled = true;
      triggerBtn.classList.add('loading');
      triggerBtn.innerHTML = `<span class="spin-icon">⏳</span> Ping...`;
    }

    try {
      const res = await fetch(`/api/buffer/ping-key?account_index=${encodeURIComponent(accountIndex)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const result = await res.json();

      // Cập nhật state in-memory
      const acc = this.data?.accounts?.find(a => a.index === accountIndex);
      if (acc && result) {
        acc.status = result.status || acc.status;
        acc.latencyMs = result.latencyMs;
        acc.httpStatus = result.httpStatus;
        if (result.quota) {
          acc.quota = result.quota;
          acc.cooldownSeconds = result.quota.cooldownSeconds || 0;
          acc.resetTs = result.quota.resetTs;
          acc.resetTimeIct = result.quota.resetTimeIct;
        }
      }

      // Cập nhật DOM thẻ tài khoản
      this.updateAccountCardUI(accountIndex, result);

      // Cập nhật 3D Scene
      if (this.onAccountUpdated) {
        this.onAccountUpdated(acc, result);
      }

      // Cập nhật Inspector nếu đang mở account này
      const inspectorHeader = document.getElementById('inspect-header-title');
      if (inspectorHeader && inspectorHeader.textContent.includes(`#${accountIndex}`)) {
        const inspectorBadge = document.getElementById('inspect-latency-badge');
        const inspectorVal = document.getElementById('inspect-latency-val');
        if (inspectorBadge && inspectorVal && result.latencyMs != null) {
          const lat = Math.round(result.latencyMs);
          inspectorVal.textContent = `${lat} ms`;
          inspectorBadge.className = 'latency-badge ' + (lat < 300 ? 'latency-green' : (lat < 800 ? 'latency-amber' : 'latency-red'));
        }
      }

      // Thông báo Toast HUD
      if (window.showToast) {
        if (result.ok) {
          const lat = result.latencyMs != null ? `${Math.round(result.latencyMs)}ms` : '--';
          window.showToast(`✓ Ping Tài khoản #${accountIndex}: ${lat} (${result.status})`);
        } else {
          window.showToast(`⚠️ Ping thất bại: ${result.errorMessage || result.status}`);
        }
      }
    } catch (err) {
      console.error(`[Telemetry] Ping error for account #${accountIndex}:`, err);
      if (window.showToast) {
        window.showToast(`⚠️ Lỗi mạng khi ping tài khoản #${accountIndex}`);
      }
    } finally {
      this.pingingAccounts.delete(accountIndex);
      if (triggerBtn) {
        triggerBtn.disabled = false;
        triggerBtn.classList.remove('loading');
        triggerBtn.innerHTML = origHtml;
      }
    }
  }

  /**
   * Cập nhật nhanh giao diện của một account card sau khi Ping
   */
  updateAccountCardUI(accountIndex, result) {
    const card = document.getElementById(`card-acc-${accountIndex}`);
    if (!card) return;

    const isCooldown = result.status === 'COOLDOWN';
    card.classList.toggle('cooldown-state', isCooldown);
    card.classList.toggle('active-state', !isCooldown);

    // Cập nhật status tag
    const tag = card.querySelector('.acc-status-tag');
    if (tag) {
      tag.className = `acc-status-tag ${isCooldown ? 'tag-cooldown' : 'tag-active'}`;
      tag.textContent = isCooldown ? 'COOLDOWN (429)' : `ACTIVE (${result.httpStatus || 200})`;
    }

    // Cập nhật latency badge
    let latBadge = card.querySelector('.acc-latency-badge') || card.querySelector('.latency-badge');
    if (result.latencyMs != null) {
      const latVal = Math.round(result.latencyMs);
      const latClass = latVal < 300 ? 'lat-fast' : (latVal < 800 ? 'lat-med' : 'lat-slow');
      if (latBadge) {
        latBadge.className = `acc-latency-badge latency-badge ${latClass}`;
        latBadge.textContent = `${latVal}ms`;
      }
    }

    // Cập nhật quota pill
    const quotaPill = card.querySelector('.quota-pill') || card.querySelector('.acc-quota-pill');
    if (quotaPill && result.quota) {
      const rem = result.quota.dailyRemaining ?? '--';
      const lim = result.quota.dailyLimit ?? 250;
      quotaPill.innerHTML = `Quota: <b>${rem}/${lim}</b>`;
    }

    // Cập nhật cooldown banner
    let cdBanner = card.querySelector('.card-cooldown-banner');
    if (isCooldown) {
      if (!cdBanner) {
        cdBanner = document.createElement('div');
        cdBanner.className = 'card-cooldown-banner';
        cdBanner.id = `cooldown-banner-${accountIndex}`;
        const metaSection = card.querySelector('.acc-meta-section') || card.querySelector('.acc-meta');
        if (metaSection) metaSection.after(cdBanner);
      }
      const resetIct = result.quota?.resetTimeIct || result.resetTimeIct || '--';
      cdBanner.innerHTML = `
        <span class="cd-title">⏳ Hồi phục lúc: <b>${resetIct} ICT</b></span>
        <span class="cd-timer" id="timer-acc-${accountIndex}">Đang tính...</span>
      `;
    } else if (cdBanner) {
      cdBanner.remove();
    }
  }

  /**
   * Khởi động vòng lặp đếm ngược 1 giây cho HTTP 429
   */
  startCountdownLoop() {
    if (this.countdownTimer) clearInterval(this.countdownTimer);
    this.countdownTimer = setInterval(() => {
      this.tickCountdowns();
    }, 1000);
  }

  tickCountdowns() {
    if (!this.data || !this.data.accounts) return;
    const nowTs = Math.floor(Date.now() / 1000);

    this.data.accounts.forEach(acc => {
      if (acc.status !== 'COOLDOWN') return;

      let remainingSec = 0;
      if (acc.resetTs) {
        remainingSec = Math.max(0, acc.resetTs - nowTs);
      } else if (acc.cooldownSeconds > 0) {
        acc.cooldownSeconds = Math.max(0, acc.cooldownSeconds - 1);
        remainingSec = acc.cooldownSeconds;
      }

      const formatted = this.formatTimeRemaining(remainingSec);
      const timerEl = document.getElementById(`timer-acc-${acc.index}`);
      if (timerEl) {
        timerEl.textContent = `Còn: ${formatted}`;
      }

      // Cập nhật trên Drawer Inspector nếu đang mở
      const inspectorTimer = document.getElementById('inspect-cooldown-timer');
      const inspectHeader = document.getElementById('inspect-header-title');
      if (inspectorTimer && inspectHeader && inspectHeader.textContent.includes(`#${acc.index}`)) {
        inspectorTimer.textContent = `${formatted} (Reset: ${acc.resetTimeIct || '--'} ICT)`;
      }

      // Tự động kiểm tra lại khi hết cooldown
      if (remainingSec === 0 && !this.pingingAccounts.has(acc.index)) {
        if (timerEl) timerEl.textContent = 'Đang tự phục hồi...';
        this.pingKey(acc.index);
      }
    });
  }

  formatTimeRemaining(seconds) {
    if (seconds <= 0) return '00:00:00';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  /**
   * Render danh sách Account Cards với kênh vệ tinh chi tiết (F7, F8, F10)
   */
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
      card.dataset.accIndex = acc.index;

      // Latency badge
      let latencyHtml = '';
      if (acc.latencyMs != null) {
        const latVal = Math.round(acc.latencyMs);
        const latClass = latVal < 300 ? 'lat-fast' : (latVal < 800 ? 'lat-med' : 'lat-slow');
        latencyHtml = `<span class="acc-latency-badge latency-badge ${latClass}">${latVal}ms</span>`;
      } else {
        latencyHtml = `<span class="acc-latency-badge latency-badge lat-fast">Online</span>`;
      }

      // Quota info
      const dailyRemaining = acc.quota?.dailyRemaining ?? (isCooldown ? 0 : 250);
      const dailyLimit = acc.quota?.dailyLimit ?? 250;

      // Danh sách vệ tinh channels (F8)
      const channelsHtml = (acc.channels || []).map(ch => {
        const service = (ch.service || 'facebook').toLowerCase();
        const isTikTok = service.includes('tiktok');
        const isInstagram = service.includes('instagram');
        const serviceClass = isTikTok ? 'tt' : (isInstagram ? 'ig' : 'fb');
        const icon = isTikTok ? '🎵' : (isInstagram ? '📷' : '📘');

        return `
          <div class="channel-metric-node ${serviceClass}" data-chan-id="${ch.id}" data-service="${service}">
            <div class="chan-metric-head">
              <span class="chan-metric-name">${icon} ${ch.name}</span>
              <span class="chan-metric-queue" title="Số bài chờ đăng">${ch.pendingCount} bài</span>
            </div>
            <div class="chan-metric-meta">
              <span class="chan-id-text">ID: <code>${ch.id}</code></span>
              <button class="btn-copy-mini" data-copy-val="${ch.id}" title="Sao chép Channel ID">📋</button>
              <span class="chan-time-text">${ch.lastPostTime ? `Đăng: ${ch.lastPostTime}` : (ch.nextPostTime ? `Tiếp: ${ch.nextPostTime}` : 'Sẵn sàng')}</span>
            </div>
          </div>
        `;
      }).join('');

      // Pills tóm tắt
      const channelPills = (acc.channels || []).map(ch => {
        const service = (ch.service || '').toLowerCase();
        const isTT = service.includes('tiktok');
        const isIG = service.includes('instagram');
        const typeClass = isTT ? 'tt' : (isIG ? 'ig' : 'fb');
        const icon = isTT ? '🎵' : (isIG ? '📷' : '📘');
        return `<span class="chan-pill ${typeClass}" data-chan-id="${ch.id}" data-service="${service}">${icon} ${ch.name} (${ch.pendingCount})</span>`;
      }).join('');

      // Cooldown Banner HTML
      const cooldownBannerHtml = isCooldown ? `
        <div class="card-cooldown-banner" id="cooldown-banner-${acc.index}">
          <span class="cd-title">⏳ Hồi phục lúc: <b>${acc.resetTimeIct || '--'} ICT</b></span>
          <span class="cd-timer" id="timer-acc-${acc.index}">Đang đếm ngược...</span>
        </div>
      ` : '';

      card.innerHTML = `
        <div class="account-card-header">
          <div class="acc-index">
            <span class="acc-order-badge acc-num-pill">#${acc.index}</span>
            <span class="acc-title acc-name">${acc.name}</span>
          </div>
          <div class="acc-header-right">
            ${latencyHtml}
            <span class="acc-status-tag ${isCooldown ? 'tag-cooldown' : 'tag-active'}">
              ${isCooldown ? 'COOLDOWN (429)' : 'ACTIVE'}
            </span>
          </div>
        </div>

        <div class="acc-email-row">
          <span class="acc-email" id="acc-email-${acc.index}">${acc.email}</span>
          <button class="btn-copy-chip copy-chip-sm" data-copy-val="${acc.email}" title="Sao chép Email">📋 Copy</button>
        </div>

        <div class="acc-meta-section">
          <div class="acc-meta-row">
            <div class="acc-key-group">
              <span>Key:</span>
              <code class="acc-key-badge masked-key-text" id="acc-key-${acc.index}">${acc.maskedKey}</code>
              <button class="btn-copy-chip copy-chip-sm" data-copy-val="${acc.maskedKey}" title="Sao chép Token">📋 Copy</button>
            </div>
            <button class="btn-ping-card btn-ping-key" data-acc-index="${acc.index}" data-account-index="${acc.index}" title="Kiểm tra kết nối và độ trễ">⚡ Ping</button>
          </div>
          <div class="acc-meta-stats">
            <span class="quota-pill acc-quota-pill">Quota: <b>${dailyRemaining}/${dailyLimit}</b></span>
            <span class="chan-count-pill">${acc.channelCount}/3 Kênh</span>
          </div>
        </div>

        ${cooldownBannerHtml}

        <div class="channels-metric-group">
          <div class="channels-metric-list">
            ${channelsHtml || '<span style="color: #64748b; font-size: 11px;">Chưa có kênh nào</span>'}
          </div>
        </div>

        <div class="channels-pill-row">
          ${channelPills || '<span style="color: #64748b; font-size: 10px;">Chưa có kênh</span>'}
        </div>
      `;

      // Touch handling for mobile tap disambiguation
      let touchStartX = 0;
      let touchStartY = 0;
      let touchMoved = false;

      card.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches.length > 0) {
          touchStartX = e.touches[0].clientX;
          touchStartY = e.touches[0].clientY;
          touchMoved = false;
        }
      }, { passive: true });

      card.addEventListener('touchmove', (e) => {
        if (e.touches && e.touches.length > 0) {
          const dx = Math.abs(e.touches[0].clientX - touchStartX);
          const dy = Math.abs(e.touches[0].clientY - touchStartY);
          if (dx > 8 || dy > 8) {
            touchMoved = true;
          }
        }
      }, { passive: true });

      card.addEventListener('touchend', (e) => {
        if (e.target.closest('button, .copy-chip, .copy-chip-sm, .btn-copy-chip, .btn-copy-mini, .btn-ping-card, .btn-ping-key')) {
          return;
        }
        if (!touchMoved) {
          window.dispatchEvent(new CustomEvent('cluster:select-account', { detail: { index: acc.index, account: acc } }));
        }
      });

      card.addEventListener('click', (e) => {
        if (e.target.closest('button, .copy-chip, .copy-chip-sm, .btn-copy-chip, .btn-copy-mini, .btn-ping-card, .btn-ping-key')) {
          return;
        }
        if (e.pointerType === 'mouse' || !('ontouchstart' in window)) {
          window.dispatchEvent(new CustomEvent('cluster:select-account', { detail: { index: acc.index, account: acc } }));
        }
      });

      container.appendChild(card);
    });

    // Event Delegation: Xử lý click Ping và Copy
    this.attachCardEventListeners(container);
  }

  attachCardEventListeners(container) {
    container.addEventListener('click', (e) => {
      // 1. Nút Copy
      const copyBtn = e.target.closest('.btn-copy-chip, .btn-copy-mini, .copy-chip-sm');
      if (copyBtn) {
        e.stopPropagation();
        const val = copyBtn.getAttribute('data-copy-val');
        if (val) copyToClipboard(val, copyBtn);
        return;
      }

      // 2. Nút Ping Key
      const pingBtn = e.target.closest('.btn-ping-key, .btn-ping-card');
      if (pingBtn) {
        e.stopPropagation();
        const accIdx = parseInt(pingBtn.getAttribute('data-acc-index') || pingBtn.getAttribute('data-account-index'), 10);
        if (accIdx) this.pingKey(accIdx, pingBtn);
      }
    });
  }

  /**
   * Khởi tạo các event listeners cho Thanh Tìm Kiếm & Lọc Nền Tảng (F9)
   */
  initFilterEvents() {
    const searchInput = document.getElementById('cluster-search-input');
    const clearBtn = document.getElementById('search-clear-btn') || document.getElementById('btn-clear-search');

    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.activeFilter.query = e.target.value.trim();
        if (clearBtn) {
          clearBtn.style.display = this.activeFilter.query.length > 0 ? 'inline-block' : 'none';
        }
        this.applyFilter(this.activeFilter);
      });

      // '/' Keyboard shortcut to focus search
      window.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement !== searchInput) {
          e.preventDefault();
          searchInput.focus();
        }
      });
    }

    if (clearBtn && searchInput) {
      clearBtn.addEventListener('click', () => {
        searchInput.value = '';
        this.activeFilter.query = '';
        clearBtn.style.display = 'none';
        this.applyFilter(this.activeFilter);
      });
    }

    const filterPills = document.querySelectorAll('.platform-filter-pill, .filter-pill');
    filterPills.forEach(pill => {
      pill.addEventListener('click', () => {
        filterPills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        this.activeFilter.platform = pill.getAttribute('data-platform') || pill.getAttribute('data-filter') || 'all';
        this.applyFilter(this.activeFilter);
      });
    });
  }

  /**
   * Áp dụng bộ lọc DOM tức thì và đồng bộ sang 3D Graph (F9)
   */
  applyFilter({ query = '', platform = 'all' } = {}) {
    const q = query.toLowerCase();
    const plat = platform.toLowerCase();
    const hasFilter = q.length > 0 || plat !== 'all';

    let totalMatchedChannels = 0;
    const cards = document.querySelectorAll('.account-card');

    cards.forEach(card => {
      const accIdx = parseInt(card.dataset.accIndex, 10);
      const acc = this.data?.accounts?.find(a => a.index === accIdx);
      if (!acc) return;

      let cardHasMatch = false;

      const emailMatches = !q || acc.email.toLowerCase().includes(q) || acc.name.toLowerCase().includes(q) || acc.maskedKey.toLowerCase().includes(q);

      const chanNodes = card.querySelectorAll('.channel-metric-node, .chan-pill');
      chanNodes.forEach(node => {
        const chanService = (node.getAttribute('data-service') || '').toLowerCase();
        const chanId = (node.getAttribute('data-chan-id') || '').toLowerCase();
        const chanName = (node.textContent || '').toLowerCase();

        const matchPlat = (plat === 'all') || chanService.includes(plat);
        const matchQuery = !q || chanName.includes(q) || chanId.includes(q) || emailMatches;
        const isChanMatch = matchPlat && matchQuery;

        if (isChanMatch) {
          node.classList.remove('pill-dimmed', 'dimmed');
          node.classList.add('pill-highlight', 'highlighted');
          cardHasMatch = true;
          totalMatchedChannels++;
        } else {
          node.classList.remove('pill-highlight', 'highlighted');
          node.classList.add('pill-dimmed', 'dimmed');
        }
      });

      // Nếu không có filter thì xóa hết class mờ
      if (!hasFilter) {
        chanNodes.forEach(node => {
          node.classList.remove('pill-dimmed', 'dimmed', 'pill-highlight', 'highlighted');
        });
        card.classList.remove('filter-hidden', 'dimmed', 'highlighted');
      } else {
        const showCard = (plat === 'all' && emailMatches) || cardHasMatch;
        card.classList.toggle('filter-hidden', !showCard);
        card.classList.toggle('highlighted', showCard);
      }
    });

    // Cập nhật thông báo số kênh khớp
    const matchCountEl = document.getElementById('filter-match-count') || document.getElementById('filtered-match-count');
    if (matchCountEl) {
      matchCountEl.textContent = `${totalMatchedChannels}`;
    }

    // Thông báo cho 3D Graph Node Dimming
    if (this.onFilterApplied) {
      this.onFilterApplied({ query, platform });
    }
  }
}
