import { useState } from 'react';
import { useAuth } from './auth';
import { Icon, Button } from './Primitives';
import { useBranches, useCreateBranch, useCreateManager } from './api';

function Field({ label, children, hint }) {
  return (
    <div className="field" style={{ flex: 1, minWidth: 200 }}>
      <label>{label}</label>
      {children}
      {hint && <div className="field-error" style={{ color: 'var(--fg-tertiary)' }}>{hint}</div>}
    </div>
  );
}

const EMPTY = {
  display_name: '', address: '', business_hours: '',
  phone_number_id: '', waba_id: '', wa_access_token: '',
  manager_email: '', manager_password: '', manager_name: '',
};

export default function Sucursales() {
  const { selectBranch } = useAuth();
  const { data: branches = [], isLoading } = useBranches();
  const createBranch = useCreateBranch();
  const createManager = useCreateManager();

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  async function handleCreate(e) {
    e.preventDefault();
    setError('');
    if (!form.display_name.trim()) { setError('El nombre de la sucursal es requerido.'); return; }
    if (form.manager_email && form.manager_password.length < 6) {
      setError('La contraseña del gerente debe tener al menos 6 caracteres.'); return;
    }
    const payload = {
      display_name: form.display_name.trim(),
      address: form.address.trim() || undefined,
      business_hours: form.business_hours.trim() || undefined,
      phone_number_id: form.phone_number_id.trim() || undefined,
      waba_id: form.waba_id.trim() || undefined,
      wa_access_token: form.wa_access_token.trim() || undefined,
    };
    if (form.manager_email.trim()) {
      payload.manager = {
        email: form.manager_email.trim(),
        password: form.manager_password,
        full_name: form.manager_name.trim() || undefined,
      };
    }
    try {
      await createBranch.mutateAsync(payload);
      setForm(EMPTY);
      setShowForm(false);
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudo crear la sucursal.');
    }
  }

  async function handleAddManager(branch) {
    const email = window.prompt(`Email del gerente para "${branch.name}":`);
    if (!email) return;
    const password = window.prompt('Contraseña inicial (mín. 6 caracteres):');
    if (!password || password.length < 6) { alert('Contraseña inválida.'); return; }
    try {
      await createManager.mutateAsync({ branchId: branch.id, email: email.trim(), password });
    } catch (err) {
      alert(err?.response?.data?.detail || 'No se pudo crear el gerente.');
    }
  }

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Sucursales</h1>
          <p className="sub">
            Cada sucursal tiene su propio WhatsApp, catálogo y equipo. Como dueño ves el
            consolidado y podés entrar a gestionar cada una.
          </p>
        </div>
        <div className="page-h-actions">
          {!showForm && (
            <Button kind="primary" icon="plus" onClick={() => setShowForm(true)}>
              Nueva sucursal
            </Button>
          )}
        </div>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          style={{
            background: 'var(--surface-raised)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-xl)',
            boxShadow: 'var(--shadow-sm)',
            marginBottom: 24,
            overflow: 'hidden',
          }}
        >
          {/* Form header */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 34, height: 34, borderRadius: 9,
                background: 'var(--accent-50)', border: '1px solid var(--accent-100)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Icon name="building" size={17} style={{ color: 'var(--accent-600)' }} />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--fg-primary)' }}>Nueva sucursal</div>
                <div style={{ fontSize: 12, color: 'var(--fg-tertiary)', marginTop: 1 }}>Completá los datos básicos para empezar.</div>
              </div>
            </div>
          </div>

          {/* Form body */}
          <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {error && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'var(--state-danger-bg, #fef2f2)',
                border: '1px solid var(--state-danger-border, #fecaca)',
                borderRadius: 'var(--radius-md)', padding: '10px 14px',
                fontSize: 13, color: 'var(--danger-500)',
              }}>
                <Icon name="alert" size={14} style={{ flexShrink: 0 }} />
                {error}
              </div>
            )}

            {/* Datos básicos */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--fg-tertiary)', marginBottom: 12 }}>
                Datos básicos
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                <Field label="Nombre de la sucursal *">
                  <input value={form.display_name} onChange={set('display_name')}
                    placeholder="Ej: Sucursal Centro" required
                    style={{ width: '100%', boxSizing: 'border-box' }} />
                </Field>
                <Field label="Dirección">
                  <input value={form.address} onChange={set('address')}
                    placeholder="Calle 123, Ciudad"
                    style={{ width: '100%', boxSizing: 'border-box' }} />
                </Field>
                <Field label="Horario de atención">
                  <input value={form.business_hours} onChange={set('business_hours')}
                    placeholder="Lun a Vie 9 a 18hs"
                    style={{ width: '100%', boxSizing: 'border-box' }} />
                </Field>
              </div>
            </div>

            {/* Gerente */}
            <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 20 }}>
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--fg-tertiary)' }}>
                  Gerente de la sucursal <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 'normal' }}>(opcional)</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--fg-tertiary)', marginTop: 4 }}>
                  Le crea un login que ve y gestiona solo esta sucursal. Podés agregarlo después también.
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                <Field label="Email del gerente">
                  <input value={form.manager_email} onChange={set('manager_email')} type="email"
                    placeholder="gerente@ejemplo.com"
                    style={{ width: '100%', boxSizing: 'border-box' }} />
                </Field>
                <Field label="Contraseña inicial">
                  <input value={form.manager_password} onChange={set('manager_password')} type="text"
                    placeholder="mín. 6 caracteres"
                    style={{ width: '100%', boxSizing: 'border-box' }} />
                </Field>
                <Field label="Nombre del gerente">
                  <input value={form.manager_name} onChange={set('manager_name')}
                    placeholder="Nombre completo"
                    style={{ width: '100%', boxSizing: 'border-box' }} />
                </Field>
              </div>
            </div>
          </div>

          {/* Form footer */}
          <div style={{
            display: 'flex', gap: 8, justifyContent: 'flex-end',
            padding: '14px 20px',
            borderTop: '1px solid var(--border-subtle)',
            background: 'var(--bg-subtle)',
          }}>
            <Button kind="secondary" type="button" onClick={() => { setShowForm(false); setError(''); }}>
              Cancelar
            </Button>
            <Button kind="primary" type="submit" disabled={createBranch.isPending}>
              {createBranch.isPending ? 'Creando…' : 'Crear sucursal'}
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>Cargando sucursales…</p>
      ) : branches.length === 0 ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>
          Todavía no tenés sucursales. Creá la primera con "+ Nueva sucursal".
        </p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
          {branches.map(b => {
            const managerName = b.manager_name || b.managers?.[0] || 'Sin gerente asignado';
            const hasStats = b.properties_count != null || b.active_leads != null || b.agents_count != null;
            return (
              <div
                key={b.id}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-3px)';
                  e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                  e.currentTarget.style.borderColor = 'var(--accent-100)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'none';
                  e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
                  e.currentTarget.style.borderColor = 'var(--border-default)';
                }}
                style={{
                  background: 'var(--surface-raised)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-xl)',
                  padding: 18,
                  boxShadow: 'var(--shadow-sm)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 14,
                  transition: 'transform 180ms cubic-bezier(.2,.7,.2,1), box-shadow 180ms cubic-bezier(.2,.7,.2,1), border-color 180ms cubic-bezier(.2,.7,.2,1)',
                }}
              >
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                  <div style={{
                    width: 42, height: 42, borderRadius: 11, flexShrink: 0,
                    background: 'var(--accent-50)', border: '1px solid var(--accent-100)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Icon name="building" size={20} style={{ color: 'var(--accent-600)' }} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontWeight: 700, fontSize: 16, color: 'var(--fg-primary)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{b.name}</div>
                  </div>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5, flexShrink: 0,
                    borderRadius: 'var(--radius-pill)', padding: '2px 8px',
                    fontSize: 11, fontWeight: 600,
                    background: b.wa_connected ? 'var(--state-success-bg)' : 'var(--state-neutral-bg)',
                    color: b.wa_connected ? 'var(--state-success-fg)' : 'var(--state-neutral-fg)',
                    border: `1px solid ${b.wa_connected ? 'var(--state-success-border)' : 'var(--state-neutral-border)'}`,
                  }}>
                    <Icon name="whatsapp" size={12} />
                    {b.wa_connected ? 'Conectado' : 'Sin WhatsApp'}
                  </span>
                </div>

                {/* Metadata list */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9, fontSize: 13, color: 'var(--fg-secondary)' }}>
                  {b.address && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Icon name="mapPin" size={15} style={{ color: 'var(--fg-muted)', flexShrink: 0 }} />
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.address}</span>
                    </div>
                  )}
                  {b.business_hours && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Icon name="clock" size={15} style={{ color: 'var(--fg-muted)', flexShrink: 0 }} />
                      <span>{b.business_hours}</span>
                    </div>
                  )}
                  {b.phone && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Icon name="phone" size={15} style={{ color: 'var(--fg-muted)', flexShrink: 0 }} />
                      <span style={{ fontVariantNumeric: 'tabular-nums' }}>{b.phone}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Icon name="user" size={15} style={{ color: 'var(--fg-muted)', flexShrink: 0 }} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      Gerente: <strong style={{ color: 'var(--fg-primary)', fontWeight: 500 }}>{managerName}</strong>
                    </span>
                  </div>
                </div>

                {/* Stats row (only when data available) */}
                {hasStats && (
                  <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
                    borderTop: '1px solid var(--border-subtle)', paddingTop: 12,
                  }}>
                    {[
                      { n: b.properties_count, label: 'Propiedades', accent: false },
                      { n: b.active_leads, label: 'Leads activos', accent: true },
                      { n: b.agents_count, label: 'Agentes', accent: false },
                    ].map((s, i) => (
                      <div key={i} style={{ textAlign: 'center' }}>
                        <div style={{
                          fontSize: 19, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
                          color: s.accent ? 'var(--accent-600)' : 'var(--fg-primary)',
                        }}>{s.n ?? 0}</div>
                        <div style={{
                          fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase',
                          letterSpacing: '0.04em', color: 'var(--fg-tertiary)', marginTop: 2,
                        }}>{s.label}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
                  <Button
                    kind="primary"
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => selectBranch(b.id)}
                  >
                    Entrar
                    <Icon name="arrowRight" size={14} style={{ marginLeft: 6 }} />
                  </Button>
                  <Button kind="secondary" icon="userPlus" onClick={() => handleAddManager(b)}>
                    Gerente
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
