import { useState, useEffect, useRef, useCallback } from 'react';

const STORAGE_KEY = 'theme';
const THEME_EVENT = 'viviendapp:theme';

/**
 * Reads the persisted theme, falling back to the OS preference.
 * @returns {'light' | 'dark'}
 */
function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    /* localStorage unavailable (private mode, SSR) — fall through */
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

function broadcast(next) {
  try { localStorage.setItem(STORAGE_KEY, next); } catch { /* ignore */ }
  // dispatchEvent is synchronous — all listeners (including this instance) fire before returning.
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: next }));
}

/**
 * Theme controller: persists choice, syncs the `data-theme` attribute, and
 * follows the OS preference until the user makes an explicit choice.
 * @returns {{ theme: 'light' | 'dark', toggleTheme: () => void, setTheme: (t: 'light' | 'dark') => void }}
 */
export function useTheme() {
  const [theme, setThemeState] = useState(getInitialTheme);
  // Ref tracks current theme so toggleTheme stays stable (no dep on `theme`).
  const themeRef = useRef(theme);
  themeRef.current = theme;

  // Keep the DOM attribute in sync with state.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Sync with other useTheme() instances in the same tab via custom event.
  // All state updates flow through this listener — setTheme/toggleTheme only broadcast.
  useEffect(() => {
    const handler = (e) => setThemeState(e.detail);
    window.addEventListener(THEME_EVENT, handler);
    return () => window.removeEventListener(THEME_EVENT, handler);
  }, []);

  // Follow OS changes only while the user has not chosen explicitly.
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => {
      let hasExplicit = false;
      try { hasExplicit = localStorage.getItem(STORAGE_KEY) !== null; } catch {}
      if (!hasExplicit) setThemeState(e.matches ? 'dark' : 'light');
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  const setTheme = useCallback((next) => { broadcast(next); }, []);

  const toggleTheme = useCallback(() => {
    broadcast(themeRef.current === 'dark' ? 'light' : 'dark');
  }, []); // themeRef is a stable object; current value read at call time

  return { theme, toggleTheme, setTheme };
}
