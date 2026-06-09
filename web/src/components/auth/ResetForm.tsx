'use client'

import { FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import { validatePassword } from '@/lib/validation'

type Status = 'idle' | 'submitting' | 'error' | 'success'

interface ResetFormProps {
  token: string
}

export default function ResetForm({ token }: ResetFormProps) {
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [apiError, setApiError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()

    const pErr = validatePassword(password)
    setPasswordError(pErr)
    if (pErr) return

    setStatus('submitting')
    setApiError(null)

    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      })

      if (!res.ok) {
        const data = await res.json() as { error?: string }
        setApiError(data.error ?? 'Error desconocido.')
        setStatus('error')
        return
      }

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
          ¡Contraseña actualizada correctamente!
        </Alert>
        <a
          href="/login"
          className="text-center text-sm text-brand-accent hover:text-primary font-medium"
        >
          Ir al inicio de sesión →
        </a>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {status === 'error' && apiError && (
        <Alert variant="error">{apiError}</Alert>
      )}

      <FormField
        label="Nueva contraseña"
        htmlFor="password"
        error={passwordError}
      >
        <Input
          id="password"
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
        Actualizar contraseña
      </Button>
    </form>
  )
}
