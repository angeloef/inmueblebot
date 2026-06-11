/**
 * Server-side session + auth-cookie helpers.
 *
 * The JWT pair is kept in httpOnly cookies so the browser JS never sees a token
 * (XSS-resistant). Cookie names + flags are kept in sync with middleware.ts.
 *
 * - setAuthCookies / clearAuthCookies: only callable from Route Handlers or
 *   Server Actions (they mutate cookies).
 * - getSessionReadOnly: safe in Server Components — it only READS the access
 *   cookie and fetches /auth/me. It never refreshes/sets cookies (that's the
 *   middleware's job), so it stays valid in a render context.
 */
import { cookies } from 'next/headers'
import { apiPost } from './api'
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  ACCESS_MAX_AGE,
  REFRESH_MAX_AGE,
} from './cookies'

const API_BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

// URL que navega el BROWSER (no el server): siempre la pública.
const PUBLIC_API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.API_URL ??
  'http://localhost:8000'

/**
 * Pide un código de handoff (un solo uso, 60s) y arma la URL que abre la sesión
 * en el dashboard (origen de la API). `next` es un deep-link relativo del
 * dashboard (ej. "/dashboard/clientes") — el backend lo valida igual.
 * Devuelve null si el backend no lo pudo emitir (el caller cae al redirect viejo).
 */
export async function buildHandoffUrl(
  accessToken: string,
  next?: string | null,
): Promise<string | null> {
  const result = await apiPost<{ code: string }>(
    '/auth/handoff-code',
    { next: next ?? null },
    accessToken,
  )
  if (!result.ok || !result.data?.code) return null
  return `${PUBLIC_API_BASE}/auth/handoff?code=${encodeURIComponent(result.data.code)}`
}

function cookieBase() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
  }
}

export async function setAuthCookies(
  accessToken: string,
  refreshToken: string,
): Promise<void> {
  const store = await cookies()
  const base = cookieBase()
  store.set(ACCESS_COOKIE, accessToken, { ...base, maxAge: ACCESS_MAX_AGE })
  store.set(REFRESH_COOKIE, refreshToken, { ...base, maxAge: REFRESH_MAX_AGE })
}

export async function clearAuthCookies(): Promise<void> {
  const store = await cookies()
  // Overwrite with an expired cookie that repeats every original flag, instead
  // of store.delete(): a bare delete can be dropped by a proxy/CDN if its path
  // or flags don't match the original, leaving a valid session token alive.
  const expired = { ...cookieBase(), maxAge: 0 }
  store.set(ACCESS_COOKIE, '', expired)
  store.set(REFRESH_COOKIE, '', expired)
}

// Shape mirrors the backend MeResponse (app/api/routes/auth.py).
export interface Session {
  account: {
    id: string
    email: string
    full_name: string | null
    role: string
    email_verified: boolean
  }
  tenant_id: string
  tenant_slug: string | null
  tenant_status: string | null
  subscription: {
    status: string
    plan: string | null
    trial_ends_at: string | null
  } | null
}

/**
 * Reads the current session from /auth/me using the access cookie.
 * Returns null when there is no access token or the token is rejected.
 * Read-only: does not attempt a refresh (middleware handles that).
 */
export async function getSessionReadOnly(): Promise<Session | null> {
  const store = await cookies()
  const access = store.get(ACCESS_COOKIE)?.value
  if (!access) return null

  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${access}` },
      cache: 'no-store',
    })
    if (!res.ok) return null
    return (await res.json()) as Session
  } catch {
    return null
  }
}
