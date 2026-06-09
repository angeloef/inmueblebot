'use client'

import { FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import { validateEmail, validatePassword } from '@/lib/validation'

type Status = 'idle' | 'submitting' | 'error'

interface LoginFormProps {
  next?: string
}

// TODO(Fase 4): redirect cross-domain al dashboard Vite una vez integrado.
// Por ahora usa NEXT_PUBLIC_DASHBOARD_URL o cae a /app.
const DASHBOARD_URL =
  typeof window !== 'undefined'
    ? (process.env.NEXT_PUBLIC_DASHBOARD_URL ?? '/app')
    : '/app'

export default function LoginForm({ next }: LoginFormProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [apiError, setApiError] = useState<string | null>(null)

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
        body: JSON.stringify({ email, password }),
      })

      if (!res.ok) {
        const data = await res.json() as { error?: string }
        setApiError(data.error ?? 'Error desconocido.')
        setStatus('error')
        return
      }

      // Determine redirect
      let redirect = DASHBOARD_URL
      if (next) {
        // Only allow internal paths (prevent open redirect)
        try {
          const url = new URL(next, window.location.origin)
          if (url.origin === window.location.origin) {
            redirect = url.pathname + url.search
          }
        } catch {
          // ignore invalid next
        }
      }

      window.location.href = redirect
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
        <Input
          id="password"
          type="password"
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
    </form>
  )
}
