'use client'

// Botón "Continuar con Google": navegación top-level al endpoint de la API que
// inicia el OAuth (no es XHR — el flujo entero vive en el origen de la API y
// termina con la sesión abierta en el dashboard, o en /signup/complete si el
// email es nuevo).
const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// Logo "G" oficial de Google (multicolor), inline para no depender de assets.
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.05l3.01-2.33z"/>
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
    </svg>
  )
}

interface GoogleButtonProps {
  disabled?: boolean
}

export default function GoogleButton({ disabled }: GoogleButtonProps) {
  return (
    <>
      <div className="flex items-center gap-3 text-sm text-ink-500">
        <span className="h-px flex-1 bg-ink-200" aria-hidden="true" />
        o
        <span className="h-px flex-1 bg-ink-200" aria-hidden="true" />
      </div>
      <a
        href={disabled ? undefined : `${API_URL}/auth/google/login`}
        aria-disabled={disabled || undefined}
        className={`flex w-full items-center justify-center gap-2.5 rounded-lg border
          border-ink-200 bg-white px-4 py-3 text-sm font-semibold text-ink-700
          transition-colors hover:bg-ink-50
          ${disabled ? 'pointer-events-none opacity-60' : ''}`}
      >
        <GoogleIcon />
        Continuar con Google
      </a>
    </>
  )
}
