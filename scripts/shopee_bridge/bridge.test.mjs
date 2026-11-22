import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { get } from 'node:http';
import { BrowserQueue } from './queue.mjs';
import { bridgeConfig, createBridgeServer } from './server.mjs';

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

async function fixture(t, overrides = {}, options = {}) {
  const calls = [];
  const backend = {
    async quote(request) { calls.push(['quote', request]); return { item_id: request.itemId, shop_id: request.shopId }; },
    async shortlink(request) { calls.push(['shortlink', request]); return 'https://s.shopee.vn/test'; },
    async vouchers(shop) { calls.push(['vouchers', shop]); return [{ voucher_code: 'TEST', discount_value: 100, internal_secret: 'must-not-export' }]; },
    async close() {},
    ...overrides,
  };
  const bridge = createBridgeServer({ backend, ...options });
  bridge.server.listen(0, '127.0.0.1');
  await once(bridge.server, 'listening');
  t.after(() => bridge.close());
  const base = `http://127.0.0.1:${bridge.server.address().port}`;
  return { calls, base, backend, bridge };
}

test('bind defaults loopback; non-loopback requires exact explicit peers', () => {
  assert.equal(bridgeConfig({}).host, '127.0.0.1');
  assert.throws(() => bridgeConfig({ SHOPEE_BRIDGE_LISTEN_HOST: '0.0.0.0' }), /explicit_peers_required/);
  const c = bridgeConfig({ SHOPEE_BRIDGE_LISTEN_HOST: '0.0.0.0', SHOPEE_BRIDGE_ALLOWED_PEERS: '192.168.112.133' });
  assert.ok(c.allowedPeers.includes('192.168.112.133'));
  for (const peer of ['0.0.0.0/0', '*.local', '192.168.112.0/24']) {
    assert.throws(() => bridgeConfig({ SHOPEE_BRIDGE_ALLOWED_PEERS: peer }), /invalid_configuration/);
  }
});

test('health preserves legacy fields without browser work or CORS grant', async t => {
  const { base, calls } = await fixture(t);
  const response = await fetch(base + '/health');
  const data = await response.json();
  assert.equal(response.status, 200);
  assert.equal(data.status, 'ok');
  assert.equal(data.server, 'shopee-mcp');
  assert.equal(data.version, '0.3.0');
  assert.equal(response.headers.get('access-control-allow-origin'), null);
  assert.equal(calls.length, 0);
});

test('quote endpoint validates identities and carries exact IDs', async t => {
  const { base, calls } = await fixture(t);
  const response = await fetch(base + '/api/product_quote?shop_id=12&item_id=34&timeout_ms=200');
  assert.deepEqual(await response.json(), { success: true, quote: { shop_id: '12', item_id: '34' } });
  assert.deepEqual(calls, [['quote', { shopId: '12', itemId: '34' }]]);
  for (const query of ['shop_id=0&item_id=3', 'shop_id=1&item_id=-2', 'shop_id=1&item_id=1e9']) {
    assert.equal((await fetch(base + '/api/product_quote?' + query)).status, 400);
  }
});

test('GET and POST shortlink preserve URL and sub_id contracts', async t => {
  const { base, calls } = await fixture(t);
  const url = 'https://shopee.vn/product/12/34';
  const query = new URLSearchParams({ url, sub_id: 'customer+r1+s2' });
  const get = await fetch(base + '/api/generate_shortlink?' + query);
  assert.equal((await get.json()).short_link, 'https://s.shopee.vn/test');
  const post = await fetch(base + '/api/generate_shortlink', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, sub_id: 'test-2' }) });
  const result = await post.json();
  assert.equal(result.success, true);
  assert.equal(result.data.data.batchCustomLink[0].shortLink, result.short_link);
  assert.deepEqual(calls, [['shortlink', { url, subId: 'customer+r1+s2' }], ['shortlink', { url, subId: 'test-2' }]]);
});

test('shortlink rejects arbitrary origins and malformed URLs before browser', async t => {
  const { base, calls } = await fixture(t);
  for (const url of ['http://127.0.0.1/private', 'https://shopee.vn.evil.test/product/1/2', 'https://user:pass@shopee.vn/product/1/2', 'file:///tmp/data', 'https://shopee.vn:444/product/1/2', 'https://shopee.vn/redirect?url=http://localhost']) {
    const response = await fetch(base + '/api/generate_shortlink?' + new URLSearchParams({ url }));
    assert.equal(response.status, 400);
  }
  assert.equal(calls.length, 0);
});

test('shortlink preserves supported shop, voucher, campaign and short Shopee pages', async t => {
  const { base, calls } = await fixture(t);
  const urls = [
    'https://shopee.vn/shop/562665255',
    'https://shopee.vn/voucher/details?evcode=TUVUQVBBUklHRE9DVDIyMTE%3D',
    'https://shopee.vn/m/goi-ShopeeVIP',
    'https://www.shopee.vn/m/test-campaign',
    'https://s.shopee.vn/7Ad4vEC2TY',
    'https://shp.ee/test',
    'https://vn.shp.ee/test',
    'https://shope.ee/test',
  ];
  for (const url of urls) {
    const response = await fetch(base + '/api/generate_shortlink?' + new URLSearchParams({ url, sub_id: 'VOUCHERS' }));
    assert.equal(response.status, 200, url);
    assert.equal((await response.json()).short_link, 'https://s.shopee.vn/test');
  }
  assert.deepEqual(calls.map(call => call[1]), urls.map(url => ({ url, subId: 'VOUCHERS' })));
  for (const url of ['https://campaign.shopee.vn.evil.test/m/sale', 'https://attacker-shopee.vn/shop/123', 'https://unknown.shopee.vn/shop/123']) {
    assert.equal((await fetch(base + '/api/generate_shortlink?' + new URLSearchParams({ url }))).status, 400);
  }
  assert.equal(calls.length, urls.length);
});

test('browser origins, cross-site requests and rebinding hostnames are denied', async t => {
  const { base, calls } = await fixture(t);
  for (const headers of [{ Origin: 'https://evil.test' }, { Origin: 'http://localhost' }, { 'Sec-Fetch-Site': 'cross-site' }, { Host: 'evil.test' }]) {
    // Native http sends the exact browser/rebinding headers; fetch can rewrite
    // Sec-Fetch-* / Host as part of its own client policy.
    const status = await new Promise((resolve, reject) => {
      get(base + '/health', { headers }, response => { response.resume(); resolve(response.statusCode); }).on('error', reject);
    });
    assert.equal(status, 403, JSON.stringify(headers));
  }
  assert.equal(calls.length, 0);
});

test('unlisted peers cannot use health or browser routes', async t => {
  const { base, calls } = await fixture(t, {}, { allowedPeers: [] });
  assert.equal((await fetch(base + '/health')).status, 403);
  assert.equal((await fetch(base + '/api/product_quote?shop_id=1&item_id=2')).status, 403);
  assert.equal(calls.length, 0);
});

test('voucher field allowlist and one-hour cache preserve contract', async t => {
  const { base, calls } = await fixture(t);
  const first = await (await fetch(base + '/api/shop_vouchers?shop_id=12')).json();
  const second = await (await fetch(base + '/api/shop_vouchers?shop_id=12')).json();
  assert.equal(first.cached, false);
  assert.equal(second.cached, true);
  assert.equal(first.count, 1);
  assert.equal(first.vouchers[0].code, 'TEST');
  assert.equal(JSON.stringify(first).includes('must-not-export'), false);
  assert.equal(calls.length, 1);
});

test('request body and timeout parameters are bounded', async t => {
  const { base, calls } = await fixture(t);
  const post = (body, type = 'application/json') => fetch(base + '/api/generate_shortlink', { method: 'POST', headers: { 'Content-Type': type }, body });
  assert.equal((await post('{')).status, 400);
  assert.equal((await post('null')).status, 400);
  assert.equal((await post('{}', 'text/plain')).status, 415);
  assert.equal((await post('x'.repeat(9000))).status, 413);
  for (const timeout of ['0', '-1', 'Infinity', '30000', '1.5']) {
    assert.equal((await fetch(base + '/api/product_quote?shop_id=1&item_id=2&timeout_ms=' + timeout)).status, 400);
  }
  assert.equal(calls.length, 0);
});

test('unexpected dependency errors never disclose transport messages', async t => {
  const { base } = await fixture(t, { async quote() { throw new Error('Authorization: secret-cookie-value'); } });
  const response = await fetch(base + '/api/product_quote?shop_id=1&item_id=2');
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { success: false, error: 'bridge_error' });
});

test('expired running job keeps queue until old work has drained', async () => {
  const queue = new BrowserQueue();
  let release, oldFinished = false, nextStarted = false;
  const gate = new Promise(resolve => { release = resolve; });
  const first = queue.run(async () => { await gate; oldFinished = true; }, 20);
  await assert.rejects(first, /timeout/);
  const second = queue.run(async () => { assert.equal(oldFinished, true); nextStarted = true; return 2; }, 200);
  await wait(15);
  assert.equal(nextStarted, false);
  release();
  assert.equal(await second, 2);
  await queue.close();
});

test('queue wait counts in caller deadline and expired jobs never run', async () => {
  const queue = new BrowserQueue();
  let release, expiredRan = false;
  const gate = new Promise(resolve => { release = resolve; });
  const first = queue.run(async () => { await gate; }, 200);
  const second = queue.run(async () => { expiredRan = true; }, 15);
  await assert.rejects(second, /timeout/);
  release();
  await first;
  await queue.close();
  assert.equal(expiredRan, false);
});

test('HTTP timeout aborts active work and the next browser route waits', async t => {
  let aborted = false;
  const { base } = await fixture(t, { async quote(_request, job) {
    await new Promise(resolve => job.signal.addEventListener('abort', resolve, { once: true }));
    await wait(15);
    aborted = true;
  }, async shortlink() { assert.equal(aborted, true); return 'https://s.shopee.vn/test'; } });
  const response = await fetch(base + '/api/product_quote?shop_id=1&item_id=2&timeout_ms=20');
  assert.equal(response.status, 504);
  const next = await fetch(base + '/api/generate_shortlink?' + new URLSearchParams({ url: 'https://shopee.vn/product/1/2' }));
  assert.equal(next.status, 200);
});
