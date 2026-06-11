import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'
import { buildHandoffUrl, setAuthCookies } from '@/lib/auth'
import { mapAuthError } from '@/lib/errors'

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function POST(req: NextRequest) {
  const body = await req.json() as { email: string; password: string; next?: string }
  const result = await apiPost<LoginResponse>('/auth/login', {
    email: body.email,
    password: body.password,
  })

  if (!result.ok) {
    return NextResponse.json(
      { error: mapAuthError(result.status, 'login') },
      { status: result.status || 500 },
    )
  }

  await setAuthCookies(result.data.access_token, result.data.refresh_token)

  // Handoff: URL que abre la sesión en el dashboard (origen de la API) con un
  // código de un solo uso. `next` preserva el deep-link bookmarkeado. Si falla,
  // el cliente cae al redirect clásico (DASHBOARD_URL).
  const next = await buildHandoffUrl(result.data.access_token, body.next ?? null)
  return NextResponse.json({ ok: true, next })
}
