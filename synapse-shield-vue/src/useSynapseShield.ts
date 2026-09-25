import { ref, onMounted, onBeforeUnmount } from 'vue';

// Safe UTF-8 Base64 Encoder
function safeBtoa(str: string): string {
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

// Get pristine Function.prototype.toString using an ephemeral iframe to defeat prototype hooks
function getCleanFunctionToString(): () => string {
  try {
    if (typeof document === "undefined" || !document.createElement) {
      return Function.prototype.toString;
    }
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    const root = document.body || document.documentElement;
    if (!root) return Function.prototype.toString;
    root.appendChild(iframe);
    const cleanToString = (iframe.contentWindow as any).Function.prototype.toString;
    root.removeChild(iframe);
    return cleanToString;
  } catch (e) {
    return Function.prototype.toString;
  }
}

export interface SynapseTelemetry {
  mouse_movements: Array<{ x: number; y: number; t: number; r?: number; f?: number }>;
  clicks: Array<{ x: number; y: number; t: number; r?: number }>;
  keystrokes: Array<{ type: string; t: number }>;
  scrolls: Array<{ y: number; t: number }>;
  browser: {
    webdriver: boolean;
    screen_width: number;
    screen_height: number;
    touch_supported: boolean;
    max_touch_points?: number;
    is_plugin_array_fake?: boolean;
    has_webdriver_own_prop?: boolean;
    is_webgl_hooked?: boolean;
    is_canvas_hooked?: boolean;
  };
}

export interface SynapsePayload {
  telemetry?: SynapseTelemetry;
  token?: string;
  pow_salt?: string;
  pow_nonce?: number;
}

export interface UseSynapseShieldOptions {
  apiEndpoint?: string;
  autoChallenge?: boolean;
  moveThrottleMs?: number;
  scrollThrottleMs?: number;
}

export function useSynapseShield(options: UseSynapseShieldOptions = {}) {
  const {
    apiEndpoint = '/api',
    autoChallenge = true,
    moveThrottleMs = 30,
    scrollThrottleMs = 100,
  } = options;

  const currentChallenge = ref<string | null>(null);
  const isReady = ref(false);
  const isSolvingPow = ref(false);

  const telemetry = ref<SynapseTelemetry>({
    mouse_movements: [],
    clicks: [],
    keystrokes: [],
    scrolls: [],
    browser: {
      webdriver: false,
      screen_width: 0,
      screen_height: 0,
      touch_supported: false,
    },
  });

  let lastMoveTime = 0;
  let lastScrollTime = 0;

  const refreshChallenge = async (): Promise<string | null> => {
    if (typeof window === 'undefined') return null;
    try {
      const res = await fetch(`${apiEndpoint}/challenge`);
      if (res.ok) {
        const data = await res.json();
        currentChallenge.value = data.challenge;
        return data.challenge;
      }
    } catch (e) {
      console.warn("[Synapse Shield] Could not fetch challenge, falling back to unsigned mode.");
    }
    return null;
  };

  const solvePow = async (challengeNonce: string, difficulty: number = 2): Promise<{ salt: string; nonce: number } | null> => {
    if (typeof crypto === 'undefined' || !crypto.subtle) return null;
    isSolvingPow.value = true;
    try {
      const targetPrefix = '0'.repeat(difficulty);
      const salt = Math.random().toString(36).substring(2, 10);
      let nonce = 0;
      const encoder = new TextEncoder();

      while (true) {
        // Yield to browser UI thread periodically to avoid jank
        if (nonce % 1000 === 0 && nonce > 0) {
          await new Promise((r) => setTimeout(r, 0));
        }

        const data = encoder.encode(challengeNonce + salt + nonce);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');

        if (hashHex.startsWith(targetPrefix)) {
          return { salt, nonce };
        }
        nonce++;
      }
    } finally {
      isSolvingPow.value = false;
    }
  };

  const reset = () => {
    telemetry.value.mouse_movements = [];
    telemetry.value.clicks = [];
    telemetry.value.keystrokes = [];
    telemetry.value.scrolls = [];
  };

  const getProtectedPayload = (powResult?: { salt: string; nonce: number }): SynapsePayload => {
    if (currentChallenge.value) {
      const envelope: any = {
        challenge: currentChallenge.value,
        telemetry: telemetry.value,
        created_at: Date.now(),
      };
      if (powResult) {
        envelope.pow_salt = powResult.salt;
        envelope.pow_nonce = powResult.nonce;
      }
      return {
        token: safeBtoa(JSON.stringify(envelope)),
        ...(powResult ? { pow_salt: powResult.salt, pow_nonce: powResult.nonce } : {}),
      };
    }
    return { telemetry: telemetry.value };
  };

  // Event handlers
  const handleMouseMove = (e: MouseEvent) => {
    const now = Date.now();
    if (now - lastMoveTime >= moveThrottleMs) {
      telemetry.value.mouse_movements.push({ x: e.clientX, y: e.clientY, t: now });
      lastMoveTime = now;
      if (telemetry.value.mouse_movements.length > 500) telemetry.value.mouse_movements.shift();
    }
  };

  const handleTouchStart = (e: TouchEvent) => {
    if (!e.touches || e.touches.length === 0) return;
    const touch = e.touches[0];
    const now = Date.now();
    const r = touch.radiusX || (touch as any).webkitRadiusX || 0;
    const f = touch.force || 0;
    telemetry.value.mouse_movements.push({
      x: touch.clientX,
      y: touch.clientY,
      t: now,
      r: Math.round(r * 10) / 10,
      f: Math.round(f * 100) / 100,
    });
    lastMoveTime = now;
    if (telemetry.value.mouse_movements.length > 500) telemetry.value.mouse_movements.shift();
  };

  const handleTouchMove = (e: TouchEvent) => {
    if (!e.touches || e.touches.length === 0) return;
    const now = Date.now();
    if (now - lastMoveTime >= moveThrottleMs) {
      const touch = e.touches[0];
      const r = touch.radiusX || (touch as any).webkitRadiusX || 0;
      const f = touch.force || 0;
      telemetry.value.mouse_movements.push({
        x: touch.clientX,
        y: touch.clientY,
        t: now,
        r: Math.round(r * 10) / 10,
        f: Math.round(f * 100) / 100,
      });
      lastMoveTime = now;
      if (telemetry.value.mouse_movements.length > 500) telemetry.value.mouse_movements.shift();
    }
  };

  const handleTouchEnd = (e: TouchEvent) => {
    if (e.changedTouches && e.changedTouches.length > 0) {
      const touch = e.changedTouches[0];
      const r = touch.radiusX || (touch as any).webkitRadiusX || 0;
      telemetry.value.clicks.push({
        x: touch.clientX,
        y: touch.clientY,
        t: Date.now(),
        r: Math.round(r * 10) / 10,
      });
      if (telemetry.value.clicks.length > 50) telemetry.value.clicks.shift();
    }
  };

  const handleClick = (e: MouseEvent) => {
    telemetry.value.clicks.push({ x: e.clientX, y: e.clientY, t: Date.now() });
    if (telemetry.value.clicks.length > 50) telemetry.value.clicks.shift();
  };

  const handleKeyDown = () => {
    telemetry.value.keystrokes.push({ type: "down", t: Date.now() });
    if (telemetry.value.keystrokes.length > 50) telemetry.value.keystrokes.shift();
  };

  const handleKeyUp = () => {
    telemetry.value.keystrokes.push({ type: "up", t: Date.now() });
    if (telemetry.value.keystrokes.length > 50) telemetry.value.keystrokes.shift();
  };

  const handleScroll = () => {
    const now = Date.now();
    if (now - lastScrollTime >= scrollThrottleMs) {
      telemetry.value.scrolls.push({
        y: window.scrollY || document.documentElement.scrollTop,
        t: now,
      });
      lastScrollTime = now;
      if (telemetry.value.scrolls.length > 200) telemetry.value.scrolls.shift();
    }
  };

  onMounted(async () => {
    if (typeof window === 'undefined') return;

    // Advanced Tamper Detection
    const checkWebGLHook = () => {
      try {
        const canvas = document.createElement("canvas");
        const gl = (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")) as any;
        if (gl) {
          const cleanToString = getCleanFunctionToString();
          const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
          if (debugInfo) {
            const getParameterFunc = gl.getParameter;
            const str = cleanToString.call(getParameterFunc);
            if (str.indexOf("[native code]") === -1) return true;
          }
        }
      } catch (e) {}
      return false;
    };

    const checkCanvasHook = () => {
      try {
        const cleanToString = getCleanFunctionToString();
        const str = cleanToString.call(HTMLCanvasElement.prototype.toDataURL);
        if (str.indexOf("[native code]") === -1) return true;
      } catch (e) {}
      return false;
    };

    const isPluginArrayFake = () => {
      try {
        if (navigator.plugins && navigator.plugins.length > 0) {
          if (navigator.plugins.constructor !== PluginArray) return true;
        }
      } catch (e) {}
      return false;
    };

    telemetry.value.browser = {
      webdriver: navigator.webdriver || false,
      screen_width: window.innerWidth || window.screen.width,
      screen_height: window.innerHeight || window.screen.height,
      touch_supported: "ontouchstart" in window || navigator.maxTouchPoints > 0,
      max_touch_points: typeof navigator !== "undefined" ? navigator.maxTouchPoints || 0 : 0,
      is_plugin_array_fake: isPluginArrayFake(),
      has_webdriver_own_prop: Object.prototype.hasOwnProperty.call(navigator, "webdriver"),
      is_webgl_hooked: checkWebGLHook(),
      is_canvas_hooked: checkCanvasHook(),
    };

    if (autoChallenge) {
      await refreshChallenge();
    }

    // Attach passive listeners
    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    window.addEventListener("click", handleClick, { passive: true });
    window.addEventListener("keydown", handleKeyDown, { passive: true });
    window.addEventListener("keyup", handleKeyUp, { passive: true });
    window.addEventListener("scroll", handleScroll, { passive: true });

    isReady.value = true;
  });

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return;

    window.removeEventListener("mousemove", handleMouseMove);
    window.removeEventListener("touchstart", handleTouchStart);
    window.removeEventListener("touchmove", handleTouchMove);
    window.removeEventListener("touchend", handleTouchEnd);
    window.removeEventListener("click", handleClick);
    window.removeEventListener("keydown", handleKeyDown);
    window.removeEventListener("keyup", handleKeyUp);
    window.removeEventListener("scroll", handleScroll);
  });

  return {
    currentChallenge,
    isReady,
    isSolvingPow,
    telemetry,
    refreshChallenge,
    solvePow,
    getProtectedPayload,
    reset,
  };
}
