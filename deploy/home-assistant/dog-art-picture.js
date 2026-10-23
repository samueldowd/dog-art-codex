/**
 * Display-only Home Assistant card for one application-owned media image.
 * No entity, service, configuration, credential, or device writes are performed.
 * Signed resolve URLs exist only in the current asynchronous request; they are
 * never logged, persisted, or placed into the DOM. A no-store same-origin fetch
 * defeats a browser cache even if HA returns the same signed URL repeatedly.
 */
(() => {
  "use strict";

  const MEDIA_ID = "media-source://media_source/local/kitchen-tv/dog-art/dog-collage.png";
  const MEDIA_PATH = "/media/local/kitchen-tv/dog-art/dog-collage.png";
  const RESOLVE_TIMEOUT_MS = 10000;
  const FETCH_TIMEOUT_MS = 10000;
  const IMAGE_TIMEOUT_MS = 10000;
  const MAX_IMAGE_BYTES = 25 * 1024 * 1024;
  const READINESS_RETRY_MS = 5000;

  class DogArtPicture extends HTMLElement {
    constructor() {
      super();
      this._config = null;
      this._hass = null;
      this._transport = null;
      this._attached = false;
      this._epoch = 0;
      this._timer = null;
      this._nextDue = 0;
      this._attempt = null;
      this._pendingOperations = 0;
      this._currentUrl = null;
      this._onVisibility = () => {
        this._invalidate();
        if (!document.hidden) {
          this._nextDue = 0;
          this._scheduleDue();
        }
      };
      const shadow = this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = `
        :host { display: block; }
        ha-card { display: block; position: relative; overflow: hidden;
          border-radius: var(--ha-card-border-radius, 12px); aspect-ratio: 16 / 9;
          background: #f3ebdd; }
        img { display: block; width: 100%; height: 100%; object-fit: contain; }
        img[hidden] { display: none; }
        .status { position: absolute; width: 1px; height: 1px; padding: 0;
          margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0);
          white-space: nowrap; border: 0; }
      `;
      this._card = document.createElement("ha-card");
      this._card.setAttribute("aria-label", "Today's dog artwork");
      this._image = document.createElement("img");
      this._image.alt = "Today's dog watercolor collage";
      this._image.hidden = true;
      this._status = document.createElement("span");
      this._status.className = "status";
      this._status.setAttribute("role", "status");
      this._status.setAttribute("aria-live", "polite");
      this._status.textContent = "Waiting for Home Assistant.";
      this._card.append(this._image, this._status);
      shadow.append(style, this._card);
      // HA may set hass on the unresolved element before this module loads.
      // Replay that own property through our setter once initialization is done;
      // otherwise it permanently shadows the prototype accessor after upgrade.
      this._upgradeProperty("hass");
    }

    _upgradeProperty(name) {
      if (Object.prototype.hasOwnProperty.call(this, name)) {
        const value = this[name];
        delete this[name];
        this[name] = value;
      }
    }

    setConfig(config) {
      const keys = new Set(["type", "media_content_id", "refresh_interval"]);
      if (!config || typeof config !== "object" || Array.isArray(config) ||
          Object.keys(config).some((key) => !keys.has(key)) ||
          config.type !== "custom:dog-art-picture" ||
          config.media_content_id !== MEDIA_ID ||
          typeof config.refresh_interval !== "number" ||
          !Number.isFinite(config.refresh_interval) ||
          config.refresh_interval < 30 || config.refresh_interval > 3600) {
        throw new Error("Dog Art requires its fixed media image and a finite refresh_interval from 30 to 3600 seconds.");
      }
      const changed = !this._config || this._config.interval !== config.refresh_interval;
      this._config = Object.freeze({ interval: config.refresh_interval });
      if (changed) {
        this._invalidate();
        this._nextDue = 0;
        this._scheduleDue();
      }
    }

    set hass(value) {
      const connection = value && value.connection;
      const callWS = value && value.callWS;
      const connected = typeof (connection && connection.connected) === "boolean"
        ? connection.connected : typeof (value && value.connected) === "boolean"
          ? value.connected : typeof callWS === "function";
      const previous = this._transport;
      const unchanged = previous && previous.connection === connection &&
        previous.connected === connected &&
        (connection || previous.callWS === callWS);
      this._hass = value;
      this._transport = { connection, callWS, connected };
      // hass state objects are replaced on unrelated entity updates. A stable
      // connection must not abort fetch/decoding when HA rebinds callWS.
      if (unchanged) return;
      this._invalidate();
      this._nextDue = 0;
      this._scheduleDue();
    }

    connectedCallback() {
      if (this._attached) return;
      this._attached = true;
      document.addEventListener("visibilitychange", this._onVisibility);
      this._invalidate();
      this._nextDue = 0;
      this._scheduleDue();
    }

    disconnectedCallback() {
      this._attached = false;
      document.removeEventListener("visibilitychange", this._onVisibility);
      this._invalidate();
      if (this._currentUrl) URL.revokeObjectURL(this._currentUrl);
      this._currentUrl = null;
    }

    getCardSize() { return 3; }

    _ready() {
      const value = this._hass;
      const connection = value && value.connection;
      const connected = typeof (connection && connection.connected) === "boolean"
        ? connection.connected : typeof (value && value.connected) === "boolean"
          ? value.connected : typeof (value && value.callWS) === "function";
      return this._attached && !document.hidden && this._config &&
        value && typeof value.callWS === "function" && connected;
    }

    _invalidate() {
      this._epoch += 1;
      if (this._timer !== null) clearTimeout(this._timer);
      this._timer = null;
      if (this._attempt) this._attempt.controller.abort();
      this._attempt = null;
    }

    _scheduleDue() {
      if (this._timer !== null) clearTimeout(this._timer);
      this._timer = null;
      if (!this._ready()) {
        // Connection readiness can change without a new hass assignment.
        // Poll only the visible configured card; no network call until ready.
        if (this._attached && !document.hidden && this._config) {
          this._timer = setTimeout(() => {
            this._timer = null;
            this._scheduleDue();
          }, READINESS_RETRY_MS);
        }
        return;
      }
      this._timer = setTimeout(() => {
        this._timer = null;
        void this._refresh();
      }, Math.max(0, this._nextDue - Date.now()));
    }

    _current(attempt) {
      return this._ready() && attempt.epoch === this._epoch &&
        !attempt.controller.signal.aborted;
    }

    _bounded(promise, milliseconds, signal) {
      return new Promise((resolve, reject) => {
        let settled = false;
        const finish = (error, result) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          signal.removeEventListener("abort", cancelled);
          if (error) reject(error); else resolve(result);
        };
        const cancelled = () => finish(new Error("cancelled"));
        const timer = setTimeout(() => finish(new Error("timeout")), milliseconds);
        signal.addEventListener("abort", cancelled, { once: true });
        if (signal.aborted) cancelled();
        Promise.resolve(promise).then((result) => finish(null, result), () => finish(new Error("unavailable")));
      });
    }

    _track(promise) {
      this._pendingOperations += 1;
      return Promise.resolve(promise).finally(() => { this._pendingOperations -= 1; });
    }

    _validatedUrl(value) {
      if (typeof value !== "string" || value.length > 16384) throw new Error("Invalid media URL");
      const url = new URL(value, window.location.origin);
      if (!new Set(["http:", "https:"]).has(url.protocol) ||
          url.origin !== window.location.origin || url.pathname !== MEDIA_PATH ||
          url.username || url.password || url.hash) {
        throw new Error("Invalid media URL");
      }
      return url.href;
    }

    async _readPng(response, signal) {
      if (!response.body || typeof response.body.getReader !== "function") {
        throw new Error("Readable image stream required");
      }
      const reader = response.body.getReader();
      let complete = false;
      let cancelled = false;
      const cancelReader = () => {
        if (cancelled || complete) return;
        cancelled = true;
        // Cancellation itself must not hold the UI deadline open.
        try { Promise.resolve(reader.cancel()).catch(() => {}); } catch (_) {}
      };
      signal.addEventListener("abort", cancelReader, { once: true });
      try {
        const mime = response.headers.get("content-type");
        if (typeof mime !== "string" || mime.split(";", 1)[0].trim().toLowerCase() !== "image/png") {
          throw new Error("Invalid image type");
        }
        const length = response.headers.get("content-length");
        if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_IMAGE_BYTES)) {
          throw new Error("Image too large");
        }
        const chunks = [];
        let total = 0;
        while (true) {
          if (signal.aborted) throw new Error("cancelled");
          const result = await reader.read();
          if (signal.aborted) throw new Error("cancelled");
          if (result.done) {
            complete = true;
            break;
          }
          const chunk = result.value;
          if (!(chunk instanceof Uint8Array) || chunk.byteLength > MAX_IMAGE_BYTES - total) {
            throw new Error("Image too large or invalid stream");
          }
          total += chunk.byteLength;
          // Copy only the allowed bytes; never retain a larger backing buffer.
          chunks.push(chunk.slice());
        }
        if (total <= 0) throw new Error("Empty image");
        return new Blob(chunks, { type: "image/png" });
      } finally {
        signal.removeEventListener("abort", cancelReader);
        if (!complete) cancelReader();
        try { reader.releaseLock(); } catch (_) {}
      }
    }

    async _refresh() {
      if (!this._ready()) {
        this._scheduleDue();
        return;
      }
      if (this._attempt || this._pendingOperations) {
        // callWS has no abort API. A timed-out unresolved call must settle
        // before another begins, including after config/hass reconnection.
        this._nextDue = Date.now() + this._config.interval * 1000;
        this._scheduleDue();
        return;
      }
      const attempt = { epoch: this._epoch, controller: new AbortController(), image: null, objectUrl: null };
      this._attempt = attempt;
      this._nextDue = Date.now() + this._config.interval * 1000;
      try {
        const resolver = this._hass;
        const resolved = await this._bounded(this._track(Promise.resolve().then(() => resolver.callWS({
          type: "media_source/resolve_media", media_content_id: MEDIA_ID,
        }))), RESOLVE_TIMEOUT_MS, attempt.controller.signal);
        if (!this._current(attempt)) return;
        const url = this._validatedUrl(resolved && resolved.url);
        const download = this._track(Promise.resolve().then(async () => {
          const response = await fetch(url, {
            cache: "no-store", credentials: "same-origin", mode: "same-origin",
            redirect: "error", signal: attempt.controller.signal,
          });
          if (!response.ok) throw new Error("Image unavailable");
          return this._readPng(response, attempt.controller.signal);
        }));
        const blob = await this._bounded(download, FETCH_TIMEOUT_MS, attempt.controller.signal);
        if (!this._current(attempt)) return;
        attempt.objectUrl = URL.createObjectURL(blob);
        const image = new Image();
        attempt.image = image;
        image.alt = "Today's dog watercolor collage";
        const loaded = new Promise((resolve, reject) => {
          image.onload = resolve;
          image.onerror = () => reject(new Error("Invalid image"));
        });
        image.src = attempt.objectUrl;
        await this._bounded(loaded, IMAGE_TIMEOUT_MS, attempt.controller.signal);
        if (!this._current(attempt)) return;
        if (image.naturalWidth !== 1920 || image.naturalHeight !== 1080) {
          throw new Error("Wrong image dimensions");
        }
        image.onload = null;
        image.onerror = null;
        this._card.replaceChild(image, this._image);
        this._image = image;
        if (this._currentUrl) URL.revokeObjectURL(this._currentUrl);
        this._currentUrl = attempt.objectUrl;
        attempt.objectUrl = null;
        this._status.textContent = "Dog artwork updated.";
      } catch (_) {
        if (this._current(attempt)) {
          this._status.textContent = "Dog artwork unavailable. Keeping the previous image.";
        }
      } finally {
        attempt.controller.abort();
        if (attempt.image) {
          attempt.image.onload = null;
          attempt.image.onerror = null;
        }
        if (attempt.objectUrl) URL.revokeObjectURL(attempt.objectUrl);
        if (this._attempt === attempt) this._attempt = null;
        this._scheduleDue();
      }
    }
  }

  if (!customElements.get("dog-art-picture")) {
    customElements.define("dog-art-picture", DogArtPicture);
  }
})();
