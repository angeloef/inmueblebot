/**
 * Login.jsx — Pantalla de acceso del dashboard (Fase 4).
 *
 * Formulario controlado (email + password) → POST /auth/login vía useAuth().
 * El backend setea las cookies httpOnly; el browser nunca toca el JWT.
 */
import React, { useEffect, useState } from 'react';
import { useAuth } from './auth';
import { authApi } from './api';

const NAVY = '#164a71';

// Mensajes para los ?error=... con que vuelve el callback de Google (no JSON crudo).
const OAUTH_ERRORS = {
  oauth: 'No se pudo completar el inicio con Google. Probá de nuevo.',
  state: 'La sesión de Google expiró. Probá de nuevo.',
  email_unverified: 'Tu email de Google no está verificado. Verificalo o usá tu contraseña.',
  suspended: 'Tu cuenta está suspendida. Contactá a soporte.',
};

const S = {
  screen: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    background: 'radial-gradient(1200px 600px at 50% -10%, #1f5d8c22, transparent), var(--surface-base, #f6f8fa)',
  },
  card: {
    width: '100%',
    maxWidth: 380,
    background: 'var(--surface-raised, #fff)',
    borderRadius: 16,
    border: '1px solid var(--border-subtle, #e6e9ee)',
    boxShadow: '0 1px 2px rgba(16,24,40,0.04), 0 12px 32px rgba(16,24,40,0.10)',
    padding: '32px 28px',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  logo: { height: 36 },
  title: {
    fontSize: 20,
    fontWeight: 700,
    color: 'var(--fg-primary, #111)',
    textAlign: 'center',
    marginBottom: 4,
  },
  sub: {
    fontSize: 13,
    color: 'var(--fg-tertiary, #667085)',
    textAlign: 'center',
    marginBottom: 24,
  },
  label: {
    display: 'block',
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--fg-secondary, #344054)',
    marginBottom: 6,
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    borderRadius: 8,
    border: '1px solid var(--border-subtle, #d0d5dd)',
    fontSize: 14,
    background: 'var(--surface-base, #fff)',
    color: 'var(--fg-primary, #111)',
    outline: 'none',
    boxSizing: 'border-box',
    marginBottom: 16,
  },
  button: (disabled) => ({
    width: '100%',
    padding: '11px 16px',
    borderRadius: 8,
    border: 'none',
    background: NAVY,
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    transition: 'opacity 0.15s, transform 0.05s',
  }),
  error: {
    background: 'var(--danger-50, #fef3f2)',
    color: 'var(--danger-600, #b42318)',
    border: '1px solid var(--danger-200, #fecdca)',
    borderRadius: 8,
    padding: '8px 12px',
    fontSize: 13,
    marginBottom: 16,
  },
  divider: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    margin: '18px 0',
    color: 'var(--fg-tertiary, #98a2b3)',
    fontSize: 12,
  },
  dividerLine: { flex: 1, height: 1, background: 'var(--border-subtle, #e6e9ee)' },
  googleBtn: (disabled) => ({
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    padding: '11px 16px',
    borderRadius: 8,
    border: '1px solid var(--border-subtle, #d0d5dd)',
    background: 'var(--surface-base, #fff)',
    color: 'var(--fg-primary, #344054)',
    fontSize: 14,
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  }),
};

// Logo "G" oficial de Google (multicolor), inline para no depender de assets externos.
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.05l3.01-2.33z"/>
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
    </svg>
  );
}

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Si volvimos del callback de Google con ?error=..., mostrar el mensaje y limpiar
  // la URL para que un reload no lo repita.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('error');
    if (code) {
      setError(OAUTH_ERRORS[code] ?? OAUTH_ERRORS.oauth);
      params.delete('error');
      const qs = params.toString();
      window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''));
    }
  }, []);

  const handleGoogle = () => {
    setError('');
    window.location.href = authApi.googleLoginUrl();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email.trim() || !password) {
      setError('Ingresá tu email y contraseña.');
      return;
    }
    setSubmitting(true);
    try {
      await login(email.trim().toLowerCase(), password);
      // En éxito, el AuthProvider cambia a 'authed' y este componente se desmonta.
    } catch (err) {
      const code = err?.response?.status;
      setError(
        code === 401 ? 'Email o contraseña incorrectos.'
        : code === 403 ? 'Tu cuenta está suspendida. Contactá a soporte.'
        : 'No se pudo iniciar sesión. Probá de nuevo en un momento.',
      );
      setSubmitting(false);
    }
  };

  return (
    <div style={S.screen}>
      <form style={S.card} onSubmit={handleSubmit} noValidate>
        <div style={S.brand}>
          <img src="/logo.svg" alt="ViviendApp" style={S.logo} />
        </div>
        <h1 style={S.title}>Panel de tu inmobiliaria</h1>
        <p style={S.sub}>Iniciá sesión para gestionar propiedades, clientes y tu bot.</p>

        {error && <div style={S.error} role="alert">{error}</div>}

        <label style={S.label} htmlFor="login-email">Email</label>
        <input
          id="login-email"
          style={S.input}
          type="email"
          autoComplete="username"
          placeholder="vos@inmobiliaria.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
          autoFocus
        />

        <label style={S.label} htmlFor="login-password">Contraseña</label>
        <input
          id="login-password"
          style={S.input}
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={submitting}
        />

        <button type="submit" style={S.button(submitting)} disabled={submitting}>
          {submitting ? 'Ingresando…' : 'Ingresar'}
        </button>

        <div style={S.divider}>
          <span style={S.dividerLine} />
          o
          <span style={S.dividerLine} />
        </div>

        <button
          type="button"
          style={S.googleBtn(submitting)}
          disabled={submitting}
          onClick={handleGoogle}
        >
          <GoogleIcon />
          Continuar con Google
        </button>
      </form>
    </div>
  );
}
