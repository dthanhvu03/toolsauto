import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { createBrowserBackend } from './browser.mjs';
import { BrowserQueue } from './queue.mjs';
import { startPreparedBridge } from './index.mjs';

function rawQuote() {
  return { code: 0, data: { item_id: '34', period_start_time: 0, period_end_time: 0,
    batch_item_for_item_card_full: { itemid: '34', shopid: '12', name: 'Test public name', currency: 'VND', status: 1, item_status: 'normal', price: '10000000000', price_min: '10000000000', price_max: '10000000000' },
    commission_rate_detail: { seller_commission_detail: { social_media_default_exist_commission_rate: 0 }, shopee_commission_detail: { social_media_shop_base_exist_commission_rate: 7000 }, channel_cap: { exist_user: { social_media_cap: '4000000000' } } },
  } };
}

function fakeBrowser({ response = rawQuote(), status = 200, origin = 'https://affiliate.shopee.vn', fetchError = null, diagnostics } = {}) {
  const calls = [];
  let pageClosed = 0, contextsClosed = 0, currentUrl = 'about:blank', pageIsClosed = false;
  const page = {
    url() { return currentUrl; },
    isClosed() { return pageIsClosed; },
    on(event, listener) { if (event === 'framenavigated') this.onNavigation = listener; },
    mainFrame() { return this; },
    async goto(url, options) { currentUrl = url; calls.push(['goto', url, options]); },
    async waitForLoadState(state, options) { calls.push(['load_state', state, options]); },
    async waitForTimeout(ms) { calls.push(['settle', ms]); },
    async close() { pageClosed += 1; pageIsClosed = true; },
    async evaluate(fn, args) {
      const sandbox = { args, location: { origin, pathname: '/offer/product_offer' }, document: { cookie: 'csrftoken=fixture-secret', readyState: 'complete' }, AbortController, setTimeout, clearTimeout, URLSearchParams, TextDecoder,
        fetch: async (url, options) => {
          calls.push(['fetch', url, options]);
          if (fetchError) throw new Error(fetchError);
          return new Response(typeof response === 'string' ? response : JSON.stringify(response), { status });
        },
      };
      return vm.runInNewContext(`(${fn.toString()})(args)`, sandbox);
    },
  };
  const context = { pages() { return []; }, async newPage() { calls.push(['new_page']); pageIsClosed = false; currentUrl = 'about:blank'; return page; } };
  const session = { async getContext() { return context; }, async closeContext() { contextsClosed += 1; } };
  const backend = createBrowserBackend({ session, async getShopVouchersRaw() { return []; }, diagnostics });
  const job = { signal: new AbortController().signal, remaining: () => 20000 };
  return { backend, page, context, session, job, calls, closed: () => ({ page: pageClosed, context: contextsClosed }) };
}

test('real page callback fetches fixed detail endpoint with in-page auth; DTO excludes auth', async () => {
  const f = fakeBrowser();
  const dto = await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  const fetch = f.calls.find(c => c[0] === 'fetch');
  assert.equal(fetch[1], '/api/v3/offer/product?item_id=34');
  assert.equal(fetch[2].credentials, 'include');
  assert.equal(fetch[2].headers['X-CSRFToken'], 'fixture-secret');
  assert.equal(dto.seller_rate_raw, '0');
  assert.equal(JSON.stringify(dto).includes('fixture-secret'), false);
  assert.deepEqual(f.closed(), { page: 0, context: 0 });
  await f.backend.close();
  assert.equal(f.closed().page, 1);
  assert.equal(f.closed().context, 1);
});

test('real page callback builds known shortlink GraphQL with original URL and exact subId', async () => {
  const f = fakeBrowser({ response: { data: { batchCustomLink: [{ shortLink: 'https://s.shopee.vn/test' }] } } });
  const url = 'https://shopee.vn/product/12/34';
  assert.equal(await f.backend.shortlink({ url, subId: 'customer+r1+s2' }, f.job), 'https://s.shopee.vn/test');
  const fetch = f.calls.find(c => c[0] === 'fetch');
  const body = JSON.parse(fetch[2].body);
  assert.equal(fetch[1], '/api/v3/gql?q=batchCustomLink');
  assert.equal(body.variables.linkParams[0].originalLink, url);
  assert.equal(body.variables.linkParams[0].advancedLinkParams.subId1, 'customer+r1+s2');
  assert.equal(f.closed().page, 0);
  await f.backend.close();
});

test('auth redirect and auth HTTP errors fail closed, all owned pages close', async () => {
  for (const options of [{ origin: 'https://shopee.vn' }, { status: 403 }, { response: { error: 90309999 } }]) {
    const f = fakeBrowser(options);
    await assert.rejects(f.backend.quote({ shopId: '12', itemId: '34' }, f.job), /auth_required/);
    assert.equal(f.closed().page, 1);
  }
});

test('response byte limit, invalid JSON and transport failures do not export raw text', async () => {
  for (const [options, code] of [[{ response: 'x'.repeat(1024 * 1024 + 1) }, 'upstream_too_large'], [{ response: 'private-header: never-export' }, 'invalid_payload'], [{ fetchError: 'Authorization secret-value' }, 'upstream_error']]) {
    const f = fakeBrowser(options);
    await assert.rejects(f.backend.quote({ shopId: '12', itemId: '34' }, f.job), error => error.code === code && !error.message.includes('secret'));
    assert.equal(f.closed().page, 1);
  }
});

test('shortlink response must have the fixed short Shopee origin', async () => {
  const f = fakeBrowser({ response: { data: { batchCustomLink: [{ shortLink: 'https://evil.test/a' }] } } });
  await assert.rejects(f.backend.shortlink({ url: 'https://shopee.vn/product/12/34', subId: 'test' }, f.job), /shortlink_failed/);
  assert.equal(f.closed().page, 1);
});

test('active timeout closes singleton context and drains cleanup before another browser route', async () => {
  const queue = new BrowserQueue();
  let rejectEvaluation, releaseClose, closing = false, cleanupDone = false, nextRan = false;
  const closeGate = new Promise(resolve => { releaseClose = resolve; });
  const f = fakeBrowser();
  await f.backend.prepare(45000);
  const evaluation = f.page.evaluate;
  f.page.evaluate = (fn, args) => args ? new Promise((_resolve, reject) => { rejectEvaluation = reject; }) : evaluation(fn, args);
  f.session.closeContext = async () => {
    closing = true;
    rejectEvaluation(new Error('context closed'));
    await closeGate;
    cleanupDone = true;
  };
  const first = queue.run(job => f.backend.quote({ shopId: '12', itemId: '34' }, job), 20);
  await assert.rejects(first, /timeout/);
  assert.equal(closing, true);
  const second = queue.run(async () => { assert.equal(cleanupDone, true); nextRan = true; }, 200);
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(nextRan, false);
  releaseClose();
  await second;
  await queue.close();
});

test('prepare starts false and repeated quotes reuse one ready portal page without navigation', async () => {
  const events = [];
  const f = fakeBrowser({ diagnostics: event => events.push(event) });
  assert.equal(f.backend.ready, false);
  await f.backend.prepare(45000);
  assert.equal(f.backend.ready, true);
  await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  assert.equal(f.calls.filter(call => call[0] === 'new_page').length, 1);
  assert.equal(f.calls.filter(call => call[0] === 'goto').length, 1);
  assert.equal(f.calls.filter(call => call[0] === 'fetch').length, 2);
  assert.equal(f.closed().page, 0);
  assert.ok(events.some(event => event.operation === 'prepare' && event.stage === 'portal_ready'));
  assert.equal(events.filter(event => event.stage === 'navigate_start').length, 1);
  for (const event of events) {
    assert.deepEqual(Object.keys(event).sort(), ['elapsed_ms', 'operation', 'request', 'stage']);
    assert.ok(Number.isFinite(event.elapsed_ms));
    assert.equal(JSON.stringify(event).includes('fixture-secret'), false);
    assert.equal(JSON.stringify(event).includes('shopee.vn'), false);
  }
  await f.backend.close();
  assert.equal(f.backend.ready, false);
  assert.equal(f.closed().page, 1);
});

test('failed prepare never marks ready and owned page is cleaned', async () => {
  const f = fakeBrowser({ origin: 'https://shopee.vn' });
  await assert.rejects(f.backend.prepare(45000), /auth_required/);
  assert.equal(f.backend.ready, false);
  assert.equal(f.closed().page, 1);
  await f.backend.close();
});

test('prepare adopts initial persistent page, navigates only fixed portal, and never opens new target', async () => {
  const f = fakeBrowser();
  await f.page.goto('https://shopee.vn/saved-profile-page');
  f.calls.length = 0;
  const closedPage = { isClosed() { return true; } };
  f.context.pages = () => [closedPage, f.page];
  f.context.newPage = async () => { throw new Error('must adopt persistent page'); };
  await f.backend.prepare(45000);
  assert.equal(f.backend.ready, true);
  assert.deepEqual(f.calls.filter(call => call[0] === 'goto').map(call => call.slice(0, 2)), [['goto', 'https://affiliate.shopee.vn/offer/product_offer']]);
  assert.equal(f.calls.some(call => call[0] === 'fetch'), false);
  await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  assert.equal(f.calls.filter(call => call[0] === 'goto').length, 1);
  assert.equal(f.calls.some(call => call[0] === 'new_page'), false);
  await f.backend.close();
  assert.equal(f.closed().page, 1);
  assert.equal(f.closed().context, 1);
});

test('timeout while context is being created retains queue until creation and close drain', async () => {
  const queue = new BrowserQueue();
  let releaseCreate, closeStarted = false, releaseClose, nextRan = false;
  const createGate = new Promise(resolve => { releaseCreate = resolve; });
  const closeGate = new Promise(resolve => { releaseClose = resolve; });
  const f = fakeBrowser();
  f.session.getContext = async () => { await createGate; return { pages() { return []; }, async newPage() { throw new Error('expired task must not create page'); } }; };
  f.session.closeContext = async () => { closeStarted = true; await createGate; await closeGate; };
  const first = queue.run(job => f.backend.quote({ shopId: '12', itemId: '34' }, job), 20);
  await assert.rejects(first, /timeout/);
  assert.equal(closeStarted, true);
  const next = queue.run(async () => { nextRan = true; }, 500);
  releaseCreate();
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(nextRan, false);
  releaseClose();
  await next;
  await queue.close();
  assert.equal(f.backend.ready, false);
});

test('prepare timeout is bounded and does not release ownership before launch drain', async () => {
  let releaseCreate;
  const createGate = new Promise(resolve => { releaseCreate = resolve; });
  const f = fakeBrowser();
  f.session.getContext = async () => { await createGate; return {}; };
  f.session.closeContext = async () => { await createGate; };
  await assert.rejects(f.backend.prepare(15), /timeout/);
  assert.equal(f.backend.ready, false);
  await assert.rejects(f.backend.prepare(15), /busy/);
  releaseCreate();
  await f.backend.close();
});

test('prepare startup budget accepts bounded explicit test values and rejects over 45 seconds', async () => {
  const f = fakeBrowser();
  for (const invalid of [0, -1, 45001, Infinity, 1.5]) {
    await assert.rejects(f.backend.prepare(invalid), /invalid_timeout/);
  }
  await f.backend.prepare(45000);
  assert.equal(f.backend.ready, true);
  await f.backend.close();
});

test('listener creation is ordered after prepare; failure closes backend without listener', async () => {
  const events = [];
  const backend = { ready: false, async prepare(ms) { assert.equal(ms, 45000); events.push('prepare'); this.ready = true; }, async close() { events.push('close'); } };
  const bridge = { server: { once() {}, listen(_port, _host, resolve) { events.push('listen'); resolve(); } } };
  const result = await startPreparedBridge({ backend, config: { port: 9224, host: '127.0.0.1', allowedPeers: [] }, createServer() { events.push('create'); return bridge; } });
  assert.equal(result, bridge);
  assert.deepEqual(events, ['prepare', 'create', 'listen']);
  events.length = 0;
  backend.prepare = async () => { events.push('prepare'); throw new Error('test'); };
  await assert.rejects(startPreparedBridge({ backend, config: {}, createServer() { events.push('must-not-listen'); } }));
  assert.deepEqual(events, ['prepare', 'close']);
});


test('lifecycle B waits for DOM, network idle and settling before readiness or any portal fetch', async () => {
  const f = fakeBrowser();
  await f.backend.prepare(45000);
  const navigation = f.calls.find(call => call[0] === 'goto');
  assert.equal(navigation[2].waitUntil, 'domcontentloaded');
  assert.ok(navigation[2].timeout > 0 && navigation[2].timeout <= 25000);
  assert.deepEqual(f.calls.filter(call => call[0] === 'load_state').map(call => call.slice(1)), [['networkidle', { timeout: 8000 }]]);
  assert.equal(f.calls.some(call => call[0] === 'fetch'), false);
  assert.equal(f.backend.ready, true);
  const preparedCallCount = f.calls.length;
  await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  const requestCalls = f.calls.slice(preparedCallCount);
  assert.deepEqual(requestCalls.map(call => call[0]), ['fetch']);
  await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  assert.equal(f.calls.filter(call => call[0] === 'load_state').length, 1);
  assert.equal(f.calls.filter(call => call[0] === 'settle').length, 1);
  assert.ok(f.calls.findIndex(call => call[0] === 'load_state') < f.calls.findIndex(call => call[0] === 'settle'));
  assert.ok(f.calls.findIndex(call => call[0] === 'settle') < f.calls.findIndex(call => call[0] === 'fetch'));
  assert.equal(f.calls.filter(call => call[0] === 'goto').length, 1);
  for (const delay of f.calls.filter(call => call[0] === 'settle')) assert.ok(delay[1] >= 2500 && delay[1] < 4000);
  await f.backend.close();
});

test('lifecycle B also settles a pre-existing portal tab and shortlink without navigating', async () => {
  const f = fakeBrowser({ response: { data: { batchCustomLink: [{ shortLink: 'https://s.shopee.vn/test' }] } } });
  await f.page.goto('https://affiliate.shopee.vn/offer/product_offer');
  f.context.pages = () => [f.page];
  f.calls.length = 0;
  await f.backend.shortlink({ url: 'https://shopee.vn/product/12/34', subId: 'test' }, f.job);
  assert.deepEqual(f.calls.map(call => call[0]), ['load_state', 'settle', 'fetch']);
  assert.equal(f.calls[0][2].timeout, 8000);
  assert.ok(f.calls[1][1] >= 2500 && f.calls[1][1] < 4000);
  await f.backend.close();
});

test('network idle timeout still settles but transport failure never reaches portal fetch', async () => {
  const timeout = Object.assign(new Error('private browser message'), { name: 'TimeoutError' });
  const f = fakeBrowser();
  f.page.waitForLoadState = async () => { throw timeout; };
  await f.backend.quote({ shopId: '12', itemId: '34' }, f.job);
  assert.deepEqual(f.calls.filter(call => ['settle', 'fetch'].includes(call[0])).map(call => call[0]), ['settle', 'fetch']);
  await f.backend.close();
  const failed = fakeBrowser();
  failed.page.waitForLoadState = async () => { throw new Error('private browser message'); };
  await assert.rejects(failed.backend.quote({ shopId: '12', itemId: '34' }, failed.job), /session_or_transport_error/);
  assert.equal(failed.calls.some(call => call[0] === 'fetch'), false);
  assert.equal(failed.closed().page, 1);
  await failed.backend.close();
});

test('expired readiness budget never fetches or publishes ready after settling', async () => {
  const f = fakeBrowser();
  let left = 5000;
  const job = { signal: new AbortController().signal, remaining: () => left };
  f.page.waitForTimeout = async ms => { f.calls.push(['settle', ms]); left = 0; };
  await assert.rejects(f.backend.quote({ shopId: '12', itemId: '34' }, job), /timeout/);
  assert.equal(f.calls.find(call => call[0] === 'load_state')[2].timeout, 5000);
  assert.ok(f.calls.find(call => call[0] === 'settle')[1] >= 2500);
  assert.equal(f.calls.some(call => call[0] === 'fetch'), false);
  assert.equal(f.backend.ready, false);
  assert.equal(f.closed().page, 1);
  await f.backend.close();
});


test('navigation invalidates settled page and an insufficient budget never shortens lifecycle B', async () => {
  const f = fakeBrowser();
  await f.backend.prepare(45000);
  f.calls.length = 0;
  f.page.onNavigation(f.page.mainFrame());
  const job = { signal: new AbortController().signal, remaining: () => 1000 };
  await assert.rejects(f.backend.quote({ shopId: '12', itemId: '34' }, job), /timeout/);
  assert.equal(f.calls.filter(call => call[0] === 'load_state').length, 1);
  assert.equal(f.calls.some(call => call[0] === 'settle'), false);
  assert.equal(f.calls.some(call => call[0] === 'fetch'), false);
  assert.equal(f.backend.ready, false);
  await f.backend.close();
});


test('main-frame navigation during settling or validation never caches a fresh document as ready', async () => {
  for (const stage of ['settle', 'validation']) {
    const f = fakeBrowser();
    if (stage === 'settle') {
      f.page.waitForTimeout = async () => { f.page.onNavigation(f.page.mainFrame()); };
    } else {
      const evaluate = f.page.evaluate;
      f.page.evaluate = async (fn, args) => {
        const result = await evaluate(fn, args);
        if (!args) f.page.onNavigation(f.page.mainFrame());
        return result;
      };
    }
    await assert.rejects(f.backend.prepare(45000), /session_or_transport_error/);
    assert.equal(f.backend.ready, false);
    assert.equal(f.calls.some(call => call[0] === 'fetch'), false);
    assert.equal(f.closed().page, 1);
    await f.backend.close();
  }
});
