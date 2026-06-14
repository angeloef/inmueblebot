'use client'

import { FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import PasswordInput from '@/components/ui/PasswordInput'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import GoogleButton from '@/components/auth/GoogleButton'
import {
  validateEmail,
  validatePassword,
  validateAgency,
} from '@/lib/validation'

type Status = 'idle' | 'submitting' | 'error' | 'success'

// Fallback si el handoff no se pudo emitir: URL pública del dashboard.
const DASHBOARD_URL = process.env.NEXT_PUBLIC_DASHBOARD_URL ?? '/app'

export default function SignupForm() {
  const [agency, setAgency] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [agencyError, setAgencyError] = useState<string | null>(null)
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [apiError, setApiError] = useState<string | null>(null)
  // URL de handoff que abre la sesión en el dashboard (la setea el submit OK).
  const [panelUrl, setPanelUrl] = useState<string>(DASHBOARD_URL)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()

    const aErr = validateAgency(agency)
    const eErr = validateEmail(email)
    const pErr = validatePassword(password)
    setAgencyError(aErr)
    setEmailError(eErr)
    setPasswordError(pErr)
    if (aErr || eErr || pErr) return

    setStatus('submitting')
    setApiError(null)

    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          agency_name: agency,
        }),
      })

      if (!res.ok) {
        const data = await res.json() as { error?: string }
        setApiError(data.error ?? 'Error desconocido.')
        setStatus('error')
        return
      }

      // URL de handoff: abre la sesión en el dashboard (origen de la API) con un
      // código de un solo uso. El botón "Continuar al panel" la usa.
      const data = await res.json() as { ok: boolean; next?: string | null }
      setPanelUrl(data.next || DASHBOARD_URL)
      setStatus('success')
    } catch {
      setApiError('Error del servidor. Probá de nuevo en unos minutos.')
      setStatus('error')
    }
  }

  if (status === 'success') {
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="success">
          ¡Cuenta creada exitosamente! Ya podés empezar a usar ViviendApp.
        </Alert>

        {/* Placeholder: WhatsApp onboarding info card */}
        <div className="rounded-xl border border-brand-tint-strong bg-brand-tint p-5 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">💬</span>
            <h3 className="font-display font-semibold text-primary">
              Conectá tu WhatsApp
            </h3>
          </div>
          <p className="text-sm text-ink-700">
            El siguiente paso es conectar tu número de WhatsApp Business para
            que el bot empiece a atender leads. Esta funcionalidad estará
            disponible próximamente.
          </p>
          <p className="text-xs text-ink-500 italic">
            {/* TODO(Fase 3): agregar onboarding de WhatsApp Business API */}
            Próximamente: guía de conexión con WhatsApp Business API.
          </p>
        </div>

        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={() => { window.location.href = panelUrl }}
        >
          Continuar al panel
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {status === 'error' && apiError && (
        <Alert variant="error">{apiError}</Alert>
      )}

      <FormField
        label="Nombre de tu inmobiliaria"
        htmlFor="agency"
        error={agencyError}
      >
        <Input
          id="agency"
          type="text"
          autoComplete="organization"
          placeholder="Inmobiliaria García"
          value={agency}
          onChange={(e) => setAgency(e.target.value)}
          error={!!agencyError}
          disabled={status === 'submitting'}
        />
      </FormField>

      <FormField label="Email" htmlFor="email" error={emailError}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          placeholder="vos@inmobiliaria.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={!!emailError}
          disabled={status === 'submitting'}
        />
      </FormField>

      <FormField label="Contraseña" htmlFor="password" error={passwordError}>
        <PasswordInput
          id="password"
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
        Crear cuenta gratis
      </Button>

      <GoogleButton disabled={status === 'submitting'} />

      <p className="text-center text-xs text-ink-500">
        Al registrarte aceptás los{' '}
        <a href="#" className="text-brand-accent hover:underline">
          Términos de servicio
        </a>{' '}
        y la{' '}
        <a href="#" className="text-brand-accent hover:underline">
          Política de privacidad
        </a>
        .
      </p>
    </form>
  )
}
