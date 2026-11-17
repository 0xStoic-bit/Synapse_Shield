import { ref, onMounted, onBeforeUnmount } from 'vue';
import {
  MIN_CHALLENGE_AGE_MS,
  alignForRetry,
  challengeTimestamp,
  fitTelemetry,
  inputEventKind,
  retryWaitMs,
} from './timing';
import type { SynapseInputKind } from './timing';

declare const Buffer: any;

// Safe UTF-8 Base64 Encoder (SSR Safe)
function safeBtoa(str: string): string {
  try {
    if (typeof window !== "undefined" && typeof window.btoa === "function") {
      return window.btoa(str);
    }
    if (typeof Buffer !== "undefined") {
      return Buffer.from(str).toString("base64");
    }
    return "";
  } catch (e) {
    if (typeof window !== "undefined" && typeof window.btoa === "function") {
      return window.btoa(
        encodeURIComponent(str).replace(/%([0-9A-F]{2})/g, function (_, p1) {
          return String.fromCharCode(parseInt(p1, 16));
        })
      );
    }
    return typeof Buffer !== "undefined" ? Buffer.from(str).toString("base64") : "";
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

function getWebGLRenderer(): string {
  try {
    if (typeof document === "undefined" || !document.createElement) return "";
    const canvas = document.createElement("canvas");
    const gl = (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")) as any;
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

export interface SynapseTelemetry {
  mouse_movements: Array<{ x: number; y: number; t: number; r?: number; f?: number; source?: string }>;
  clicks: Array<{ x: number; y: number; t: number; r?: number; tap_duration_ms?: number; source?: string }>;
  keystrokes: Array<{ type: string; key?: string; t: number; down?: number; up?: number; duration_ms?: number; is_freq_digraph?: boolean }>;
  scrolls: Array<{ y: number; t: number }>;
  /** Zero-PII non-keyboard text entry (autofill, paste, IME, typed insertions): kind and time only, never content. */
  input_events: Array<{ t: number; kind: SynapseInputKind }>;
  browser: {
    webdriver: boolean;
    screen_width: number;
    screen_height: number;
    device_pixel_ratio?: number;
    touch_supported: boolean;
    max_touch_points?: number;
    motion_variance?: number;
    webgl_renderer?: string;
    orientation?: string;
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

const FREQUENT_DIGRAPHS = new Set([
  "th", "er", "on", "an", "re", "he", "in", "ed", "nd", "ha",
  "at", "en", "es", "of", "or", "nt", "ea", "ti", "to", "it",
  "st", "io", "le", "is", "ou", "ar", "as", "de", "rt", "ve",
  "er", "en", "de", "an", "ar", "in", "la", "le",
  "ik", "ak", "el", "al", "ma", "me", "ba", "ka"
]);

// Zero-PII: only standard named keys (UI Events "key" values such as "Enter", "ArrowLeft",
// "Unidentified", "F1") may leave the browser by name. Anything else is printed text and is
// masked — including values longer than one UTF-16 unit (emoji, ligature keys such as "لا",
// combining sequences, and Turkish "İ" whose lower-case form is two code units).
const NAMED_KEYS: ReadonlySet<string> = new Set([
  "enter", "backspace", "tab", "shift", "control", "alt", "altgraph", "meta",
  "capslock", "escape", "arrowleft", "arrowright", "arrowup", "arrowdown", "home", "end",
  "pageup", "pagedown", "insert", "delete", "dead", "process", "unidentified", "numlock",
  "scrolllock", "contextmenu", "pause", "printscreen", "clear", "compose", "f1", "f2",
  "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10",
  "f11", "f12", "f13", "f14", "f15", "f16", "f17", "f18",
  "f19", "f20", "f21", "f22", "f23", "f24",
]);
export function telemetryKeyName(key: string | undefined | null, isSensitive: boolean): string {
  if (!key) return "unknown";
  if (isSensitive || !NAMED_KEYS.has(key.toLowerCase())) return "masked";
  return key.toLowerCase();
}

function isSensitiveInput(target: any): boolean {
  if (!target) return false;
  try {
    const type = (target.getAttribute && target.getAttribute("type")) || target.type || "";
    const name = (target.getAttribute && target.getAttribute("name")) || target.name || "";
    const id = target.id || "";
    const autocomplete = (target.getAttribute && target.getAttribute("autocomplete")) || target.autocomplete || "";
    const sensitiveRegex = /password|passcode|secret|pin|cvv|cvc|card|credit|security_code|token/i;
    const tLower = String(type).toLowerCase();
    const aLower = String(autocomplete).toLowerCase();
    if (
      tLower === "password" ||
      aLower === "current-password" ||
      aLower === "new-password" ||
      aLower === "cc-number" ||
      aLower === "cc-csc"
    ) {
      return true;
    }
    if (sensitiveRegex.test(String(name)) || sensitiveRegex.test(String(id))) {
      return true;
    }
  } catch (e) {}
  return false;
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
    input_events: [],
    browser: {
      webdriver: false,
      screen_width: 0,
      screen_height: 0,
      touch_supported: false,
    },
  });

  let lastMoveTime = 0;
  let lastScrollTime = 0;
  let lastMotionTime = 0;
  let lastTouchStartTime = 0;
  let motionSamples: number[] = [];
  const activeKeys: Record<string, { down: number; isFreq: boolean }> = {};
  let lastRawKey = "";

  // Local time at which the current challenge arrived (its age decides which telemetry the server accepts).
  let challengeFetchedAt = 0;

  const fetchChallenge = async (): Promise<string | null> => {
    if (typeof window === 'undefined') return null;
    try {
      const res = await fetch(`${apiEndpoint}/challenge`);
      if (res.ok) {
        const data = await res.json();
        return typeof data.challenge === "string" ? data.challenge : null;
      }
    } catch (e) {
      console.warn("[Synapse Shield] Could not fetch challenge, falling back to unsigned mode.");
    }
    return null;
  };

  const refreshChallenge = async (): Promise<string | null> => {
    const challenge = await fetchChallenge();
    if (challenge) {
      currentChallenge.value = challenge;
      challengeFetchedAt = Date.now();
    }
    return challenge;
  };

  /**
   * Solves the server's proof-of-work: find `nonce` so that sha256(powSalt + nonce) starts with `difficulty`
   * zeros. `powSalt` MUST be the signed `pow_salt` from the `challenge_required` response (the server verifies
   * its HMAC, expiry and difficulty); a client-generated salt can never be accepted.
   */
  const solvePow = async (powSalt: string, difficulty: number = 4): Promise<{ salt: string; nonce: number } | null> => {
    if (typeof crypto === 'undefined' || !crypto.subtle) return null;
    isSolvingPow.value = true;
    try {
      const targetPrefix = '0'.repeat(difficulty);
      const salt = powSalt;
      let nonce = 0;
      const maxAttempts = 20_000_000;
      const encoder = new TextEncoder();

      while (nonce < maxAttempts) {
        // Yield to browser UI thread periodically to avoid jank
        if (nonce % 1000 === 0 && nonce > 0) {
          await new Promise((r) => setTimeout(r, 0));
        }

        const data = encoder.encode(salt + nonce);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');

        if (hashHex.startsWith(targetPrefix)) {
          return { salt, nonce };
        }
        nonce++;
      }
      return null;
    } finally {
      isSolvingPow.value = false;
    }
  };

  const reset = () => {
    telemetry.value.mouse_movements = [];
    telemetry.value.clicks = [];
    telemetry.value.keystrokes = [];
    telemetry.value.scrolls = [];
    telemetry.value.input_events = [];
    motionSamples = [];
    lastTouchStartTime = 0;
  };

  const getProtectedPayload = (powResult?: { salt: string; nonce: number }): SynapsePayload => {
    const n = motionSamples.length;
    if (n >= 2) {
      const mean = motionSamples.reduce((a, b) => a + b, 0) / n;
      const variance = motionSamples.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / n;
      telemetry.value.browser.motion_variance = Math.round(variance * 1000000) / 1000000;
    } else {
      telemetry.value.browser.motion_variance = 0;
    }

    if (currentChallenge.value) {
      // Only the events this challenge can vouch for: older ones (long SPA session, renewed challenge) would make
      // the server reject the whole token as Stale Telemetry / Time Travel.
      const envelope: any = {
        challenge: currentChallenge.value,
        telemetry: fitTelemetry(telemetry.value, challengeTimestamp(currentChallenge.value), Date.now() - challengeFetchedAt),
        created_at: Date.now(),
      };
      if (powResult) {
        envelope.pow_salt = powResult.salt;
        envelope.pow_nonce = powResult.nonce;
      }
      // The challenge is single-use: consume it and fetch the next one in the background so a second
      // submission in the same SPA session does not replay it (HTTP 403).
      currentChallenge.value = null;
      void refreshChallenge();
      return {
        token: safeBtoa(JSON.stringify(envelope)),
        ...(powResult ? { pow_salt: powResult.salt, pow_nonce: powResult.nonce } : {}),
      };
    }
    return { telemetry: telemetry.value };
  };

  /**
   * POSTs a protected request and transparently handles the gray-area proof-of-work challenge (parity with the
   * React SDK). `buildBody` receives the payload (`token`, plus `pow_salt`/`pow_nonce` on the retry) and returns the
   * JSON body; put `pow_salt` and `pow_nonce` at the top level of that body, where the server middleware reads them.
   * On HTTP 429 `challenge_required` it fetches a fresh challenge, solves the PoW and retries exactly ONCE.
   * The final Response (including a second 429) is returned as is; there is no further retry.
   */
  const submitProtected = async (
    url: string,
    buildBody: (payload: SynapsePayload) => unknown,
    init: RequestInit = {},
  ): Promise<Response> => {
    const send = (payload: SynapsePayload): Promise<Response> => {
      const headers = new Headers(init.headers);
      if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      return fetch(url, {
        ...init,
        method: init.method || "POST",
        headers,
        body: JSON.stringify(buildBody(payload)),
      });
    };
    const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

    // A missing or nearly-expired challenge (60 s lifetime) is renewed first; any challenge younger than the
    // server's 1.5 s minimum is aged first. getProtectedPayload() then drops events older than its window.
    if (!currentChallenge.value || Date.now() - challengeFetchedAt > 45000) {
      await refreshChallenge();
    }
    const age = Date.now() - challengeFetchedAt;
    if (currentChallenge.value && age < MIN_CHALLENGE_AGE_MS) await sleep(MIN_CHALLENGE_AGE_MS - age);

    const first = await send(getProtectedPayload());
    if (first.status !== 429) {
      reset();
      return first;
    }

    let body: any = null;
    try {
      body = await first.clone().json();
    } catch (e) {}
    if (!body || body.status !== "challenge_required" || typeof body.pow_salt !== "string" || !body.pow_salt) {
      reset();
      return first;
    }

    // The first token consumed our challenge: fetch a fresh one while the PoW is solved.
    let freshAt = 0;
    const [fresh, solution] = await Promise.all([
      fetchChallenge().then((c) => {
        freshAt = Date.now();
        return c;
      }),
      solvePow(body.pow_salt, Number(body.pow_difficulty) || 4),
    ]);
    if (!fresh || !solution) return first; // cannot comply (no Web Crypto / no challenge); caller sees the 429

    // Server checks: token age >= 1.5 s and telemetry span <= token age + 0.5 s. Wait briefly (<= 3 s; <= 8 s only
    // to keep the last 3 mouse points), then send the most recent window that fits, shifted past challenge_ts.
    const remaining = retryWaitMs(telemetry.value) - (Date.now() - freshAt);
    if (remaining > 0) await sleep(remaining);
    alignForRetry(telemetry.value, challengeTimestamp(fresh) ?? freshAt, Date.now() - freshAt);
    // Re-assert our challenge: a background refresh started by the first payload may have replaced it.
    currentChallenge.value = fresh;
    challengeFetchedAt = freshAt;

    const second = await send(getProtectedPayload(solution));
    reset();
    return second;
  };

  // Non-keyboard text entry: counted in input_events so key_count is never inflated (Zero-PII: no content read).
  const pushInputEvent = (kind: SynapseInputKind) => {
    telemetry.value.input_events.push({ t: Date.now(), kind });
    if (telemetry.value.input_events.length > 50) telemetry.value.input_events.shift();
  };
  const handleInput = (e: Event) => {
    const kind = inputEventKind(e);
    if (kind) pushInputEvent(kind);
  };
  const handlePaste = () => pushInputEvent("paste");
  const handleCompositionEnd = () => pushInputEvent("ime");

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
    lastTouchStartTime = now;
    const rX = touch.radiusX || (touch as any).webkitRadiusX || 0;
    const rY = touch.radiusY || (touch as any).webkitRadiusY || rX;
    const r = (rX + rY) * 0.5;
    const f = touch.force || (touch as any).webkitForce || 0;
    telemetry.value.mouse_movements.push({
      x: touch.clientX,
      y: touch.clientY,
      t: now,
      r: Math.round(r * 1000) / 1000,
      f: Math.round(f * 1000) / 1000,
      source: "touch",
    });
    lastMoveTime = now;
    if (telemetry.value.mouse_movements.length > 500) telemetry.value.mouse_movements.shift();
  };

  const handleTouchMove = (e: TouchEvent) => {
    if (!e.touches || e.touches.length === 0) return;
    const now = Date.now();
    if (now - lastMoveTime >= moveThrottleMs) {
      const touch = e.touches[0];
      const rX = touch.radiusX || (touch as any).webkitRadiusX || 0;
      const rY = touch.radiusY || (touch as any).webkitRadiusY || rX;
      const r = (rX + rY) * 0.5;
      const f = touch.force || (touch as any).webkitForce || 0;
      telemetry.value.mouse_movements.push({
        x: touch.clientX,
        y: touch.clientY,
        t: now,
        r: Math.round(r * 1000) / 1000,
        f: Math.round(f * 1000) / 1000,
        source: "touch",
      });
      lastMoveTime = now;
      if (telemetry.value.mouse_movements.length > 500) telemetry.value.mouse_movements.shift();
    }
  };

  const handleTouchEnd = (e: TouchEvent) => {
    if (e.changedTouches && e.changedTouches.length > 0) {
      const touch = e.changedTouches[0];
      const now = Date.now();
      const rX = touch.radiusX || (touch as any).webkitRadiusX || 0;
      const rY = touch.radiusY || (touch as any).webkitRadiusY || rX;
      const r = (rX + rY) * 0.5;
      const tapDuration = lastTouchStartTime > 0 ? Math.max(1, now - lastTouchStartTime) : 0;
      telemetry.value.clicks.push({
        x: touch.clientX,
        y: touch.clientY,
        t: now,
        r: Math.round(r * 1000) / 1000,
        tap_duration_ms: tapDuration,
        source: "touch",
      });
      if (telemetry.value.clicks.length > 50) telemetry.value.clicks.shift();
    }
  };

  const handleDeviceMotion = (e: DeviceMotionEvent) => {
    const now = Date.now();
    if (now - lastMotionTime < 50) return;
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
      motionSamples.push(mag);
      lastMotionTime = now;
      if (motionSamples.length > 40) motionSamples.shift();
    }
  };

  const handleClick = (e: MouseEvent) => {
    const now = Date.now();
    if (lastTouchStartTime > 0 && now - lastTouchStartTime < 800) {
      return;
    }
    telemetry.value.clicks.push({ x: e.clientX, y: e.clientY, t: now });
    if (telemetry.value.clicks.length > 50) telemetry.value.clicks.shift();
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    const isSens = isSensitiveInput(e.target);
    const rawKey = e.key ? (e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase() || e.code || "unknown") : "unknown";
    const lookupId = e.code || rawKey;
    const now = Date.now();

    let isFreq = false;
    if (lastRawKey && rawKey && lastRawKey.length === 1 && rawKey.length === 1) {
      isFreq = FREQUENT_DIGRAPHS.has(lastRawKey + rawKey);
    }
    lastRawKey = rawKey;

    const keyName = telemetryKeyName(e.key, isSens);

    if (!activeKeys[lookupId]) {
      activeKeys[lookupId] = { down: now, isFreq };
    }
    telemetry.value.keystrokes.push({
      type: "down",
      key: keyName,
      t: now,
      is_freq_digraph: isFreq,
    });
    if (telemetry.value.keystrokes.length > 50) telemetry.value.keystrokes.shift();
  };

  const handleKeyUp = (e: KeyboardEvent) => {
    const isSens = isSensitiveInput(e.target);
    const rawKey = e.key ? (e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase() || e.code || "unknown") : "unknown";
    const lookupId = e.code || rawKey;
    const keyName = telemetryKeyName(e.key, isSens);
    const now = Date.now();
    const keyState = activeKeys[lookupId];
    delete activeKeys[lookupId];
    const downTime = keyState ? keyState.down : now;
    const isFreq = keyState ? keyState.isFreq : false;
    const duration = keyState ? (now - downTime) : 0;
    telemetry.value.keystrokes.push({
      type: "up",
      key: keyName,
      t: now,
      down: downTime,
      up: now,
      duration_ms: duration,
      is_freq_digraph: isFreq,
    });
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
      device_pixel_ratio: window.devicePixelRatio || 1,
      touch_supported: "ontouchstart" in window || navigator.maxTouchPoints > 0,
      max_touch_points: typeof navigator !== "undefined" ? navigator.maxTouchPoints || 0 : 0,
      motion_variance: 0,
      webgl_renderer: getWebGLRenderer(),
      orientation: (window.screen && (window.screen as any).orientation && (window.screen as any).orientation.type) ? (window.screen as any).orientation.type : "",
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
    window.addEventListener("devicemotion", handleDeviceMotion, { passive: true });
    window.addEventListener("click", handleClick, { passive: true });
    window.addEventListener("keydown", handleKeyDown, { passive: true });
    window.addEventListener("keyup", handleKeyUp, { passive: true });
    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("input", handleInput, { passive: true, capture: true });
    window.addEventListener("paste", handlePaste, { passive: true, capture: true });
    window.addEventListener("compositionend", handleCompositionEnd, { passive: true, capture: true });

    isReady.value = true;
  });

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return;

    window.removeEventListener("mousemove", handleMouseMove);
    window.removeEventListener("touchstart", handleTouchStart);
    window.removeEventListener("touchmove", handleTouchMove);
    window.removeEventListener("touchend", handleTouchEnd);
    window.removeEventListener("devicemotion", handleDeviceMotion);
    window.removeEventListener("click", handleClick);
    window.removeEventListener("keydown", handleKeyDown);
    window.removeEventListener("keyup", handleKeyUp);
    window.removeEventListener("scroll", handleScroll);
    window.removeEventListener("input", handleInput, true);
    window.removeEventListener("paste", handlePaste, true);
    window.removeEventListener("compositionend", handleCompositionEnd, true);
  });

  return {
    currentChallenge,
    isReady,
    isSolvingPow,
    telemetry,
    refreshChallenge,
    solvePow,
    getProtectedPayload,
    submitProtected,
    reset,
  };
}
