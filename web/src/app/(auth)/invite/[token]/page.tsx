import type { Metadata } from 'next'
import InviteForm from '@/components/auth/InviteForm'

export const metadata: Metadata = { title: 'Aceptar invitación — ViviendApp' }

const API_BASE = process.env.API_URL ?? 'http://localhost:8000'

interface InvitePageProps {
  params: Promise<{ token: string }>
}

interface InviteInfo {
  valid: boolean
  email?: string | null
  agency_name?: string | null
}

async function fetchInvite(token: string): Promise<InviteInfo> {
  try {
    const res = await fetch(
      `${API_BASE}/team/invite/${encodeURIComponent(token)}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return { valid: false }
    return (await res.json()) as InviteInfo
  } catch {
    return { valid: false }
  }
}

export default async function InvitePage({ params }: InvitePageProps) {
  const { token } = await params
  const info = await fetchInvite(token)

  if (!info.valid) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Invitación inválida
        </h1>
        <p className="text-sm text-ink-700">
          Esta invitación no existe, ya fue usada o expiró. Pedile al administrador
          que te envíe una nueva.
        </p>
        <a
          href="/login"
          className="text-brand-accent hover:underline text-sm font-medium"
        >
          Ir a iniciar sesión
        </a>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Unite a {info.agency_name}
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Creá tu cuenta para empezar a trabajar con el equipo.
        </p>
      </div>
      <InviteForm
        token={token}
        email={info.email ?? ''}
        agencyName={info.agency_name ?? ''}
      />
    </div>
  )
}
