/**
 * Module Graph: Quản lý khởi tạo và render các Node mạng lưới 3D (Core, Accounts, Channels)
 * cùng các chùm tia laser kết nối, hạt photon chuyển động, và 3D Node Dimming (F9).
 */

export class ClusterGraph {
  constructor(scene) {
    this.scene = scene;
    this.coreNode = null;
    this.accountNodes = [];
    this.channelNodes = [];
    this.splineCurves = [];
    this.particleSystems = [];
    this.currentFilter = null;
  }

  clear() {
    this.accountNodes.forEach(n => {
      this.scene.remove(n.mesh);
      if (n.mesh.geometry) n.mesh.geometry.dispose();
      if (n.mesh.material) n.mesh.material.dispose();
    });
    this.channelNodes.forEach(n => {
      this.scene.remove(n.mesh);
      if (n.mesh.geometry) n.mesh.geometry.dispose();
      if (n.mesh.material) n.mesh.material.dispose();
    });
    if (this.coreNode) {
      this.scene.remove(this.coreNode);
    }
    this.splineCurves.forEach(c => {
      this.scene.remove(c.lineMesh);
      if (c.lineMesh.geometry) c.lineMesh.geometry.dispose();
      if (c.lineMesh.material) c.lineMesh.material.dispose();
    });
    this.particleSystems.forEach(p => {
      this.scene.remove(p.points);
      if (p.points.geometry) p.points.geometry.dispose();
      if (p.points.material) p.points.material.dispose();
    });

    this.accountNodes = [];
    this.channelNodes = [];
    this.splineCurves = [];
    this.particleSystems = [];
  }

  build(data) {
    this.clear();

    // 1. Central Gateway Core Node
    const coreGeo = new THREE.SphereGeometry(16, 32, 32);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x00f0ff,
      emissive: 0x0088cc,
      emissiveIntensity: 0.8,
      roughness: 0.2,
      metalness: 0.8,
      transparent: true,
      opacity: 1.0,
    });
    this.coreNode = new THREE.Mesh(coreGeo, coreMat);
    this.coreNode.position.set(0, 20, 0);
    this.coreNode.userData = { type: 'core', name: 'ToolsAuto Gateway Core' };
    this.scene.add(this.coreNode);

    // Rotating Energy Ring around Core
    const ringGeo = new THREE.TorusGeometry(26, 0.8, 16, 100);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x00f0ff, wireframe: true });
    const coreRing = new THREE.Mesh(ringGeo, ringMat);
    coreRing.rotation.x = Math.PI / 3;
    this.coreNode.add(coreRing);

    // 2. Orbiting Account Nodes
    const accounts = data.accounts || [];
    const numAccounts = accounts.length;
    const orbitRadius = 90;

    accounts.forEach((acc, i) => {
      const angle = (i / numAccounts) * Math.PI * 2;
      const ax = Math.cos(angle) * orbitRadius;
      const az = Math.sin(angle) * orbitRadius;
      const ay = 15 + (i % 2 === 0 ? 10 : -10);

      const isCooldown = acc.status === 'COOLDOWN';
      const accColor = isCooldown ? 0xf59e0b : (acc.index === 3 ? 0x00f0ff : 0x10b981);
      const emissiveColor = isCooldown ? 0xb45309 : 0x047857;

      const accGeo = new THREE.DodecahedronGeometry(12, 1);
      const accMat = new THREE.MeshStandardMaterial({
        color: accColor,
        emissive: emissiveColor,
        emissiveIntensity: 0.6,
        roughness: 0.3,
        metalness: 0.6,
        transparent: true,
        opacity: 1.0,
      });
      const accMesh = new THREE.Mesh(accGeo, accMat);
      accMesh.position.set(ax, ay, az);
      accMesh.userData = { type: 'account', data: acc };
      this.scene.add(accMesh);

      // Energy Halo
      const haloGeo = new THREE.RingGeometry(16, 18, 32);
      const haloMat = new THREE.MeshBasicMaterial({
        color: accColor,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.45,
      });
      const haloMesh = new THREE.Mesh(haloGeo, haloMat);
      haloMesh.rotation.x = Math.PI / 2;
      accMesh.add(haloMesh);

      this.accountNodes.push({
        mesh: accMesh,
        halo: haloMesh,
        data: acc,
        defaultColor: accColor,
        defaultEmissive: emissiveColor,
        defaultEmissiveIntensity: 0.6,
      });

      // Laser Spline: Core -> Account
      this.createLaserConnection(this.coreNode.position, accMesh.position, accColor, 1.0, {
        type: 'core-to-account',
        accountIndex: acc.index,
      });

      // 3. Satellite Channels for this Account
      const channels = acc.channels || [];
      const numChannels = channels.length;
      const chanOrbitRadius = 38;

      channels.forEach((ch, ci) => {
        const chanAngle = angle - 0.7 + (ci / Math.max(numChannels - 1, 1)) * 1.4;
        const cx = ax + Math.cos(chanAngle) * chanOrbitRadius;
        const cz = az + Math.sin(chanAngle) * chanOrbitRadius;
        const cy = ay + (ci % 2 === 0 ? 12 : -12);

        const service = (ch.service || '').toLowerCase();
        const isTikTok = service.includes('tiktok');
        const isInstagram = service.includes('instagram');
        const chanColor = isTikTok ? 0xec4899 : (isInstagram ? 0xa855f7 : 0x3b82f6);

        const chanGeo = new THREE.SphereGeometry(6, 24, 24);
        const chanMat = new THREE.MeshStandardMaterial({
          color: chanColor,
          emissive: chanColor,
          emissiveIntensity: 0.4,
          roughness: 0.4,
          transparent: true,
          opacity: 1.0,
        });
        const chanMesh = new THREE.Mesh(chanGeo, chanMat);
        chanMesh.position.set(cx, cy, cz);
        chanMesh.userData = { type: 'channel', data: ch, parentAccount: acc };
        this.scene.add(chanMesh);

        this.channelNodes.push({
          mesh: chanMesh,
          data: ch,
          parentAccount: acc,
          defaultColor: chanColor,
          defaultEmissiveIntensity: 0.4,
        });

        // Spline: Account -> Channel
        this.createLaserConnection(accMesh.position, chanMesh.position, chanColor, 0.5, {
          type: 'account-to-channel',
          accountIndex: acc.index,
          channelId: ch.id,
        });
      });
    });

    // Re-apply filter if active
    if (this.currentFilter) {
      this.applyFilter(this.currentFilter);
    }
  }

  createLaserConnection(p1, p2, colorHex, particleSpeed = 1.0, meta = {}) {
    const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
    mid.y += 10;

    const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
    const points = curve.getPoints(30);
    const geometry = new THREE.BufferGeometry().setFromPoints(points);

    const material = new THREE.LineBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: 0.35,
    });
    const lineMesh = new THREE.Line(geometry, material);
    lineMesh.userData = { ...meta };
    this.scene.add(lineMesh);
    this.splineCurves.push({ curve, lineMesh, meta });

    // Flowing particle
    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array([p1.x, p1.y, p1.z]), 3));
    const pMat = new THREE.PointsMaterial({
      color: colorHex,
      size: 5,
      transparent: true,
      opacity: 0.9,
    });
    const particleMesh = new THREE.Points(pGeo, pMat);
    particleMesh.userData = { ...meta };
    this.scene.add(particleMesh);

    this.particleSystems.push({
      points: particleMesh,
      curve: curve,
      progress: Math.random(),
      speed: (0.003 + Math.random() * 0.002) * particleSpeed,
      meta,
    });
  }

  /**
   * 3D Graph Node & Laser Dimming (F9)
   * Làm mờ các node và laser không khớp bộ lọc về opacity: 0.15 / 0.05
   * và làm nổi bật các node khớp (opacity: 1.0, emissiveIntensity cao).
   */
  applyFilter({ query = '', platform = 'all' } = {}) {
    this.currentFilter = { query, platform };
    const q = (query || '').trim().toLowerCase();
    const plat = (platform || 'all').trim().toLowerCase();
    const hasFilter = q.length > 0 || plat !== 'all';

    const matchedChannelIds = new Set();
    const matchedAccountIndices = new Set();

    if (hasFilter) {
      // 1. Quét tìm các kênh khớp
      this.channelNodes.forEach(({ data: ch, parentAccount: acc }) => {
        const service = (ch.service || '').toLowerCase();
        const matchPlat = (plat === 'all') || service.includes(plat);
        const matchQuery = !q || (
          (ch.name || '').toLowerCase().includes(q) ||
          (ch.id || '').toLowerCase().includes(q) ||
          (acc && (acc.email || '').toLowerCase().includes(q)) ||
          (acc && (acc.maskedKey || '').toLowerCase().includes(q))
        );
        if (matchPlat && matchQuery) {
          matchedChannelIds.add(ch.id);
          if (acc) matchedAccountIndices.add(acc.index);
        }
      });

      // 2. Tài khoản khớp trực tiếp qua email khi platform là 'all'
      if (plat === 'all') {
        this.accountNodes.forEach(({ data: acc }) => {
          if (!q || (acc.email || '').toLowerCase().includes(q) || (acc.name || '').toLowerCase().includes(q) || (acc.maskedKey || '').toLowerCase().includes(q)) {
            matchedAccountIndices.add(acc.index);
          }
        });
      }
    }

    // A. Dimming Channel Nodes
    this.channelNodes.forEach(({ mesh, data: ch, defaultEmissiveIntensity }) => {
      const isMatch = !hasFilter || matchedChannelIds.has(ch.id);
      if (isMatch) {
        mesh.material.opacity = 1.0;
        mesh.material.emissiveIntensity = hasFilter ? 0.85 : defaultEmissiveIntensity;
        mesh.scale.set(hasFilter ? 1.15 : 1.0, hasFilter ? 1.15 : 1.0, hasFilter ? 1.15 : 1.0);
      } else {
        mesh.material.opacity = 0.15;
        mesh.material.emissiveIntensity = 0.05;
        mesh.scale.set(0.7, 0.7, 0.7);
      }
    });

    // B. Dimming Account Nodes
    this.accountNodes.forEach(({ mesh, halo, data: acc, defaultEmissiveIntensity }) => {
      const isMatch = !hasFilter || matchedAccountIndices.has(acc.index);
      if (isMatch) {
        mesh.material.opacity = 1.0;
        mesh.material.emissiveIntensity = hasFilter ? 0.85 : defaultEmissiveIntensity;
        if (halo) halo.material.opacity = 0.45;
        mesh.scale.set(hasFilter ? 1.1 : 1.0, hasFilter ? 1.1 : 1.0, hasFilter ? 1.1 : 1.0);
      } else {
        mesh.material.opacity = 0.15;
        mesh.material.emissiveIntensity = 0.05;
        if (halo) halo.material.opacity = 0.05;
        mesh.scale.set(0.75, 0.75, 0.75);
      }
    });

    // C. Dimming Spline Laser Beams
    this.splineCurves.forEach(({ lineMesh, meta }) => {
      let isMatch = true;
      if (hasFilter) {
        if (meta.type === 'core-to-account') {
          isMatch = matchedAccountIndices.has(meta.accountIndex);
        } else if (meta.type === 'account-to-channel') {
          isMatch = matchedChannelIds.has(meta.channelId);
        }
      }
      lineMesh.material.opacity = isMatch ? (hasFilter ? 0.6 : 0.35) : 0.05;
    });

    // D. Dimming Photon Flow Particles
    this.particleSystems.forEach(p => {
      let isMatch = true;
      if (hasFilter && p.meta) {
        if (p.meta.type === 'core-to-account') {
          isMatch = matchedAccountIndices.has(p.meta.accountIndex);
        } else if (p.meta.type === 'account-to-channel') {
          isMatch = matchedChannelIds.has(p.meta.channelId);
        }
      }
      p.points.material.opacity = isMatch ? (hasFilter ? 1.0 : 0.9) : 0.1;
    });
  }

  /**
   * Cập nhật màu sắc node khi account đổi trạng thái COOLDOWN <-> ACTIVE
   */
  updateAccountStatus(accountIndex, newStatus) {
    const accNode = this.accountNodes.find(n => n.data.index === accountIndex);
    if (!accNode) return;

    const isCooldown = newStatus === 'COOLDOWN';
    const newColor = isCooldown ? 0xf59e0b : (accountIndex === 3 ? 0x00f0ff : 0x10b981);
    const newEmissive = isCooldown ? 0xb45309 : (accountIndex === 3 ? 0x0088cc : 0x047857);

    accNode.mesh.material.color.setHex(newColor);
    accNode.mesh.material.emissive.setHex(newEmissive);
    if (accNode.halo) accNode.halo.material.color.setHex(newColor);

    // Cập nhật laser Core -> Account
    this.splineCurves.forEach(({ lineMesh, meta }) => {
      if (meta.type === 'core-to-account' && meta.accountIndex === accountIndex) {
        lineMesh.material.color.setHex(newColor);
      }
    });
    this.particleSystems.forEach(p => {
      if (p.meta?.type === 'core-to-account' && p.meta?.accountIndex === accountIndex) {
        p.points.material.color.setHex(newColor);
      }
    });
  }

  updateAnimations() {
    if (this.coreNode) {
      this.coreNode.rotation.y += 0.006;
    }

    this.particleSystems.forEach(p => {
      p.progress += p.speed;
      if (p.progress > 1) p.progress = 0;
      const pt = p.curve.getPoint(p.progress);
      const pos = p.points.geometry.attributes.position;
      pos.setXYZ(0, pt.x, pt.y, pt.z);
      pos.needsUpdate = true;
    });
  }

  getInteractiveMeshes() {
    return [
      this.coreNode,
      ...this.accountNodes.map(a => a.mesh),
      ...this.channelNodes.map(c => c.mesh),
    ].filter(Boolean);
  }
}
