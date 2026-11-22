import { performance } from 'node:perf_hooks';

export class BridgeError extends Error {
  constructor(code, status = 502) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

// A caller can time out immediately, but its browser work retains ownership until
// cancellation/finally has drained. The next request never navigates concurrently.
export class BrowserQueue {
  #tail = Promise.resolve();
  #pending = 0;
  #closed = false;

  constructor({ maxPending = 32 } = {}) {
    this.maxPending = maxPending;
  }

  run(work, timeoutMs, externalSignal) {
    if (this.#closed) return Promise.reject(new BridgeError('unavailable', 503));
    if (this.#pending >= this.maxPending) return Promise.reject(new BridgeError('busy', 503));
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      return Promise.reject(new BridgeError('timeout', 504));
    }
    this.#pending += 1;
    const deadline = performance.now() + timeoutMs;
    const controller = new AbortController();
    let resolveCaller, rejectCaller;
    const caller = new Promise((resolve, reject) => {
      resolveCaller = resolve;
      rejectCaller = reject;
    });
    const abort = () => {
      controller.abort();
      rejectCaller(new BridgeError('timeout', 504));
    };
    const timer = setTimeout(abort, timeoutMs);
    externalSignal?.addEventListener('abort', abort, { once: true });
    if (externalSignal?.aborted) abort();
    const task = this.#tail.then(async () => {
      if (controller.signal.aborted) return;
      try {
        const value = await work({
          signal: controller.signal,
          remaining: () => Math.max(0, deadline - performance.now()),
        });
        if (!controller.signal.aborted) resolveCaller(value);
      } catch (error) {
        if (!controller.signal.aborted) rejectCaller(error);
      }
    }).finally(() => {
      clearTimeout(timer);
      externalSignal?.removeEventListener('abort', abort);
      this.#pending -= 1;
    });
    this.#tail = task.catch(() => {});
    return caller;
  }

  async close() {
    this.#closed = true;
    await this.#tail;
  }
}
