'use client'

import { FormEvent, useState } from 'react'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import FormField from '@/components/ui/FormField'
import Alert from '@/components/ui/Alert'
import { validateEmail } from '@/lib/validation'

type Status = 'idle' | 'submitting' | 'sent'

export default function ForgotForm() {
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>('idle')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()

    const eErr = validateEmail(email)
    setEmailError(eErr)
    if (eErr) return

    setStatus('submitting')

    try {
      await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
    } catch {
      // always show success message (prevent email enumeration)
    }

    setStatus('sent')
  }

  if (status === 'sent') {
    return (
      <Alert variant="success">
        Si el email está registrado, te enviamos las instrucciones para
        restablecer tu contraseña. Revisá tu bandeja de entrada (y el spam).
      </Alert>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
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

      <Button
        type="submit"
        variant="primary"
        size="lg"
        loading={status === 'submitting'}
        className="w-full"
      >
        Enviar instrucciones
      </Button>
    </form>
  )
}
