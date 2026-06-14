'use client'

import { FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import PasswordInput from '@/components/ui/PasswordInput'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import GoogleButton from '@/components/auth/GoogleButton'
import { validateEmail, validatePassword } from '@/lib/validation'

type Status = 'idle' | 'submitting' | 'error'

interface LoginFormProps {
  next?: string
  /** Código de error con el que volvió el callback OAuth / handoff (?error=...). */
  errorCode?: string
}

// Fallback si el handoff no se pudo emitir: URL pública del dashboard.
const DASHBOARD_URL = process.env.NEXT_PUBLIC_DASHBOARD_URL ?? '/app'

// Mensajes para los ?error=... con que vuelven el callback de Google y el handoff.
const OAUTH_ERRORS: Record<string, string> = {
  oauth: 'No se pudo completar el inicio con Google. Probá de nuevo.',
  state: 'La sesión de Google expiró. Probá de nuevo.',
  email_unverified: 'Tu email de Google no está verificado. Verificalo o usá tu contraseña.',
  suspended: 'Tu cuenta está suspendida. Escribinos para reactivarla.',
  handoff: 'No pudimos abrir tu sesión en el panel. Iniciá sesión de nuevo.',
}

export default function LoginForm({ next, errorCode }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>(errorCode ? 'error' : 'idle')
  const [apiError, setApiError] = useState<string | null>(
    errorCode ? (OAUTH_ERRORS[errorCode] ?? OAUTH_ERRORS.oauth) : null,
  )

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()

    const eErr = validateEmail(email)
    const pErr = validatePassword(password)
    setEmailError(eErr)
    setPasswordError(pErr)
    if (eErr || pErr) return

    setStatus('submitting')
    setApiError(null)

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // `next` = deep-link del dashboard (?next=/dashboard/clientes). Viaja al
        // BFF, que lo embebe en el handoff token; la API lo valida (path relativo).
        body: JSON.stringify({ email, password, next: next ?? null }),
      })

      if (!res.ok) {
        const data = await res.json() as { error?: string }
        setApiError(data.error ?? 'Error desconocido.')
        setStatus('error')
        return
      }

      // El BFF devuelve la URL de handoff que abre la sesión en el dashboard
      // (origen de la API). Fallback: redirect clásico a DASHBOARD_URL.
      const data = await res.json() as { ok: boolean; next?: string | null }
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
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={!!passwordError}
          disabled={status === 'submitting'}
        />
      </FormField>

      <div className="text-right -mt-2">
        <a
          href="/forgot-password"
          className="text-sm text-brand-accent hover:text-primary"
        >
          ¿Olvidaste tu contraseña?
        </a>
      </div>

      <Button
        type="submit"
        variant="primary"
        size="lg"
        loading={status === 'submitting'}
        className="w-full"
      >
        Ingresar
      </Button>

      <GoogleButton disabled={status === 'submitting'} />
    </form>
  )
}
