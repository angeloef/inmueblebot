import { NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import { ACCESS_COOKIE } from '@/lib/cookies'

/**
 * Server-side proxy for starting a MercadoPago subscription.
 *
 * The JWT lives in an httpOnly cookie the browser JS can't read, so the checkout
 * button can't call the backend directly. This handler reads the access cookie,
 * forwards it as a Bearer token to `POST /billing/subscribe`, and returns the
 * MercadoPago `init_point` for the client to redirect to. The token never reaches
 * the browser.
 */

const API_BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

interface SubscribeResponse {
  init_point: string
}

export async function POST() {
  const store = await cookies()
  const access = store.get(ACCESS_COOKIE)?.value

  if (!access) {
    return NextResponse.json(
      { error: 'Tu sesión expiró. Iniciá sesión de nuevo.' },
      { status: 401 },
    )
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}/billing/subscribe`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${access}` },
      cache: 'no-store',
    })
  } catch {
    return NextResponse.json(
      { error: 'No pudimos conectar con el servidor. Probá de nuevo.' },
      { status: 502 },
    )
  }

  if (!res.ok) {
    // Map backend statuses to safe Spanish messages — never surface raw detail.
    const message =
      res.status === 401
        ? 'Tu sesión expiró. Iniciá sesión de nuevo.'
        : res.status === 503
          ? 'Los pagos no están disponibles en este momento. Probá más tarde.'
          : 'No pudimos iniciar la suscripción. Probá de nuevo en unos minutos.'
    return NextResponse.json({ error: message }, { status: res.status })
  }

  const data = (await res.json()) as SubscribeResponse
  return NextResponse.json({ init_point: data.init_point })
}
