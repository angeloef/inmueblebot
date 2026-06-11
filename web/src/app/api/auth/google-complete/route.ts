import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'
import { buildHandoffUrl, setAuthCookies } from '@/lib/auth'

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/**
 * Paso 2 del registro con Google: el usuario eligió el nombre de su inmobiliaria.
 * Reenvía el registration token (firmado por la API, un solo uso) + agency_name a
 * la API, que crea Tenant + trial + cuenta Google-only y devuelve la sesión.
 */
export async function POST(req: NextRequest) {
  const body = await req.json() as { token: string; agency_name: string }
  const result = await apiPost<TokenResponse>('/auth/google/complete', body)

  if (!result.ok) {
    let error = 'Ocurrió un error inesperado. Probá de nuevo.'
    if (result.status === 0) {
      error = 'No pudimos conectar con el servidor. Probá de nuevo en unos minutos.'
    } else if (result.status === 400) {
      error = 'El enlace de registro expiró o ya fue usado. Volvé a intentar con Google.'
    } else if (result.status === 409) {
      error = 'Ese email ya tiene una cuenta. Probá iniciar sesión.'
    } else if (result.status === 422) {
      error = 'Revisá el nombre ingresado (mínimo 2 caracteres).'
    } else if (result.status >= 500) {
      error = 'Error del servidor. Probá de nuevo en unos minutos.'
    }
    return NextResponse.json({ error }, { status: result.status || 500 })
  }

  await setAuthCookies(result.data.access_token, result.data.refresh_token)

  // Sesión recién creada → directo al dashboard vía handoff.
  const next = await buildHandoffUrl(result.data.access_token, null)
  return NextResponse.json({ ok: true, next })
}
