/**
 * Synapse Shield SDK v0.10.0 - Cryptographic Behavioral & Mobile Biometric Telemetry Collector
 * Next-Gen Open-Source Behavioral Biometrics & Bot Mitigation Engine (Desktop + Mobile SDK v2.0)
 */

(function (window) {
  "use strict";

  // Safe UTF-8 Base64 Encoder (MDN standard fallback for non-Latin1 / Unicode characters)
  function safeBtoa(str) {
    try {
      return window.btoa(str);
    } catch (e) {
      return window.btoa(
        encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, function (_, p1) {
          return String.fromCharCode(parseInt(p1, 16));
        })
      );
    }
  }

  // Get pristine Function.prototype.toString using a transient iframe to defeat prototype hooks
  function getCleanFunctionToString() {
    try {
      if (typeof document === "undefined" || !document.createElement) {
        return Function.prototype.toString;
      }
      const iframe = document.createElement("iframe");
      iframe.style.display = "none";
      const root = document.body || document.documentElement;
      if (!root) return Function.prototype.toString;
      root.appendChild(iframe);
      const cleanToString = iframe.contentWindow.Function.prototype.toString;
      root.removeChild(iframe);
      return cleanToString;
    } catch (e) {
      return Function.prototype.toString;
    }
  }

  // Extract WebGL unmasked renderer string once for anti-emulator hardware verification
  function getWebGLRenderer() {
    try {
      if (typeof document === "undefined" || !document.createElement) return "";
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) return "";
      const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
      if (debugInfo) {
        return String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || "");
      }
      return String(gl.getParameter(gl.RENDERER) || "");
    } catch (e) {
      return "";
    }
  }

  // Dynamic Proof of Work Leading Zero Hex Validator
  function checkLeadingZeroHex(hashArray, difficulty) {
    const fullBytes = Math.floor(difficulty / 2);
    for (let i = 0; i < fullBytes; i++) {
      if (hashArray[i] !== 0) return false;
    }
    if (difficulty % 2 !== 0) {
      if ((hashArray[fullBytes] >> 4) !== 0) return false;
    }
    return true;
  }

  const SynapseShield = {
    mouseMovements: [],
    clicks: [],
    keystrokes: [],
    scrolls: [],
    motionSamples: [],
    lastMoveTime: 0,
    lastScrollTime: 0,
    lastMotionTime: 0,
    lastTouchStartTime: 0,
    moveThrottleMs: 30,
    scrollThrottleMs: 100,
    motionThrottleMs: 50,
    cachedWebGLRenderer: "",
    currentChallenge: null,
    isInitialized: false,

    async init() {
      if (this.isInitialized) return;

      this.cachedWebGLRenderer = getWebGLRenderer();

      // Mouse movements
      window.addEventListener("mousemove", (e) => {
        const now = Date.now();
        if (now - this.lastMoveTime >= this.moveThrottleMs) {
          this.mouseMovements.push({ x: e.clientX, y: e.clientY, t: now });
          this.lastMoveTime = now;
          if (this.mouseMovements.length > 500) this.mouseMovements.shift();
        }
      }, { passive: true });

      // Mobile / Touch interactions (Capacitive ellipse, Tap hold duration & Touch source tagging)
      window.addEventListener("touchstart", (e) => {
        if (!e.touches || e.touches.length === 0) return;
        const touch = e.touches[0];
        const now = Date.now();
        this.lastTouchStartTime = now;
        const rX = touch.radiusX || touch.webkitRadiusX || 0;
        const rY = touch.radiusY || touch.webkitRadiusY || rX;
        const r = (rX + rY) * 0.5;
        const f = touch.force || touch.webkitForce || 0;
        this.mouseMovements.push({
          x: touch.clientX,
          y: touch.clientY,
          t: now,
          r: Math.round(r * 1000) / 1000,
          f: Math.round(f * 1000) / 1000,
          source: "touch",
        });
        this.lastMoveTime = now;
        if (this.mouseMovements.length > 500) this.mouseMovements.shift();
      }, { passive: true });

      window.addEventListener("touchmove", (e) => {
        if (!e.touches || e.touches.length === 0) return;
        const now = Date.now();
        if (now - this.lastMoveTime >= this.moveThrottleMs) {
          const touch = e.touches[0];
          const rX = touch.radiusX || touch.webkitRadiusX || 0;
          const rY = touch.radiusY || touch.webkitRadiusY || rX;
          const r = (rX + rY) * 0.5;
          const f = touch.force || touch.webkitForce || 0;
          this.mouseMovements.push({
            x: touch.clientX,
            y: touch.clientY,
            t: now,
            r: Math.round(r * 1000) / 1000,
            f: Math.round(f * 1000) / 1000,
            source: "touch",
          });
          this.lastMoveTime = now;
          if (this.mouseMovements.length > 500) this.mouseMovements.shift();
        }
      }, { passive: true });

      window.addEventListener("touchend", (e) => {
        if (e.changedTouches && e.changedTouches.length > 0) {
          const touch = e.changedTouches[0];
          const now = Date.now();
          const rX = touch.radiusX || touch.webkitRadiusX || 0;
          const rY = touch.radiusY || touch.webkitRadiusY || rX;
          const r = (rX + rY) * 0.5;
          const tapDuration = this.lastTouchStartTime > 0 ? Math.max(1, now - this.lastTouchStartTime) : 0;
          this.clicks.push({
            x: touch.clientX,
            y: touch.clientY,
            t: now,
            r: Math.round(r * 1000) / 1000,
            tap_duration_ms: tapDuration,
            source: "touch",
          });
          if (this.clicks.length > 50) this.clicks.shift();
        }
      }, { passive: true });

      // Handheld Mobile Micro-Motion / Gyroscope Biometrics
      window.addEventListener("devicemotion", (e) => {
        const now = Date.now();
        if (now - this.lastMotionTime < this.motionThrottleMs) return;
        const acc = e.accelerationIncludingGravity || e.acceleration;
        const rot = e.rotationRate;
        let mag = 0;
        if (acc && (acc.x !== null || acc.y !== null || acc.z !== null)) {
          const ax = Number(acc.x) || 0;
          const ay = Number(acc.y) || 0;
          const az = Number(acc.z) || 0;
          mag += Math.sqrt(ax * ax + ay * ay + az * az);
        }
        if (rot && (rot.alpha !== null || rot.beta !== null || rot.gamma !== null)) {
          const ra = Number(rot.alpha) || 0;
          const rb = Number(rot.beta) || 0;
          const rg = Number(rot.gamma) || 0;
          mag += Math.sqrt(ra * ra + rb * rb + rg * rg) * 0.1;
        }
        if (mag > 0) {
          this.motionSamples.push(mag);
          this.lastMotionTime = now;
          if (this.motionSamples.length > 40) this.motionSamples.shift();
        }
      }, { passive: true });

      // Desktop Click interactions (Deduplicate synthetic click right after touchend)
      window.addEventListener("click", (e) => {
        const now = Date.now();
        if (this.lastTouchStartTime > 0 && now - this.lastTouchStartTime < 800) {
          return;
        }
        this.clicks.push({ x: e.clientX, y: e.clientY, t: now });
        if (this.clicks.length > 50) this.clicks.shift();
      }, { passive: true });

      // Keyboard dynamics (Dwell & Flight Time Tracking + Mobile IME Compatibility)
      const activeKeys = {};
      window.addEventListener("keydown", (e) => {
        const keyName = e.key ? (e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase() || e.code || "unknown") : "unknown";
        const now = Date.now();
        if (!activeKeys[keyName]) {
          activeKeys[keyName] = now;
        }
        this.keystrokes.push({ type: "down", key: keyName, t: now });
        if (this.keystrokes.length > 50) this.keystrokes.shift();
      }, { passive: true });

      window.addEventListener("keyup", (e) => {
        const keyName = e.key ? (e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase() || e.code || "unknown") : "unknown";
        const now = Date.now();
        const downTime = activeKeys[keyName];
        delete activeKeys[keyName];
        const duration = downTime ? (now - downTime) : 0;
        this.keystrokes.push({
          type: "up",
          key: keyName,
          t: now,
          down: downTime || now,
          up: now,
          duration_ms: duration,
        });
        if (this.keystrokes.length > 50) this.keystrokes.shift();
      }, { passive: true });

      // Scroll dynamics
      window.addEventListener("scroll", () => {
        const now = Date.now();
        if (now - this.lastScrollTime >= this.scrollThrottleMs) {
          this.scrolls.push({
            y: window.scrollY || (document.documentElement ? document.documentElement.scrollTop : 0),
            t: now,
          });
          this.lastScrollTime = now;
          if (this.scrolls.length > 200) this.scrolls.shift();
        }
      }, { passive: true });

      // Fetch cryptographic one-time challenge from server
      await this.refreshChallenge();
      this.isInitialized = true;
    },

    async refreshChallenge() {
      try {
        const res = await fetch("/api/challenge");
        if (res.ok) {
          const data = await res.json();
          this.currentChallenge = data.challenge;
        }
      } catch (e) {
        console.warn("Could not fetch challenge, falling back to unsigned mode.");
      }
    },

    reset() {
      this.mouseMovements = [];
      this.clicks = [];
      this.keystrokes = [];
      this.scrolls = [];
      this.motionSamples = [];
      this.lastTouchStartTime = 0;
    },

    getMotionVariance() {
      const n = this.motionSamples.length;
      if (n < 2) return 0;
      const mean = this.motionSamples.reduce((a, b) => a + b, 0) / n;
      const variance = this.motionSamples.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / n;
      return Math.round(variance * 1000000) / 1000000;
    },

    getPayload() {
      const cleanToString = getCleanFunctionToString();
      const telemetry = {
        mouse_movements: this.mouseMovements,
        clicks: this.clicks,
        keystrokes: this.keystrokes,
        scrolls: this.scrolls,
        browser: {
          webdriver: Boolean(navigator.webdriver),
          screen_width: window.innerWidth || (window.screen ? window.screen.width : 0),
          screen_height: window.innerHeight || (window.screen ? window.screen.height : 0),
          device_pixel_ratio: window.devicePixelRatio || 1,
          touch_supported: ("ontouchstart" in window) || (navigator.maxTouchPoints > 0),
          max_touch_points: navigator.maxTouchPoints || 0,
          motion_variance: this.getMotionVariance(),
          webgl_renderer: this.cachedWebGLRenderer || getWebGLRenderer(),
          orientation: (window.screen && window.screen.orientation && window.screen.orientation.type) ? window.screen.orientation.type : "",
          plugins_length: navigator.plugins ? navigator.plugins.length : 0,
          languages: navigator.languages ? navigator.languages.join(",") : (navigator.language || ""),
          is_plugin_array_fake: (function () {
            try {
              return Object.prototype.toString.call(navigator.plugins) !== "[object PluginArray]";
            } catch (e) {
              return true;
            }
          })(),
          has_webdriver_own_prop: Object.prototype.hasOwnProperty.call(navigator, "webdriver"),
          is_webgl_hooked: (function () {
            try {
              if (typeof WebGLRenderingContext === "undefined") return false;
              const fnStr = cleanToString.call(WebGLRenderingContext.prototype.getParameter);
              return !fnStr.includes("[native code]");
            } catch (e) {
              return false;
            }
          })(),
          is_canvas_hooked: (function () {
            try {
              if (typeof HTMLCanvasElement === "undefined") return false;
              const fnStr = cleanToString.call(HTMLCanvasElement.prototype.toDataURL);
              return !fnStr.includes("[native code]");
            } catch (e) {
              return false;
            }
          })(),
        },
      };

      // Challenge ile birleştirip Base64 Token üretir
      if (!this.currentChallenge) {
        throw new Error("Synapse Shield: Missing challenge token. Cannot submit telemetry securely.");
      }

      const envelope = {
        challenge: this.currentChallenge,
        telemetry: telemetry,
        created_at: Date.now(),
      };

      return { token: safeBtoa(JSON.stringify(envelope)) };
    },

    async solvePoW(salt, difficulty = 4) {
      const encoder = new TextEncoder();
      let nonce = 0;
      const batchSize = 1000;
      const maxAttempts = 1000000;

      while (nonce < maxAttempts) {
        const promises = [];
        for (let i = 0; i < batchSize; i++) {
          const currentNonce = nonce + i;
          const str = salt + currentNonce;
          promises.push(
            crypto.subtle.digest("SHA-256", encoder.encode(str)).then((buffer) => {
              const hashArray = new Uint8Array(buffer);
              if (checkLeadingZeroHex(hashArray, difficulty)) {
                return currentNonce.toString();
              }
              return null;
            })
          );
        }

        const results = await Promise.all(promises);
        const found = results.find((r) => r !== null);
        if (found !== undefined) return found;

        nonce += batchSize;

        // Yield execution back to the browser event loop to prevent UI stutter
        await new Promise((resolve) => setTimeout(resolve, 0));
      }

      throw new Error("Synapse Shield: PoW solution could not be found within attempt bounds.");
    },

    async submit(url = "/api/score", retryWithPoW = false, powData = null) {
      const payload = this.getPayload();

      if (powData) {
        payload.pow_nonce = powData.nonce;
        payload.pow_salt = powData.salt;
      }

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await response.json();

        // Handle Token Expiration transparent retry (Masum yavaş kullanıcı koruması)
        if ((data.code === "EXPIRED" || data.status === "token_expired") && !retryWithPoW) {
          console.log("[Synapse Shield] Challenge token expired. Refreshing token and retrying seamlessly...");
          await this.refreshChallenge();
          await new Promise((resolve) => setTimeout(resolve, 1600));
          return await this.submit(url, false, powData);
        }

        // Handle Smart Challenge (PoW) on Gray Area Classification
        if (data.status === "challenge_required" && !retryWithPoW) {
          console.log("[Synapse Shield] Gray area detected. Solving PoW challenge in background...");

          // 1. Concurrently fetch a fresh challenge to prevent Replay Attack rejection
          const refreshPromise = this.refreshChallenge();

          // 2. Solve PoW in background without freezing UI
          const diff = data.pow_difficulty || 4;
          const powNonce = await this.solvePoW(data.pow_salt, diff);
          console.log("[Synapse Shield] PoW solved. Preparing secure retry...");

          // 3. Ensure fresh challenge is fetched
          await refreshPromise;

          // 4. Ensure minimum elapsed time (1600ms) has passed since fresh challenge creation
          let challengeTs = Date.now();
          if (this.currentChallenge) {
            const parts = this.currentChallenge.split(".");
            if (parts.length >= 2) {
              const parsed = parseInt(parts[1], 10);
              if (!isNaN(parsed)) challengeTs = parsed;
            }
          }
          const elapsed = Date.now() - challengeTs;
          if (elapsed < 1600) {
            await new Promise((resolve) => setTimeout(resolve, 1600 - elapsed));
          }

          // 5. Trim telemetry window so telemetry_duration_sec <= elapsed + 0.3s
          // (Prevents Time Travel Bot detection when retrying with a fresh challenge)
          const now = Date.now();
          const maxWindowMs = Math.max(1200, now - challengeTs);
          const windowStart = now - maxWindowMs;
          this.mouseMovements = this.mouseMovements.filter((e) => e.t >= windowStart);
          this.clicks = this.clicks.filter((e) => e.t >= windowStart);
          this.keystrokes = this.keystrokes.filter((e) => e.t >= windowStart);
          this.scrolls = this.scrolls.filter((e) => e.t >= windowStart);

          // Retry with fresh challenge token and valid PoW data
          return await this.submit(url, true, { nonce: powNonce, salt: data.pow_salt });
        }

        // Reset telemetry after successful completion or terminal response
        this.reset();
        // Prepare next challenge proactively in background
        this.refreshChallenge();
        return data;
      } catch (error) {
        this.reset();
        this.refreshChallenge();
        throw error;
      }
    },

    async getToken() {
      if (!this.isInitialized) {
        await this.init();
      }
      if (!this.currentChallenge) {
        await this.refreshChallenge();
      }
      return this.getPayload().token;
    },

    protectFetch(urlPatterns) {
      if (typeof window === "undefined" || !window.fetch) return;
      const originalFetch = window.fetch;
      const patterns = Array.isArray(urlPatterns) ? urlPatterns : [urlPatterns];

      window.fetch = async (input, init = {}) => {
        let url = typeof input === "string" ? input : (input && input.url ? input.url : "");
        const shouldProtect = patterns.some((p) => {
          if (p instanceof RegExp) return p.test(url);
          return typeof p === "string" && url.includes(p);
        });

        if (shouldProtect) {
          try {
            const token = await this.getToken();
            let headers = init.headers ? new Headers(init.headers) : (typeof input === "object" && input.headers ? new Headers(input.headers) : new Headers());
            if (!headers.has("X-Synapse-Token")) {
              headers.set("X-Synapse-Token", token);
            }
            init = { ...init, headers };
          } catch (err) {
            console.warn("[Synapse Shield] Failed to auto-attach X-Synapse-Token to fetch:", err);
          }
        }
        return originalFetch(input, init);
      };
    },

    protectAxios(axiosInstance, urlPatterns) {
      if (!axiosInstance || !axiosInstance.interceptors) return;
      const patterns = Array.isArray(urlPatterns) ? urlPatterns : [urlPatterns];

      axiosInstance.interceptors.request.use(async (config) => {
        const url = config.url || "";
        const shouldProtect = patterns.some((p) => {
          if (p instanceof RegExp) return p.test(url);
          return typeof p === "string" && url.includes(p);
        });

        if (shouldProtect) {
          try {
            const token = await this.getToken();
            config.headers = config.headers || {};
            config.headers["X-Synapse-Token"] = token;
          } catch (err) {
            console.warn("[Synapse Shield] Failed to auto-attach X-Synapse-Token to Axios:", err);
          }
        }
        return config;
      });
    },
  };

  // Prevent prototype and property tampering
  try {
    Object.defineProperty(window, "SynapseShield", {
      value: SynapseShield,
      writable: false,
      configurable: false,
      enumerable: true,
    });
  } catch (e) {
    window.SynapseShield = SynapseShield;
  }
})(typeof window !== "undefined" ? window : globalThis);
