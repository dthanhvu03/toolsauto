import { readFile } from 'node:fs/promises';
import { performance } from 'node:perf_hooks';
import { BridgeError } from './queue.mjs';
import { sanitizeQuote } from './quote.mjs';

const PORTAL = 'https://affiliate.shopee.vn';

function check(job) {
  if (job.signal.aborted || job.remaining() <= 0) throw new BridgeError('timeout', 504);
}

export function createBrowserBackend({ session, getShopVouchersRaw, cookiePath, diagnostics }) {
  let portalPage, portalContext, ready = false, sequence = 0;
  const active = new Set();

  function measured(job, operation) {
    const started = performance.now();
    const request = ++sequence;
    return { ...job, mark(stage) {
      // Only fixed operation/stage names and durations reach the callback.
      // Observer failures must not affect browser work or leak exception text.
      try { diagnostics?.({ operation, request, stage, elapsed_ms: Math.round(performance.now() - started) }); } catch {}
    } };
  }

  async function context(job) {
    check(job);
    job.mark('get_context_start');
    const ctx = await session.getContext();
    job.mark('get_context_done');
    check(job);
    if (cookiePath) {
      let cookies;
      try {
        cookies = JSON.parse(await readFile(cookiePath, 'utf8'));
      } catch (error) {
        if (error.code !== 'ENOENT') throw new BridgeError('session_unavailable', 503);
      }
      if (cookies) {
        if (typeof cookies !== 'object' || Array.isArray(cookies)) throw new BridgeError('session_unavailable', 503);
        const list = Object.entries(cookies).map(([name, value]) => {
          if (typeof value !== 'string' || value.length > 8192) throw new BridgeError('session_unavailable', 503);
          return { name, value, domain: '.shopee.vn', path: '/', secure: true };
        });
        await ctx.addCookies(list);
      }
    }
    job.mark('cookies_sync_done');
    check(job);
    return ctx;
  }

  async function executeOwned(job, task, needsPage) {
    let page;
    let cancellation;
    const cancel = () => {
      ready = false;
      portalPage = undefined;
      portalContext = undefined;
      job.mark('abort');
      cancellation ??= session.closeContext().catch(() => {});
    };
    job.signal.addEventListener('abort', cancel, { once: true });
    try {
      const ctx = await context(job);
      if (needsPage) {
        job.mark('page_start');
        if (!portalPage || portalContext !== ctx || portalPage.isClosed()) {
          // Persistent profiles can already provide their initial page. Adopt
          // it like the proven POC instead of opening another Chromium target;
          // portalReady navigates any non-portal URL before reading its content.
          portalPage = ctx.pages().find(existing => !existing.isClosed()) ?? await ctx.newPage();
          portalContext = ctx;
        }
        page = portalPage;
        job.mark('page_ready');
      }
      check(job);
      return await task(page);
    } catch (error) {
      ready = false;
      if (page) {
        if (portalPage === page) { portalPage = undefined; portalContext = undefined; }
        await page.close().catch(() => {});
      }
      if (error instanceof BridgeError) throw error;
      if (job.signal.aborted || error?.name === 'TimeoutError') throw new BridgeError('timeout', 504);
      throw new BridgeError('session_or_transport_error', 502);
    } finally {
      job.signal.removeEventListener('abort', cancel);
      // Keep the outer queue occupied until cancellation has really closed the
      // context. A timed-out evaluation must not overlap the next operation.
      if (cancellation) await cancellation;
      job.mark('cleanup_done');
    }
  }

  function owned(job, operation, task, needsPage = true) {
    const measuredJob = measured(job, operation);
    measuredJob.mark('start');
    const taskPromise = executeOwned(measuredJob, page => task(page, measuredJob), needsPage);
    active.add(taskPromise);
    taskPromise.then(() => active.delete(taskPromise), () => active.delete(taskPromise));
    return taskPromise;
  }

  async function portalReady(page, job) {
    check(job);
    let validUrl = false;
    try { const url = new URL(page.url()); validUrl = url.origin === PORTAL && url.pathname.startsWith('/offer/'); } catch {}
    if (!validUrl) {
      job.mark('navigate_start');
      await page.goto(`${PORTAL}/offer/product_offer`, {
        waitUntil: 'domcontentloaded', timeout: Math.max(1, Math.floor(job.remaining())),
      });
      await page.waitForLoadState('networkidle', { timeout: Math.max(1, Math.min(2500, Math.floor(job.remaining()))) }).catch(() => {});
      job.mark('navigate_done');
    }
    check(job);
    const validPage = await page.evaluate(() => location.origin === 'https://affiliate.shopee.vn'
      && location.pathname.startsWith('/offer/') && ['interactive', 'complete'].includes(document.readyState));
    if (!validPage) throw new BridgeError('auth_required');
    job.mark('portal_ready');
  }

  async function portalRequest(page, job, request) {
    await portalReady(page, job);
    check(job);
    job.mark('evaluate_start');
    await page.waitForTimeout(Math.min(250 + Math.random() * 250, job.remaining()));
    check(job);
    const result = await page.evaluate(async ({ request, timeout }) => {
      if (location.origin !== 'https://affiliate.shopee.vn' || /\/(?:auth|login|verify)(?:\/|$)/.test(location.pathname)) {
        return { error: 'auth_required' };
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try {
        const csrf = (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';
        const options = { credentials: 'include', signal: controller.signal, headers: { 'X-CSRFToken': csrf } };
        let endpoint;
        if (request.kind === 'quote') {
          endpoint = '/api/v3/offer/product?' + new URLSearchParams({ item_id: request.itemId });
        } else {
          endpoint = '/api/v3/gql?q=batchCustomLink';
          options.method = 'POST';
          options.headers['Content-Type'] = 'application/json';
          options.body = JSON.stringify({
            operationName: 'batchGetCustomLink',
            query: 'query batchGetCustomLink($linkParams: [CustomLinkParam!], $sourceCaller: SourceCaller){batchCustomLink(linkParams: $linkParams, sourceCaller: $sourceCaller){shortLink longLink failCode}}',
            variables: { linkParams: [{ originalLink: request.url, advancedLinkParams: { subId1: request.subId } }], sourceCaller: 'CUSTOM_LINK_CALLER' },
          });
        }
        const response = await fetch(endpoint, options);
        if ([401, 403].includes(response.status)) return { error: 'auth_required' };
        if (!response.ok) return { error: 'upstream_error' };
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let text = '', size = 0;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 1024 * 1024) {
            await reader.cancel();
            return { error: 'upstream_too_large' };
          }
          text += decoder.decode(value, { stream: true });
        }
        text += decoder.decode();
        let body;
        try { body = JSON.parse(text); } catch { return { error: 'invalid_payload' }; }
        if (body?.error === 90309999 || body?.code === 90309999) return { error: 'auth_required' };
        return { body };
      } catch (error) {
        return { error: error?.name === 'AbortError' ? 'timeout' : 'upstream_error' };
      } finally {
        clearTimeout(timer);
      }
    }, { request, timeout: Math.max(1, Math.floor(job.remaining())) });
    job.mark('evaluate_done');
    check(job);
    if (result.error) throw new BridgeError(result.error, result.error === 'timeout' ? 504 : 502);
    return result.body;
  }

  return {
    get ready() { return ready; },
    async prepare(timeoutMs = 45000) {
      if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 45000) throw new BridgeError('invalid_timeout', 400);
      if (active.size) throw new BridgeError('busy', 503);
      ready = false;
      const controller = new AbortController();
      const deadline = performance.now() + timeoutMs;
      let timer;
      const expired = new Promise((_resolve, reject) => {
        timer = setTimeout(() => { controller.abort(); reject(new BridgeError('timeout', 504)); }, timeoutMs);
      });
      const preparation = owned({ signal: controller.signal, remaining: () => Math.max(0, deadline - performance.now()) }, 'prepare', async (page, job) => {
        await portalReady(page, job);
        check(job);
        ready = true;
      });
      try { await Promise.race([preparation, expired]); } finally { clearTimeout(timer); }
    },
    async quote(request, job) {
      return owned(job, 'quote', async (page, currentJob) => {
        const body = await portalRequest(page, currentJob, { ...request, kind: 'quote' });
        if (body?.code !== 0) throw new BridgeError('upstream_error');
        return sanitizeQuote(body.data, request);
      });
    },
    async shortlink(request, job) {
      return owned(job, 'shortlink', async (page, currentJob) => {
        const body = await portalRequest(page, currentJob, { ...request, kind: 'shortlink' });
        const row = body?.data?.batchCustomLink?.[0];
        if (typeof row?.shortLink !== 'string' || row.shortLink.length > 2048) throw new BridgeError('shortlink_failed');
        let parsed;
        try { parsed = new URL(row.shortLink); } catch { throw new BridgeError('shortlink_failed'); }
        if (parsed.protocol !== 'https:' || parsed.hostname !== 's.shopee.vn' || parsed.username || parsed.password) {
          throw new BridgeError('shortlink_failed');
        }
        return row.shortLink;
      });
    },
    async vouchers(shopId, job) {
      return owned(job, 'vouchers', async (_page, currentJob) => {
        const result = await getShopVouchersRaw(shopId);
        check(currentJob);
        if (!Array.isArray(result)) throw new BridgeError('invalid_payload');
        return result;
      }, false);
    },
    async close() {
      ready = false;
      await Promise.allSettled([...active]);
      try { if (portalPage) await portalPage.close(); } finally {
        portalPage = undefined;
        portalContext = undefined;
        await session.closeContext();
      }
    },
  };
}
