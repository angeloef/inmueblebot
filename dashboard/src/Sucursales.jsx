import { useState } from 'react';
import { useAuth } from './auth';
import { Icon } from './Primitives';
import { useBranches, useCreateBranch, useCreateManager } from './api';

const FIELD_LABEL = { fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 4 };
const CARD = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 10, padding: 16,
};

function Field({ label, children, hint }) {
  return (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label style={FIELD_LABEL}>{label}</label>
      {children}
      {hint && <div style={{ fontSize: 11, color: 'var(--muted, #6b7280)', marginTop: 3 }}>{hint}</div>}
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
        {!showForm && (
          <button className="btn btn-primary" type="button" onClick={() => setShowForm(true)}>
            + Nueva sucursal
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={handleCreate} style={{ ...CARD, marginBottom: 24, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <strong>Nueva sucursal</strong>
          {error && <p style={{ color: 'var(--danger-600, #dc2626)', fontSize: 13, margin: 0 }}>{error}</p>}

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Field label="Nombre de la sucursal *">
              <input value={form.display_name} onChange={set('display_name')} placeholder="Ej: Sucursal Centro"
                     required style={{ width: '100%', boxSizing: 'border-box' }} />
            </Field>
            <Field label="Dirección">
              <input value={form.address} onChange={set('address')} placeholder="Calle 123, Ciudad"
                     style={{ width: '100%', boxSizing: 'border-box' }} />
            </Field>
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Field label="Horario de atención">
              <input value={form.business_hours} onChange={set('business_hours')}
                     placeholder="Lun a Vie 9 a 18hs" style={{ width: '100%', boxSizing: 'border-box' }} />
            </Field>
          </div>

          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <strong style={{ fontSize: 13 }}>WhatsApp de la sucursal</strong>
            <p style={{ fontSize: 12, color: 'var(--muted, #6b7280)', margin: '4px 0 10px' }}>
              Cada sucursal usa su propio número de Meta. Pegá el Phone Number ID, el WABA ID y el token de acceso.
            </p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Field label="Phone Number ID">
                <input value={form.phone_number_id} onChange={set('phone_number_id')}
                       placeholder="1234567890" style={{ width: '100%', boxSizing: 'border-box' }} />
              </Field>
              <Field label="WABA ID">
                <input value={form.waba_id} onChange={set('waba_id')}
                       placeholder="9876543210" style={{ width: '100%', boxSizing: 'border-box' }} />
              </Field>
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
              <Field label="Access Token de Meta" hint="Se guarda cifrado.">
                <input value={form.wa_access_token} onChange={set('wa_access_token')} type="password"
                       placeholder="EAAG..." style={{ width: '100%', boxSizing: 'border-box' }} />
              </Field>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <strong style={{ fontSize: 13 }}>Gerente de la sucursal (opcional)</strong>
            <p style={{ fontSize: 12, color: 'var(--muted, #6b7280)', margin: '4px 0 10px' }}>
              Le crea un login que ve y gestiona solo esta sucursal. Podés agregarlo después también.
            </p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Field label="Email del gerente">
                <input value={form.manager_email} onChange={set('manager_email')} type="email"
                       placeholder="gerente@ejemplo.com" style={{ width: '100%', boxSizing: 'border-box' }} />
              </Field>
              <Field label="Contraseña inicial">
                <input value={form.manager_password} onChange={set('manager_password')} type="text"
                       placeholder="mín. 6 caracteres" style={{ width: '100%', boxSizing: 'border-box' }} />
              </Field>
              <Field label="Nombre (opcional)">
                <input value={form.manager_name} onChange={set('manager_name')}
                       placeholder="Nombre del gerente" style={{ width: '100%', boxSizing: 'border-box' }} />
              </Field>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" type="submit" disabled={createBranch.isPending}>
              {createBranch.isPending ? 'Creando…' : 'Crear sucursal'}
            </button>
            <button className="btn btn-secondary" type="button" onClick={() => { setShowForm(false); setError(''); }}>
              Cancelar
            </button>
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
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {branches.map(b => (
            <div key={b.id} style={CARD}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--surface-2, #f3f4f6)',
                              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon name="building" size={18} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</div>
                  {b.address && <div style={{ fontSize: 12, color: 'var(--muted, #6b7280)' }}>{b.address}</div>}
                </div>
                <span title={b.wa_connected ? 'WhatsApp conectado' : 'Sin WhatsApp'}
                      style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 10,
                               background: b.wa_connected ? '#d1fae5' : '#f3f4f6',
                               color: b.wa_connected ? '#065f46' : '#6b7280' }}>
                  {b.wa_connected ? 'WhatsApp OK' : 'Sin WhatsApp'}
                </span>
              </div>
              {b.business_hours && (
                <div style={{ fontSize: 12, color: 'var(--muted, #6b7280)', marginBottom: 6 }}>🕑 {b.business_hours}</div>
              )}
              <div style={{ fontSize: 12, color: 'var(--muted, #6b7280)', marginBottom: 12 }}>
                {b.managers?.length ? `Gerentes: ${b.managers.join(', ')}` : 'Sin gerente asignado'}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-primary" type="button" style={{ flex: 1 }} onClick={() => selectBranch(b.id)}>
                  Entrar
                </button>
                <button className="btn btn-secondary" type="button" onClick={() => handleAddManager(b)}>
                  + Gerente
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
