/**
 * Module Controls: Xử lý tương tác người dùng, Raycasting hover tooltips,
 * Camera fly-to lerp animation, mở Telemetry Drawer bên phải và tiện ích copy.
 */

export class ClusterControlsManager {
  constructor(camera, orbitControls, graph) {
    this.camera = camera;
    this.orbitControls = orbitControls;
    this.graph = graph;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.tooltipEl = document.getElementById('tooltip-3d');
    this.inspectorEl = document.getElementById('right-inspector');

    this.pointerDownPos = { x: 0, y: 0 };
    this.initEvents();
  }

  initEvents() {
    window.addEventListener('mousemove', (e) => this.onMouseMove(e));
    
    // Prevent dragging to rotate from accidentally triggering node clicks
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

    // Mobile swipe down to close Bottom Sheet
    let sheetStartY = 0;
    this.inspectorEl.addEventListener('touchstart', (e) => {
      sheetStartY = e.touches[0].clientY;
    }, { passive: true });

    this.inspectorEl.addEventListener('touchend', (e) => {
      const deltaY = e.changedTouches[0].clientY - sheetStartY;
      if (deltaY > 50 && this.inspectorEl.scrollTop <= 5) {
        this.closeInspector();
      }
    }, { passive: true });

    const resetCamBtn = document.getElementById('btn-reset-cam');
    if (resetCamBtn) {
      resetCamBtn.addEventListener('click', () => {
        const isMob = window.innerWidth <= 768;
        this.smoothMoveCamera(new THREE.Vector3(0, isMob ? 180 : 140, isMob ? 380 : 280), new THREE.Vector3(0, 20, 0));
      });
    }

    window.addEventListener('cluster:select-account', (e) => {
      this.focusAccountNode(e.detail.index);
      this.openInspector('account', e.detail.account);
    });
  }

  closeInspector() {
    this.inspectorEl.classList.remove('visible');
    const backdrop = document.getElementById('inspector-backdrop');
    if (backdrop) backdrop.classList.remove('visible');
  }

  onMouseMove(event) {
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
    } else {
      document.body.style.cursor = 'default';
      this.tooltipEl.style.opacity = '0';
    }
  }

  onPointerClick(event) {
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
    const nodeObj = this.graph.accountNodes.find(n => n.data.index === index);
    if (!nodeObj) return;

    document.querySelectorAll('.account-card').forEach(c => c.classList.remove('selected'));
    const activeCard = document.getElementById(`card-acc-${index}`);
    if (activeCard) {
      activeCard.classList.add('selected');
      activeCard.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    const isMobile = window.innerWidth <= 768;
    const targetPos = nodeObj.mesh.position.clone();
    // On mobile, keep node elevated in upper screen half so it's not hidden behind bottom sheet
    const cameraOffset = isMobile ? new THREE.Vector3(0, 50, 110) : new THREE.Vector3(0, 30, 80);
    const lookAtPos = isMobile ? targetPos.clone().add(new THREE.Vector3(0, -15, 0)) : targetPos;
    const newCamPos = targetPos.clone().add(cameraOffset);

    this.smoothMoveCamera(newCamPos, lookAtPos);
  }

  smoothMoveCamera(toPos, lookAtPos) {
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
    this.inspectorEl.classList.add('visible');
    const backdrop = document.getElementById('inspector-backdrop');
    if (backdrop) backdrop.classList.add('visible');

    const titleEl = document.getElementById('inspect-header-title');
    const emailEl = document.getElementById('inspect-email-text');
    const keyEl = document.getElementById('inspect-key-text');
    const statusEl = document.getElementById('inspect-status');
    const cooldownRow = document.getElementById('inspect-cooldown-row');
    const cooldownTimer = document.getElementById('inspect-cooldown-timer');
    const chanCountEl = document.getElementById('inspect-channel-count');
    const chanListEl = document.getElementById('inspect-channels-list');

    if (type === 'account') {
      titleEl.textContent = `${data.name.toUpperCase()} TELEMETRY`;
      emailEl.textContent = data.email || 'Chưa rõ';
      keyEl.textContent = data.maskedKey || '--';

      if (data.status === 'COOLDOWN') {
        statusEl.innerHTML = `<span style="color: #fbbf24; font-weight: 700;">🟡 TẠM KHÓA TẦN SUẤT (HTTP 429)</span>`;
        cooldownRow.style.display = 'block';
        this.formatCountdown(cooldownTimer, data.cooldownSeconds);
      } else {
        statusEl.innerHTML = `<span style="color: #34d399; font-weight: 700;">🟢 HOẠT ĐỘNG TỐT (200 OK)</span>`;
        cooldownRow.style.display = 'none';
      }

      chanCountEl.textContent = data.channels ? data.channels.length : 0;
      chanListEl.innerHTML = (data.channels || []).map(ch => {
        const isTT = (ch.service || '').toLowerCase().includes('tiktok');
        const nextTime = ch.nextPostTime ? `Lịch tiếp: <b>${ch.nextPostTime}</b>` : 'Chưa có lịch tiếp';
        return `
          <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); padding: 8px 12px; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <span style="font-weight: 700; color: ${isTT ? '#f472b6' : '#93c5fd'}">${isTT ? '🎵' : '📘'} ${ch.name}</span>
              <span style="font-size: 11px; background: rgba(0,240,255,0.15); color: #38bdf8; padding: 2px 6px; border-radius: 4px;">${ch.pendingCount} bài chờ</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted);">${nextTime}</div>
          </div>
        `;
      }).join('') || '<div style="color: #64748b; font-size: 12px;">Không có kênh nào</div>';

    } else if (type === 'channel') {
      const isTT = (data.service || '').toLowerCase().includes('tiktok');
      titleEl.textContent = `KÊNH: ${data.name.toUpperCase()}`;
      emailEl.textContent = parentAcc ? parentAcc.email : '--';
      keyEl.textContent = parentAcc ? parentAcc.maskedKey : '--';
      statusEl.innerHTML = `<span style="color: ${isTT ? '#f472b6' : '#60a5fa'}; font-weight: 700;">${isTT ? 'TIKTOK' : 'FACEBOOK PAGE'}</span>`;
      cooldownRow.style.display = 'none';
      chanCountEl.textContent = '1';
      chanListEl.innerHTML = `
        <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
          <div style="font-size: 12px; margin-bottom: 6px;">ID: <code>${data.id}</code></div>
          <div style="font-size: 12px; margin-bottom: 6px;">Hàng chờ: <b>${data.pendingCount} bài</b></div>
          <div style="font-size: 12px; color: #38bdf8;">${data.nextPostTime ? `Lịch tiếp theo: ${data.nextPostTime}` : 'Đang chờ nội dung mới'}</div>
        </div>
      `;
    }
  }

  formatCountdown(element, seconds) {
    if (!seconds || seconds <= 0) {
      element.textContent = 'Hết thời gian chờ';
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

export function copyText(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = el.textContent.trim();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      showToast('✓ Đã sao chép: ' + (text.length > 25 ? text.slice(0, 22) + '...' : text));
    }).catch(() => {
      showToast('Không thể sao chép');
    });
  } else {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('✓ Đã sao chép: ' + (text.length > 25 ? text.slice(0, 22) + '...' : text));
  }
}
window.copyText = copyText;
