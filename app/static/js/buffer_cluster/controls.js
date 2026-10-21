/**
 * Module Controls: Xử lý tương tác người dùng, Raycasting hover tooltips,
 * Camera fly-to lerp animation, mở Telemetry Drawer bên phải, touch gestures và tiện ích copy.
 */

export class ClusterControlsManager {
  constructor(camera, orbitControls, graph, options = {}) {
    this.camera = camera;
    this.orbitControls = orbitControls;
    this.graph = graph;
    this.mobile2d = Boolean(options.mobile2d);
    this.raycaster = (typeof THREE !== 'undefined' && !this.mobile2d) ? new THREE.Raycaster() : null;
    this.mouse = (typeof THREE !== 'undefined') ? new THREE.Vector2() : { x: 0, y: 0 };
    this.tooltipEl = document.getElementById('tooltip-3d');
    this.inspectorEl = document.getElementById('right-inspector');
    this.currentAccount = null;

    this.pointerDownPos = { x: 0, y: 0 };
    this.initEvents();
  }

  /**
   * Không bao giờ bật full-screen backdrop.
   * Overlay này z-index cao hơn cả HUD → click card làm mờ cả màn (kể cả inspector).
   */
  _setBackdropVisible(_visible) {
    const backdrop = document.getElementById('inspector-backdrop');
    if (!backdrop) return;
    backdrop.classList.remove('visible');
    backdrop.setAttribute('aria-hidden', 'true');
  }

  initEvents() {
    window.addEventListener('mousemove', (e) => this.onMouseMove(e));
    
    // Prevent dragging to rotate from accidentally triggering node clicks (8px threshold)
    window.addEventListener('pointerdown', (e) => {
      this.pointerDownPos = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('pointerup', (e) => {
      const dist = Math.hypot(e.clientX - this.pointerDownPos.x, e.clientY - this.pointerDownPos.y);
      if (dist > 8) return; // User was dragging to rotate/pan, cancel click
      this.onPointerClick(e);
    });

    const closeBtn = document.getElementById('inspect-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        this.closeInspector();
      });
    }

    const backdrop = document.getElementById('inspector-backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', () => {
        this.closeInspector();
      });
    }

    const resetCamBtn = document.getElementById('btn-reset-cam');
    if (resetCamBtn) {
      resetCamBtn.addEventListener('click', () => {
        const isMob = window.innerWidth <= 768;
        this.smoothMoveCamera(new THREE.Vector3(0, isMob ? 180 : 140, isMob ? 360 : 280), new THREE.Vector3(0, 20, 0));
      });
    }

    // Mobile pull-to-dismiss bottom sheet interaction
    const dragHandle = document.getElementById('inspector-drag-handle') || document.getElementById('sheet-drag-handle');
    if (dragHandle && this.inspectorEl) {
      let touchStartY = 0;
      let currentDeltaY = 0;

      dragHandle.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches.length > 0) {
          touchStartY = e.touches[0].clientY;
          currentDeltaY = 0;
        }
      }, { passive: true });

      dragHandle.addEventListener('touchmove', (e) => {
        if (e.touches && e.touches.length > 0) {
          const touchY = e.touches[0].clientY;
          currentDeltaY = touchY - touchStartY;
          if (currentDeltaY > 0) {
            this.inspectorEl.style.transform = `translate3d(0, ${currentDeltaY}px, 0)`;
          }
        }
      }, { passive: true });

      dragHandle.addEventListener('touchend', () => {
        if (currentDeltaY > 80) {
          this.closeInspector();
        }
        this.inspectorEl.style.transform = '';
      });
    }

    // Hero Ping Button inside Inspector
    const heroPingBtn = document.getElementById('inspect-btn-ping');
    if (heroPingBtn) {
      heroPingBtn.addEventListener('click', () => {
        if (this.currentAccount && window.telemetryService) {
          window.telemetryService.pingKey(this.currentAccount.index, heroPingBtn);
        }
      });
    }

    window.addEventListener('cluster:select-account', (e) => {
      this.focusAccountNode(e.detail.index);
      this.openInspector('account', e.detail.account);
    });
  }

  closeInspector() {
    if (this.inspectorEl) {
      this.inspectorEl.classList.remove('visible');
      this.inspectorEl.style.transform = '';
    }
    this._setBackdropVisible(false);
  }

  onMouseMove(event) {
    if (this.mobile2d || !this.raycaster || !this.camera) return;

    this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const meshes = this.graph.getInteractiveMeshes();
    const intersects = this.raycaster.intersectObjects(meshes, true);

    if (intersects.length > 0) {
      document.body.style.cursor = 'pointer';
      let hit = intersects[0].object;
      while (hit && !hit.userData.type && hit.parent) {
        hit = hit.parent;
      }
      const u = hit.userData;

      if (this.tooltipEl) {
        this.tooltipEl.style.opacity = '1';
        this.tooltipEl.style.left = `${event.clientX}px`;
        this.tooltipEl.style.top = `${event.clientY}px`;

        if (u.type === 'core') {
          this.tooltipEl.innerHTML = `<b>ToolsAuto Core Dispatcher</b><br><span style="color: #38bdf8">Cổng điều phối trung tâm</span>`;
        } else if (u.type === 'account') {
          this.tooltipEl.innerHTML = `<b>${u.data.name}</b> (${u.data.status})<br><span style="color: #38bdf8">📧 ${u.data.email}</span>`;
        } else if (u.type === 'channel') {
          this.tooltipEl.innerHTML = `<b>${u.data.name}</b><br><span style="color: #f472b6">Bài chờ: ${u.data.pendingCount} bài</span>`;
        }
      }
    } else {
      document.body.style.cursor = 'default';
      if (this.tooltipEl) this.tooltipEl.style.opacity = '0';
    }
  }

  onPointerClick(event) {
    if (this.mobile2d || !this.raycaster || !this.camera) return;
    if (event.target.closest('.interactive')) return;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const meshes = [
      ...this.graph.accountNodes.map(a => a.mesh),
      ...this.graph.channelNodes.map(c => c.mesh),
    ];

    const intersects = this.raycaster.intersectObjects(meshes, true);
    if (intersects.length > 0) {
      let hit = intersects[0].object;
      while (hit && !hit.userData.type && hit.parent) {
        hit = hit.parent;
      }
      const u = hit.userData;

      if (u.type === 'account') {
        this.focusAccountNode(u.data.index);
        this.openInspector('account', u.data);
      } else if (u.type === 'channel') {
        this.openInspector('channel', u.data, u.parentAccount);
        this.smoothMoveCamera(
          hit.position.clone().add(new THREE.Vector3(0, 15, 40)),
          hit.position.clone()
        );
      }
    }
  }

  focusAccountNode(index) {
    document.querySelectorAll('.account-card').forEach(c => c.classList.remove('selected'));
    const activeCard = document.getElementById(`card-acc-${index}`);
    if (activeCard) activeCard.classList.add('selected');

    if (this.mobile2d || !this.camera || !this.graph) return;

    const nodeObj = this.graph.accountNodes.find(n => n.data.index === index);
    if (!nodeObj || !nodeObj.mesh) return;

    const targetPos = nodeObj.mesh.position.clone();
    const cameraOffset = new THREE.Vector3(0, 30, 80);
    const newCamPos = targetPos.clone().add(cameraOffset);

    this.smoothMoveCamera(newCamPos, targetPos);
  }

  smoothMoveCamera(toPos, lookAtPos) {
    if (this.mobile2d || !this.camera || !this.orbitControls) return;

    const startPos = this.camera.position.clone();
    const startLookAt = this.orbitControls.target.clone();
    let t = 0;

    const anim = () => {
      t += 0.04;
      this.camera.position.lerpVectors(startPos, toPos, 1 - Math.pow(1 - t, 3));
      this.orbitControls.target.lerpVectors(startLookAt, lookAtPos, 1 - Math.pow(1 - t, 3));
      if (t < 1) {
        requestAnimationFrame(anim);
      }
    };
    anim();
  }

  openInspector(type, data, parentAcc = null) {
    if (!this.inspectorEl) return;
    this.inspectorEl.classList.add('visible');
    // Desktop only: dim backdrop. Mobile dùng bottom sheet, không làm mờ cả màn.
    this._setBackdropVisible(true);

    const titleEl = document.getElementById('inspect-header-title');
    const emailEl = document.getElementById('inspect-email-text');
    const keyEl = document.getElementById('inspect-key-text');
    const statusEl = document.getElementById('inspect-status');
    const cooldownRow = document.getElementById('inspect-cooldown-row');
    const cooldownTimer = document.getElementById('inspect-cooldown-timer');
    const cooldownResetIct = document.getElementById('inspect-cooldown-reset-ict');
    const chanCountEl = document.getElementById('inspect-channel-count');
    const chanListEl = document.getElementById('inspect-channels-list');
    const latencyBadge = document.getElementById('inspect-latency-badge');
    const latencyVal = document.getElementById('inspect-latency-val');
    const dailyQuotaEl = document.getElementById('inspect-daily-quota');
    const burstQuotaEl = document.getElementById('inspect-burst-quota');
    const quotaFillEl = document.getElementById('inspect-quota-fill');

    if (type === 'account') {
      this.currentAccount = data;
      if (titleEl) titleEl.textContent = `${data.name.toUpperCase()} TELEMETRY`;
      if (emailEl) emailEl.textContent = data.email || 'Chưa rõ';
      if (keyEl) keyEl.textContent = data.maskedKey || '--';

      const isCooldown = data.status === 'COOLDOWN';
      if (statusEl) {
        if (isCooldown) {
          statusEl.innerHTML = `<span style="color: #fbbf24; font-weight: 700;">🟡 TẠM KHÓA TẦN SUẤT (HTTP 429)</span>`;
        } else {
          statusEl.innerHTML = `<span style="color: #34d399; font-weight: 700;">🟢 HOẠT ĐỘNG TỐT (200 OK)</span>`;
        }
      }

      if (cooldownRow) {
        cooldownRow.style.display = isCooldown ? 'block' : 'none';
      }
      if (cooldownResetIct) {
        cooldownResetIct.textContent = data.resetTimeIct ? `${data.resetTimeIct} ICT` : '--:-- --/-- ICT';
      }
      if (cooldownTimer) {
        this.formatCountdown(cooldownTimer, data.cooldownSeconds);
      }

      // Latency badge
      if (latencyBadge && latencyVal) {
        if (data.latencyMs != null) {
          const lat = Math.round(data.latencyMs);
          latencyVal.textContent = `${lat} ms`;
          latencyBadge.className = 'latency-badge ' + (lat < 300 ? 'latency-green' : (lat < 800 ? 'latency-amber' : 'latency-red'));
        } else {
          latencyVal.textContent = '-- ms';
          latencyBadge.className = 'latency-badge latency-green';
        }
      }

      // Quota
      const dailyRem = data.quota?.dailyRemaining ?? (isCooldown ? 0 : 250);
      const dailyLim = data.quota?.dailyLimit ?? 250;
      if (dailyQuotaEl) dailyQuotaEl.textContent = `${dailyRem} / ${dailyLim}`;
      if (burstQuotaEl) burstQuotaEl.textContent = `${data.quota?.burstRemaining ?? 85} / ${data.quota?.burstLimit ?? 100}`;
      if (quotaFillEl) {
        const pct = Math.max(0, Math.min(100, Math.round((dailyRem / dailyLim) * 100)));
        quotaFillEl.style.width = `${pct}%`;
      }

      if (chanCountEl) chanCountEl.textContent = data.channels ? data.channels.length : 0;
      if (chanListEl) {
        chanListEl.innerHTML = (data.channels || []).map(ch => {
          const service = (ch.service || '').toLowerCase();
          const isTT = service.includes('tiktok');
          const isIG = service.includes('instagram');
          const svcClass = isTT ? 'tt' : (isIG ? 'ig' : 'fb');
          const icon = isTT ? '🎵' : (isIG ? '📸' : '📘');
          const svcName = isTT ? 'TikTok' : (isIG ? 'Instagram' : 'Facebook Page');

          return `
            <div class="satellite-channel-card ${svcClass}">
              <div class="satellite-header">
                <div class="satellite-name-wrap">
                  <span class="satellite-icon">${icon}</span>
                  <span class="satellite-title">${ch.name}</span>
                  <span class="satellite-service-tag ${svcClass}">${svcName}</span>
                </div>
                <span class="satellite-queue-badge" title="Số bài chờ đăng">
                  ${ch.pendingCount} bài chờ
                </span>
              </div>
              <div class="satellite-meta-row">
                <div class="satellite-id-wrap">
                  <span class="meta-label">Buffer ID:</span>
                  <code class="satellite-id-code" id="sat-id-${ch.id}">${ch.id}</code>
                  <span class="copy-chip-sm" onclick="event.stopPropagation(); copyText('sat-id-${ch.id}')" title="Sao chép ID">Copy</span>
                </div>
              </div>
              <div class="satellite-times-row">
                <span class="time-item">Đăng gần nhất: <b>${ch.lastPostTime || 'Chưa có'}</b></span>
                <span class="time-item">Lên lịch tiếp: <b>${ch.nextPostTime || 'Chưa có'}</b></span>
              </div>
            </div>
          `;
        }).join('') || '<div style="color: #64748b; font-size: 12px;">Không có kênh nào</div>';
      }

    } else if (type === 'channel') {
      const service = (data.service || '').toLowerCase();
      const isTT = service.includes('tiktok');
      const isIG = service.includes('instagram');
      const svcName = isTT ? 'TIKTOK' : (isIG ? 'INSTAGRAM' : 'FACEBOOK PAGE');

      if (titleEl) titleEl.textContent = `KÊNH: ${data.name.toUpperCase()}`;
      if (emailEl) emailEl.textContent = parentAcc ? parentAcc.email : '--';
      if (keyEl) keyEl.textContent = parentAcc ? parentAcc.maskedKey : '--';
      if (statusEl) {
        statusEl.innerHTML = `<span style="color: ${isTT ? '#f472b6' : (isIG ? '#f43f5e' : '#60a5fa')}; font-weight: 700;">${svcName}</span>`;
      }
      if (cooldownRow) cooldownRow.style.display = 'none';
      if (chanCountEl) chanCountEl.textContent = '1';
      if (chanListEl) {
        chanListEl.innerHTML = `
          <div class="satellite-channel-card">
            <div style="font-size: 12px; margin-bottom: 6px;">ID: <code>${data.id}</code></div>
            <div style="font-size: 12px; margin-bottom: 6px;">Hàng chờ: <b>${data.pendingCount} bài</b></div>
            <div style="font-size: 12px; color: #38bdf8;">${data.nextPostTime ? `Lịch tiếp theo: ${data.nextPostTime}` : 'Đang chờ nội dung mới'}</div>
          </div>
        `;
      }
    }
  }

  formatCountdown(element, seconds) {
    if (!element) return;
    if (!seconds || seconds <= 0) {
      element.textContent = '00:00:00';
      return;
    }
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    element.textContent = `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
}

export function showToast(text, duration = 2200) {
  const toast = document.getElementById('toast-msg');
  if (!toast) return;
  toast.textContent = text;
  toast.classList.add('visible');
  if (window._toastTimeout) clearTimeout(window._toastTimeout);
  window._toastTimeout = setTimeout(() => {
    toast.classList.remove('visible');
  }, duration);
}
window.showToast = showToast;

export function copyToClipboard(text, triggerBtn = null, label = '') {
  if (!text) return;
  const cleanText = text.trim();
  const textSnippet = cleanText.length > 25 ? cleanText.slice(0, 22) + '...' : cleanText;

  const handleSuccess = () => {
    if (triggerBtn) {
      const origHtml = triggerBtn.innerHTML;
      triggerBtn.classList.add('copied');
      triggerBtn.innerHTML = `✓ Copied!`;
      setTimeout(() => {
        triggerBtn.innerHTML = origHtml;
        triggerBtn.classList.remove('copied');
      }, 1500);
    }
    showToast(`✓ Đã sao chép ${label ? label + ': ' : ''}${textSnippet}`);
  };

  const handleFallback = () => {
    const ta = document.createElement('textarea');
    ta.value = cleanText;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    ta.style.top = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, 99999);
    try {
      const successful = document.execCommand('copy');
      if (successful) {
        handleSuccess();
      } else {
        showToast('⚠️ Không thể sao chép văn bản');
      }
    } catch (err) {
      console.error('[Controls] Clipboard execCommand failed:', err);
      showToast('⚠️ Trình duyệt chặn quyền sao chép');
    } finally {
      if (ta.parentNode) document.body.removeChild(ta);
    }
  };

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(cleanText)
      .then(handleSuccess)
      .catch((err) => {
        console.warn('[Controls] navigator.clipboard failed, using fallback:', err);
        handleFallback();
      });
  } else {
    handleFallback();
  }
}
window.copyToClipboard = copyToClipboard;

export function copyText(elementId, triggerBtn = null) {
  const el = document.getElementById(elementId);
  if (!el) return;
  copyToClipboard(el.textContent.trim(), triggerBtn);
}
window.copyText = copyText;
