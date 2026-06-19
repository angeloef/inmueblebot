import React, { useState, useEffect, useRef, useCallback } from 'react';
import { pushToast } from './Primitives';
import { useAuth } from './auth';
import { useTheme } from './useTheme';
import {
  useTenants, useCreateTenant, useUpdateTenant, useDeleteTenant,
  useUpdateTenantSettings,
  useBillingStatus, useBillingPlans, useSubscribe, usePaymentHistory,
  useTeamMembers, useInviteMember, useRemoveMember,
  useUsage, useChangePassword, useUpdateProfile, useMyTenant, useUpdateMyTenant,
} from './api';

// ── Design tokens (handoff) ────────────────────────────────────────────────────

const CFG_VARS = {
  light: {
    '--cfg-page': '#f6f7f9', '--cfg-rail': '#ffffff', '--cfg-card': '#ffffff',
    '--cfg-card2': '#f3f5f7', '--cfg-input': '#ffffff',
    '--cfg-nav-act': '#eaf1f7', '--cfg-nav-act-fg': '#164a71',
    '--cfg-nav-hov': '#f1f4f7', '--cfg-bar-track': '#e8eaed',
    '--cfg-strong': '#1d2024', '--cfg-txt': '#2f3337',
    '--cfg-muted': '#5b626b', '--cfg-soft': '#8b929b',
    '--cfg-line': '#e6e9ec', '--cfg-line-soft': '#eef0f2',
    '--cfg-brand': '#164a71', '--cfg-brand-hov': '#1d5a88', '--cfg-brand-fg': '#ffffff',
    '--cfg-ok': '#2f8f4e', '--cfg-ok-bg': '#e6f4ea',
    '--cfg-warn': '#9a6c10', '--cfg-warn-bg': '#fbf2dc',
    '--cfg-bad': '#c0392b', '--cfg-bad-bg': '#fbe9e7',
    '--cfg-wa': '#1f9d57',
  },
  dark: {
    '--cfg-page': '#15171c', '--cfg-rail': '#191c21', '--cfg-card': '#1e2127',
    '--cfg-card2': '#23272e', '--cfg-input': '#22262d',
    '--cfg-nav-act': '#23344a', '--cfg-nav-act-fg': '#9cc4e8',
    '--cfg-nav-hov': '#21252c', '--cfg-bar-track': '#2b303a',
    '--cfg-strong': '#f0f3f6', '--cfg-txt': '#d7dbe1',
    '--cfg-muted': '#a3aab3', '--cfg-soft': '#7b828c',
    '--cfg-line': '#2c313a', '--cfg-line-soft': '#23262d',
    '--cfg-brand': '#3f8ccc', '--cfg-brand-hov': '#4f9bd8', '--cfg-brand-fg': '#0e1116',
    '--cfg-ok': '#46b06a', '--cfg-ok-bg': '#17291d',
    '--cfg-warn': '#d6a13d', '--cfg-warn-bg': '#2a2414',
    '--cfg-bad': '#e3705f', '--cfg-bad-bg': '#2c1815',
    '--cfg-wa': '#2ec46b',
  },
};

// ── Avatar color palette ───────────────────────────────────────────────────────

const AVATAR_COLORS = [
  { key: 'navy',   hex: '#164a71', label: 'Navy' },
  { key: 'teal',   hex: '#2e7686', label: 'Teal' },
  { key: 'violet', hex: '#6b4d99', label: 'Violeta' },
  { key: 'green',  hex: '#2f8f4e', label: 'Verde' },
  { key: 'orange', hex: '#c2651a', label: 'Naranja' },
];

function avatarHex(color) {
  return AVATAR_COLORS.find(a => a.key === color)?.hex ?? '#164a71';
}

// ── Minimal primitives (inline-styled for the new layout) ────────────────────

function CfgBtn({ children, onClick, disabled, variant = 'secondary', type = 'button', style: extraStyle }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 7, cursor: disabled ? 'default' : 'pointer',
    font: '600 14px/1 Inter,sans-serif', borderRadius: 8, padding: '9px 14px',
    border: '1px solid', transition: 'background .15s,border-color .15s',
    opacity: disabled ? 0.6 : 1,
    ...extraStyle,
  };
  const styles = {
    primary: { color: 'var(--cfg-brand-fg)', background: 'var(--cfg-brand)', borderColor: 'var(--cfg-brand)' },
    secondary: { color: 'var(--cfg-strong)', background: 'var(--cfg-card)', borderColor: 'var(--cfg-line)' },
    danger: { color: 'var(--cfg-bad)', background: 'transparent', borderColor: 'var(--cfg-line)' },
    ghost: { color: 'var(--cfg-muted)', background: 'transparent', borderColor: 'var(--cfg-line)' },
  };
  return (
    <button type={type} style={{ ...base, ...styles[variant] }} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

function CfgInput({ value, onChange, placeholder, type = 'text', disabled, maxLength, autoComplete }) {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      disabled={disabled}
      maxLength={maxLength}
      autoComplete={autoComplete}
      style={{
        font: '400 14px/1.4 Inter,sans-serif', color: 'var(--cfg-strong)',
        background: 'var(--cfg-input)', border: '1px solid var(--cfg-line)',
        borderRadius: 8, padding: '9px 12px', width: 280, outline: 'none',
      }}
    />
  );
}

function CfgRow({ label, hint, children }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 16, padding: '16px 0', borderBottom: '1px solid var(--cfg-line-soft)',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ font: '600 14px/1.4 Inter,sans-serif', color: 'var(--cfg-strong)' }}>{label}</span>
        {hint && <span style={{ font: '400 12px/1.4 Inter,sans-serif', color: 'var(--cfg-soft)' }}>{hint}</span>}
      </div>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

function CfgSectionHead({ title, description }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <h2 style={{ font: '600 22px/1.2 Inter,sans-serif', letterSpacing: '-.02em', color: 'var(--cfg-strong)', margin: 0 }}>{title}</h2>
      {description && <p style={{ font: '400 14px/1.5 Inter,sans-serif', color: 'var(--cfg-muted)', margin: '6px 0 0' }}>{description}</p>}
    </div>
  );
}

function H3({ children }) {
  return <h3 style={{ font: '600 15px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)', margin: '32px 0 4px' }}>{children}</h3>;
}

// ── Inline SVG icons (small set) ──────────────────────────────────────────────

const ICONS = {
  general:      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><line x1="4" y1="6" x2="20" y2="6"/><circle cx="9" cy="6" r="2"/><line x1="4" y1="12" x2="20" y2="12"/><circle cx="15" cy="12" r="2"/><line x1="4" y1="18" x2="20" y2="18"/><circle cx="9" cy="18" r="2"/></svg>,
  cuenta:       <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3"/><path d="M6.4 18.6a6 6 0 0 1 11.2 0"/></svg>,
  inmobiliaria: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l1.6-4.5h14.8L21 9"/><path d="M5 9v10h14V9"/><path d="M9.5 19v-5h5v5"/></svg>,
  facturacion:  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="6" width="18" height="12" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="7" y1="14.5" x2="11" y2="14.5"/></svg>,
  uso:          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><line x1="4" y1="20" x2="20" y2="20"/><rect x="6" y="11" width="3" height="6"/><rect x="11" y="7" width="3" height="10"/><rect x="16" y="14" width="3" height="3"/></svg>,
  equipo:       <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="9" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><path d="M16 6.4a3 3 0 0 1 0 5.7"/><path d="M17.8 19a5.5 5.5 0 0 0-3-4.9"/></svg>,
  sistema:      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="10" y="10" width="4" height="4"/><line x1="9" y1="2.5" x2="9" y2="4"/><line x1="15" y1="2.5" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="21.5"/><line x1="15" y1="20" x2="15" y2="21.5"/><line x1="2.5" y1="9" x2="4" y2="9"/><line x1="2.5" y1="15" x2="4" y2="15"/><line x1="20" y1="9" x2="21.5" y2="9"/><line x1="20" y1="15" x2="21.5" y2="15"/></svg>,
  inmobiliarias:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="8" width="7" height="11"/><rect x="13" y="4" width="7" height="15"/><line x1="6.5" y1="12" x2="8.5" y2="12"/><line x1="6.5" y1="15.5" x2="8.5" y2="15.5"/><line x1="15.5" y1="8" x2="17.5" y2="8"/><line x1="15.5" y1="11.5" x2="17.5" y2="11.5"/></svg>,
  plus:         <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>,
  check:        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4 4 10-10"/></svg>,
  wa:           <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.5 8.5 0 0 1-12.5 7.5L4 20l1-4.5A8.5 8.5 0 1 1 21 11.5z"/></svg>,
  sun:          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="4"/><line x1="12" y1="3" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="21"/><line x1="3" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="21" y2="12"/><line x1="5.6" y1="5.6" x2="6.8" y2="6.8"/><line x1="17.2" y1="17.2" x2="18.4" y2="18.4"/><line x1="18.4" y1="5.6" x2="17.2" y2="6.8"/><line x1="6.8" y1="17.2" x2="5.6" y2="18.4"/></svg>,
  moon:         <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z"/></svg>,
  search:       <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.5" y2="16.5"/></svg>,
  alert:        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12" y2="17"/></svg>,
};

// ── Nav sections definition ──────────────────────────────────────────────────

const NAV_SECTIONS = [
  { key: 'general',       label: 'General',          icon: 'general',       admin: false },
  { key: 'cuenta',        label: 'Cuenta',            icon: 'cuenta',        admin: false },
  { key: 'inmobiliaria',  label: 'Mi inmobiliaria',   icon: 'inmobiliaria',  admin: false },
  { key: 'facturacion',   label: 'Facturación',       icon: 'facturacion',   admin: false },
  { key: 'uso',           label: 'Uso',               icon: 'uso',           admin: false },
  { key: 'equipo',        label: 'Equipo',            icon: 'equipo',        admin: false },
  { key: 'sistema',       label: 'Sistema',           icon: 'sistema',       admin: true },
  { key: 'inmobiliarias', label: 'Inmobiliarias',     icon: 'inmobiliarias', admin: true },
];

// Search index: searchable terms per section
const SEARCH_INDEX = [
  { key: 'general',       terms: ['perfil', 'avatar', 'nombre', 'apariencia', 'tema', 'oscuro', 'claro'] },
  { key: 'cuenta',        terms: ['email', 'contraseña', 'password', 'seguridad', 'login', 'google', 'sesion', 'cerrar'] },
  { key: 'inmobiliaria',  terms: ['inmobiliaria', 'nombre comercial', 'horario', 'whatsapp', 'agente', 'timezone', 'zona horaria'] },
  { key: 'facturacion',   terms: ['facturacion', 'plan', 'pago', 'suscripcion', 'basico', 'profesional', 'enterprise', 'mercadopago'] },
  { key: 'uso',           terms: ['uso', 'propiedades', 'conversaciones', 'miembros', 'limite', 'consumo'] },
  { key: 'equipo',        terms: ['equipo', 'miembro', 'invitar', 'rol', 'admin', 'agente', 'propietario'] },
  { key: 'sistema',       terms: ['sistema', 'router', 'chatbot', 'v1', 'v2', 'v3'] },
  { key: 'inmobiliarias', terms: ['inmobiliarias', 'tenant', 'sucursal', 'wa', 'slug'] },
];

// Router options
const ROUTER_OPTIONS = [
  { value: 'v1', label: 'V1', desc: 'Clasificador de intent + agente monolítico. Sistema clásico y estable.' },
  { value: 'v2', label: 'V2', desc: 'S1 (regex rápido) + S2 (coordinador con especialistas). Scheduling conversacional.' },
  { value: 'v3', label: 'V3', desc: 'Router multi-tenant schema-guided (en construcción). Por ahora hace fallback a V2 sin riesgo.' },
];

// ── Skeleton & Error states ────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div>
      {[200, 320, '100%', '100%', '70%'].map((w, i) => (
        <div key={i} style={{
          height: i < 2 ? (i === 0 ? 26 : 15) : 44,
          width: w, borderRadius: 7, marginTop: i === 0 ? 0 : i === 1 ? 12 : 18,
          background: 'var(--cfg-card2)',
          animation: 'cfgpulse 1.4s ease-in-out infinite',
        }} />
      ))}
    </div>
  );
}

function SectionError({ onRetry }) {
  return (
    <div style={{ textAlign: 'center', padding: '64px 24px', maxWidth: 420, margin: '0 auto' }}>
      <div style={{ width: 52, height: 52, borderRadius: 9999, background: 'var(--cfg-bad-bg)', color: 'var(--cfg-bad)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 18px' }}>{ICONS.alert}</div>
      <h3 style={{ font: '600 18px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)', margin: '0 0 8px' }}>No pudimos cargar esta sección</h3>
      <p style={{ font: '400 14px/1.55 Inter,sans-serif', color: 'var(--cfg-muted)', margin: '0 0 22px' }}>Puede ser un arranque en frío del servidor. Reintentá en unos segundos.</p>
      {onRetry && <CfgBtn variant="primary" onClick={onRetry}>Reintentar</CfgBtn>}
    </div>
  );
}

// ── Section: General ─────────────────────────────────────────────────────────

function SectionGeneral() {
  const { me, setMe } = useAuth();
  const { theme, setTheme } = useTheme();
  const updateProfile = useUpdateProfile();

  const account = me?.account ?? {};
  const [fullName, setFullName] = useState(account.full_name ?? '');
  const [avatarColor, setAvatarColor] = useState(account.avatar_color ?? 'navy');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setFullName(account.full_name ?? '');
    setAvatarColor(account.avatar_color ?? 'navy');
    setDirty(false);
  }, [account.full_name, account.avatar_color]);

  const initial = account.full_name ?? '';
  const initials = (fullName || initial || account.email || '?').substring(0, 2).toUpperCase();

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateProfile.mutateAsync({ full_name: fullName, avatar_color: avatarColor });
      pushToast({ text: 'Perfil actualizado.', kind: 'success' });
      setDirty(false);
    } catch {
      pushToast({ text: 'Error al guardar el perfil.', kind: 'danger' });
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setFullName(account.full_name ?? '');
    setAvatarColor(account.avatar_color ?? 'navy');
    setDirty(false);
  };

  return (
    <div>
      <CfgSectionHead title="General" description="Tu perfil y las preferencias de la aplicación." />

      <H3>Perfil</H3>
      <CfgRow label="Avatar" hint="Inicial generada a partir de tu nombre.">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {AVATAR_COLORS.map(c => (
              <button key={c.key} title={c.label} onClick={() => { setAvatarColor(c.key); setDirty(true); }} style={{
                width: 18, height: 18, borderRadius: 9999, background: c.hex, cursor: 'pointer',
                border: `2px solid ${avatarColor === c.key ? 'var(--cfg-brand)' : 'transparent'}`,
                outline: 'none',
              }} />
            ))}
          </div>
          <div style={{
            width: 44, height: 44, borderRadius: 9999, background: avatarHex(avatarColor),
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            font: '600 16px/1 Inter,sans-serif',
          }}>{initials}</div>
        </div>
      </CfgRow>
      <CfgRow label="Nombre completo" hint="Cómo aparece tu nombre en el panel.">
        <CfgInput value={fullName} onChange={e => { setFullName(e.target.value); setDirty(true); }} placeholder="Tu nombre" maxLength={200} />
      </CfgRow>

      <H3>Preferencias</H3>
      <CfgRow label="Apariencia" hint="Claro u oscuro para toda la aplicación.">
        <div style={{ display: 'flex', gap: 3, background: 'var(--cfg-card2)', borderRadius: 9, padding: 3 }}>
          {[
            { key: 'light', icon: ICONS.sun,  label: 'Claro' },
            { key: 'dark',  icon: ICONS.moon, label: 'Oscuro' },
          ].map(t => (
            <button key={t.key} title={t.label} onClick={() => setTheme(t.key)} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 5, padding: '6px 12px', borderRadius: 7, border: 'none', cursor: 'pointer',
              font: '500 13px/1 Inter,sans-serif',
              background: theme === t.key ? 'var(--cfg-card)' : 'transparent',
              color: theme === t.key ? 'var(--cfg-strong)' : 'var(--cfg-muted)',
              boxShadow: theme === t.key ? '0 1px 3px rgba(0,0,0,.1)' : 'none',
            }}>{t.icon}{t.label}</button>
          ))}
        </div>
      </CfgRow>

      {dirty && (
        <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
          <CfgBtn variant="ghost" onClick={handleDiscard} disabled={saving}>Descartar</CfgBtn>
          <CfgBtn variant="primary" onClick={handleSave} disabled={saving}>{saving ? 'Guardando…' : 'Guardar perfil'}</CfgBtn>
        </div>
      )}
    </div>
  );
}

// ── Section: Cuenta ────────────────────────────────────────────────────────────

function SectionCuenta() {
  const { me, logout } = useAuth();
  const changePasswordMut = useChangePassword();
  const account = me?.account ?? {};
  const authMethods = me?.auth_methods ?? [];
  const hasPassword = authMethods.includes('password');
  const hasGoogle = authMethods.includes('google');

  const [showPwd, setShowPwd] = useState(false);
  const [curPwd, setCurPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [repPwd, setRepPwd] = useState('');
  const [savingPwd, setSavingPwd] = useState(false);

  const handleChangePwd = async () => {
    if (!curPwd || !newPwd) { pushToast({ text: 'Completá todos los campos.', kind: 'danger' }); return; }
    if (newPwd !== repPwd) { pushToast({ text: 'Las contraseñas nuevas no coinciden.', kind: 'danger' }); return; }
    if (newPwd.length < 8) { pushToast({ text: 'La nueva contraseña debe tener al menos 8 caracteres.', kind: 'danger' }); return; }
    setSavingPwd(true);
    try {
      await changePasswordMut.mutateAsync({ current_password: curPwd, new_password: newPwd });
      pushToast({ text: 'Contraseña actualizada.', kind: 'success' });
      setCurPwd(''); setNewPwd(''); setRepPwd('');
      setShowPwd(false);
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'Error al cambiar la contraseña.', kind: 'danger' });
    } finally {
      setSavingPwd(false);
    }
  };

  return (
    <div>
      <CfgSectionHead title="Cuenta" description="Tu acceso y seguridad." />

      <H3>Identidad</H3>
      <CfgRow label="Email" hint="Tu dirección de acceso.">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ font: '400 14px/1.4 Inter,sans-serif', color: 'var(--cfg-muted)' }}>{account.email}</span>
          <span style={{ font: '500 11px/1 Inter,sans-serif', color: 'var(--cfg-soft)', background: 'var(--cfg-card2)', padding: '4px 8px', borderRadius: 6 }}>Solo lectura</span>
        </div>
      </CfgRow>
      <CfgRow label="Email verificado" hint={account.email_verified ? 'Email confirmado.' : 'Pendiente de verificación.'}>
        {account.email_verified ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-ok)', background: 'var(--cfg-ok-bg)', padding: '6px 11px', borderRadius: 9999 }}>{ICONS.check}Verificado</span>
        ) : (
          <span style={{ font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-warn)', background: 'var(--cfg-warn-bg)', padding: '6px 11px', borderRadius: 9999 }}>No verificado</span>
        )}
      </CfgRow>
      <CfgRow label="Métodos de login" hint="Cómo ingresás a tu cuenta.">
        <div style={{ display: 'flex', gap: 8 }}>
          {hasPassword && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '500 13px/1 Inter,sans-serif', color: 'var(--cfg-strong)', border: '1px solid var(--cfg-line)', background: 'var(--cfg-card)', padding: '7px 11px', borderRadius: 8 }}>
              🔒 Contraseña
            </span>
          )}
          {hasGoogle && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '500 13px/1 Inter,sans-serif', color: 'var(--cfg-strong)', border: '1px solid var(--cfg-line)', background: 'var(--cfg-card)', padding: '7px 11px', borderRadius: 8 }}>
              <span style={{ font: '700 13px/1 Inter,sans-serif', color: '#4285F4' }}>G</span> Google
            </span>
          )}
        </div>
      </CfgRow>

      <H3>Seguridad</H3>
      <CfgRow label="Contraseña" hint={hasPassword ? 'Autenticación con email y clave.' : 'Esta cuenta usa solo Google OAuth.'}>
        {hasPassword ? (
          <CfgBtn variant="secondary" onClick={() => setShowPwd(v => !v)}>{showPwd ? 'Cancelar' : 'Cambiar contraseña'}</CfgBtn>
        ) : (
          <span style={{ font: '400 13px/1.4 Inter,sans-serif', color: 'var(--cfg-muted)' }}>No aplica (cuenta Google)</span>
        )}
      </CfgRow>
      {showPwd && (
        <div style={{ background: 'var(--cfg-card2)', border: '1px solid var(--cfg-line)', borderRadius: 12, padding: 18, marginTop: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {[
            { label: 'Contraseña actual', val: curPwd, set: setCurPwd, placeholder: '••••••••' },
            { label: 'Nueva contraseña',  val: newPwd, set: setNewPwd, placeholder: 'Mínimo 8 caracteres' },
            { label: 'Repetir nueva contraseña', val: repPwd, set: setRepPwd, placeholder: 'Repetí la nueva clave' },
          ].map(f => (
            <div key={f.label} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-muted)' }}>{f.label}</label>
              <CfgInput type="password" value={f.val} onChange={e => f.set(e.target.value)} placeholder={f.placeholder} autoComplete="new-password" />
            </div>
          ))}
          <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
            <CfgBtn variant="primary" onClick={handleChangePwd} disabled={savingPwd}>{savingPwd ? 'Guardando…' : 'Guardar contraseña'}</CfgBtn>
            <CfgBtn variant="ghost" onClick={() => setShowPwd(false)}>Cancelar</CfgBtn>
          </div>
        </div>
      )}
      <CfgRow label="Sesión" hint="Cerrar sesión en este dispositivo.">
        <CfgBtn variant="danger" onClick={logout}>Cerrar sesión</CfgBtn>
      </CfgRow>
    </div>
  );
}

// ── Section: Mi inmobiliaria ───────────────────────────────────────────────────

const TIMEZONES = [
  'America/Argentina/Buenos_Aires',
  'America/Argentina/Cordoba',
  'America/Montevideo',
  'America/Santiago',
  'America/Bogota',
  'America/Lima',
];

function SectionInmobiliaria() {
  const { me } = useAuth();
  const { data: tenantData, isLoading, isError, refetch } = useMyTenant();
  const updateMyTenant = useUpdateMyTenant();

  const [form, setForm] = useState({ display_name: '', business_hours: '', agent_whatsapp: '', timezone: '', company_name: '' });
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!tenantData) return;
    setForm({
      display_name: tenantData.display_name ?? '',
      company_name: tenantData.company_name ?? '',
      business_hours: tenantData.business_hours ?? '',
      agent_whatsapp: tenantData.agent_whatsapp ?? '',
      timezone: tenantData.timezone ?? 'America/Argentina/Buenos_Aires',
    });
    setDirty(false);
  }, [tenantData]);

  const set = (k) => (e) => { setForm(f => ({ ...f, [k]: e.target.value })); setDirty(true); };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMyTenant.mutateAsync(form);
      pushToast({ text: 'Datos de la inmobiliaria actualizados.', kind: 'success' });
      setDirty(false);
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'Error al guardar.', kind: 'danger' });
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    if (!tenantData) return;
    setForm({
      display_name: tenantData.display_name ?? '',
      company_name: tenantData.company_name ?? '',
      business_hours: tenantData.business_hours ?? '',
      agent_whatsapp: tenantData.agent_whatsapp ?? '',
      timezone: tenantData.timezone ?? 'America/Argentina/Buenos_Aires',
    });
    setDirty(false);
  };

  if (isLoading) return <Skeleton />;
  if (isError) return <SectionError onRetry={refetch} />;

  const waConnected = me?.whatsapp_status === 'connected';

  return (
    <div>
      <CfgSectionHead title="Mi inmobiliaria" description="Estos datos aparecen en los mensajes de WhatsApp que envía el bot." />

      <H3>Identidad del negocio</H3>
      <CfgRow label="Nombre comercial" hint="Aparece en el saludo inicial del bot.">
        <CfgInput value={form.display_name} onChange={set('display_name')} placeholder="Inmobiliaria López" maxLength={200} />
      </CfgRow>

      <H3>Operación</H3>
      <CfgRow label="Horario de atención" hint="El bot lo menciona al explicar disponibilidad.">
        <CfgInput value={form.business_hours} onChange={set('business_hours')} placeholder="Lunes a sábado de 9 a 18 hs" maxLength={300} />
      </CfgRow>
      <CfgRow label="WhatsApp del agente humano" hint="Número al que se transfiere cuando piden hablar con una persona.">
        <CfgInput value={form.agent_whatsapp} onChange={set('agent_whatsapp')} placeholder="+54 9 11 5555-3456" maxLength={30} />
      </CfgRow>
      <CfgRow label="Zona horaria" hint="Define horarios y recordatorios de visitas.">
        <select value={form.timezone} onChange={set('timezone')} style={{ font: '400 14px/1.4 Inter,sans-serif', color: 'var(--cfg-strong)', background: 'var(--cfg-input)', border: '1px solid var(--cfg-line)', borderRadius: 8, padding: '9px 12px', width: 280, outline: 'none' }}>
          {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
        </select>
      </CfgRow>
      <CfgRow label="Estado de WhatsApp" hint="Conexión del número del bot con Meta.">
        {waConnected ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-ok)', background: 'var(--cfg-ok-bg)', padding: '7px 12px', borderRadius: 9999 }}>
            <span style={{ width: 7, height: 7, borderRadius: 9999, background: 'var(--cfg-wa)' }} />Conectado
          </span>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-warn)', background: 'var(--cfg-warn-bg)', padding: '7px 12px', borderRadius: 9999 }}>
              <span style={{ width: 7, height: 7, borderRadius: 9999, background: 'var(--cfg-warn)' }} />Pendiente
            </span>
            <button disabled title="Próximamente: Embedded Signup de Meta" style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 13px/1 Inter,sans-serif', color: '#fff', background: 'var(--cfg-wa)', border: '1px solid var(--cfg-wa)', borderRadius: 8, padding: '8px 12px', cursor: 'not-allowed', opacity: 0.5 }}>
              {ICONS.wa}Conectar WhatsApp
            </button>
          </div>
        )}
      </CfgRow>

      {dirty && (
        <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
          <CfgBtn variant="ghost" onClick={handleDiscard} disabled={saving}>Descartar</CfgBtn>
          <CfgBtn variant="primary" onClick={handleSave} disabled={saving}>{saving ? 'Guardando…' : 'Guardar cambios'}</CfgBtn>
        </div>
      )}
    </div>
  );
}

// ── Section: Facturación ──────────────────────────────────────────────────────

function SectionFacturacion() {
  const { me } = useAuth();
  const { data: billing, isLoading: loadingBilling, refetch: refetchBilling } = useBillingStatus();
  const { data: plans, isLoading: loadingPlans } = useBillingPlans();
  const { data: payments, isLoading: loadingPayments } = usePaymentHistory();
  const subscribeMut = useSubscribe();
  const [subscribing, setSubscribing] = useState(null);
  const [awaitingPayment, setAwaitingPayment] = useState(null);
  const prevBillingRef = useRef(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const mpStatus = params.get('payment_status') || params.get('status');
    if (mpStatus === 'approved') {
      pushToast({ kind: 'success', text: '¡Pago procesado! Tu plan se actualizará en instantes.' });
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    } else if (mpStatus === 'failure') {
      pushToast({ kind: 'danger', text: 'El pago no pudo procesarse. Intentá de nuevo.' });
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    } else if (mpStatus === 'pending') {
      pushToast({ kind: 'info', text: 'Pago pendiente de confirmación.' });
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    }
  }, []);

  const handleSubscribe = async (planName) => {
    setSubscribing(planName);
    try {
      const { init_point } = await subscribeMut.mutateAsync(planName);
      window.open(init_point, '_blank', 'noopener,noreferrer');
      prevBillingRef.current = null; // reset so effect captures fresh baseline
      setAwaitingPayment(planName);
    } catch (err) {
      const msg = err?.response?.data?.detail ?? 'No se pudo iniciar el pago.';
      pushToast({ kind: 'danger', text: typeof msg === 'string' ? msg : 'No se pudo iniciar el pago.' });
    } finally {
      setSubscribing(null);
    }
  };

  // ponytail: poll on window focus + 5s fallback while awaiting MP confirmation
  useEffect(() => {
    if (!awaitingPayment) return;
    window.addEventListener('focus', refetchBilling);
    const interval = setInterval(refetchBilling, 5000);
    return () => { window.removeEventListener('focus', refetchBilling); clearInterval(interval); };
  }, [awaitingPayment, refetchBilling]);

  useEffect(() => {
    if (!awaitingPayment || !billing) return;
    if (!prevBillingRef.current) { prevBillingRef.current = billing; return; }
    const prev = prevBillingRef.current;
    prevBillingRef.current = billing;
    const planMatch = billing.plan?.toLowerCase() === awaitingPayment.toLowerCase();
    if (billing.status === 'active' && (planMatch || prev.status !== 'active')) {
      setAwaitingPayment(null);
      pushToast({ kind: 'success', text: `¡Plan ${awaitingPayment} activado!` });
    }
  }, [billing, awaitingPayment]);

  const currentPlan = billing?.plan ?? me?.subscription?.plan ?? me?.plan ?? null;
  const currentStatus = billing?.status ?? me?.subscription?.status ?? null;
  const trialEnds = billing?.trial_ends_at ?? me?.subscription?.trial_ends_at ?? null;
  const periodEnd = billing?.current_period_end ?? null;

  const daysLeft = trialEnds
    ? Math.ceil((new Date(trialEnds).getTime() - Date.now()) / 86_400_000)
    : null;

  return (
    <div>
      <CfgSectionHead title="Facturación" description="Gestioná tu plan y tu suscripción." />

      {awaitingPayment && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, background: 'var(--cfg-card)', border: '1px solid var(--cfg-brand)', borderRadius: 12, padding: '16px 20px', marginTop: 22 }}>
          <div>
            <div style={{ font: '600 14px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>Esperando confirmación del pago…</div>
            <div style={{ font: '400 12px/1.4 Inter,sans-serif', color: 'var(--cfg-muted)', marginTop: 4 }}>Completá el pago en la ventana de MercadoPago. La página se actualizará automáticamente.</div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <CfgBtn variant="secondary" onClick={() => refetchBilling()}>Verificar ahora</CfgBtn>
            <CfgBtn variant="ghost" onClick={() => setAwaitingPayment(null)}>Cancelar</CfgBtn>
          </div>
        </div>
      )}

      {loadingBilling ? (
        <Skeleton />
      ) : (
        <>
          {currentStatus === 'trial' && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, background: 'var(--cfg-warn-bg)', border: '1px solid color-mix(in srgb, var(--cfg-warn) 30%, transparent)', borderRadius: 12, padding: '18px 20px', marginTop: 22 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ font: '600 17px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>Prueba gratis</span>
                  {daysLeft !== null && <span style={{ font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-warn)', background: 'color-mix(in srgb, var(--cfg-warn) 16%, transparent)', padding: '5px 10px', borderRadius: 9999 }}>Quedan {Math.max(0, daysLeft)} días</span>}
                </div>
              </div>
              <CfgBtn variant="primary" onClick={() => handleSubscribe(currentPlan ?? 'profesional')}>Activar ahora</CfgBtn>
            </div>
          )}
          {currentStatus === 'active' && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, background: 'var(--cfg-card)', border: '1px solid var(--cfg-line)', borderRadius: 12, padding: '18px 20px', marginTop: 22 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ font: '600 17px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>Plan {currentPlan}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-ok)', background: 'var(--cfg-ok-bg)', padding: '5px 10px', borderRadius: 9999 }}><span style={{ width: 6, height: 6, borderRadius: 9999, background: 'var(--cfg-ok)' }} />Activo</span>
                </div>
                {periodEnd && <p style={{ font: '400 13px/1.5 Inter,sans-serif', color: 'var(--cfg-muted)', margin: '6px 0 0' }}>Se renueva el {new Date(periodEnd).toLocaleDateString('es-AR')}.</p>}
              </div>
              <CfgBtn variant="secondary" onClick={() => handleSubscribe(currentPlan)}>Gestionar pago</CfgBtn>
            </div>
          )}
          {currentStatus === 'past_due' && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, background: 'var(--cfg-bad-bg)', border: '1px solid color-mix(in srgb, var(--cfg-bad) 32%, transparent)', borderRadius: 12, padding: '18px 20px', marginTop: 22 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ font: '600 17px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>Plan vencido</span>
                  <span style={{ font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-bad)', background: 'color-mix(in srgb, var(--cfg-bad) 15%, transparent)', padding: '5px 10px', borderRadius: 9999 }}>Vencido</span>
                </div>
                <p style={{ font: '400 13px/1.5 Inter,sans-serif', color: 'var(--cfg-muted)', margin: '6px 0 0' }}>Regularizá el pago para reactivar el bot.</p>
              </div>
              <CfgBtn variant="danger" onClick={() => handleSubscribe(currentPlan)}>Reintentar pago</CfgBtn>
            </div>
          )}
        </>
      )}

      <div style={{ font: '600 12px/1 Inter,sans-serif', letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--cfg-soft)', margin: '32px 0 14px' }}>Planes disponibles</div>
      {loadingPlans ? <Skeleton /> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {(plans ?? []).map(plan => {
            const isCurrent = plan.name === currentPlan;
            const isEnterprise = !plan.self_serve;
            return (
              <div key={plan.name} style={{ background: 'var(--cfg-card)', border: isCurrent ? '1.5px solid var(--cfg-brand)' : '1px solid var(--cfg-line)', borderRadius: 12, padding: 20, display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ font: '600 15px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>{plan.display_name ?? plan.name}</span>
                  {isCurrent && <span style={{ font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-brand)', background: 'var(--cfg-nav-act)', padding: '5px 9px', borderRadius: 9999 }}>Tu plan</span>}
                </div>
                <div style={{ margin: '10px 0 14px' }}>
                  {plan.price_ars_monthly ? (
                    <><span style={{ font: '600 26px/1 Inter,sans-serif', color: 'var(--cfg-strong)', letterSpacing: '-.02em' }}>${Number(plan.price_ars_monthly).toLocaleString('es-AR')}</span><span style={{ font: '400 13px/1 Inter,sans-serif', color: 'var(--cfg-soft)' }}> /mes</span></>
                  ) : <span style={{ font: '600 20px/1 Inter,sans-serif', color: 'var(--cfg-strong)' }}>{isEnterprise ? 'A consultar' : 'Gratis'}</span>}
                </div>
                <div style={{ borderTop: '1px solid var(--cfg-line-soft)', paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 9, flex: 1 }}>
                  {(plan.features ?? []).slice(0, 4).map(f => (
                    <span key={f} style={{ display: 'flex', gap: 8, font: '400 13px/1.4 Inter,sans-serif', color: 'var(--cfg-txt)' }}>
                      <span style={{ color: 'var(--cfg-ok)', flexShrink: 0 }}>{ICONS.check}</span>{f}
                    </span>
                  ))}
                </div>
                <div style={{ marginTop: 16 }}>
                  {isCurrent ? (
                    <button disabled style={{ width: '100%', font: '600 14px/1 Inter,sans-serif', color: 'var(--cfg-soft)', background: 'var(--cfg-card2)', border: '1px solid var(--cfg-line)', borderRadius: 8, padding: 10, cursor: 'default' }}>Plan actual</button>
                  ) : isEnterprise ? (
                    <a href="mailto:ventas@viviendapp.com" style={{ display: 'block', textAlign: 'center', font: '600 14px/1 Inter,sans-serif', color: 'var(--cfg-strong)', background: 'var(--cfg-card)', border: '1px solid var(--cfg-line)', borderRadius: 8, padding: 10, textDecoration: 'none' }}>Hablar con ventas</a>
                  ) : (
                    <button onClick={() => handleSubscribe(plan.name)} disabled={subscribing === plan.name || !!awaitingPayment} style={{ width: '100%', font: '600 14px/1 Inter,sans-serif', color: 'var(--cfg-strong)', background: 'var(--cfg-card)', border: '1px solid var(--cfg-line)', borderRadius: 8, padding: 10, cursor: 'pointer' }}>
                      {subscribing === plan.name ? 'Abriendo…' : awaitingPayment ? 'Pago pendiente…' : `Cambiar a ${plan.display_name ?? plan.name}`}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ font: '600 12px/1 Inter,sans-serif', letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--cfg-soft)', margin: '32px 0 14px' }}>Historial de pagos</div>
      {loadingPayments ? <Skeleton /> : (!payments || payments.length === 0) ? (
        <p style={{ font: '400 13px/1.5 Inter,sans-serif', color: 'var(--cfg-muted)', margin: 0 }}>Sin pagos registrados aún.</p>
      ) : (
        <div style={{ border: '1px solid var(--cfg-line)', borderRadius: 10, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', font: '400 13px/1.4 Inter,sans-serif', color: 'var(--cfg-txt)' }}>
            <thead>
              <tr style={{ background: 'var(--cfg-card2)', borderBottom: '1px solid var(--cfg-line)' }}>
                {['Fecha', 'Monto', 'Estado'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '10px 14px', font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-soft)', letterSpacing: '.04em', textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {payments.map((p, i) => (
                <tr key={p.id} style={{ borderBottom: i < payments.length - 1 ? '1px solid var(--cfg-line-soft)' : 'none' }}>
                  <td style={{ padding: '11px 14px' }}>{p.date ? new Date(p.date).toLocaleDateString('es-AR') : '—'}</td>
                  <td style={{ padding: '11px 14px' }}>${Number(p.amount).toLocaleString('es-AR', { minimumFractionDigits: 2 })} {p.currency}</td>
                  <td style={{ padding: '11px 14px' }}>
                    <span style={{ font: '600 11px/1 Inter,sans-serif', padding: '4px 9px', borderRadius: 9999, background: p.status === 'approved' ? 'var(--cfg-ok-bg)' : 'var(--cfg-card2)', color: p.status === 'approved' ? 'var(--cfg-ok)' : 'var(--cfg-muted)' }}>
                      {p.status === 'approved' ? 'Aprobado' : p.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Section: Uso ───────────────────────────────────────────────────────────────

function UsageBar({ label, used, limit }) {
  const pct = limit && used != null ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const fillColor = pct >= 80 ? 'var(--cfg-bad)' : pct >= 50 ? 'var(--cfg-warn)' : 'var(--cfg-brand)';
  const note = pct >= 80 ? 'Cerca del límite' : pct >= 50 ? 'Uso moderado' : null;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ font: '600 14px/1.4 Inter,sans-serif', color: 'var(--cfg-strong)' }}>{label}</span>
        <span style={{ font: '500 13px/1 Inter,sans-serif', color: 'var(--cfg-muted)' }}>
          {limit ? `${used ?? '—'} / ${limit}` : 'Ilimitado'}
        </span>
      </div>
      <div style={{ height: 9, borderRadius: 9999, background: 'var(--cfg-bar-track)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: fillColor, borderRadius: 9999, transition: 'width .3s' }} />
      </div>
      {note && <div style={{ font: '400 12px/1.4 Inter,sans-serif', color: fillColor, marginTop: 6 }}>{note}</div>}
    </div>
  );
}

function SectionUso() {
  const { data: usage, isLoading, isError, refetch } = useUsage();

  if (isLoading) return <Skeleton />;
  if (isError) return <SectionError onRetry={refetch} />;

  const periodEnd = usage?.period_end;
  const periodLabel = periodEnd
    ? `Conversaciones del período (se renueva el ${new Date(periodEnd).toLocaleDateString('es-AR')})`
    : 'Conversaciones (últimos 30 días)';

  return (
    <div>
      <CfgSectionHead title="Uso" description="Consumo del período de facturación actual." />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, marginTop: 28 }}>
        <UsageBar label="Propiedades" used={usage?.properties?.used} limit={usage?.properties?.limit} />
        <UsageBar label={periodLabel} used={usage?.conversations_month?.used} limit={usage?.conversations_month?.limit} />
        <UsageBar label="Miembros del equipo" used={usage?.team_members?.used} limit={usage?.team_members?.limit} />
      </div>
      <p style={{ font: '400 12px/1.5 Inter,sans-serif', color: 'var(--cfg-soft)', margin: '26px 0 0' }}>
        El bot sigue respondiendo aunque superes el límite, pero te recomendamos ampliar el plan para no interrumpir el servicio.
      </p>
    </div>
  );
}

// ── Section: Equipo ────────────────────────────────────────────────────────────

function SectionEquipo() {
  const { data: members, isLoading, isError, refetch } = useTeamMembers();
  const inviteMut = useInviteMember();
  const removeMut = useRemoveMember();
  const { me } = useAuth();

  const [showInvite, setShowInvite] = useState(false);
  const [invEmail, setInvEmail] = useState('');
  const [invName, setInvName] = useState('');
  const [inviting, setInviting] = useState(false);

  const handleInvite = async () => {
    if (!invEmail) { pushToast({ text: 'Ingresá un email.', kind: 'danger' }); return; }
    setInviting(true);
    try {
      await inviteMut.mutateAsync({ email: invEmail, name: invName || undefined });
      pushToast({ text: `Invitación enviada a ${invEmail}.`, kind: 'success' });
      setInvEmail(''); setInvName(''); setShowInvite(false);
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'Error al invitar.', kind: 'danger' });
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (m) => {
    if (!window.confirm(`¿Quitar a ${m.name ?? m.email} del equipo?`)) return;
    try {
      await removeMut.mutateAsync(m.id);
      pushToast({ text: 'Miembro eliminado.', kind: 'success' });
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'Error al quitar miembro.', kind: 'danger' });
    }
  };

  if (isLoading) return <Skeleton />;
  if (isError) return <SectionError onRetry={refetch} />;

  const list = members ?? [];
  const myId = me?.account?.id;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <CfgSectionHead title="Equipo" description="Quién tiene acceso a este panel." />
        <CfgBtn variant="primary" onClick={() => setShowInvite(v => !v)} style={{ flexShrink: 0 }}>
          {ICONS.plus}Invitar miembro
        </CfgBtn>
      </div>

      {showInvite && (
        <div style={{ background: 'var(--cfg-card2)', border: '1px solid var(--cfg-line)', borderRadius: 12, padding: 18, marginTop: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 10 }}>
            <CfgInput value={invEmail} onChange={e => setInvEmail(e.target.value)} placeholder="email@ejemplo.com" type="email" />
            <CfgInput value={invName} onChange={e => setInvName(e.target.value)} placeholder="Nombre (opcional)" />
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <CfgBtn variant="primary" onClick={handleInvite} disabled={inviting}>{inviting ? 'Enviando…' : 'Enviar invitación'}</CfgBtn>
            <CfgBtn variant="ghost" onClick={() => setShowInvite(false)}>Cancelar</CfgBtn>
          </div>
        </div>
      )}

      {list.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '56px 24px', border: '1px dashed var(--cfg-line)', borderRadius: 12, marginTop: 24 }}>
          <div style={{ width: 48, height: 48, borderRadius: 9999, background: 'var(--cfg-card2)', color: 'var(--cfg-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>{ICONS.equipo}</div>
          <h3 style={{ font: '600 16px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)', margin: '0 0 6px' }}>Todavía no invitaste a nadie</h3>
          <p style={{ font: '400 14px/1.55 Inter,sans-serif', color: 'var(--cfg-muted)', margin: '0 0 20px' }}>Sumá a tu equipo para que respondan y gestionen leads juntos.</p>
        </div>
      ) : (
        <div style={{ border: '1px solid var(--cfg-line)', borderRadius: 12, overflow: 'hidden', marginTop: 24 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.4fr auto', gap: 12, padding: '11px 18px', background: 'var(--cfg-card2)', font: '600 11px/1 Inter,sans-serif', letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--cfg-soft)' }}>
            <span>Miembro</span><span>Rol</span><span />
          </div>
          {list.map(m => {
            const ini = (m.name ?? m.email ?? '?').substring(0, 2).toUpperCase();
            const rolLabel = m.role === 'owner' ? 'Propietario' : m.role === 'admin' ? 'Administrador' : 'Agente';
            const isMe = m.id === myId;
            return (
              <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '2fr 1.4fr auto', gap: 12, alignItems: 'center', padding: '14px 18px', borderTop: '1px solid var(--cfg-line-soft)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 11, minWidth: 0 }}>
                  <div style={{ width: 34, height: 34, borderRadius: 9999, background: m.avatar_color ? avatarHex(m.avatar_color) : 'var(--cfg-nav-act)', color: m.avatar_color ? '#fff' : 'var(--cfg-nav-act-fg)', display: 'flex', alignItems: 'center', justifyContent: 'center', font: '600 13px/1 Inter,sans-serif', flexShrink: 0 }}>{ini}</div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ font: '600 14px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name ?? m.email}</div>
                    <div style={{ font: '400 12px/1.3 Inter,sans-serif', color: 'var(--cfg-soft)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.email}</div>
                  </div>
                </div>
                <span style={{ font: '500 13px/1.3 Inter,sans-serif', color: 'var(--cfg-txt)' }}>{rolLabel}</span>
                {isMe || m.role === 'owner' ? (
                  <span style={{ font: '500 13px/1 Inter,sans-serif', color: 'var(--cfg-soft)', padding: '6px 8px' }}>—</span>
                ) : (
                  <button onClick={() => handleRemove(m)} style={{ font: '500 13px/1 Inter,sans-serif', color: 'var(--cfg-bad)', background: 'transparent', border: 'none', cursor: 'pointer', padding: '6px 8px' }}>Quitar</button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Section: Sistema ───────────────────────────────────────────────────────────

function SectionSistema() {
  const { me } = useAuth();
  const updateSettings = useUpdateTenantSettings();
  const [router, setRouter] = useState('v2');
  const [switching, setSwitching] = useState(false);

  // Read from tenant's settings (comes from me response or bot settings)
  // Use the tenant_id's active router if available
  useEffect(() => {
    // The me response doesn't expose active_router directly;
    // default to v2 unless we get it from somewhere
  }, [me]);

  const handleSwitch = async (val) => {
    if (switching || val === router) return;
    const prev = router;
    setRouter(val);
    setSwitching(true);
    try {
      await updateSettings.mutateAsync({ id: me?.tenant_id, active_router: val });
      pushToast({ text: `Router ${val.toUpperCase()} activado.`, kind: 'success' });
    } catch {
      setRouter(prev);
      pushToast({ text: 'Error al cambiar el router.', kind: 'danger' });
    } finally {
      setSwitching(false);
    }
  };

  const activeOpt = ROUTER_OPTIONS.find(o => o.value === router) ?? ROUTER_OPTIONS[1];

  return (
    <div>
      <CfgSectionHead title="Sistema" description="Control del motor del chatbot. Los cambios aplican en el próximo mensaje recibido." />
      <div style={{ font: '600 12px/1 Inter,sans-serif', letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--cfg-soft)', margin: '30px 0 12px' }}>Router del chatbot</div>
      <div style={{ display: 'flex', gap: 4, background: 'var(--cfg-card2)', borderRadius: 10, padding: 4, maxWidth: 420 }}>
        {ROUTER_OPTIONS.map(o => (
          <button key={o.value} onClick={() => handleSwitch(o.value)} disabled={switching} style={{
            flex: 1, padding: '9px 0', borderRadius: 8, border: 'none', cursor: switching ? 'default' : 'pointer',
            font: '600 14px/1 Inter,sans-serif',
            background: router === o.value ? 'var(--cfg-card)' : 'transparent',
            color: router === o.value ? 'var(--cfg-strong)' : 'var(--cfg-muted)',
            boxShadow: router === o.value ? '0 1px 3px rgba(0,0,0,.1)' : 'none',
          }}>{o.label}</button>
        ))}
      </div>
      <p style={{ font: '400 13px/1.55 Inter,sans-serif', color: 'var(--cfg-muted)', margin: '14px 0 0', maxWidth: 520 }}>{activeOpt.desc}</p>
    </div>
  );
}

// ── Section: Inmobiliarias (admin) ────────────────────────────────────────────

const EMPTY_TENANT = { slug: '', display_name: '', company_name: '', business_hours: '', timezone: 'America/Argentina/Cordoba', waba_id: '', phone_number_id: '', wa_access_token: '', plan: '', status: 'active' };

function TenantRow({ t, onEdit, onDelete, busy }) {
  const waConnected = !!t.phone_number_id;
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, border: '1px solid var(--cfg-line)', borderRadius: 12, padding: '16px 18px', background: 'var(--cfg-card)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 13, minWidth: 0 }}>
        <div style={{ width: 38, height: 38, borderRadius: 9, background: 'var(--cfg-nav-act)', color: 'var(--cfg-nav-act-fg)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{ICONS.inmobiliaria}</div>
        <div style={{ minWidth: 0 }}>
          <div style={{ font: '600 14px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>{t.display_name}</div>
          <div style={{ font: '400 12px/1.3 Inter,sans-serif', color: 'var(--cfg-soft)', fontFamily: 'monospace' }}>{t.phone_number_id ?? t.slug}</div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        {t.active_router && <span style={{ font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-muted)', background: 'var(--cfg-card2)', padding: '5px 9px', borderRadius: 6 }}>Router {t.active_router.toUpperCase()}</span>}
        {waConnected ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-ok)', background: 'var(--cfg-ok-bg)', padding: '5px 10px', borderRadius: 9999 }}><span style={{ width: 6, height: 6, borderRadius: 9999, background: 'var(--cfg-wa)' }} />Conectado</span>
        ) : (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '600 11px/1 Inter,sans-serif', color: 'var(--cfg-warn)', background: 'var(--cfg-warn-bg)', padding: '5px 10px', borderRadius: 9999 }}><span style={{ width: 6, height: 6, borderRadius: 9999, background: 'var(--cfg-warn)' }} />Pendiente</span>
        )}
        <CfgBtn variant="secondary" onClick={() => onEdit(t.id)} disabled={busy} style={{ padding: '6px 12px', fontSize: 13 }}>Editar</CfgBtn>
        <CfgBtn variant="danger" onClick={() => onDelete(t)} disabled={busy} style={{ padding: '6px 12px', fontSize: 13 }}>Eliminar</CfgBtn>
      </div>
    </div>
  );
}

function TenantForm({ initial, onSubmit, onCancel, busy, isEdit }) {
  const [form, setForm] = useState(initial);
  useEffect(() => { setForm(initial); }, [initial]);
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  const submit = () => {
    if (!form.display_name.trim() || (!isEdit && !form.slug.trim())) {
      pushToast({ text: 'Slug y nombre son obligatorios.', kind: 'danger' }); return;
    }
    const payload = {};
    Object.entries(form).forEach(([k, v]) => { if (v !== '' && v != null) payload[k] = typeof v === 'string' ? v.trim() : v; });
    if (isEdit) delete payload.slug;
    onSubmit(payload);
  };

  const inputStyle = { font: '400 14px/1.4 Inter,sans-serif', color: 'var(--cfg-strong)', background: 'var(--cfg-input)', border: '1px solid var(--cfg-line)', borderRadius: 8, padding: '9px 12px', width: '100%', outline: 'none' };
  const labelStyle = { font: '600 12px/1 Inter,sans-serif', color: 'var(--cfg-muted)', display: 'block', marginBottom: 4 };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 16, padding: 18, background: 'var(--cfg-card2)', borderRadius: 12, border: '1px solid var(--cfg-line)' }}>
      {!isEdit && (
        <div><label style={labelStyle}>Slug</label><input type="text" value={form.slug} onChange={set('slug')} placeholder="obera" maxLength={60} style={inputStyle} /></div>
      )}
      <div><label style={labelStyle}>Nombre visible</label><input type="text" value={form.display_name} onChange={set('display_name')} placeholder="Inmobiliaria Oberá" maxLength={200} style={inputStyle} /></div>
      {isEdit && (
        <>
          <div><label style={labelStyle}>Phone Number ID (Meta)</label><input type="text" value={form.phone_number_id} onChange={set('phone_number_id')} placeholder="1120063544518404" maxLength={64} style={inputStyle} /></div>
          <div><label style={labelStyle}>WABA ID (Meta)</label><input type="text" value={form.waba_id} onChange={set('waba_id')} placeholder="WhatsApp Business Account id" maxLength={64} style={inputStyle} /></div>
          <div><label style={labelStyle}>Access token (vacío = no cambiar)</label><input type="password" value={form.wa_access_token} onChange={set('wa_access_token')} placeholder="EAAG…" autoComplete="off" style={inputStyle} /></div>
        </>
      )}
      <div><label style={labelStyle}>Horario de atención</label><input type="text" value={form.business_hours} onChange={set('business_hours')} placeholder="Lunes a sábado de 9 a 18hs" maxLength={300} style={inputStyle} /></div>
      <div><label style={labelStyle}>Zona horaria</label><input type="text" value={form.timezone} onChange={set('timezone')} placeholder="America/Argentina/Cordoba" maxLength={60} style={inputStyle} /></div>
      <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
        <CfgBtn variant="ghost" onClick={onCancel} disabled={busy}>Cancelar</CfgBtn>
        <CfgBtn variant="primary" onClick={submit} disabled={busy}>{busy ? 'Guardando…' : isEdit ? 'Guardar' : 'Crear inmobiliaria'}</CfgBtn>
      </div>
    </div>
  );
}

function SectionInmobiliarias() {
  const { data: tenants, isLoading } = useTenants();
  const createMut = useCreateTenant();
  const updateMut = useUpdateTenant();
  const deleteMut = useDeleteTenant();
  const [mode, setMode] = useState(null);
  const busy = createMut.isPending || updateMut.isPending || deleteMut.isPending;

  const handleCreate = async (payload) => {
    try { await createMut.mutateAsync(payload); pushToast({ text: 'Inmobiliaria creada.', kind: 'success' }); setMode(null); }
    catch (err) { pushToast({ text: err?.response?.data?.detail ?? 'Error al crear.', kind: 'danger' }); }
  };
  const handleUpdate = async (id, payload) => {
    try { await updateMut.mutateAsync({ id, ...payload }); pushToast({ text: 'Inmobiliaria actualizada.', kind: 'success' }); setMode(null); }
    catch (err) { pushToast({ text: err?.response?.data?.detail ?? 'Error al actualizar.', kind: 'danger' }); }
  };
  const handleDelete = async (t) => {
    if (!window.confirm(`¿Eliminar "${t.display_name}"? Se borran sus datos.`)) return;
    try { await deleteMut.mutateAsync(t.id); pushToast({ text: 'Inmobiliaria eliminada.', kind: 'success' }); }
    catch (err) { pushToast({ text: err?.response?.data?.detail ?? 'No se pudo eliminar.', kind: 'danger' }); }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <CfgSectionHead title="Inmobiliarias" description="Cada inmobiliaria tiene sus propios datos, número de WhatsApp y branding." />
        <CfgBtn variant="primary" onClick={() => setMode('create')} disabled={busy} style={{ flexShrink: 0 }}>{ICONS.plus}Nueva inmobiliaria</CfgBtn>
      </div>

      {isLoading ? <Skeleton /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 24 }}>
          {(tenants ?? []).map(t => (
            <TenantRow key={t.id} t={t} onEdit={id => setMode(id)} onDelete={handleDelete} busy={busy} />
          ))}
          {(tenants ?? []).length === 0 && <p style={{ color: 'var(--cfg-muted)', font: '400 14px/1.5 Inter,sans-serif' }}>No hay inmobiliarias provisionadas todavía.</p>}
        </div>
      )}

      {mode === 'create' && (
        <TenantForm initial={EMPTY_TENANT} onSubmit={handleCreate} onCancel={() => setMode(null)} busy={busy} isEdit={false} />
      )}
      {mode && mode !== 'create' && (() => {
        const t = (tenants ?? []).find(x => x.id === mode);
        if (!t) return null;
        return <TenantForm initial={{ ...EMPTY_TENANT, ...t, wa_access_token: '' }} onSubmit={p => handleUpdate(t.id, p)} onCancel={() => setMode(null)} busy={busy} isEdit />;
      })()}
    </div>
  );
}

// ── Main Config component ─────────────────────────────────────────────────────

export default function Config() {
  const { me } = useAuth();
  const { theme } = useTheme();
  const [active, setActive] = useState('general');
  const [query, setQuery] = useState('');
  const role = me?.account?.role ?? 'agent';
  const isAdmin = role === 'owner' || role === 'admin' || role === 'superadmin';

  const visibleSections = NAV_SECTIONS.filter(s => !s.admin || isAdmin);

  const searchMode = query.trim().length > 0;
  const results = searchMode
    ? SEARCH_INDEX
        .filter(s => !NAV_SECTIONS.find(n => n.key === s.key)?.admin || isAdmin)
        .filter(s => s.terms.some(t => t.toLowerCase().includes(query.toLowerCase())))
        .map(s => ({ key: s.key, label: NAV_SECTIONS.find(n => n.key === s.key)?.label ?? s.key }))
    : [];

  const vars = CFG_VARS[theme === 'dark' ? 'dark' : 'light'];

  const navStyle = (key) => ({
    display: 'flex', alignItems: 'center', gap: 10,
    width: '100%', textAlign: 'left',
    padding: '9px 10px', borderRadius: 9, border: 'none', cursor: 'pointer',
    font: '500 14px/1.3 Inter,sans-serif',
    background: active === key ? 'var(--cfg-nav-act)' : 'transparent',
    color: active === key ? 'var(--cfg-nav-act-fg)' : 'var(--cfg-txt)',
  });

  const renderSection = () => {
    if (searchMode) {
      if (results.length === 0) {
        return (
          <div>
            <div style={{ font: '600 13px/1.4 Inter,sans-serif', color: 'var(--cfg-muted)', marginBottom: 16 }}>Resultados para «{query}»</div>
            <div style={{ textAlign: 'center', padding: '56px 20px', border: '1px dashed var(--cfg-line)', borderRadius: 12, color: 'var(--cfg-soft)', font: '400 15px/1.5 Inter,sans-serif' }}>No encontramos ajustes que coincidan.</div>
          </div>
        );
      }
      return (
        <div>
          <div style={{ font: '600 13px/1.4 Inter,sans-serif', color: 'var(--cfg-muted)', marginBottom: 16 }}>Resultados para «{query}»</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {results.map(r => (
              <button key={r.key} onClick={() => { setActive(r.key); setQuery(''); }} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14, width: '100%', textAlign: 'left', padding: '13px 16px', border: '1px solid var(--cfg-line)', borderRadius: 10, background: 'var(--cfg-card)', cursor: 'pointer', font: '600 14px/1.3 Inter,sans-serif', color: 'var(--cfg-strong)' }}>
                {r.label}
                <span style={{ font: '600 11px/1 Inter,sans-serif', letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--cfg-soft)' }}>Ir a sección</span>
              </button>
            ))}
          </div>
        </div>
      );
    }

    switch (active) {
      case 'general':       return <SectionGeneral />;
      case 'cuenta':        return <SectionCuenta />;
      case 'inmobiliaria':  return <SectionInmobiliaria />;
      case 'facturacion':   return <SectionFacturacion />;
      case 'uso':           return <SectionUso />;
      case 'equipo':        return <SectionEquipo />;
      case 'sistema':       return isAdmin ? <SectionSistema /> : null;
      case 'inmobiliarias': return isAdmin ? <SectionInmobiliarias /> : null;
      default:              return null;
    }
  };

  const searchInputStyle = {
    width: '100%', padding: '9px 12px 9px 34px',
    border: '1px solid var(--cfg-line)', borderRadius: 9,
    background: 'var(--cfg-card2)', color: 'var(--cfg-strong)',
    font: '400 14px/1 Inter,sans-serif', outline: 'none',
  };

  return (
    <div style={{ ...vars, height: '100vh', background: 'var(--cfg-page)', fontFamily: 'Inter,system-ui,sans-serif', display: 'flex', overflow: 'hidden', color: 'var(--cfg-txt)' }}>
      <style>{`
        @keyframes cfgpulse{0%,100%{opacity:.5}50%{opacity:1}}
        @keyframes cfgup{from{transform:translateY(110%)}to{transform:translateY(0)}}
        @media(max-width:860px){.cfg-rail{display:none!important}.cfg-mobnav{display:flex!important}.cfg-main-inner{padding:18px 16px 130px!important}}
      `}</style>

      {/* Rail */}
      <aside className="cfg-rail" style={{ width: 256, flexShrink: 0, background: 'var(--cfg-rail)', borderRight: '1px solid var(--cfg-line)', display: 'flex', flexDirection: 'column', padding: '16px 14px', overflowY: 'auto' }}>
        <div style={{ position: 'relative', marginBottom: 14 }}>
          <span style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--cfg-soft)', display: 'flex' }}>{ICONS.search}</span>
          <input type="text" placeholder="Buscar" value={query} onChange={e => setQuery(e.target.value)} style={searchInputStyle} />
        </div>
        <div style={{ font: '600 11px/1 Inter,sans-serif', letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--cfg-soft)', padding: '6px 10px 9px' }}>Configuración</div>
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {visibleSections.map(s => (
            <button key={s.key} onClick={() => { setActive(s.key); setQuery(''); }} style={navStyle(s.key)}>
              {ICONS[s.icon]}
              <span style={{ flex: 1 }}>{s.label}</span>
              {s.admin && <span style={{ font: '600 9px/1 Inter,sans-serif', letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--cfg-soft)', background: 'var(--cfg-card2)', padding: '3px 6px', borderRadius: 5 }}>Admin</span>}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, overflowY: 'auto', position: 'relative' }}>
        {/* Mobile nav */}
        <div className="cfg-mobnav" style={{ display: 'none', flexDirection: 'column', gap: 10, padding: '16px 16px 0', marginBottom: 0 }}>
          <div style={{ position: 'relative' }}>
            <span style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--cfg-soft)', display: 'flex' }}>{ICONS.search}</span>
            <input type="text" placeholder="Buscar" value={query} onChange={e => setQuery(e.target.value)} style={{ ...searchInputStyle, padding: '10px 12px 10px 34px', fontSize: 15 }} />
          </div>
          <select value={active} onChange={e => { setActive(e.target.value); setQuery(''); }} style={{ width: '100%', padding: '11px 12px', border: '1px solid var(--cfg-line)', borderRadius: 9, background: 'var(--cfg-input)', color: 'var(--cfg-strong)', font: '600 15px/1 Inter,sans-serif', outline: 'none' }}>
            {visibleSections.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>

        <div className="cfg-main-inner" style={{ maxWidth: 780, margin: '0 auto', padding: '34px 40px 130px' }}>
          {renderSection()}
        </div>
      </main>
    </div>
  );
}
