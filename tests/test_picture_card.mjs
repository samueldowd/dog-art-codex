import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../deploy/home-assistant/dog-art-picture.js", import.meta.url), "utf8");
const example = JSON.parse(readFileSync(new URL("../deploy/home-assistant/dog-art-picture.example.json", import.meta.url), "utf8"));
const MEDIA_ID = "media-source://media_source/local/kitchen-tv/dog-art/dog-collage.png";
const MEDIA_PATH = "/media/local/kitchen-tv/dog-art/dog-collage.png";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function streamResponse({ mime = "image/png", length = "100", chunks = [new Uint8Array(100)], stats = {}, read, cancel } = {}) {
  let index = 0;
  const reader = {
    read() {
      stats.reads = (stats.reads || 0) + 1;
      if (read) return read();
      return Promise.resolve(index < chunks.length ? { done: false, value: chunks[index++] } : { done: true });
    },
    cancel() { stats.cancelled = (stats.cancelled || 0) + 1; return cancel ? cancel() : Promise.resolve(); },
    releaseLock() { stats.released = (stats.released || 0) + 1; },
  };
  return {
    ok: true,
    headers: { get(name) { return name === "content-type" ? mime : name === "content-length" ? length : null; } },
    body: { getReader() { stats.readers = (stats.readers || 0) + 1; return reader; } },
    blob() { throw new Error("unbounded blob read forbidden"); },
  };
}

class FakeClock {
  constructor() { this.now = 0; this.sequence = 0; this.jobs = new Map(); }
  setTimeout(callback, delay) {
    const id = ++this.sequence;
    this.jobs.set(id, { when: this.now + Math.max(0, Number(delay)), callback });
    return id;
  }
  clearTimeout(id) { this.jobs.delete(id); }
  async flush() { for (let i = 0; i < 40; i += 1) await Promise.resolve(); }
  async advance(milliseconds) {
    const until = this.now + milliseconds;
    await this.flush();
    for (let safety = 0; safety < 10000; safety += 1) {
      const due = [...this.jobs].filter(([, job]) => job.when <= until)
        .sort((a, b) => a[1].when - b[1].when || a[0] - b[0])[0];
      if (!due) { this.now = until; await this.flush(); return; }
      this.jobs.delete(due[0]);
      this.now = due[1].when;
      due[1].callback();
      await this.flush();
    }
    throw new Error("timer loop");
  }
}

function harness({ upgrade = false, beforeDefinitionHass = "connected" } = {}) {
  const clock = new FakeClock();
  let upgradeTarget = null;
  class Node {
    constructor(tag = "node") {
      // Browser custom-element upgrade returns the existing element from super(),
      // retaining properties assigned before registration, rather than a new node.
      if (upgradeTarget) {
        const existing = upgradeTarget;
        upgradeTarget = null;
        Object.setPrototypeOf(existing, new.target.prototype);
        return existing;
      }
      this.tagName = tag; this.children = []; this.attributes = {}; this.hidden = false;
    }
    append(...children) { this.children.push(...children); }
    setAttribute(name, value) { this.attributes[name] = value; }
    replaceChild(next, previous) {
      const index = this.children.indexOf(previous);
      assert.ok(index >= 0);
      this.children[index] = next;
    }
    attachShadow() { this.shadowRoot = new Node("shadow"); return this.shadowRoot; }
    set innerHTML(_) { throw new Error("untrusted innerHTML forbidden"); }
  }
  const document = {
    hidden: false,
    handlers: new Set(),
    createElement(tag) { return new Node(tag); },
    addEventListener(type, callback) { assert.equal(type, "visibilitychange"); this.handlers.add(callback); },
    removeEventListener(type, callback) { assert.equal(type, "visibilitychange"); this.handlers.delete(callback); },
    visibility(hidden) { this.hidden = hidden; for (const callback of [...this.handlers]) callback(); },
  };
  const state = { calls: [], fetches: [], images: [], created: [], revoked: [], imageMode: "load", imageWidth: 1920, imageHeight: 1080 };
  let resolveHandler = () => Promise.resolve({ url: `${MEDIA_PATH}?authSig=test-${state.calls.length}` });
  let fetchHandler = () => Promise.resolve(streamResponse());
  class FakeImage extends Node {
    constructor() { super("img"); this.naturalWidth = state.imageWidth; this.naturalHeight = state.imageHeight; state.images.push(this); }
    set src(value) {
      this._src = value;
      if (state.imageMode === "hold") return;
      const mode = state.imageMode;
      clock.setTimeout(() => { if (mode === "load") this.onload?.(); else this.onerror?.(); }, 1);
    }
    get src() { return this._src; }
  }
  class FakeUrl extends URL {
    static createObjectURL(value) { assert.ok(value instanceof Blob); assert.equal(value.type, "image/png"); assert.ok(value.size > 0 && value.size <= 25 * 1024 * 1024); const url = `blob:test/${state.created.length + 1}`; state.created.push(url); return url; }
    static revokeObjectURL(url) { state.revoked.push(url); }
  }
  const registry = new Map();
  const makeHass = () => ({ connection: { connected: true }, callWS(payload) { state.calls.push(payload); return resolveHandler(payload); } });
  const hass = makeHass();
  const unresolved = upgrade ? new Node("dog-art-picture") : null;
  if (unresolved) {
    unresolved.hass = beforeDefinitionHass === "connected" ? hass : beforeDefinitionHass;
    assert.equal(Object.hasOwn(unresolved, "hass"), true);
    assert.equal(unresolved._hass, undefined);
  }
  const context = vm.createContext({
    HTMLElement: Node, document, window: { location: { origin: "https://ha.example.test" } },
    URL: FakeUrl, Image: FakeImage, AbortController, Blob, Uint8Array,
    setTimeout: clock.setTimeout.bind(clock), clearTimeout: clock.clearTimeout.bind(clock),
    Date: class extends Date { static now() { return clock.now; } },
    customElements: {
      get: registry.get.bind(registry),
      define(name, constructor) {
        registry.set(name, constructor);
        if (unresolved) {
          upgradeTarget = unresolved;
          assert.equal(new constructor(), unresolved);
        }
      },
    },
    fetch: (url, options) => { state.fetches.push({ url, options }); return fetchHandler(url, options); },
    console: { log() { throw new Error("logging forbidden"); }, error() { throw new Error("logging forbidden"); }, warn() { throw new Error("logging forbidden"); } },
  });
  vm.runInContext(source, context);
  const Card = registry.get("dog-art-picture");
  assert.ok(Card);
  const card = unresolved || new Card();
  const mount = () => { card.setConfig({ ...example }); card.hass = hass; card.connectedCallback(); };
  return { clock, state, card, document, makeHass, hass, mount, setResolve(fn) { resolveHandler = fn; }, setFetch(fn) { fetchHandler = fn; }, runAgain() { vm.runInContext(source, context); } };
}

function assertOnlyOwnedCalls(state) {
  for (const call of state.calls) {
    assert.equal(call.type, "media_source/resolve_media");
    assert.equal(call.media_content_id, MEDIA_ID);
    assert.equal(Object.keys(call).length, 2);
  }
  for (const fetch of state.fetches) {
    const url = new URL(fetch.url);
    assert.equal(url.origin, "https://ha.example.test");
    assert.equal(url.pathname, MEDIA_PATH);
    assert.equal(fetch.options.cache, "no-store");
    assert.equal(fetch.options.credentials, "same-origin");
    assert.equal(fetch.options.mode, "same-origin");
    assert.equal(fetch.options.redirect, "error");
    assert.ok(fetch.options.signal instanceof AbortSignal);
  }
}

test("predefinition own hass is replayed during upgrade without waiting for another HA update", async () => {
  const h = harness({ upgrade: true });
  assert.equal(Object.hasOwn(h.card, "hass"), false, "own data must not shadow the prototype setter");
  assert.equal(h.card._hass, h.hass);
  assert.equal(h.state.calls.length, 0, "upgrade alone must not start a detached card");
  // A connected element can upgrade before HA supplies its card configuration.
  h.card.connectedCallback();
  await h.clock.advance(1);
  assert.equal(h.state.calls.length, 0);
  h.card.setConfig({ ...example });
  await h.clock.advance(1);
  assert.equal(h.state.calls.length, 1, "first refresh uses the predefinition hass value");
  assert.equal(h.card._image.hidden, false);
  assert.equal(h.card._image.naturalWidth, 1920);
  assert.match(h.card._status.textContent, /updated/);
  for (let i = 0; i < 20; i += 1) {
    h.card.hass = { ...h.hass, states: { unrelated: i } };
  }
  assert.equal(Object.hasOwn(h.card, "hass"), false);
  await h.clock.advance(30000);
  assert.equal(h.state.calls.length, 2);
  assertOnlyOwnedCalls(h.state);
  h.card.disconnectedCallback();
  assert.equal(h.document.handlers.size, 0);
  assert.equal(h.clock.jobs.size, 0);
  assert.equal(h.state.created.length, h.state.revoked.length);
});

test("null predefinition hass is removed so later HA assignment and reconnect can start the card", async () => {
  const h = harness({ upgrade: true, beforeDefinitionHass: null });
  assert.equal(Object.hasOwn(h.card, "hass"), false);
  assert.equal(h.card._hass, null);
  h.card.setConfig({ ...example });
  h.card.connectedCallback();
  await h.clock.advance(30000);
  assert.equal(h.state.calls.length, 0);
  h.card.hass = h.hass;
  await h.clock.advance(1);
  assert.equal(h.state.calls.length, 1);
  assert.equal(h.card._image.hidden, false);
  h.card.disconnectedCallback();
  h.card.connectedCallback();
  await h.clock.advance(1);
  assert.equal(h.state.calls.length, 2);
  assert.equal(h.document.handlers.size, 1);
  assertOnlyOwnedCalls(h.state);
  h.card.disconnectedCallback();
});

test("exact example refreshes on a future 30-second timer with no-store fetch and blob swap", async () => {
  const h = harness(); h.mount();
  await h.clock.advance(1);
  const initial = h.card._image;
  assert.equal(h.state.calls.length, 1);
  assert.match(initial.src, /^blob:test\//);
  assert.equal(initial.alt, "Today's dog watercolor collage");
  assert.equal(h.card._status.attributes["aria-live"], "polite");
  await h.clock.advance(29998);
  assert.equal(h.state.calls.length, 1);
  await h.clock.advance(2);
  assert.equal(h.state.calls.length, 2);
  assert.notEqual(h.card._image, initial);
  assert.deepEqual(h.state.revoked, [initial.src]);
  assert.equal(h.clock.jobs.size, 1);
  assertOnlyOwnedCalls(h.state);
  assert.ok(!h.card._image.src.includes("authSig"));
  h.card.disconnectedCallback();
  assert.equal(h.clock.jobs.size, 0);
  assert.equal(h.state.created.length, h.state.revoked.length);
});

test("same signed URL still refetches each time and errors retain decoded old image", async () => {
  const h = harness();
  h.setResolve(() => Promise.resolve({ url: `${MEDIA_PATH}?authSig=unchanged-test` }));
  h.mount(); await h.clock.advance(1);
  const initial = h.card._image;
  h.state.imageMode = "error";
  await h.clock.advance(30000);
  assert.equal(h.card._image, initial);
  assert.equal(h.state.fetches.length, 2);
  assert.equal(h.state.fetches[0].url, h.state.fetches[1].url);
  assert.match(h.card._status.textContent, /Keeping the previous/);
  assert.deepEqual(h.state.revoked, ["blob:test/2"]);
  assertOnlyOwnedCalls(h.state);
});

test("HA resolution outage and HTTP outage keep last image and retry on next interval", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const initial = h.card._image;
  h.setResolve(() => Promise.reject(new Error("private server details")));
  await h.clock.advance(30000);
  assert.equal(h.card._image, initial);
  assert.ok(!h.card._status.textContent.includes("private"));
  h.setResolve(() => Promise.resolve({ url: MEDIA_PATH }));
  h.setFetch(() => Promise.resolve({ ok: false }));
  await h.clock.advance(30000);
  assert.equal(h.card._image, initial);
  assert.equal(h.clock.jobs.size, 1);
});

test("unresolved WS times out boundedly without overlapping a later request", async () => {
  const h = harness();
  const pending = deferred();
  h.setResolve(() => pending.promise);
  h.mount(); await h.clock.advance(10000);
  assert.match(h.card._status.textContent, /unavailable/);
  await h.clock.advance(80000);
  assert.equal(h.state.calls.length, 1);
  pending.resolve({ url: MEDIA_PATH });
  await h.clock.flush();
  assert.equal(h.state.fetches.length, 0);
  h.setResolve(() => Promise.resolve({ url: MEDIA_PATH }));
  await h.clock.advance(30001);
  assert.equal(h.state.calls.length, 2);
  assert.equal(h.state.fetches.length, 1);
});

test("fetch/body and image timeouts abort and preserve prior image", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const initial = h.card._image;
  const pending = deferred();
  h.setFetch((_url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
    pending.promise.then(resolve, reject);
  }));
  await h.clock.advance(40000);
  assert.equal(h.card._image, initial);
  assert.equal(h.state.fetches.at(-1).options.signal.aborted, true);
  // A separate harness exercises the image decoder deadline independently.
  const imageCase = harness(); imageCase.mount(); await imageCase.clock.advance(1);
  const loaded = imageCase.card._image;
  imageCase.state.imageMode = "hold";
  await imageCase.clock.advance(40000);
  assert.equal(imageCase.card._image, loaded);
  assert.deepEqual(imageCase.state.revoked, ["blob:test/2"]);
  assert.equal(imageCase.clock.jobs.size, 1);
});

test("disconnect/config/hass generation changes cannot apply stale pending results", async () => {
  const h = harness(); const old = deferred(); h.setResolve(() => old.promise);
  h.mount(); await h.clock.advance(0);
  h.card.setConfig({ ...example, refresh_interval: 60 });
  h.card.hass = h.makeHass();
  h.card.disconnectedCallback();
  await h.clock.flush();
  assert.equal(h.clock.jobs.size, 0);
  assert.equal(h.document.handlers.size, 0);
  old.resolve({ url: MEDIA_PATH }); await h.clock.flush();
  assert.equal(h.state.fetches.length, 0);
  h.setResolve(() => Promise.resolve({ url: MEDIA_PATH }));
  h.card.connectedCallback(); await h.clock.advance(1);
  assert.equal(h.state.calls.length, 2);
  assert.equal(h.state.fetches.length, 1);
  assert.equal(h.document.handlers.size, 1);
});

test("stale decoded image after hass change cannot replace current image", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const initial = h.card._image;
  h.state.imageMode = "hold";
  await h.clock.advance(30000);
  const pendingImage = h.state.images.at(-1);
  const capturedLoad = pendingImage.onload;
  h.card.hass = h.makeHass();
  capturedLoad(); await h.clock.flush();
  assert.equal(h.card._image, initial);
  assert.ok(h.state.revoked.includes(pendingImage.src));
});

test("hidden tabs stop work and resume immediately without interval/listener leaks", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  h.document.visibility(true);
  assert.equal(h.clock.jobs.size, 0);
  await h.clock.advance(120000);
  assert.equal(h.state.calls.length, 1);
  h.document.visibility(false); await h.clock.advance(1);
  assert.equal(h.state.calls.length, 2);
  for (let i = 0; i < 20; i += 1) {
    h.card.setConfig({ ...example });
    h.card.hass = { ...h.hass, states: { unrelated: i } };
    h.card.connectedCallback();
  }
  assert.equal(h.clock.jobs.size, 1);
  assert.equal(h.document.handlers.size, 1);
  await h.clock.advance(30000);
  assert.equal(h.state.calls.length, 3);
  h.card.disconnectedCallback();
  assert.equal(h.clock.jobs.size, 0);
  assert.equal(h.document.handlers.size, 0);
});

test("foreign origins, protocols, redirecting/path variants and auth userinfo are rejected before fetch", async () => {
  const invalid = [
    `https://elsewhere.example${MEDIA_PATH}`, `//elsewhere.example${MEDIA_PATH}`,
    `http://ha.example.test${MEDIA_PATH}`, "javascript:alert(1)",
    "/media/local/kitchen-tv/other.png", `${MEDIA_PATH}/other`,
    `https://user:pass@ha.example.test${MEDIA_PATH}`, `${MEDIA_PATH}#fragment`,
    "/media/local/kitchen-tv/dog-art/%64og-collage.png", null, {},
  ];
  for (const value of invalid) {
    const h = harness(); h.setResolve(() => Promise.resolve({ url: value }));
    h.mount(); await h.clock.advance(1);
    assert.equal(h.state.fetches.length, 0);
    assert.match(h.card._status.textContent, /unavailable/);
    h.card.disconnectedCallback();
  }
});

test("wrong dimensions and untrusted non-PNG/oversized response never replace old image", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const initial = h.card._image;
  h.state.imageWidth = 800;
  await h.clock.advance(30000);
  assert.equal(h.card._image, initial);
  assert.ok(h.state.revoked.includes("blob:test/2"));
  h.setFetch(() => Promise.resolve(streamResponse({ mime: "text/html" })));
  await h.clock.advance(30000);
  assert.equal(h.card._image, initial);
  assert.equal(h.state.created.length, 2);
  h.setFetch(() => Promise.resolve(streamResponse({ length: "999999999", read() { throw new Error("must not read oversized body"); } })));
  await h.clock.advance(30000);
  assert.equal(h.card._image, initial);
});

test("invalid config cannot widen image/path/interval authority; duplicate resource definition is safe", () => {
  const h = harness(); h.runAgain();
  const invalid = [null, [], {}, { ...example, type: "picture" }, { ...example, media_content_id: MEDIA_ID + "/other" },
    ...[0, 29, 3601, NaN, Infinity, "30", null].map((refresh_interval) => ({ ...example, refresh_interval })),
    { ...example, entity: "switch.anything" }, { ...example, url: "https://other.example" }];
  for (const config of invalid) assert.throws(() => h.card.setConfig(config));
  for (const interval of [30, 30.5, 3600]) h.card.setConfig({ ...example, refresh_interval: interval });
  assert.equal(h.clock.jobs.size, 0);
});


test("stalled response stream times out, cancels its reader and prevents overlap", async () => {
  const h = harness();
  const pending = deferred();
  const stats = {};
  h.setFetch(() => Promise.resolve(streamResponse({
    length: null, stats, read: () => pending.promise,
    cancel: () => { pending.reject(new Error("body cancelled")); return Promise.resolve(); },
  })));
  h.mount(); await h.clock.advance(10000);
  assert.equal(stats.cancelled, 1);
  assert.equal(stats.released, 1);
  assert.equal(h.state.calls.length, 1);
  assert.equal(h.state.fetches[0].options.signal.aborted, true);
  assert.match(h.card._status.textContent, /unavailable/);
  assert.equal(h.clock.jobs.size, 1);
  h.card.disconnectedCallback();
});

test("config change invalidates old image decoder without altering its fixed media scope", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const initial = h.card._image;
  h.state.imageMode = "hold";
  await h.clock.advance(30000);
  const pending = h.state.images.at(-1);
  const staleLoad = pending.onload;
  h.card.setConfig({ ...example, refresh_interval: 90 });
  staleLoad(); await h.clock.flush();
  assert.equal(h.card._image, initial);
  assert.ok(h.state.revoked.includes(pending.src));
  h.state.imageMode = "load";
  await h.clock.advance(90001);
  assertOnlyOwnedCalls(h.state);
  assert.equal(h.clock.jobs.size, 1);
});


test("ordinary hass state objects preserve both pending fetch and pending image decoding", async () => {
  const h = harness();
  const waitingFetch = deferred();
  h.setFetch(() => waitingFetch.promise);
  h.mount(); await h.clock.advance(0);
  const signal = h.state.fetches[0].options.signal;
  for (let i = 0; i < 100; i += 1) {
    h.card.hass = { ...h.hass, states: { unrelated: i } };
  }
  assert.equal(signal.aborted, false);
  assert.equal(h.state.calls.length, 1);
  h.state.imageMode = "hold";
  waitingFetch.resolve(streamResponse()); await h.clock.flush();
  const loading = h.state.images.at(-1);
  const originalOnLoad = loading.onload;
  assert.equal(typeof originalOnLoad, "function");
  for (let i = 0; i < 100; i += 1) {
    h.card.hass = { ...h.hass, states: { another: i } };
  }
  assert.equal(loading.onload, originalOnLoad);
  originalOnLoad(); await h.clock.flush();
  assert.equal(h.card._image, loading);
  assert.equal(h.state.calls.length, 1);
  await h.clock.advance(29999);
  assert.equal(h.state.calls.length, 1);
  h.state.imageMode = "load";
  h.setFetch(() => Promise.resolve(streamResponse()));
  await h.clock.advance(2);
  assert.equal(h.state.calls.length, 2);
});


test("real HA transport disconnection invalidates decoding and reconnect resumes", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const original = h.card._image;
  h.state.imageMode = "hold";
  await h.clock.advance(30000);
  const loading = h.state.images.at(-1);
  const staleLoad = loading.onload;
  h.hass.connection.connected = false;
  h.card.hass = { ...h.hass, states: { unrelated: 1 } };
  staleLoad(); await h.clock.flush();
  assert.equal(h.card._image, original);
  assert.equal(h.clock.jobs.size, 1, "only a local readiness retry remains");
  const requestsWhileDisconnected = h.state.calls.length;
  await h.clock.advance(15000);
  assert.equal(h.state.calls.length, requestsWhileDisconnected, "disconnected retries must not send requests");
  h.hass.connection.connected = true;
  h.card.hass = h.hass;
  h.state.imageMode = "load";
  await h.clock.advance(1);
  assert.notEqual(h.card._image, original);
  assert.equal(h.state.calls.length, 3);
  assert.equal(h.clock.jobs.size, 1);
});


test("missing or false Content-Length cannot accumulate a body beyond 25 MiB", async () => {
  for (const length of [null, "1"]) {
    const h = harness(); h.mount(); await h.clock.advance(1);
    const original = h.card._image;
    const stats = {};
    h.setFetch(() => Promise.resolve(streamResponse({
      length, stats,
      chunks: [new Uint8Array(20 * 1024 * 1024), new Uint8Array(6 * 1024 * 1024), new Uint8Array(1)],
    })));
    await h.clock.advance(30000);
    assert.equal(h.card._image, original);
    assert.equal(stats.reads, 2, "must cancel before reading a further chunk");
    assert.equal(stats.cancelled, 1);
    assert.equal(stats.released, 1);
    assert.equal(h.state.created.length, 1, "oversized stream must never become an image blob");
    assert.match(h.card._status.textContent, /unavailable/);
    h.card.disconnectedCallback();
  }
});


test("PNG stream requires response MIME, nonempty bytes and a reader; invalid bodies are cancelled", async () => {
  for (const overrides of [{ mime: "text/html" }, { mime: null }, { chunks: [] }, { length: "999999999" }]) {
    const h = harness(); const stats = {};
    h.setFetch(() => Promise.resolve(streamResponse({ ...overrides, stats })));
    h.mount(); await h.clock.advance(1);
    assert.equal(h.state.created.length, 0);
    assert.equal(stats.released, 1);
    if (!overrides.chunks) {
      assert.equal(stats.reads || 0, 0);
      assert.equal(stats.cancelled, 1);
    }
    h.card.disconnectedCallback();
  }
  const h = harness();
  h.setFetch(() => Promise.resolve({ ok: true, headers: { get() { return "image/png"; } }, body: null,
    blob() { throw new Error("must never fallback to unbounded blob"); } }));
  h.mount(); await h.clock.advance(1);
  assert.equal(h.state.created.length, 0);
  assert.match(h.card._status.textContent, /unavailable/);
});

test("connection becomes ready without another hass assignment", async () => {
  const h = harness();
  h.hass.connection.connected = false;
  h.mount();
  await h.clock.advance(15000);
  assert.equal(h.state.calls.length, 0);
  assert.equal(h.clock.jobs.size, 1, "one bounded local readiness timer");
  h.hass.connection.connected = true;
  await h.clock.advance(5001);
  assert.equal(h.state.calls.length, 1);
  assert.equal(h.card._image.naturalWidth, 1920);
  assert.equal(h.card._status.textContent, "Dog artwork updated.");
  h.card.disconnectedCallback();
  assert.equal(h.clock.jobs.size, 0);
});

test("rebinding callWS on the same connected HA transport preserves pending work", async () => {
  const h = harness();
  const pending = deferred();
  h.setResolve(() => pending.promise);
  h.mount();
  await h.clock.advance(0);
  for (let i = 0; i < 6; i += 1) {
    h.card.hass = { ...h.hass, callWS: h.hass.callWS.bind(h.hass), states: { unrelated: i } };
    await h.clock.advance(100);
  }
  assert.equal(h.state.calls.length, 1);
  pending.resolve({ url: MEDIA_PATH });
  await h.clock.advance(1);
  assert.equal(h.state.fetches.length, 1);
  assert.equal(h.card._status.textContent, "Dog artwork updated.");
  assertOnlyOwnedCalls(h.state);
});

test("connection drop at scheduled refresh recovers without hass reassignment", async () => {
  const h = harness(); h.mount(); await h.clock.advance(1);
  const first = h.card._image;
  h.hass.connection.connected = false;
  await h.clock.advance(30000);
  assert.equal(h.state.calls.length, 1);
  assert.equal(h.clock.jobs.size, 1);
  h.hass.connection.connected = true;
  await h.clock.advance(5001);
  assert.equal(h.state.calls.length, 2);
  assert.notEqual(h.card._image, first);
  h.document.visibility(true);
  assert.equal(h.clock.jobs.size, 0);
});

test("connection drop during resolution leaves a recoverable local readiness timer", async () => {
  const h = harness(); const pending = deferred();
  h.setResolve(() => pending.promise);
  h.mount(); await h.clock.advance(0);
  h.hass.connection.connected = false;
  pending.resolve({ url: MEDIA_PATH });
  await h.clock.flush();
  assert.equal(h.state.fetches.length, 0);
  assert.equal(h.clock.jobs.size, 1);
  h.setResolve(() => Promise.resolve({ url: MEDIA_PATH }));
  h.hass.connection.connected = true;
  await h.clock.advance(35001);
  assert.equal(h.state.fetches.length, 1);
  assert.equal(h.card._status.textContent, "Dog artwork updated.");
  h.card.disconnectedCallback();
  assert.equal(h.clock.jobs.size, 0);
});
