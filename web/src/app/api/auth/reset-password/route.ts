import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'
import { mapAuthError } from '@/lib/errors'

export async function POST(req: NextRequest) {
  const body = await req.json() as { token: string; new_password: string }
  const result = await apiPost('/auth/reset-password', body)

  if (!result.ok) {
    return NextResponse.json(
      { error: mapAuthError(result.status, 'reset') },
      { status: result.status || 500 },
    )
  }

  return NextResponse.json({ ok: true })
}
