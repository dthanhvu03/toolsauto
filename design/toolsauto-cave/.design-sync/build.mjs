#!/usr/bin/env node
// .design-sync/build.mjs — bộ sinh bundle "off-script" cho thư viện HTML tĩnh ToolsAuto Cave.
//
// Thư viện này KHÔNG phải package React/Storybook nên converter chuẩn của /design-sync
// (package-build.mjs) không áp dụng. Script này tạo đúng layout mà claude.ai/design đọc:
//   _ds_bundle.js (namespace rỗng + header @ds-bundle)  styles.css (@import tokens + components)
//   tokens/{tokens,components}.css   components/<Group>/<Name>/<Name>.{html,prompt.md}
//   README.md (conventions.md + chỉ mục card)   _ds_needs_recompile   _ds_sync.json (anchor)
//   .ds-build-meta.json  .review.html  (dot-prefixed: chỉ dùng local, không upload)
//
// Chạy:  node .design-sync/build.mjs [--out ./ds-bundle]
// Sau đó: node .ds-sync/package-validate.mjs ./ds-bundle   (DS_CHROMIUM_PATH=... nếu cần)
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url)); // .design-sync/
const SRC = resolve(HERE, '..'); // design/toolsauto-cave/
const argv = process.argv.slice(2);
const outIdx = argv.indexOf('--out');
const OUT = resolve(SRC, outIdx >= 0 ? argv[outIdx + 1] : 'ds-bundle');
const cfg = JSON.parse(readFileSync(join(HERE, 'config.json'), 'utf8'));
const NS = cfg.globalName || 'ToolsAutoCave';
const GROUP_DIRS = cfg.sourceDirs || ['foundations', 'components', 'patterns'];
const sha12 = (buf) => createHash('sha256').update(buf).digest('hex').slice(0, 12);
const pascal = (s) => s.split(/[-_ ]+/).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join('');
const log = (m) => console.error(m);

// ── 1. Thu thập card từ marker @dsCard ─────────────────────────────────────
const MARK = /^<!--\s*@dsCard\s+([^>]*?)-->/;
const attrsOf = (s) => Object.fromEntries([...s.matchAll(/(\w+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
const cards = [];
for (const dir of GROUP_DIRS) {
  const abs = join(SRC, dir);
  if (!existsSync(abs)) continue;
  for (const f of readdirSync(abs).filter((n) => n.endsWith('.html')).sort()) {
    const html = readFileSync(join(abs, f), 'utf8');
    const m = MARK.exec(html.split('\n', 1)[0]);
    if (!m) { log(`✗ ${dir}/${f}: dòng đầu không phải marker @dsCard`); process.exit(1); }
    const a = attrsOf(m[1]);
    if (!a.group) { log(`✗ ${dir}/${f}: marker thiếu group=`); process.exit(1); }
    const base = basename(f, '.html');
    const name = (cfg.componentNames || {})[base] || pascal(base);
    cards.push({ src: join(abs, f), rel: `${dir}/${f}`, base, name, group: a.group, attrs: a, html });
  }
}
if (!cards.length) { log('✗ không tìm thấy card nào'); process.exit(1); }

// ── 2. Dọn output ──────────────────────────────────────────────────────────
if (basename(OUT) !== 'ds-bundle' && existsSync(OUT)) { log(`✗ từ chối xoá ${OUT} (không phải ds-bundle)`); process.exit(1); }
rmSync(OUT, { recursive: true, force: true });
mkdirSync(join(OUT, 'tokens'), { recursive: true });

// ── 3. tokens/ + styles.css ────────────────────────────────────────────────
const cssFiles = cfg.cssFiles || ['tokens.css', 'components.css'];
for (const c of cssFiles) writeFileSync(join(OUT, 'tokens', c), readFileSync(join(SRC, c)));
const fontImport = cfg.fontsUrl ? `@import url("${cfg.fontsUrl}");\n` : '';
writeFileSync(join(OUT, 'styles.css'),
  `/* ToolsAuto Cave — điểm vào CSS. Thiết kế sinh ra chỉ nhận closure @import của file này. */\n` +
  fontImport + cssFiles.map((c) => `@import "./tokens/${c}";`).join('\n') + '\n');

// ── 4. components/<Group>/<Name>/ ──────────────────────────────────────────
const sourceHashes = {};
for (const c of cards) {
  const dir = join(OUT, 'components', c.group, c.name);
  mkdirSync(dir, { recursive: true });
  const a = c.attrs;
  const vp = a.width && a.height ? ` viewport="${a.width}x${a.height}"` : '';
  const marker = `<!-- @dsCard group="${a.group}"` +
    (a.name ? ` name="${a.name}"` : '') + (a.subtitle ? ` subtitle="${a.subtitle}"` : '') +
    (a.width ? ` width="${a.width}"` : '') + (a.height ? ` height="${a.height}"` : '') + vp + ' -->';
  let html = c.html.replace(MARK, marker);
  // Link CSS: mọi <link> nội bộ → ../../../styles.css (giữ link https Google Fonts)
  let linked = false;
  html = html.replace(/[ \t]*<link rel="stylesheet" href="\.\.\/[^"]+">\r?\n/g, () => {
    if (linked) return '';
    linked = true;
    return '<link rel="stylesheet" href="../../../styles.css">\n';
  });
  if (!linked) { log(`✗ ${c.rel}: không thấy <link> CSS nội bộ để thay`); process.exit(1); }
  // Bọc nội dung body trong #root — render check của validate đo mount này
  html = html.replace(/<body([^>]*)>/, '<body$1>\n<div id="root">');
  html = html.replace(/<\/body>/, '</div>\n</body>');
  writeFileSync(join(dir, `${c.name}.html`), html);
  const promptSrc = join(HERE, 'prompts', `${c.name}.md`);
  if (!existsSync(promptSrc)) { log(`✗ thiếu .design-sync/prompts/${c.name}.md (usage reference cho design agent)`); process.exit(1); }
  const prompt = readFileSync(promptSrc, 'utf8');
  if (!prompt.split('\n', 1)[0].trim()) { log(`✗ prompts/${c.name}.md: dòng đầu trống`); process.exit(1); }
  writeFileSync(join(dir, `${c.name}.prompt.md`), prompt);
  const relBase = `components/${c.group}/${c.name}/${c.name}`;
  sourceHashes[`${relBase}.html`] = sha12(readFileSync(join(dir, `${c.name}.html`)));
  sourceHashes[`${relBase}.prompt.md`] = sha12(readFileSync(join(dir, `${c.name}.prompt.md`)));
}

// ── 5. _ds_bundle.js — namespace rỗng: DS này không có component React ────
const header = { namespace: NS, components: [], sourceHashes, inlinedExternals: [], builtBy: 'cc-design-sync' };
const bundleBody =
  `// ToolsAuto Cave là thư viện HTML + CSS thuần (Jinja/HTMX phía tool). Không có component React;\n` +
  `// dựng giao diện bằng class trong styles.css (xem README). Namespace giữ rỗng để app tự kiểm.\n` +
  `;(function () { var g = typeof window !== 'undefined' ? window : globalThis; g[${JSON.stringify(NS)}] = g[${JSON.stringify(NS)}] || {}; })();\n`;
writeFileSync(join(OUT, '_ds_bundle.js'), `/* @ds-bundle: ${JSON.stringify(header).replace(/\*\//g, '*\\/')} */\n` + bundleBody);

// ── 6. README.md = conventions.md + chỉ mục sinh tự động ──────────────────
const headerPath = cfg.readmeHeader ? resolve(SRC, cfg.readmeHeader) : null;
const conv = headerPath && existsSync(headerPath) ? readFileSync(headerPath, 'utf8').trimEnd() + '\n\n' : '';
if (cfg.readmeHeader && !conv) log(`! readmeHeader ${cfg.readmeHeader} không tồn tại — README không có phần quy ước`);
const byGroup = {};
for (const c of cards) (byGroup[c.group] ||= []).push(c);
let index = `## Chỉ mục card (${cards.length})\n\n| Nhóm | Card | Thư mục | Nội dung | Kích thước |\n|---|---|---|---|---|\n`;
for (const g of Object.keys(byGroup)) for (const c of byGroup[g]) {
  index += `| ${g} | ${c.attrs.name || c.name} | \`components/${g}/${c.name}/\` | ${c.attrs.subtitle || ''} | ${c.attrs.width || '?'}×${c.attrs.height || '?'} |\n`;
}
const srcReadme = readFileSync(join(SRC, 'README.md'), 'utf8');
const caveats = /(^## Những chỗ[\s\S]*?)(?=^## |\s*$(?![\s\S]))/m.exec(srcReadme)?.[1]?.trimEnd() ?? '';
writeFileSync(join(OUT, 'README.md'), conv + index + '\n' + (caveats ? caveats + '\n' : ''));
if (readFileSync(join(OUT, 'README.md')).length > 31_000) log('! README.md > 31k ký tự — phần đuôi có thể bị cắt trong system prompt');

// ── 7. Tệp phụ: sentinel, meta, review ────────────────────────────────────
writeFileSync(join(OUT, '_ds_needs_recompile'), '{"by":"design-sync-cli"}\n');
writeFileSync(join(OUT, '.ds-build-meta.json'), JSON.stringify({
  shape: 'package', offScript: true, generator: '.design-sync/build.mjs', componentCount: cards.length, namespace: NS,
}, null, 2) + '\n');
const review = `<!doctype html><meta charset="utf-8"><title>ToolsAuto Cave — review</title>
<style>body{margin:0;padding:24px;background:#0c0b0a;color:#ebe4d8;font:14px system-ui}h2{margin:32px 0 8px;font-size:18px}h3{margin:16px 0 6px;font-size:13px;color:#9a9186;font-weight:500}iframe{border:1px solid #453f36;border-radius:8px;background:#0c0b0a;display:block}</style>
<h1>ToolsAuto Cave — ${cards.length} card (build local, không upload)</h1>
${Object.keys(byGroup).map((g) => `<h2>${g}</h2>` + byGroup[g].map((c) =>
  `<h3>${c.attrs.name || c.name} — <code>${c.name}</code> · ${c.attrs.subtitle || ''}</h3>` +
  `<iframe src="components/${g}/${c.name}/${c.name}.html" width="${c.attrs.width || 960}" height="${c.attrs.height || 600}" loading="lazy"></iframe>`).join('\n')).join('\n')}
`;
writeFileSync(join(OUT, '.review.html'), review);

// ── 8. _ds_sync.json — anchor cho lần sync sau (dùng đúng recipe của skill) ─
const hashesLib = join(SRC, '.ds-sync', 'lib', 'sync-hashes.mjs');
if (existsSync(hashesLib)) {
  const { styleShaFor, renderHashFor, auxShaFor, scriptsShaFor } = await import(pathToFileURL(hashesLib).href);
  const renderHashes = Object.fromEntries(cards.map((c) => [c.name, renderHashFor(OUT, { name: c.name, group: c.group }, {})]));
  writeFileSync(join(OUT, '_ds_sync.json'), JSON.stringify({
    shape: 'package',
    styleSha: styleShaFor(OUT, { includeBundleBody: true }),
    renderHashes,
    // sourceKeys bỏ trống có chủ đích: recipe của skill cần story facts; thiếu → lần sync sau
    // re-verify những card có renderHash thay đổi (12 card tĩnh, rẻ).
    scriptsSha: scriptsShaFor(),
    sourceHashes,
    auxSha: auxShaFor(OUT),
    bundleSha12: sha12(readFileSync(join(OUT, '_ds_bundle.js'))),
  }, null, 2) + '\n');
  log(`  _ds_sync.json: ${cards.length} render hash (anchor)`);
} else {
  log('! .ds-sync/lib/sync-hashes.mjs chưa stage → bỏ qua _ds_sync.json (lần sync sau re-verify tất cả)');
}

log(`✓ ${OUT}: ${cards.length} card → ${Object.keys(byGroup).map((g) => `${g}(${byGroup[g].length})`).join(' ')}; styles.css + ${cssFiles.join(', ')}`);
