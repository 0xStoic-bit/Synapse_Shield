/**
 * Synapse Shield SDK - Behavioral Telemetry Collector
 *
 * Captures user mechanics (mouse movements, clicking coordinates, keystroke timings,
 * scrolls, and system flags) safely and efficiently.
 *
 * Note: To preserve user privacy, no keystroke values/char codes are captured,
 * only event types (keydown/keyup) and millisecond timestamps to compute intervals.
 */

(function (window) {
  const SynapseShield = {
    // Buffers
    mouseMovements: [],
    clicks: [],
    keystrokes: [],
    scrolls: [],

    // Throttling timers
    lastMoveTime: 0,
    lastScrollTime: 0,
    moveThrottleMs: 30, // Sample mouse every 30ms
    scrollThrottleMs: 100, // Sample scroll every 100ms

    // Initialization state
    isInitialized: false,

    init() {
      if (this.isInitialized) return;

      // Mouse movements listener
      window.addEventListener("mousemove", (e) => {
        const now = Date.now();
        if (now - this.lastMoveTime >= this.moveThrottleMs) {
          this.mouseMovements.push({
            x: e.clientX,
            y: e.clientY,
            t: now,
          });
          this.lastMoveTime = now;
          // Cap movements array at 1000 items to avoid memory issues
          if (this.mouseMovements.length > 1000) {
            this.mouseMovements.shift();
          }
        }
      });

      // Click listener
      window.addEventListener("click", (e) => {
        this.clicks.push({
          x: e.clientX,
          y: e.clientY,
          t: Date.now(),
        });
        if (this.clicks.length > 100) this.clicks.shift();
      });

      // Keystroke dynamics (Only capturing timestamps for privacy)
      window.addEventListener("keydown", () => {
        this.keystrokes.push({
          type: "down",
          t: Date.now(),
        });
        if (this.keystrokes.length > 100) this.keystrokes.shift();
      });

      window.addEventListener("keyup", () => {
        this.keystrokes.push({
          type: "up",
          t: Date.now(),
        });
        if (this.keystrokes.length > 100) this.keystrokes.shift();
      });

      // Scroll listener
      window.addEventListener("scroll", () => {
        const now = Date.now();
        if (now - this.lastScrollTime >= this.scrollThrottleMs) {
          this.scrolls.push({
            y: window.scrollY,
            t: now,
          });
          this.lastScrollTime = now;
          if (this.scrolls.length > 100) this.scrolls.shift();
        }
      });

      this.isInitialized = true;
      console.log("Synapse Shield Telemetry SDK initialized.");
    },

    reset() {
      this.mouseMovements = [];
      this.clicks = [];
      this.keystrokes = [];
      this.scrolls = [];
      console.log("Synapse Shield Telemetry buffer reset.");
    },

    getPayload() {
      return {
        mouse_movements: this.mouseMovements,
        clicks: this.clicks,
        keystrokes: this.keystrokes,
        scrolls: this.scrolls,
        browser: {
          webdriver: navigator.webdriver || false,
          screen_width: window.innerWidth || window.screen.width,
          screen_height: window.innerHeight || window.screen.height,
          touch_supported:
            "ontouchstart" in window || navigator.maxTouchPoints > 0,
        },
      };
    },

    async submit(url = "/api/score") {
      const payload = this.getPayload();
      this.reset(); // Reset buffer after fetch to start capturing fresh events

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
      } catch (error) {
        console.error("Failed to submit telemetry to Synapse Shield:", error);
        throw error;
      }
    },
  };

  // Expose globally
  window.SynapseShield = SynapseShield;
})(window);
