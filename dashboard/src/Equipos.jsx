import { useState } from 'react';
import { useAuth } from './auth';
import { useTeamMembers, useInviteMember, useRemoveMember } from './api';
import { Button, Icon } from './Primitives';

const AVATAR_PALETTE = ['#155f6f', '#3a5fa8', '#6b4d99', '#3d8b4f', '#b07d12'];

function getAvatarColor(str) {
  if (!str) return AVATAR_PALETTE[0];
  return AVATAR_PALETTE[str.charCodeAt(0) % AVATAR_PALETTE.length];
}

function getInitials(name, email) {
  const source = name || email || '?';
  const parts = source.split(/[\s@]/);
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : source.slice(0, 2).toUpperCase();
}

const ROLE_LABELS = {
  owner:      'Propietario',
  superadmin: 'Propietario',
  admin:      'Administrador',
  manager:    'Gerente',
};

const ROLE_PILL = {
  owner:      { label: 'Propietario',   kind: 'purple' },
  superadmin: { label: 'Propietario',   kind: 'purple' },
  admin:      { label: 'Administrador', kind: 'info' },
  manager:    { label: 'Gerente',       kind: 'neutral' },
};

const STATE_VARS = {
  success: { bg: 'var(--state-success-bg)', fg: 'var(--state-success-fg)', border: 'var(--state-success-border)' },
  warning: { bg: 'var(--state-warning-bg)', fg: 'var(--state-warning-fg)', border: 'var(--state-warning-border)' },
  purple:  { bg: 'var(--state-purple-bg)',  fg: 'var(--state-purple-fg)',  border: 'var(--state-purple-border)' },
  info:    { bg: 'var(--state-info-bg)',    fg: 'var(--state-info-fg)',    border: 'var(--state-info-border)' },
  neutral: { bg: 'var(--state-neutral-bg)', fg: 'var(--state-neutral-fg)', border: 'var(--state-neutral-border)' },
};

function StatePill({ kind, children, dot }) {
  const v = STATE_VARS[kind] || STATE_VARS.neutral;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap',
      background: v.bg, color: v.fg, border: `1px solid ${v.border}`,
      borderRadius: 'var(--radius-pill)', padding: '2px 10px',
      fontSize: 12, fontWeight: 600,
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: v.fg, flexShrink: 0 }} />}
      {children}
    </span>
  );
}

function formatRelative(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const now = new Date();
  const diffMin = Math.floor((now - d) / 60000);
  if (diffMin < 60) return `Hace ${Math.max(diffMin, 0)} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `Hace ${diffH} h`;
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const yest = new Date(now); yest.setDate(now.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return `Ayer · ${hh}:${mm}`;
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
}

export default function Equipos() {
  const { me } = useAuth();
  const { data: members = [], isLoading } = useTeamMembers();
  const inviteMutation = useInviteMember();
  const removeMutation = useRemoveMember();

  const [showForm, setShowForm]     = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName]   = useState('');
  const [formError, setFormError]     = useState('');
  const [expandedId, setExpandedId] = useState(null);

  async function handleInvite(e) {
    e.preventDefault();
    setFormError('');
    if (!inviteEmail.trim()) { setFormError('El email es requerido.'); return; }
    try {
      await inviteMutation.mutateAsync({
        email: inviteEmail.trim(),
        name:  inviteName.trim() || undefined,
      });
      setShowForm(false);
      setInviteEmail('');
      setInviteName('');
    } catch (err) {
      setFormError(err?.response?.data?.detail || 'Error al enviar la invitación.');
    }
  }

  async function handleRemove(member) {
    if (!window.confirm(`¿Eliminar a ${member.name || member.email} del equipo?`)) return;
    try {
      await removeMutation.mutateAsync(member.id);
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error al eliminar el miembro.');
    }
  }

  const myEmail = me?.account?.email;

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Equipos</h1>
          <p className="sub">
            Invitá usuarios a tu inmobiliaria para que trabajen en el dashboard. Tocá una persona para ver su sucursal a cargo y datos de contacto.
          </p>
        </div>
        {!showForm && (
          <div className="page-h-actions">
            <Button kind="primary" icon="plus" type="button" onClick={() => setShowForm(true)}>
              Nuevo usuario
            </Button>
          </div>
        )}
      </div>

      {showForm && (
        <form
          onSubmit={handleInvite}
          style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: 20, marginBottom: 24,
            display: 'flex', flexDirection: 'column', gap: 14,
          }}
        >
          <strong>Invitar usuario</strong>
          {formError && (
            <p style={{ color: 'var(--danger-600, #dc2626)', fontSize: 13, margin: 0 }}>
              {formError}
            </p>
          )}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 }}>
                Email *
              </label>
              <input
                type="email"
                placeholder="agente@ejemplo.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
                disabled={inviteMutation.isPending}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 }}>
                Nombre (opcional)
              </label>
              <input
                type="text"
                placeholder="Nombre del agente"
                value={inviteName}
                onChange={(e) => setInviteName(e.target.value)}
                disabled={inviteMutation.isPending}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" type="submit" disabled={inviteMutation.isPending}>
              {inviteMutation.isPending ? 'Enviando…' : 'Enviar invitación'}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => { setShowForm(false); setFormError(''); }}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>Cargando equipo…</p>
      ) : members.length === 0 ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>
          Todavía no invitaste a nadie. Hacé clic en "+ Nuevo usuario" para empezar.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {members.map((member) => {
            const isMe = member.email === myEmail;
            const isPrivileged = member.role === 'owner' || member.role === 'superadmin';
            const canDelete = !isMe && !isPrivileged && !member.branch_name;
            const isOpen = expandedId === member.id;
            const rolePill = ROLE_PILL[member.role];
            const isActive = member.status === 'accepted';
            const branchLabel = member.branch_name
              ? member.branch_name
              : (['owner', 'superadmin', 'admin'].includes(member.role) ? 'Todas las sucursales' : '—');

            return (
              <div
                key={member.id}
                style={{
                  background: 'var(--surface-raised)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 13,
                  boxShadow: 'var(--shadow-sm)',
                  overflow: 'hidden',
                }}
              >
                {/* Main row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '13px 16px' }}>
                  <div style={{
                    width: 42, height: 42, borderRadius: '50%', flexShrink: 0,
                    background: getAvatarColor(member.email),
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff', fontWeight: 700, fontSize: 15,
                  }}>
                    {getInitials(member.name, member.email)}
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14.5, color: 'var(--fg-primary)' }}>
                      {member.name || member.email}
                      {isMe && (
                        <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--fg-tertiary)', fontWeight: 400 }}>
                          (vos)
                        </span>
                      )}
                    </div>
                    <div style={{
                      fontSize: 12.5, color: 'var(--fg-tertiary)',
                      display: 'flex', alignItems: 'center', gap: 5,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{member.email}</span>
                      {member.branch_name && (
                        <>
                          <span style={{ flexShrink: 0 }}>·</span>
                          <Icon name="building" size={13} style={{ flexShrink: 0 }} />
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{member.branch_name}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {rolePill && <StatePill kind={rolePill.kind}>{rolePill.label}</StatePill>}
                  <StatePill kind={isActive ? 'success' : 'warning'} dot>
                    {isActive ? 'Activo' : 'Pendiente'}
                  </StatePill>
                  <button
                    type="button"
                    onClick={() => setExpandedId(isOpen ? null : member.id)}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0,
                      background: 'var(--surface-raised)', border: '1px solid var(--border-strong)',
                      borderRadius: 8, padding: '7px 12px', fontSize: 12.5, fontWeight: 500,
                      color: 'var(--fg-secondary)', cursor: 'pointer', whiteSpace: 'nowrap',
                    }}
                  >
                    {isOpen ? 'Ocultar' : 'Ver datos'}
                    <Icon name="chevronDown" size={14}
                      style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 200ms ease' }} />
                  </button>
                </div>

                {/* Detail panel */}
                {isOpen && (
                  <div style={{
                    borderTop: '1px solid var(--border-subtle)',
                    background: 'var(--bg-subtle)',
                    padding: 16,
                    animation: 'equiposFadeIn 200ms ease',
                  }}>
                    <style>{`@keyframes equiposFadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }`}</style>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
                      {[
                        { icon: 'building', label: 'Sucursal a cargo', value: branchLabel },
                        { icon: 'phone',   label: 'Teléfono',          value: member.phone || '—' },
                        { icon: 'mail',    label: 'Email',              value: member.email },
                        { icon: 'clock',   label: 'Último acceso',      value: formatRelative(member.last_active_at) },
                      ].map((cell, i) => (
                        <div key={i}>
                          <div style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase',
                            letterSpacing: '0.04em', color: 'var(--fg-tertiary)',
                          }}>
                            <Icon name={cell.icon} size={13} />
                            {cell.label}
                          </div>
                          <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-primary)', marginTop: 5 }}>
                            {cell.value}
                          </div>
                        </div>
                      ))}
                    </div>

                    <div style={{ display: 'flex', gap: 8, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                      <a
                        href={member.phone ? `https://wa.me/${member.phone.replace(/[^\d]/g, '')}` : undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={!member.phone ? (e) => e.preventDefault() : undefined}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none',
                          background: 'var(--state-success-bg)', color: 'var(--state-success-fg)',
                          border: '1px solid var(--state-success-border)',
                          borderRadius: 8, padding: '7px 12px', fontSize: 12.5, fontWeight: 500,
                          opacity: member.phone ? 1 : 0.4,
                          cursor: member.phone ? 'pointer' : 'not-allowed',
                        }}
                      >
                        <Icon name="whatsapp" size={14} /> WhatsApp
                      </a>
                      <a
                        href={member.phone ? `tel:${member.phone}` : undefined}
                        onClick={!member.phone ? (e) => e.preventDefault() : undefined}
                        className="btn btn-secondary"
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none',
                          padding: '7px 12px', fontSize: 12.5,
                          opacity: member.phone ? 1 : 0.4,
                          cursor: member.phone ? 'pointer' : 'not-allowed',
                        }}
                      >
                        <Icon name="phone" size={14} /> Llamar
                      </a>
                      <a
                        href={`mailto:${member.email}`}
                        className="btn btn-secondary"
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none',
                          padding: '7px 12px', fontSize: 12.5,
                        }}
                      >
                        <Icon name="mail" size={14} /> Email
                      </a>
                      {canDelete && (
                        <button
                          type="button"
                          onClick={() => handleRemove(member)}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 6, marginLeft: 'auto',
                            background: 'transparent', border: '1px solid var(--danger-100)',
                            borderRadius: 8, padding: '7px 12px', fontSize: 12.5, fontWeight: 500,
                            color: 'var(--danger-500)', cursor: 'pointer',
                          }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--danger-50)'; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                        >
                          <Icon name="trash" size={14} /> Quitar
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
