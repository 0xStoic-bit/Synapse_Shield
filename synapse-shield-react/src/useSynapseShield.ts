import { useState, useEffect, useCallback, useRef } from 'react';

export interface SynapseTelemetry {
  mouse_movements: Array<{ x: number; y: number; t: number }>;
  clicks: Array<{ x: number; y: number; t: number }>;
  keystrokes: Array<{ type: string; t: number }>;
  scrolls: Array<{ y: number; t: number }>;
  browser: {
    webdriver: boolean;
    screen_width: number;
    screen_height: number;
    touch_supported: boolean;
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

  const moveThrottleMs = 30;
  const scrollThrottleMs = 100;

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
    // Initialize browser info safely on the client
    telemetry.current.browser = {
      webdriver: navigator.webdriver || false,
      screen_width: window.innerWidth || window.screen.width,
      screen_height: window.innerHeight || window.screen.height,
      touch_supported: "ontouchstart" in window || navigator.maxTouchPoints > 0,
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

    const handleClick = (e: MouseEvent) => {
      telemetry.current.clicks.push({ x: e.clientX, y: e.clientY, t: Date.now() });
      if (telemetry.current.clicks.length > 50) telemetry.current.clicks.shift();
    };

    const handleKeyDown = () => {
      telemetry.current.keystrokes.push({ type: "down", t: Date.now() });
      if (telemetry.current.keystrokes.length > 50) telemetry.current.keystrokes.shift();
    };

    const handleKeyUp = () => {
      telemetry.current.keystrokes.push({ type: "up", t: Date.now() });
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
    window.addEventListener("click", handleClick, { passive: true });
    window.addEventListener("keydown", handleKeyDown, { passive: true });
    window.addEventListener("keyup", handleKeyUp, { passive: true });
    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
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
  }, []);

  const getProtectedPayload = useCallback((): SynapsePayload => {
    if (currentChallenge) {
      const envelope = {
        challenge: currentChallenge,
        telemetry: telemetry.current,
        created_at: Date.now(),
      };
      return { token: btoa(JSON.stringify(envelope)) };
    }
    return { telemetry: telemetry.current };
  }, [currentChallenge]);

  return { getProtectedPayload, refreshChallenge, reset };
}
