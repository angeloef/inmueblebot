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
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authApi } from './api';

const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  return ctx;
}

export function AuthProvider({ children }) {
  const [status, setStatus] = useState('loading');
  const [me, setMe] = useState(null);

  const loadMe = useCallback(async () => {
    try {
      const data = await authApi.me();
      setMe(data);
      setStatus('authed');
    } catch {
      setMe(null);
      setStatus('anon');
    }
  }, []);

  useEffect(() => { loadMe(); }, [loadMe]);

  // El refresh falló (sesión realmente expirada) → volver al login.
  useEffect(() => {
    const onExpired = () => { setMe(null); setStatus('anon'); };
    window.addEventListener('auth:expired', onExpired);
    return () => window.removeEventListener('auth:expired', onExpired);
  }, []);

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
