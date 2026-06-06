import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'theme';

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

/**
 * Theme controller: persists choice, syncs the `data-theme` attribute, and
 * follows the OS preference until the user makes an explicit choice.
 * @returns {{ theme: 'light' | 'dark', toggleTheme: () => void, setTheme: (t: 'light' | 'dark') => void }}
 */
export function useTheme() {
  const [theme, setThemeState] = useState(getInitialTheme);

  // Keep the DOM attribute in sync with state.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Follow OS changes only while the user has not chosen explicitly.
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => {
      let hasExplicit = false;
      try {
        hasExplicit = localStorage.getItem(STORAGE_KEY) !== null;
      } catch {
        hasExplicit = false;
      }
      if (!hasExplicit) setThemeState(e.matches ? 'dark' : 'light');
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  const setTheme = useCallback((next) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore persistence failures */
    }
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return { theme, toggleTheme, setTheme };
}
