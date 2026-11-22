import http from 'node:http';
import { isIP } from 'node:net';
import { performance } from 'node:perf_hooks';
import { BridgeError, BrowserQueue } from './queue.mjs';
import { positiveId } from './quote.mjs';

const ROUTES = new Set(['/health', '/api/generate_shortlink', '/api/shop_vouchers', '/api/product_quote']);
const LOOPBACK = ['127.0.0.1', '::1'];
const MAX_BODY = 8192;
// Existing sale-relay/shortener origins. Never navigate these input URLs here;
// they are only submitted to the fixed Affiliate GraphQL endpoint.
const SHORTLINK_HOSTS = new Set(['shopee.vn', 'www.shopee.vn', 's.shopee.vn', 'shp.ee', 'vn.shp.ee', 'shope.ee']);

function normalizedIp(value) {
  return value?.startsWith('::ffff:') ? value.slice(7) : value;
}

export function bridgeConfig(env = process.env) {
  const host = env.SHOPEE_BRIDGE_LISTEN_HOST || '127.0.0.1';
  const port = Number(env.SHOPEE_BRIDGE_PORT || 9224);
  const peers = (env.SHOPEE_BRIDGE_ALLOWED_PEERS || '').split(',').map(s => normalizedIp(s.trim())).filter(Boolean);
  if (!isIP(host) || !Number.isInteger(port) || port < 1 || port > 65535 || peers.some(ip => !isIP(ip))) {
    throw new BridgeError('invalid_configuration');
  }
  if (!LOOPBACK.includes(host) && peers.length === 0) throw new BridgeError('explicit_peers_required');
  return { host, port, allowedPeers: [...LOOPBACK, ...peers] };
}

function respond(res, status, body) {
  if (res.destroyed || res.writableEnded) return;
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}

function validateClient(req, allowedPeers) {
  if (!allowedPeers.has(normalizedIp(req.socket.remoteAddress))) throw new BridgeError('forbidden', 403);
  // CLI/WSL clients send no Origin. Reject all browser-origin API requests,
  // including local origins, and cross-site no-cors requests such as image tags.
  if (req.headers.origin || req.headers['sec-fetch-site'] === 'cross-site') throw new BridgeError('forbidden', 403);
  let host;
  try { host = new URL(`http://${req.headers.host}`).hostname.replace(/^\[|\]$/g, ''); } catch { throw new BridgeError('forbidden', 403); }
  if (host !== 'localhost' && !isIP(host)) throw new BridgeError('forbidden', 403);
}

async function readBody(req, remaining) {
  if (Number(req.headers['content-length'] || 0) > MAX_BODY) throw new BridgeError('body_too_large', 413);
  if (!(req.headers['content-type'] || '').toLowerCase().startsWith('application/json')) throw new BridgeError('invalid_content_type', 415);
  return new Promise((resolve, reject) => {
    let size = 0, text = '';
    const cleanup = () => { clearTimeout(timer); req.off('data', data); req.off('end', end); req.off('error', error); req.off('aborted', error); };
    const fail = reason => { cleanup(); reject(reason); req.resume(); };
    const data = chunk => {
      size += chunk.length;
      if (size > MAX_BODY) { fail(new BridgeError('body_too_large', 413)); return; }
      text += chunk.toString('utf8');
    };
    const end = () => {
      cleanup();
      try {
        const body = JSON.parse(text);
        if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error();
        resolve(body);
      } catch { reject(new BridgeError('invalid_json', 400)); }
    };
    const error = () => fail(new BridgeError('request_aborted', 400));
    const timer = setTimeout(() => fail(new BridgeError('timeout', 504)), Math.max(1, remaining()));
    req.on('data', data); req.once('end', end); req.once('error', error); req.once('aborted', error);
  });
}

function shopeeUrl(value) {
  let url;
  try { url = new URL(value); } catch { throw new BridgeError('invalid_url', 400); }
  if (typeof value !== 'string' || value.length > 4096 || !['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.port) {
    throw new BridgeError('invalid_url', 400);
  }
  if (!SHORTLINK_HOSTS.has(url.hostname)) throw new BridgeError('invalid_url', 400);
  // Do not turn an explicitly supplied off-origin redirect wrapper into a
  // trusted-looking short link. Ordinary shop/campaign/voucher query data stays.
  for (const key of ['url', 'origin_link', 'redirect_url', 'redirect_uri']) {
    const target = url.searchParams.get(key);
    if (!target) continue;
    let wrapped;
    try { wrapped = new URL(target, url.origin); } catch { throw new BridgeError('invalid_url', 400); }
    if (!['http:', 'https:'].includes(wrapped.protocol) || !SHORTLINK_HOSTS.has(wrapped.hostname) || wrapped.username || wrapped.password || wrapped.port) {
      throw new BridgeError('invalid_url', 400);
    }
  }
  return url.href;
}

function voucherRows(rows) {
  const fields = { code: 'voucher_code', discount_percentage: 'discount_percentage', discount_value: 'discount_value', discount_cap: 'discount_cap', min_spend: 'min_spend', end_time: 'end_time', percentage_used: 'percentage_used', is_claimed_before: 'is_claimed_before', shop_name: 'shop_name', icon_text: 'icon_text' };
  return rows.slice(0, 200).map(row => Object.fromEntries(Object.entries(fields).map(([out, key]) => {
    const value = row[key];
    return [out, typeof value === 'string' ? value.slice(0, 300) : typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value) ? value : null];
  })));
}

export function createBridgeServer({ backend, allowedPeers = LOOPBACK, maxTimeoutMs = 20000, queue = new BrowserQueue() }) {
  const peers = new Set(allowedPeers.map(normalizedIp));
  const cache = new Map();
  const server = http.createServer(async (req, res) => {
    const received = performance.now();
    const controller = new AbortController();
    const disconnected = () => { if (!res.writableEnded) controller.abort(); };
    res.once('close', disconnected);
    try {
      validateClient(req, peers);
      if (!req.url || req.url.length > 8192) throw new BridgeError('invalid_request', 400);
      const url = new URL(req.url, 'http://localhost');
      if (!ROUTES.has(url.pathname)) throw new BridgeError('not_found', 404);
      if (!['GET', 'POST'].includes(req.method) || req.method === 'POST' && url.pathname !== '/api/generate_shortlink') {
        throw new BridgeError('method_not_allowed', 405);
      }
      const requested = url.searchParams.get('timeout_ms');
      const timeout = requested === null ? maxTimeoutMs : Number(requested);
      if (!Number.isInteger(timeout) || timeout < 1 || timeout > maxTimeoutMs) throw new BridgeError('invalid_timeout', 400);
      const remaining = () => Math.max(0, received + timeout - performance.now());
      const run = task => queue.run(task, remaining(), controller.signal);
      if (url.pathname === '/health') {
        respond(res, 200, { status: 'ok', server: 'shopee-mcp', version: '0.3.0', implementation: 'toolsauto', quote_schema: 1 });
      } else if (url.pathname === '/api/product_quote') {
        const shopId = positiveId(url.searchParams.get('shop_id'));
        const itemId = positiveId(url.searchParams.get('item_id'));
        if (!shopId || !itemId) throw new BridgeError('invalid_identity', 400);
        const quote = await run(job => backend.quote({ shopId, itemId }, job));
        respond(res, 200, { success: true, quote });
      } else if (url.pathname === '/api/generate_shortlink') {
        const body = req.method === 'POST' ? await readBody(req, remaining) : {};
        const target = shopeeUrl(body.url ?? url.searchParams.get('url'));
        const subId = body.sub_id ?? url.searchParams.get('sub_id') ?? 'AUTOSALE';
        if (typeof subId !== 'string' || !/^[A-Za-z0-9_.+\-]{1,100}$/.test(subId)) throw new BridgeError('invalid_sub_id', 400);
        const short = await run(job => backend.shortlink({ url: target, subId }, job));
        respond(res, 200, { success: true, short_link: short, data: { data: { batchCustomLink: [{ shortLink: short }] } } });
      } else {
        const shopId = positiveId(url.searchParams.get('shop_id'));
        if (!shopId) throw new BridgeError('invalid_identity', 400);
        const cached = cache.get(shopId);
        if (cached && Date.now() - cached.at < 3600000) {
          respond(res, 200, { shop_id: shopId, cached: true, count: cached.rows.length, vouchers: cached.rows });
        } else {
          const rows = voucherRows(await run(job => backend.vouchers(shopId, job)));
          if (cache.size >= 500) cache.delete(cache.keys().next().value);
          cache.set(shopId, { at: Date.now(), rows });
          respond(res, 200, { shop_id: shopId, cached: false, count: rows.length, vouchers: rows });
        }
      }
    } catch (error) {
      const safe = error instanceof BridgeError ? error : new BridgeError('bridge_error');
      respond(res, safe.status, { success: false, error: safe.code });
    } finally {
      res.off('close', disconnected);
    }
  });
  server.requestTimeout = 25000;
  server.headersTimeout = 10000;
  return { server, async close() { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); await queue.close(); await backend.close(); } };
}
