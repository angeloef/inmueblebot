/**
 * Server-side API client for talking to the FastAPI backend.
 *
 * Only ever runs inside Route Handlers (web/src/app/api/auth/*) — never in the
 * browser — so it targets the internal `API_URL` and the JWT never reaches the
 * client. Returns a discriminated result instead of throwing, so callers can
 * branch on `ok` and forward `status` to `mapAuthError`.
 */

const API_BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; data: unknown }

export async function apiPost<T>(
  path: string,
  body: unknown,
  bearerToken?: string,
): Promise<ApiResult<T>> {
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (bearerToken) headers.Authorization = `Bearer ${bearerToken}`
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      cache: 'no-store',
    })

    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      // Non-JSON or empty body — leave data as null.
    }

    if (!res.ok) {
      return { ok: false, status: res.status, data }
    }
    return { ok: true, status: res.status, data: data as T }
  } catch {
    // Network/DNS failure or backend unreachable. status 0 signals "no response".
    return { ok: false, status: 0, data: null }
  }
}
