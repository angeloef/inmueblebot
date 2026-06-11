'use client'

import { FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import { validateAgency } from '@/lib/validation'

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const DASHBOARD_URL = process.env.NEXT_PUBLIC_DASHBOARD_URL ?? '/app'

type Status = 'idle' | 'submitting' | 'error'

interface GoogleCompleteFormProps {
  /** Registration token firmado por la API (?gt=). La identidad ya fue verificada. */
  token: string
  /** Email de Google, solo para mostrar (ya verificado server-side). */
  email: string
}

export default function GoogleCompleteForm({ token, email }: GoogleCompleteFormProps) {
  const [agency, setAgency] = useState('')
  const [agencyError, setAgencyError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [apiError, setApiError] = useState<string | null>(null)
  // Token ausente → el link caducó o se abrió la página directo. Sin token no hay
  // forma de completar el registro: ofrecemos reintentar con Google.
  const [expired, setExpired] = useState<boolean>(!token)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const aErr = validateAgency(agency)
    setAgencyError(aErr)
    if (aErr) return

    setStatus('submitting')
    setApiError(null)
    try {
      const res = await fetch('/api/auth/google-complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, agency_name: agency }),
      })
      if (!res.ok) {
        const data = await res.json() as { error?: string }
        // 400 = token expirado/usado → ofrecer reintentar con Google.
        if (res.status === 400) setExpired(true)
        setApiError(data.error ?? 'Error desconocido.')
        setStatus('error')
        return
      }
      const data = await res.json() as { ok: boolean; next?: string | null }
      window.location.href = data.next || DASHBOARD_URL
    } catch {
      setApiError('Error del servidor. Probá de nuevo en unos minutos.')
      setStatus('error')
    }
  }

  if (expired) {
    return (
      <div className="flex flex-col gap-4">
        {apiError && <Alert variant="error">{apiError}</Alert>}
        <p className="text-sm text-ink-700">
          El enlace para terminar tu registro venció o ya fue usado. Volvé a
          empezar con Google.
        </p>
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={() => { window.location.href = `${API_URL}/auth/google/login` }}
        >
          Continuar con Google
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {status === 'error' && apiError && <Alert variant="error">{apiError}</Alert>}

      {email && (
        <p className="text-sm text-ink-500">
          Vas a crear tu cuenta con <span className="font-medium text-ink-700">{email}</span>.
        </p>
      )}

      <FormField label="Nombre de tu inmobiliaria" htmlFor="agency" error={agencyError}>
        <Input
          id="agency"
          type="text"
          autoComplete="organization"
          placeholder="Inmobiliaria García"
          value={agency}
          onChange={(e) => setAgency(e.target.value)}
          error={!!agencyError}
          disabled={status === 'submitting'}
          autoFocus
        />
      </FormField>

      <Button
        type="submit"
        variant="primary"
        size="lg"
        loading={status === 'submitting'}
        className="w-full"
      >
        Crear cuenta gratis
      </Button>
    </form>
  )
}
