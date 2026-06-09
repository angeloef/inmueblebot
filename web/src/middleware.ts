import { NextRequest, NextResponse } from 'next/server'
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  ACCESS_MAX_AGE,
  REFRESH_MAX_AGE,
} from '@/lib/cookies'

export const config = {
  matcher: ['/app/:path*'],
}

const API_BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

export default async function middleware(req: NextRequest) {
  const access = req.cookies.get(ACCESS_COOKIE)?.value
  const refresh = req.cookies.get(REFRESH_COOKIE)?.value

  // No tokens at all → redirect to login
  if (!access && !refresh) {
    const loginUrl = new URL('/login', req.url)
    loginUrl.searchParams.set('next', req.nextUrl.pathname)
    return NextResponse.redirect(loginUrl)
  }

  // Has access token → allow
  if (access) {
    return NextResponse.next()
  }

  // No access but has refresh → try to refresh
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refresh }),
    })

    if (res.ok) {
      const data = await res.json() as {
        access_token: string
        refresh_token: string
      }
      const response = NextResponse.next()
      const base = {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax' as const,
        path: '/',
      }
      response.cookies.set(ACCESS_COOKIE, data.access_token, {
        ...base,
        maxAge: ACCESS_MAX_AGE,
      })
      response.cookies.set(REFRESH_COOKIE, data.refresh_token, {
        ...base,
        maxAge: REFRESH_MAX_AGE,
      })
      return response
    }
  } catch {
    // network error → redirect to login
  }

  // Refresh failed → redirect and clear cookies
  const loginUrl = new URL('/login', req.url)
  loginUrl.searchParams.set('next', req.nextUrl.pathname)
  const response = NextResponse.redirect(loginUrl)
  response.cookies.delete(ACCESS_COOKIE)
  response.cookies.delete(REFRESH_COOKIE)
  return response
}
