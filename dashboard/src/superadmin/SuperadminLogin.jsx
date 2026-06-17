/**
 * SuperadminLogin.jsx — login propio de la superficie /superadmin.
 *
 * Reutiliza POST /auth/login vía useAuth().login (mismas cookies httpOnly). El gate de
 * rol vive en SuperadminApp: este form solo autentica; si la cuenta no es superadmin,
 * SuperadminApp muestra el 403. Defensa en profundidad — el backend ya es fail-closed.
 */
import React, { useState } from 'react';
import { useAuth } from '../auth';

const NAVY = '#164a71';

const S = {
  screen: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    background: 'radial-gradient(1200px 600px at 50% -10%, #0f2e4622, transparent), var(--surface-base, #0b1620)',
  },
  card: {
    width: '100%',
    maxWidth: 380,
    background: 'var(--surface-raised, #fff)',
    borderRadius: 16,
    border: '1px solid var(--border-subtle, #e6e9ee)',
    boxShadow: '0 1px 2px rgba(16,24,40,0.04), 0 12px 32px rgba(16,24,40,0.18)',
    padding: '32px 28px',
  },
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: NAVY,
    background: 'var(--accent-50, #eef4f9)',
    border: '1px solid var(--border-subtle, #dbe6ef)',
    borderRadius: 999,
    padding: '4px 10px',
    marginBottom: 16,
  },
  title: { fontSize: 20, fontWeight: 700, color: 'var(--fg-primary, #111)', marginBottom: 4 },
  sub: { fontSize: 13, color: 'var(--fg-tertiary, #667085)', marginBottom: 24 },
  label: {
    display: 'block', fontSize: 12, fontWeight: 600,
    color: 'var(--fg-secondary, #344054)', marginBottom: 6,
  },
  input: {
    width: '100%', padding: '10px 12px', borderRadius: 8,
    border: '1px solid var(--border-subtle, #d0d5dd)', fontSize: 14,
    background: 'var(--surface-base, #fff)', color: 'var(--fg-primary, #111)',
    outline: 'none', boxSizing: 'border-box', marginBottom: 16,
  },
  button: (disabled) => ({
    width: '100%', padding: '11px 16px', borderRadius: 8, border: 'none',
    background: NAVY, color: '#fff', fontSize: 14, fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1,
  }),
  error: {
    background: 'var(--danger-50, #fef3f2)', color: 'var(--danger-600, #b42318)',
    border: '1px solid var(--danger-100)', borderRadius: 8,
    padding: '8px 12px', fontSize: 13, marginBottom: 16,
  },
};

export default function SuperadminLogin() {
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
      // En éxito el AuthProvider pasa a 'authed' y SuperadminApp evalúa el rol.
    } catch (err) {
      const code = err?.response?.status;
      setError(
        code === 401 ? 'Email o contraseña incorrectos.'
        : code === 403 ? 'Tu cuenta está suspendida.'
        : 'No se pudo iniciar sesión. Probá de nuevo en un momento.',
      );
      setSubmitting(false);
    }
  };

  return (
    <div style={S.screen}>
      <form style={S.card} onSubmit={handleSubmit} noValidate>
        <span style={S.badge}>Super-admin</span>
        <h1 style={S.title}>Consola de plataforma</h1>
        <p style={S.sub}>Acceso restringido al equipo de ViviendApp.</p>

        {error && <div style={S.error} role="alert">{error}</div>}

        <label style={S.label} htmlFor="sa-email">Email</label>
        <input
          id="sa-email"
          style={S.input}
          type="email"
          autoComplete="username"
          placeholder="vos@viviendapp.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
          autoFocus
        />

        <label style={S.label} htmlFor="sa-password">Contraseña</label>
        <input
          id="sa-password"
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
