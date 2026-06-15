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
import { useQueryClient } from '@tanstack/react-query';
import { authApi, getActiveBranchId, setActiveBranchId } from './api';

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
  // Sucursal activa (Enterprise): id del tenant hijo al que "entró" el dueño, o null
  // (vista consolidada). Espejo en React del módulo de api.js (que lo manda en el header).
  const [activeBranch, setActiveBranch] = useState(() => getActiveBranchId());
  const queryClient = useQueryClient();

  const reconnectTimer = useRef(null);
  // Identidad de la última sesión cargada (account.id). Sirve para detectar un
  // cambio de usuario (logout → login con otra cuenta) y purgar el estado viejo
  // ANTES de que las queries del nuevo usuario rendericen. null = primera carga.
  const lastAccountId = useRef(null);

  // Distingue "no autenticado" (401, tras fallar el refresh) de "no hay red"
  // (cold-start de Render / 5xx / timeout). Solo el primero manda al login; el
  // segundo reintenta con backoff y NO expulsa a un usuario con cookies válidas.
  const loadMe = useCallback(async (attempt = 0) => {
    try {
      const data = await authApi.me();

      // ── Guard de cambio de sesión ────────────────────────────────────────
      // Si la identidad cargada difiere de la anterior conocida (y había una
      // real, no la primera carga), purgamos TODA la caché de React Query para
      // que no se vea data del usuario previo mientras refrescan las queries.
      const newAccountId = data?.account?.id ?? null;
      const prevAccountId = lastAccountId.current;
      if (prevAccountId !== null && newAccountId !== prevAccountId) {
        queryClient.clear();
      }
      lastAccountId.current = newAccountId;

      // ── Reconciliación de sucursal activa ────────────────────────────────
      // Solo una org puede tener sucursal activa, y solo entre las suyas. Si la
      // sucursal persistida (header X-Branch-Id) no es válida para ESTA sesión,
      // la limpiamos ANTES de renderizar para no scopear queries a un tenant ajeno.
      const persistedBranch = getActiveBranchId();
      if (persistedBranch) {
        const validIds = data?.scope === 'org'
          ? (data.branches || []).map(b => b.id)
          : [];
        if (!validIds.includes(persistedBranch)) {
          setActiveBranchId(null);   // limpia módulo api.js + localStorage
          setActiveBranch(null);     // espejo en React
        }
      }

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
  }, [queryClient]);

  useEffect(() => {
    loadMe();
    return () => { if (reconnectTimer.current) clearTimeout(reconnectTimer.current); };
  }, [loadMe]);

  // Cambiar de sucursal (o volver a "Todas"): persiste el id (header X-Branch-Id en
  // api.js) y limpia la caché de React Query para que TODO el dashboard se recargue
  // scopeado al nuevo tenant. id=null → vista consolidada de la org.
  const selectBranch = useCallback((id) => {
    setActiveBranchId(id);
    setActiveBranch(id || null);
    queryClient.clear();
  }, [queryClient]);

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
    setActiveBranchId(null);
    setActiveBranch(null);
    setMe(null);
    setStatus('anon');
    lastAccountId.current = null;   // próxima carga = "primera", no dispara clear espurio
    queryClient.clear();            // purga la caché del usuario que se va
    // Login canónico en la landing: tras cerrar sesión volvemos allá (si está
    // configurado). El guard anti-loop de main.jsx no aplica: esto es intencional.
    const loginUrl = import.meta.env.VITE_LOGIN_URL || '';
    if (loginUrl) window.location.assign(loginUrl);
  }, [queryClient]);

  const value = { status, me, login, logout, reload: loadMe, activeBranch, selectBranch };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
