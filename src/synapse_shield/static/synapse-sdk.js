/**
 * Synapse Shield SDK v0.4.0 - Cryptographic Behavioral Telemetry Collector
 */

(function (window) {
  const SynapseShield = {
    mouseMovements: [],
    clicks: [],
    keystrokes: [],
    scrolls: [],
    lastMoveTime: 0,
    lastScrollTime: 0,
    moveThrottleMs: 30,
    scrollThrottleMs: 100,
    currentChallenge: null,
    isInitialized: false,

    async init() {
      if (this.isInitialized) return;

      window.addEventListener("mousemove", (e) => {
        const now = Date.now();
        if (now - this.lastMoveTime >= this.moveThrottleMs) {
          this.mouseMovements.push({ x: e.clientX, y: e.clientY, t: now });
          this.lastMoveTime = now;
          if (this.mouseMovements.length > 500) this.mouseMovements.shift();
        }
      });

      window.addEventListener("click", (e) => {
        this.clicks.push({ x: e.clientX, y: e.clientY, t: Date.now() });
        if (this.clicks.length > 50) this.clicks.shift();
      });

      window.addEventListener("keydown", () => {
        this.keystrokes.push({ type: "down", t: Date.now() });
        if (this.keystrokes.length > 50) this.keystrokes.shift();
      });

      window.addEventListener("keyup", () => {
        this.keystrokes.push({ type: "up", t: Date.now() });
        if (this.keystrokes.length > 50) this.keystrokes.shift();
      });

      window.addEventListener("scroll", () => {
        const now = Date.now();
        if (now - this.lastScrollTime >= this.scrollThrottleMs) {
          this.scrolls.push({
            y: window.scrollY || document.documentElement.scrollTop,
            t: now,
          });
          this.lastScrollTime = now;
          if (this.scrolls.length > 200) this.scrolls.shift();
        }
      });

      // Sunucudan tek kullanımlık challenge al
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
    },

    getPayload() {
      const telemetry = {
        mouse_movements: this.mouseMovements,
        clicks: this.clicks,
        keystrokes: this.keystrokes,
        scrolls: this.scrolls,
        browser: {
          webdriver: navigator.webdriver || false,
          screen_width: window.innerWidth || window.screen.width,
          screen_height: window.innerHeight || window.screen.height,
          touch_supported: "ontouchstart" in window || navigator.maxTouchPoints > 0,
          plugins_length: navigator.plugins ? navigator.plugins.length : 0,
          languages: navigator.languages ? navigator.languages.join(",") : navigator.language,
          is_plugin_array_fake: (function() {
            try {
              return Object.prototype.toString.call(navigator.plugins) !== '[object PluginArray]';
            } catch(e) { return true; }
          })(),
          has_webdriver_own_prop: navigator.hasOwnProperty("webdriver"),
          is_webgl_hooked: (function() {
            try {
              const nativeToString = Function.prototype.toString;
              const fnStr = nativeToString.call(WebGLRenderingContext.prototype.getParameter);
              return !fnStr.includes("[native code]");
            } catch(e) { return false; }
          })(),
          is_canvas_hooked: (function() {
            try {
              const nativeToString = Function.prototype.toString;
              const fnStr = nativeToString.call(HTMLCanvasElement.prototype.toDataURL);
              return !fnStr.includes("[native code]");
            } catch(e) { return false; }
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
      return { token: btoa(JSON.stringify(envelope)) };
    },

    async solvePoW(salt, difficulty) {
      const encoder = new TextEncoder();
      let nonce = 0;
      const batchSize = 1000;
      
      while (true) {
        const promises = [];
        for (let i = 0; i < batchSize; i++) {
          const currentNonce = nonce + i;
          const str = salt + currentNonce;
          promises.push(
            crypto.subtle.digest('SHA-256', encoder.encode(str)).then(buffer => {
              const hashArray = new Uint8Array(buffer);
              // Difficulty 4 means 4 hex zeros, which is 2 bytes of 0x00
              if (hashArray[0] === 0 && hashArray[1] === 0) {
                 return currentNonce.toString();
              }
              return null;
            })
          );
        }
        const results = await Promise.all(promises);
        const found = results.find(r => r !== null);
        if (found) return found;
        nonce += batchSize;
      }
    },

    async submit(url = "/api/score", retryWithPoW = false, powData = null) {
      const payload = this.getPayload();
      
      if (powData) {
        payload.pow_nonce = powData.nonce;
        payload.pow_salt = powData.salt;
      } else {
        this.reset();
      }

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        
        const data = await response.json();
        
        // Handle Smart Challenge (PoW)
        if (data.status === "challenge_required" && !retryWithPoW) {
          console.log("[Synapse Shield] Gray area detected. Solving PoW challenge in background...");
          const powNonce = await this.solvePoW(data.pow_salt, data.pow_difficulty);
          console.log("[Synapse Shield] PoW solved. Retrying request...");
          return await this.submit(url, true, { nonce: powNonce, salt: data.pow_salt });
        }
        
        // Bir sonraki istek için hemen yeni challenge al
        this.refreshChallenge();
        return data;
      } catch (error) {
        this.refreshChallenge();
        throw error;
      }
    },

  };

  window.SynapseShield = SynapseShield;
})(window);
