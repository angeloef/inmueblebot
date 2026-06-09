/**
 * Single source of truth for auth cookie names + lifetimes.
 *
 * Kept in its own module (no `next/headers` import) so it's safe to import from
 * BOTH the Edge middleware and the Node server helpers in auth.ts. Previously the
 * names were duplicated as string literals in middleware.ts — a rename in one
 * place would have silently broken authentication.
 */
export const ACCESS_COOKIE = 'vivienda_access'
export const REFRESH_COOKIE = 'vivienda_refresh'

export const ACCESS_MAX_AGE = 60 * 60 // 1h — matches backend access-token TTL
export const REFRESH_MAX_AGE = 60 * 60 * 24 * 7 // 7d — matches backend refresh-token TTL
