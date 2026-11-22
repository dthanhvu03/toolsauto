#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createBrowserBackend } from './browser.mjs';
import { bridgeConfig, createBridgeServer } from './server.mjs';

const packageName = '@bintangtimurlangit/shopee-mcp';
const packageVersion = '0.3.0';

export async function loadBackend(env = process.env, { diagnostics } = {}) {
  const appData = env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
  const packageDir = env.SHOPEE_MCP_PACKAGE_DIR || path.join(appData, 'npm', 'node_modules', ...packageName.split('/'));
  const pkg = JSON.parse(await readFile(path.join(packageDir, 'package.json'), 'utf8'));
  if (pkg.name !== packageName || pkg.version !== packageVersion) throw new Error('unsupported_dependency');
  // Only browser/action exports: importing the installed index would start a
  // second listener and expose its legacy diagnostic routes.
  const [session, actions] = await Promise.all([
    import(pathToFileURL(path.join(packageDir, 'build/browser/session.js')).href),
    import(pathToFileURL(path.join(packageDir, 'build/tools/actions.js')).href),
  ]);
  const cookiePath = env.SHOPEE_AFFILIATE_COOKIE_FILE
    || fileURLToPath(new URL('../../storage/db/config/shopee_affiliate_cookies.json', import.meta.url));
  return createBrowserBackend({ session, getShopVouchersRaw: actions.getShopVouchersRaw, cookiePath, diagnostics });
}

export async function startPreparedBridge({ backend, config, createServer = createBridgeServer, prepareTimeoutMs = 45000 }) {
  let bridge;
  try {
    await backend.prepare(prepareTimeoutMs);
    if (!backend.ready) throw new Error('not_ready');
    bridge = createServer({ backend, allowedPeers: config.allowedPeers });
    await new Promise((resolve, reject) => {
      bridge.server.once('error', reject);
      bridge.server.listen(config.port, config.host, resolve);
    });
    return bridge;
  } catch (error) {
    if (bridge) await bridge.close();
    else await backend.close();
    throw error;
  }
}

async function main() {
  const config = bridgeConfig();
  const backend = await loadBackend();
  // Caller deadlines never include cold preparation. No listener exists until
  // portal readiness passes; fail closed if dependency launch cannot drain.
  const startupStop = setTimeout(() => process.exit(1), 55000);
  let bridge;
  try { bridge = await startPreparedBridge({ backend, config }); }
  finally { clearTimeout(startupStop); }
  let closing = false;
  const stop = async () => {
    if (closing) return;
    closing = true;
    const hardStop = setTimeout(() => process.exit(1), 10000);
    try { await bridge.close(); } finally { clearTimeout(hardStop); }
  };
  process.once('SIGINT', () => { void stop().catch(() => { process.exitCode = 1; }); });
  process.once('SIGTERM', () => { void stop().catch(() => { process.exitCode = 1; }); });
  if (process.platform === 'win32') process.once('SIGBREAK', () => { void stop().catch(() => { process.exitCode = 1; }); });
  // Constant message only: no paths, request arguments, cookies or browser errors.
  process.stdout.write('[shopee-bridge] ready\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    process.stderr.write('[shopee-bridge] startup_failed\n');
    process.exitCode = 1;
  });
}
