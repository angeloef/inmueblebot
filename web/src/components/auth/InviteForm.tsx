'use client'

import { type FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import { validatePassword } from '@/lib/validation'

const DASHBOARD_URL = process.env.NEXT_PUBLIC_DASHBOARD_URL ?? '/app'

type Status = 'idle' | 'submitting' | 'error'

interface InviteFormProps {
  token: string
  email: string
  agencyName: string
}

export default function InviteForm({ token, email }: InviteFormProps) {
  const [name, setName]                   = useState('')
  const [password, setPassword]           = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [status, setStatus]               = useState<Status>('idle')
  const [apiError, setApiError]           = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const pErr = validatePassword(password)
    setPasswordError(pErr)
    if (pErr) return

    setStatus('submitting')
    setApiError(null)
    try {
      const res = await fetch('/api/auth/accept-invite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, name: name.trim() || null, password }),
      })
      if (!res.ok) {
        const data = (await res.json()) as { error?: string }
        setApiError(data.error ?? 'Error desconocido.')
        setStatus('error')
        return
      }
      const data = (await res.json()) as { ok: boolean; next?: string | null }
      window.location.href = data.next || DASHBOARD_URL
    } catch {
      setApiError('Error del servidor. Probá de nuevo en unos minutos.')
      setStatus('error')
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {status === 'error' && apiError && (
        <Alert variant="error">{apiError}</Alert>
      )}

      {email && (
        <p className="text-sm text-ink-500">
          Tu cuenta se creará con{' '}
          <span className="font-medium text-ink-700">{email}</span>.
        </p>
      )}

      <FormField label="Tu nombre (opcional)" htmlFor="invite-name">
        <Input
          id="invite-name"
          type="text"
          autoComplete="name"
          placeholder="Nombre y apellido"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={status === 'submitting'}
          autoFocus
        />
      </FormField>

      <FormField label="Contraseña" htmlFor="invite-password" error={passwordError}>
        <Input
          id="invite-password"
          type="password"
          autoComplete="new-password"
          placeholder="Mínimo 8 caracteres"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={!!passwordError}
          disabled={status === 'submitting'}
        />
      </FormField>

      <Button
        type="submit"
        variant="primary"
        size="lg"
        loading={status === 'submitting'}
        className="w-full"
      >
        Unirme al equipo
      </Button>
    </form>
  )
}
