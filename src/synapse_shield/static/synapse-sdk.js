/**
 * Synapse Shield SDK v0.3.1 - Cryptographic Behavioral Telemetry Collector
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
        },
      };

      // Challenge ile birleştirip Base64 Token üretir
      if (this.currentChallenge) {
        const envelope = {
          challenge: this.currentChallenge,
          telemetry: telemetry,
          created_at: Date.now(),
        };
        return { token: btoa(JSON.stringify(envelope)) };
      }

      return { telemetry: telemetry };
    },

    async submit(url = "/api/score") {
      const payload = this.getPayload();
      this.reset();

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        
        // Bir sonraki istek için hemen yeni challenge al
        this.refreshChallenge();
        return await response.json();
      } catch (error) {
        this.refreshChallenge();
        throw error;
      }
    },
  };

  window.SynapseShield = SynapseShield;
})(window);
