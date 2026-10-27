import { useState, useEffect, useCallback, useRef } from 'react';

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

// Get pristine Function.prototype.toString using a transient iframe to defeat prototype hooks
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
    const gl = (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
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
  keystrokes: Array<{ type: string; key?: string; t: number; down?: number; up?: number; duration_ms?: number }>;
  scrolls: Array<{ y: number; t: number }>;
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
}

export function useSynapseShield() {
  const [currentChallenge, setCurrentChallenge] = useState<string | null>(null);
  
  const telemetry = useRef<SynapseTelemetry>({
    mouse_movements: [],
    clicks: [],
    keystrokes: [],
    scrolls: [],
    browser: {
      webdriver: false,
      screen_width: 0,
      screen_height: 0,
      touch_supported: false,
    }
  });

  const lastMoveTime = useRef(0);
  const lastScrollTime = useRef(0);
  const lastMotionTime = useRef(0);
  const lastTouchStartTime = useRef(0);
  const motionSamples = useRef<number[]>([]);

  const moveThrottleMs = 30;
  const scrollThrottleMs = 100;
  const motionThrottleMs = 50;

  const refreshChallenge = useCallback(async () => {
    try {
      const res = await fetch('/api/challenge');
      if (res.ok) {
        const data = await res.json();
        setCurrentChallenge(data.challenge);
      }
    } catch (e) {
      console.warn("Could not fetch challenge, falling back to unsigned mode.");
    }
  }, []);

  useEffect(() => {
    // Advanced Tamper Detection
    const checkWebGLHook = () => {
      try {
        const canvas = document.createElement("canvas");
        const gl = (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")) as WebGLRenderingContext | null;
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

    // Initialize browser info safely on the client
    telemetry.current.browser = {
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
    
    refreshChallenge();

    const handleMouseMove = (e: MouseEvent) => {
      const now = Date.now();
      if (now - lastMoveTime.current >= moveThrottleMs) {
        telemetry.current.mouse_movements.push({ x: e.clientX, y: e.clientY, t: now });
        lastMoveTime.current = now;
        if (telemetry.current.mouse_movements.length > 500) telemetry.current.mouse_movements.shift();
      }
    };

    const handleTouchStart = (e: TouchEvent) => {
      if (!e.touches || e.touches.length === 0) return;
      const touch = e.touches[0];
      const now = Date.now();
      lastTouchStartTime.current = now;
      const rX = touch.radiusX || (touch as any).webkitRadiusX || 0;
      const rY = touch.radiusY || (touch as any).webkitRadiusY || rX;
      const r = (rX + rY) * 0.5;
      const f = touch.force || (touch as any).webkitForce || 0;
      telemetry.current.mouse_movements.push({
        x: touch.clientX,
        y: touch.clientY,
        t: now,
        r: Math.round(r * 1000) / 1000,
        f: Math.round(f * 1000) / 1000,
        source: "touch",
      });
      lastMoveTime.current = now;
      if (telemetry.current.mouse_movements.length > 500) telemetry.current.mouse_movements.shift();
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!e.touches || e.touches.length === 0) return;
      const now = Date.now();
      if (now - lastMoveTime.current >= moveThrottleMs) {
        const touch = e.touches[0];
        const rX = touch.radiusX || (touch as any).webkitRadiusX || 0;
        const rY = touch.radiusY || (touch as any).webkitRadiusY || rX;
        const r = (rX + rY) * 0.5;
        const f = touch.force || (touch as any).webkitForce || 0;
        telemetry.current.mouse_movements.push({
          x: touch.clientX,
          y: touch.clientY,
          t: now,
          r: Math.round(r * 1000) / 1000,
          f: Math.round(f * 1000) / 1000,
          source: "touch",
        });
        lastMoveTime.current = now;
        if (telemetry.current.mouse_movements.length > 500) telemetry.current.mouse_movements.shift();
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      if (e.changedTouches && e.changedTouches.length > 0) {
        const touch = e.changedTouches[0];
        const now = Date.now();
        const rX = touch.radiusX || (touch as any).webkitRadiusX || 0;
        const rY = touch.radiusY || (touch as any).webkitRadiusY || rX;
        const r = (rX + rY) * 0.5;
        const tapDuration = lastTouchStartTime.current > 0 ? Math.max(1, now - lastTouchStartTime.current) : 0;
        telemetry.current.clicks.push({
          x: touch.clientX,
          y: touch.clientY,
          t: now,
          r: Math.round(r * 1000) / 1000,
          tap_duration_ms: tapDuration,
          source: "touch",
        });
        if (telemetry.current.clicks.length > 50) telemetry.current.clicks.shift();
      }
    };

    const handleDeviceMotion = (e: DeviceMotionEvent) => {
      const now = Date.now();
      if (now - lastMotionTime.current < motionThrottleMs) return;
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
        motionSamples.current.push(mag);
        lastMotionTime.current = now;
        if (motionSamples.current.length > 40) motionSamples.current.shift();
      }
    };

    const handleClick = (e: MouseEvent) => {
      const now = Date.now();
      if (lastTouchStartTime.current > 0 && now - lastTouchStartTime.current < 800) {
        return;
      }
      telemetry.current.clicks.push({ x: e.clientX, y: e.clientY, t: now });
      if (telemetry.current.clicks.length > 50) telemetry.current.clicks.shift();
    };

    const activeKeys: Record<string, number> = {};
    const handleKeyDown = (e: KeyboardEvent) => {
      const keyName = e.key ? e.key.toLowerCase() : (e.code || "unknown");
      const now = Date.now();
      if (!activeKeys[keyName]) {
        activeKeys[keyName] = now;
      }
      telemetry.current.keystrokes.push({ type: "down", key: keyName, t: now });
      if (telemetry.current.keystrokes.length > 50) telemetry.current.keystrokes.shift();
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      const keyName = e.key ? e.key.toLowerCase() : (e.code || "unknown");
      const now = Date.now();
      const downTime = activeKeys[keyName];
      delete activeKeys[keyName];
      const duration = downTime ? (now - downTime) : 0;
      telemetry.current.keystrokes.push({
        type: "up",
        key: keyName,
        t: now,
        down: downTime || now,
        up: now,
        duration_ms: duration,
      });
      if (telemetry.current.keystrokes.length > 50) telemetry.current.keystrokes.shift();
    };

    const handleScroll = () => {
      const now = Date.now();
      if (now - lastScrollTime.current >= scrollThrottleMs) {
        telemetry.current.scrolls.push({
          y: window.scrollY || document.documentElement.scrollTop,
          t: now,
        });
        lastScrollTime.current = now;
        if (telemetry.current.scrolls.length > 200) telemetry.current.scrolls.shift();
      }
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    window.addEventListener("devicemotion", handleDeviceMotion, { passive: true });
    window.addEventListener("click", handleClick, { passive: true });
    window.addEventListener("keydown", handleKeyDown, { passive: true });
    window.addEventListener("keyup", handleKeyUp, { passive: true });
    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("devicemotion", handleDeviceMotion);
      window.removeEventListener("click", handleClick);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("scroll", handleScroll);
    };
  }, [refreshChallenge]);

  const reset = useCallback(() => {
    telemetry.current.mouse_movements = [];
    telemetry.current.clicks = [];
    telemetry.current.keystrokes = [];
    telemetry.current.scrolls = [];
    motionSamples.current = [];
    lastTouchStartTime.current = 0;
  }, []);

  const getProtectedPayload = useCallback((): SynapsePayload => {
    const n = motionSamples.current.length;
    if (n >= 2) {
      const mean = motionSamples.current.reduce((a, b) => a + b, 0) / n;
      const variance = motionSamples.current.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / n;
      telemetry.current.browser.motion_variance = Math.round(variance * 1000000) / 1000000;
    } else {
      telemetry.current.browser.motion_variance = 0;
    }

    if (currentChallenge) {
      const envelope = {
        challenge: currentChallenge,
        telemetry: telemetry.current,
        created_at: Date.now(),
      };
      return { token: safeBtoa(JSON.stringify(envelope)) };
    }
    return { telemetry: telemetry.current };
  }, [currentChallenge]);

  return { getProtectedPayload, refreshChallenge, reset };
}
