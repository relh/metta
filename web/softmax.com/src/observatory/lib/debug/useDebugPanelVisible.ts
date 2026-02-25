"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "observatory:debugPanelVisible";

let visible = false;

// Load from localStorage on client
if (typeof window !== "undefined") {
  const stored = localStorage.getItem(STORAGE_KEY);
  visible = stored === "true";
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return visible;
}

function getServerSnapshot() {
  return false;
}

export function useDebugPanelVisible() {
  const isVisible = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );

  const toggle = useCallback(() => {
    visible = !visible;
    localStorage.setItem(STORAGE_KEY, String(visible));
    listeners.forEach((listener) => listener());
  }, []);

  return { isVisible, toggle };
}
