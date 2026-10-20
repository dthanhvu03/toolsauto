/**
 * Module Graph: Quản lý khởi tạo và render các Node mạng lưới (Core, Accounts, Channels)
 * cùng các chùm tia laser kết nối và hạt photon chuyển động.
 */

export class ClusterGraph {
  constructor(scene) {
    this.scene = scene;
    this.coreNode = null;
    this.accountNodes = [];
    this.channelNodes = [];
    this.splineCurves = [];
    this.particleSystems = [];
  }

  clear() {
    this.accountNodes.forEach(n => this.scene.remove(n.mesh));
    this.channelNodes.forEach(n => this.scene.remove(n.mesh));
    if (this.coreNode) this.scene.remove(this.coreNode);
    this.splineCurves.forEach(c => this.scene.remove(c.lineMesh));
    this.particleSystems.forEach(p => this.scene.remove(p.points));

    this.accountNodes = [];
    this.channelNodes = [];
    this.splineCurves = [];
    this.particleSystems = [];
  }

  build(data) {
    this.clear();

    // 1. Central Core Node
    const coreGeo = new THREE.SphereGeometry(16, 32, 32);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x00f0ff,
      emissive: 0x0088cc,
      emissiveIntensity: 0.8,
      roughness: 0.2,
      metalness: 0.8,
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

      this.accountNodes.push({ mesh: accMesh, data: acc });

      // Laser Spline: Core -> Account
      this.createLaserConnection(this.coreNode.position, accMesh.position, accColor);

      // 3. Satellite Channels for this Account
      const channels = acc.channels || [];
      const numChannels = channels.length;
      const chanOrbitRadius = 38;

      channels.forEach((ch, ci) => {
        const chanAngle = angle - 0.7 + (ci / Math.max(numChannels - 1, 1)) * 1.4;
        const cx = ax + Math.cos(chanAngle) * chanOrbitRadius;
        const cz = az + Math.sin(chanAngle) * chanOrbitRadius;
        const cy = ay + (ci % 2 === 0 ? 12 : -12);

        const isTikTok = (ch.service || '').toLowerCase().includes('tiktok');
        const chanColor = isTikTok ? 0xec4899 : 0x3b82f6;

        const chanGeo = new THREE.SphereGeometry(6, 24, 24);
        const chanMat = new THREE.MeshStandardMaterial({
          color: chanColor,
          emissive: chanColor,
          emissiveIntensity: 0.4,
          roughness: 0.4,
        });
        const chanMesh = new THREE.Mesh(chanGeo, chanMat);
        chanMesh.position.set(cx, cy, cz);
        chanMesh.userData = { type: 'channel', data: ch, parentAccount: acc };
        this.scene.add(chanMesh);

        this.channelNodes.push({ mesh: chanMesh, data: ch });

        // Spline: Account -> Channel
        this.createLaserConnection(accMesh.position, chanMesh.position, chanColor, 0.5);
      });
    });
  }

  createLaserConnection(p1, p2, colorHex, particleSpeed = 1.0) {
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
    this.scene.add(lineMesh);
    this.splineCurves.push({ curve, lineMesh });

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
    this.scene.add(particleMesh);

    this.particleSystems.push({
      points: particleMesh,
      curve: curve,
      progress: Math.random(),
      speed: (0.003 + Math.random() * 0.002) * particleSpeed,
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
