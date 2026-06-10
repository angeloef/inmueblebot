/**
 * Login.jsx — Pantalla de acceso del dashboard (Fase 4).
 *
 * Formulario controlado (email + password) → POST /auth/login vía useAuth().
 * El backend setea las cookies httpOnly; el browser nunca toca el JWT.
 */
import React, { useState } from 'react';
import { useAuth } from './auth';

const NAVY = '#164a71';

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
};

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

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
      </form>
    </div>
  );
}
