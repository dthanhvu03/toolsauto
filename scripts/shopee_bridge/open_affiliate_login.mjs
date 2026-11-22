#!/usr/bin/env node
/**
 * Mở CloakBrowser với đúng profile shopee-mcp, hiện cửa sổ, vào affiliate.shopee.vn
 * để anh login. Chạy khi shopee-mcp đã stop (không chia profile).
 *
 * Usage (Windows node):
 *   SHOPEE_PROFILE_DIR=C:\Users\Admin\.shopee-mcp\chrome-profile \
 *   node open_affiliate_login.mjs
 */
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// Resolve cloakbrowser from the installed shopee-mcp package (Win32 node + WSL path).
const require = createRequire(
  pathToFileURL(
    process.env.SHOPEE_MCP_PACKAGE_DIR ||
      path.join(
        process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming'),
        'npm',
        'node_modules',
        '@bintangtimurlangit',
        'shopee-mcp',
        'package.json',
      ),
  ).href,
);
const { launchPersistentContext } = require('cloakbrowser');

const PROFILE =
  process.env.SHOPEE_PROFILE_DIR ||
  path.join(os.homedir(), '.shopee-mcp', 'chrome-profile');
const PORTAL = process.env.SHOPEE_AFFILIATE_URL || 'https://affiliate.shopee.vn';

const ctx = await launchPersistentContext({
  userDataDir: PROFILE,
  headless: false,
  locale: 'vi-VN',
  timezone: 'Asia/Ho_Chi_Minh',
  viewport: { width: 1366, height: 768 },
  humanize: true,
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--hide-crash-restore-bubble',
    '--disable-session-crashed-bubble',
    '--noerrdialogs',
    '--start-maximized',
    '--window-position=80,40',
  ],
});

const page = ctx.pages().find((p) => !p.isClosed()) ?? (await ctx.newPage());
// Đưa cửa sổ ra giữa màn hình (profile mcp thường launch minimized/off-screen).
try {
  const session = await ctx.newCDPSession(page);
  const { windowId } = await session.send('Browser.getWindowForTarget');
  await session.send('Browser.setWindowBounds', {
    windowId,
    bounds: { left: 80, top: 40, width: 1280, height: 800, windowState: 'normal' },
  });
} catch {
  /* ignore */
}

await page.goto(PORTAL, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
process.stdout.write(`[open_affiliate_login] profile=${PROFILE}\n`);
process.stdout.write(`[open_affiliate_login] url=${page.url()}\n`);
process.stdout.write('[open_affiliate_login] Anh login trên cửa sổ Cloak. Giữ process này tới khi xong.\n');

// Giữ sống cho tới SIGINT/SIGTERM (anh báo xong → stop).
await new Promise((resolve) => {
  const stop = () => resolve();
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
});
await ctx.close().catch(() => {});
process.stdout.write('[open_affiliate_login] closed\n');
