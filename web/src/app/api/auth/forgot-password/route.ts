import { NextRequest, NextResponse } from 'next/server'
import { apiPost } from '@/lib/api'

export async function POST(req: NextRequest) {
  const body = await req.json() as { email: string }
  // Always fire request but always return ok:true (prevent email enumeration)
  await apiPost('/auth/forgot-password', body)
  return NextResponse.json({ ok: true })
}
