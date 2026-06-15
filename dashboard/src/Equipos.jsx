import { useState } from 'react';
import { useAuth } from './auth';
import { useTeamMembers, useInviteMember, useRemoveMember } from './api';
import { Button } from './Primitives';

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

function StatusBadge({ status }) {
  const map = {
    accepted: { label: 'Activo',    bg: '#d1fae5', color: '#065f46' },
    pending:  { label: 'Pendiente', bg: '#fef3c7', color: '#92400e' },
    revoked:  { label: 'Revocado',  bg: '#f3f4f6', color: '#6b7280' },
  };
  const s = map[status] || map.revoked;
  return (
    <span style={{
      background: s.bg, color: s.color, borderRadius: 12,
      padding: '2px 10px', fontSize: 12, fontWeight: 600,
    }}>
      {s.label}
    </span>
  );
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
            Invitá usuarios a tu inmobiliaria para que trabajen en el dashboard.
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {members.map((member) => {
            const isMe = member.email === myEmail;
            const canDelete = !isMe;
            return (
              <div
                key={member.id}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 10, padding: '12px 16px',
                }}
              >
                <div style={{
                  width: 40, height: 40, borderRadius: '50%',
                  background: getAvatarColor(member.email),
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontWeight: 700, fontSize: 15, flexShrink: 0,
                }}>
                  {getInitials(member.name, member.email)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>
                    {member.name || member.email}
                    {isMe && (
                      <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--muted, #6b7280)', fontWeight: 400 }}>
                        (vos)
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize: 12, color: 'var(--muted, #6b7280)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {member.email}
                  </div>
                </div>
                <StatusBadge status={member.status} />
                {canDelete && (
                  <button
                    className="btn btn-danger"
                    type="button"
                    onClick={() => handleRemove(member)}
                    disabled={removeMutation.isPending}
                    style={{ padding: '4px 12px', fontSize: 13 }}
                  >
                    Eliminar
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
