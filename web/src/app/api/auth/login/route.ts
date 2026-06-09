import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'
import { setAuthCookies } from '@/lib/auth'
import { mapAuthError } from '@/lib/errors'

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function POST(req: NextRequest) {
  const body = await req.json() as { email: string; password: string }
  const result = await apiPost<LoginResponse>('/auth/login', body)

  if (!result.ok) {
    return NextResponse.json(
      { error: mapAuthError(result.status, 'login') },
      { status: result.status || 500 },
    )
  }

  await setAuthCookies(result.data.access_token, result.data.refresh_token)
  return NextResponse.json({ ok: true })
}
