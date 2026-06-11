import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'
import { buildHandoffUrl, setAuthCookies } from '@/lib/auth'

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as {
    token: string
    name?: string | null
    password: string
  }

  const result = await apiPost<TokenResponse>(
    `/team/invite/${encodeURIComponent(body.token)}/accept`,
    { name: body.name ?? null, password: body.password },
  )

  if (!result.ok) {
    let error = 'Ocurrió un error inesperado. Probá de nuevo.'
    if (result.status === 0) {
      error = 'No pudimos conectar con el servidor.'
    } else if (result.status === 404) {
      error = 'Invitación inválida o ya usada.'
    } else if (result.status === 410) {
      error = 'La invitación expiró. Pedile al administrador que te reenvíe una.'
    } else if (result.status === 409) {
      error = 'Ese email ya tiene una cuenta. Probá iniciar sesión.'
    } else if (result.status === 422) {
      error = 'Revisá los datos (contraseña mínimo 8 caracteres).'
    } else if (result.status >= 500) {
      error = 'Error del servidor. Probá de nuevo en unos minutos.'
    }
    return NextResponse.json({ error }, { status: result.status || 500 })
  }

  await setAuthCookies(result.data.access_token, result.data.refresh_token)
  const next = await buildHandoffUrl(result.data.access_token, null)
  return NextResponse.json({ ok: true, next })
}
