/**
 * auth.jsx — Sesión del dashboard (Fase 4).
 *
 * El JWT vive en una cookie httpOnly (mismo origen vía el proxy /api); el browser
 * nunca lo ve en JS. Este provider solo conoce el estado de la sesión:
 *   - 'loading' → todavía consultando GET /auth/me
 *   - 'authed'  → hay sesión válida (guarda los datos de /auth/me en `me`)
 *   - 'anon'    → sin sesión → se muestra el login
 *
 * Escucha el evento `auth:expired` que emite el interceptor de api.js cuando un
 * 401 no se pudo refrescar, para volver al login sin recargar la página.
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { authApi } from './api';

// Refresh proactivo: el access token vive 60 min; refrescamos a los 50 para que el
// usuario nunca tope un 401 visible mientras la pestaña está abierta.
const PROACTIVE_REFRESH_MS = 50 * 60 * 1000;
// Reintentos de loadMe ante error de red/cold-start (NO 401): backoff exponencial.
const MAX_RECONNECT_ATTEMPTS = 4;

const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  return ctx;
}

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading');
  const [me, setMe] = useState(null);

  const reconnectTimer = useRef(null);

  // Distingue "no autenticado" (401, tras fallar el refresh) de "no hay red"
  // (cold-start de Render / 5xx / timeout). Solo el primero manda al login; el
  // segundo reintenta con backoff y NO expulsa a un usuario con cookies válidas.
  const loadMe = useCallback(async (attempt = 0) => {
    try {
      const data = await authApi.me();
      setMe(data);
      setStatus('authed');
    } catch (err) {
      const code = err?.response?.status;
      if (code === 401 || code === 403) {
        // El interceptor de api.js ya intentó refrescar; si llega 401/403, la
        // sesión es realmente inválida.
        setMe(null);
        setStatus('anon');
        return;
      }
      // Error de red / 5xx / cold start → reintentar, no ir al login.
      if (attempt < MAX_RECONNECT_ATTEMPTS) {
        setStatus('reconnecting');
        const delay = Math.min(2000 * 2 ** attempt, 15000);
        reconnectTimer.current = setTimeout(() => loadMe(attempt + 1), delay);
      } else {
        setMe(null);
        setStatus('anon');
      }
    }
  }, []);

  useEffect(() => {
    loadMe();
    return () => { if (reconnectTimer.current) clearTimeout(reconnectTimer.current); };
  }, [loadMe]);

  // El refresh falló (sesión realmente expirada) → volver al login.
  useEffect(() => {
    const onExpired = () => { setMe(null); setStatus('anon'); };
    window.addEventListener('auth:expired', onExpired);
    return () => window.removeEventListener('auth:expired', onExpired);
  }, []);

  // Refresh proactivo: mientras hay sesión, refrescamos cada 50 min y también al
  // volver el foco a una pestaña que durmió (el access pudo haber expirado).
  useEffect(() => {
    if (status !== 'authed') return undefined;
    const tick = () => { authApi.refresh().catch(() => { /* el interceptor maneja el 401 */ }); };
    const interval = setInterval(tick, PROACTIVE_REFRESH_MS);
    const onVisible = () => { if (document.visibilityState === 'visible') tick(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [status]);

  const login = useCallback(async (email, password) => {
    await authApi.login(email, password);   // setea las cookies httpOnly
    await loadMe();
  }, [loadMe]);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch { /* la sesión local se limpia igual */ }
    setMe(null);
    setStatus('anon');
  }, []);

  const value = { status, me, login, logout, reload: loadMe };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
