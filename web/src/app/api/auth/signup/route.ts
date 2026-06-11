import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'
import { buildHandoffUrl, setAuthCookies } from '@/lib/auth'
import { mapAuthError } from '@/lib/errors'

interface SignupResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function POST(req: NextRequest) {
  const body = await req.json() as {
    email: string
    password: string
    agency_name: string
  }
  const result = await apiPost<SignupResponse>('/auth/signup', {
    email: body.email,
    password: body.password,
    agency_name: body.agency_name,
  })

  if (!result.ok) {
    return NextResponse.json(
      { error: mapAuthError(result.status, 'signup') },
      { status: result.status || 500 },
    )
  }

  await setAuthCookies(result.data.access_token, result.data.refresh_token)

  // Handoff: el botón "Continuar al panel" navega directo con sesión abierta.
  const next = await buildHandoffUrl(result.data.access_token, null)
  return NextResponse.json({ ok: true, next })
}
