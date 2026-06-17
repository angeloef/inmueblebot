/**
 * SuperadminApp.jsx — raíz de la superficie /superadmin (gate por rol + layout).
 *
 * Árbol de rutas separado del dashboard normal: su propio login y su propio gate. Estados:
 *   - loading/reconnecting → splash
 *   - anon                 → SuperadminLogin
 *   - authed, role!=superadmin → 403 (nunca renderiza la consola a un no-superadmin)
 *   - authed, role==superadmin → SuperadminTenantProvider + SuperadminShell
 *
 * El gate de UI es defensa en profundidad: el backend (require_superadmin) ya es
 * fail-closed, así que aunque alguien fuerce el render, las APIs responden 401/403.
 */
import React from 'react';
import { useAuth } from '../auth';
import SuperadminLogin from './SuperadminLogin';
import SuperadminShell from './SuperadminShell';
import { SuperadminTenantProvider } from './TenantContext';

const NAVY = '#164a71';

function Splash({ text = 'Cargando…' }) {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: 'var(--fg-tertiary, #667085)', fontSize: 14,
    }}>
      {text}
    </div>
  );
}

function Forbidden({ email, onLogout }) {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column', gap: 14,
      alignItems: 'center', justifyContent: 'center', padding: 24, textAlign: 'center',
    }}>
      <div style={{ fontSize: 40 }} aria-hidden="true">🔒</div>
      <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Acceso restringido</h1>
      <p style={{ color: 'var(--fg-tertiary, #667085)', maxWidth: 360, margin: 0 }}>
        La cuenta <strong>{email}</strong> no tiene permisos de super-admin. Esta consola es
        solo para el equipo de plataforma.
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
        <a href="/" style={{
          padding: '9px 14px', borderRadius: 8, background: NAVY, color: '#fff',
          fontSize: 14, fontWeight: 600, textDecoration: 'none',
        }}>Ir al panel</a>
        <button type="button" onClick={onLogout} style={{
          padding: '9px 14px', borderRadius: 8, border: '1px solid var(--border-subtle, #d0d5dd)',
          background: 'var(--surface-raised, #fff)', color: 'var(--fg-secondary, #344054)',
          fontSize: 14, fontWeight: 600, cursor: 'pointer',
        }}>Cambiar de cuenta</button>
      </div>
    </div>
  );
}

export default function SuperadminApp() {
  const { status, me, logout } = useAuth();

  if (status === 'loading') return <Splash />;
  if (status === 'reconnecting') return <Splash text="Conectando con el servidor…" />;
  if (status === 'anon') return <SuperadminLogin />;

  const account = me?.account ?? null;
  if (account?.role !== 'superadmin') {
    return <Forbidden email={account?.email ?? 'desconocida'} onLogout={logout} />;
  }

  return (
    <SuperadminTenantProvider>
      <SuperadminShell account={account} />
    </SuperadminTenantProvider>
  );
}
