import React, { useState, Fragment } from 'react';
import { Icon, Button, IconButton, Pill, pushToast } from './Primitives';
import { fmtCurrency } from './data';
import {
  useContracts, useContract, useCobranzasSummary, useClients, useProperties,
  useCreateContract, useUpdateContract, useDeleteContract,
  useGenerateCharges, useUpdateCharge, usePayCharge, useRemindCharge,
  useCreateExpense, useDeleteExpense, useIndices, useUpsertIndex,
} from './api';
import { useFocusTrap } from './useFocusTrap';
import DocumentsPanel from './DocumentsPanel';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const money = (n, cur) => fmtCurrency(n, cur);

const fmtDate = (iso) => {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
};

const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const fmtPeriod = (iso) => {
  if (!iso) return '—';
  const [y, m] = iso.slice(0, 10).split('-');
  return `${MONTHS[Number(m) - 1]} ${y}`;
};

// charge.display_status → Pill kind
const CHARGE_PILL = {
  paid:      { kind: 'paid',      label: 'Pagado' },
  pending:   { kind: 'pending',   label: 'Pendiente' },
  partial:   { kind: 'pending',   label: 'Parcial' },
  overdue:   { kind: 'expired',   label: 'Vencido' },
  cancelled: { kind: 'cancelled', label: 'Anulado' },
};

const CONTRACT_PILL = {
  active:    { kind: 'active',    label: 'Activo' },
  ended:     { kind: 'cancelled', label: 'Finalizado' },
  cancelled: { kind: 'cancelled', label: 'Cancelado' },
};

const ADJ_LABEL = { IPC: 'IPC (INDEC)', fixed: '% fijo', none: 'Sin ajuste' };

const adjDescription = (c) => {
  if (c.adjustment_index === 'none') return 'Sin ajuste';
  const each = `cada ${c.adjustment_frequency_months} ${c.adjustment_frequency_months === 1 ? 'mes' : 'meses'}`;
  if (c.adjustment_index === 'fixed') return `+${c.adjustment_fixed_pct ?? 0}% ${each}`;
  return `IPC ${each}`;
};

// ─── Editor de contrato (modal) ───────────────────────────────────────────────

function ContractEditor({ contract, mode, onClose, onSave, saving }) {
  const isEdit = mode === 'edit';
  const { data: clients = [] } = useClients();
  const { data: properties = [] } = useProperties();

  const [form, setForm] = useState({
    property_id: contract?.property_id ?? '',
    tenant_id:   contract?.tenant_id ?? '',
    owner_id:    contract?.owner_id ?? '',
    start_date:  contract?.start_date?.slice(0, 10) ?? '',
    end_date:    contract?.end_date?.slice(0, 10) ?? '',
    base_rent:   contract?.base_rent ?? '',
    currency:    contract?.currency ?? 'ARS',
    payment_due_day: contract?.payment_due_day ?? 10,
    grace_days:  contract?.grace_days ?? 0,
    adjustment_index: contract?.adjustment_index ?? 'IPC',
    adjustment_frequency_months: contract?.adjustment_frequency_months ?? 3,
    adjustment_fixed_pct: contract?.adjustment_fixed_pct ?? '',
    punitorio_daily_pct: contract?.punitorio_daily_pct ?? 0,
    commission_pct: contract?.commission_pct ?? 0,
    notes: contract?.notes ?? '',
  });
  const [errors, setErrors] = useState({});
  const set = (k, v) => { setErrors(e => ({ ...e, [k]: '' })); setForm(f => ({ ...f, [k]: v })); };

  const handleSave = () => {
    const errs = {};
    if (!form.start_date) errs.start_date = 'Requerido.';
    if (!form.base_rent || Number(form.base_rent) <= 0) errs.base_rent = 'Ingresá el alquiler.';
    if (Object.keys(errs).length) { setErrors(errs); return; }
    const payload = {
      property_id: form.property_id ? Number(form.property_id) : null,
      tenant_id:   form.tenant_id || null,
      owner_id:    form.owner_id || null,
      start_date:  form.start_date,
      end_date:    form.end_date || null,
      base_rent:   Number(form.base_rent) || 0,
      currency:    form.currency,
      payment_due_day: Number(form.payment_due_day) || 10,
      grace_days:  Number(form.grace_days) || 0,
      adjustment_index: form.adjustment_index,
      adjustment_frequency_months: Number(form.adjustment_frequency_months) || 1,
      adjustment_fixed_pct: form.adjustment_index === 'fixed' ? (Number(form.adjustment_fixed_pct) || 0) : null,
      punitorio_daily_pct: Number(form.punitorio_daily_pct) || 0,
      commission_pct: Number(form.commission_pct) || 0,
      notes: form.notes || null,
    };
    onSave(payload);
  };

  const rentals = properties.filter(p => p.operation === 'rent');
  const propList = rentals.length ? rentals : properties;

  const trapRef = useFocusTrap(onClose);

  return (
    <div className="modal-backdrop" onClick={onClose} aria-hidden="true">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="contract-editor-title" ref={trapRef} onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-head">
          <h3 id="contract-editor-title">{isEdit ? 'Modificar contrato' : 'Nuevo contrato'}</h3>
          <span className="close"><IconButton name="x" title="Cerrar" onClick={onClose} /></span>
        </div>
        <div className="modal-body">
          <div className="field-row">
            <div className="field">
              <label>Propiedad</label>
              <select value={form.property_id} onChange={e => set('property_id', e.target.value)}>
                <option value="">— Sin asignar —</option>
                {propList.map(p => <option key={p.id} value={p.id}>{p.addr || `Propiedad ${p.id}`}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Inquilino</label>
              <select value={form.tenant_id} onChange={e => set('tenant_id', e.target.value)}>
                <option value="">— Sin asignar —</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Propietario</label>
              <select value={form.owner_id} onChange={e => set('owner_id', e.target.value)}>
                <option value="">— Sin asignar —</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Comisión inmobiliaria (%)</label>
              <input type="number" value={form.commission_pct} onChange={e => set('commission_pct', e.target.value)} placeholder="0" />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Inicio *</label>
              <input type="date" className={errors.start_date ? 'invalid' : ''} value={form.start_date} onChange={e => set('start_date', e.target.value)} />
              {errors.start_date && <span className="field-error">{errors.start_date}</span>}
            </div>
            <div className="field">
              <label>Fin</label>
              <input type="date" value={form.end_date} onChange={e => set('end_date', e.target.value)} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Alquiler base *</label>
              <input type="number" className={errors.base_rent ? 'invalid' : ''} value={form.base_rent} onChange={e => set('base_rent', e.target.value)} placeholder="0" />
              {errors.base_rent && <span className="field-error">{errors.base_rent}</span>}
            </div>
            <div className="field">
              <label>Moneda</label>
              <select value={form.currency} onChange={e => set('currency', e.target.value)}>
                <option value="ARS">ARS ($)</option>
                <option value="USD">USD</option>
              </select>
            </div>
            <div className="field">
              <label>Día de vencimiento</label>
              <input type="number" min="1" max="31" value={form.payment_due_day} onChange={e => set('payment_due_day', e.target.value)} />
            </div>
          </div>
          <div className="field-row">
            <div className="field">
              <label>Ajuste</label>
              <select value={form.adjustment_index} onChange={e => set('adjustment_index', e.target.value)}>
                <option value="IPC">IPC (INDEC)</option>
                <option value="fixed">% fijo</option>
                <option value="none">Sin ajuste</option>
              </select>
            </div>
            <div className="field">
              <label>Frecuencia ajuste (meses)</label>
              <input type="number" min="1" value={form.adjustment_frequency_months} onChange={e => set('adjustment_frequency_months', e.target.value)} disabled={form.adjustment_index === 'none'} />
            </div>
            {form.adjustment_index === 'fixed' && (
              <div className="field">
                <label>% por ajuste</label>
                <input type="number" value={form.adjustment_fixed_pct} onChange={e => set('adjustment_fixed_pct', e.target.value)} placeholder="8" />
              </div>
            )}
          </div>
          <div className="field-row">
            <div className="field">
              <label>Punitorio diario (%)</label>
              <input type="number" step="0.01" value={form.punitorio_daily_pct} onChange={e => set('punitorio_daily_pct', e.target.value)} placeholder="0.1" />
            </div>
            <div className="field">
              <label>Días de gracia</label>
              <input type="number" min="0" value={form.grace_days} onChange={e => set('grace_days', e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label>Notas</label>
            <textarea value={form.notes} onChange={e => set('notes', e.target.value)} placeholder="Cláusulas, observaciones..." />
          </div>
        </div>
        <div className="modal-foot">
          <Button kind="ghost" size="sm" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button kind="primary" size="sm" icon="check" onClick={handleSave} disabled={saving}>
            {saving ? 'Guardando…' : isEdit ? 'Guardar cambios' : 'Crear contrato'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Fila de cobro ────────────────────────────────────────────────────────────

function ChargeRow({ ch, contract, onPay, onRemind, onEditAmount, busy }) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(ch.base_amount);
  const pill = CHARGE_PILL[ch.display_status] ?? CHARGE_PILL.pending;
  const cur = contract.currency;
  const isOpen = ch.display_status !== 'paid' && ch.display_status !== 'cancelled';

  const saveAmount = () => { setEditing(false); if (Number(amount) !== ch.base_amount) onEditAmount(ch, Number(amount) || 0); };

  return (
    <tr>
      <td>{fmtPeriod(ch.period)}</td>
      <td className="muted">{fmtDate(ch.due_date)}</td>
      <td className="tabular">
        {editing ? (
          <input type="number" value={amount} autoFocus style={{ width: 110 }}
                 onChange={e => setAmount(e.target.value)}
                 onBlur={saveAmount}
                 onKeyDown={e => { if (e.key === 'Enter') saveAmount(); if (e.key === 'Escape') setEditing(false); }} />
        ) : (
          isOpen ? (
            <button type="button" className="amount-edit-btn" aria-label={`Editar monto (${money(ch.base_amount, cur)})`}
                    style={{ background: 'none', border: 'none', font: 'inherit', color: 'inherit', cursor: 'pointer', padding: 0 }}
                    onClick={() => setEditing(true)}>
              {money(ch.base_amount, cur)}<Icon name="edit" size={11} style={{ marginLeft: 4, opacity: 0.4, verticalAlign: 'middle' }} />
            </button>
          ) : (
            <span>{money(ch.base_amount, cur)}</span>
          )
        )}
      </td>
      <td className="tabular muted">{ch.expenses_amount ? money(ch.expenses_amount, cur) : '—'}</td>
      <td className="tabular" style={{ color: ch.punitorio_amount ? 'var(--danger-600)' : undefined }}>
        {ch.punitorio_amount ? money(ch.punitorio_amount, cur) : '—'}
      </td>
      <td className="tabular"><b>{money(ch.total_amount, cur)}</b></td>
      <td><Pill kind={pill.kind}>{pill.label}</Pill></td>
      <td>
        <div className="row-actions" style={{ justifyContent: 'flex-end' }}>
          {isOpen && <IconButton name="whatsapp" title="Recordar por WhatsApp" onClick={() => onRemind(ch)} />}
          {isOpen && <Button kind="primary" size="sm" icon="check" onClick={() => onPay(ch)} disabled={busy}>Pagar</Button>}
          {ch.reminder_sent_at && !isOpen && <span className="muted" style={{ fontSize: 11 }}>recordado</span>}
        </div>
      </td>
    </tr>
  );
}

// ─── Drawer de contrato ───────────────────────────────────────────────────────

function ContractDrawer({ contractId, onClose, onEdit, onDelete }) {
  const { data: contract, isLoading } = useContract(contractId);
  const generateMut = useGenerateCharges();
  const payMut       = usePayCharge(contractId);
  const remindMut    = useRemindCharge(contractId);
  const updateChargeMut = useUpdateCharge(contractId);
  const createExpenseMut = useCreateExpense(contractId);
  const deleteExpenseMut = useDeleteExpense(contractId);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [exp, setExp] = useState({ description: '', amount: '', category: 'servicio', recurring: false });
  const trapRef = useFocusTrap(onClose);

  if (!contractId) return null;

  const cur = contract?.currency ?? 'ARS';

  const handleGenerate = () => generateMut.mutate(contractId, {
    onSuccess: (d) => pushToast({ text: d.created > 0 ? `${d.created} cobro(s) generados.` : 'Sin cobros nuevos.' }),
    onError:   () => pushToast({ text: 'Error al generar cobros.', kind: 'danger' }),
  });
  const handlePay = (ch) => payMut.mutate({ id: ch.id }, {
    onSuccess: () => pushToast({ text: 'Cobro registrado como pagado.' }),
    onError:   () => pushToast({ text: 'Error al registrar el pago.', kind: 'danger' }),
  });
  const handleRemind = (ch) => remindMut.mutate(ch.id, {
    onSuccess: (d) => pushToast({ text: d.status === 'sent' ? 'Recordatorio enviado por WhatsApp.' : 'No se pudo enviar el recordatorio.', kind: d.status === 'sent' ? undefined : 'danger' }),
    onError:   (e) => pushToast({ text: e?.response?.data?.detail || 'Error al enviar el recordatorio.', kind: 'danger' }),
  });
  const handleEditAmount = (ch, base_amount) => updateChargeMut.mutate({ id: ch.id, base_amount }, {
    onSuccess: () => pushToast({ text: 'Monto actualizado.' }),
    onError:   () => pushToast({ text: 'Error al actualizar el monto.', kind: 'danger' }),
  });
  const handleAddExpense = () => {
    if (!exp.description.trim() || !Number(exp.amount)) { pushToast({ text: 'Completá descripción y monto.', kind: 'danger' }); return; }
    createExpenseMut.mutate({ contractId, description: exp.description, amount: Number(exp.amount), category: exp.category, recurring: exp.recurring }, {
      onSuccess: () => { setExp({ description: '', amount: '', category: 'servicio', recurring: false }); pushToast({ text: 'Gasto registrado.' }); },
      onError:   () => pushToast({ text: 'Error al registrar el gasto.', kind: 'danger' }),
    });
  };

  return (
    <Fragment>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="drawer wide" role="dialog" aria-modal="true" aria-labelledby="contract-drawer-title" ref={trapRef}>
        <div className="drawer-head" style={{ padding: 0, display: 'block', borderBottom: 'none' }}>
          <div style={{ display: 'flex', padding: '12px 16px 0', justifyContent: 'flex-end', gap: 4, alignItems: 'center' }}>
            <IconButton name="edit" title="Editar contrato" aria-label="Editar contrato" onClick={() => onEdit(contract)} />
            {confirmDelete
              ? <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--danger-600)' }}>
                  ¿Eliminar?
                  <Button kind="danger" size="sm" onClick={() => onDelete(contract)}>Sí</Button>
                  <Button kind="ghost" size="sm" onClick={() => setConfirmDelete(false)}>No</Button>
                </span>
              : <IconButton name="trash" title="Eliminar contrato" aria-label="Eliminar contrato" onClick={() => setConfirmDelete(true)} />
            }
            <IconButton name="x" title="Cerrar" onClick={onClose} />
          </div>
          <div className="client-hero" style={{ borderBottom: 'none', paddingTop: 6 }}>
            <span className="client-av size-lg" aria-hidden="true"><Icon name="contract" /></span>
            <div className="info">
              <h2 id="contract-drawer-title">{contract?.property_label || 'Contrato'}</h2>
              <div className="meta">
                {contract && <Pill kind={(CONTRACT_PILL[contract.status] ?? CONTRACT_PILL.active).kind}>{(CONTRACT_PILL[contract.status] ?? CONTRACT_PILL.active).label}</Pill>}
                {contract?.tenant_name && <span className="client-tag">{contract.tenant_name}</span>}
              </div>
              {contract && (
                <div className="meta" style={{ marginTop: 8 }}>
                  <span><Icon name="money" size={12} style={{ verticalAlign: 'middle', marginRight: 4, color: 'var(--fg-tertiary)' }} /> {money(contract.current_rent, cur)}/mes</span>
                  <span><Icon name="activity" size={12} style={{ verticalAlign: 'middle', marginRight: 4, color: 'var(--fg-tertiary)' }} /> {adjDescription(contract)}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="drawer-body">
          {isLoading && <div className="muted" style={{ fontSize: 13 }}>Cargando…</div>}
          {contract && (
            <Fragment>
              {contract.index_pending && (
                <div className="detail-block" style={{ background: 'var(--warn-50, #fff7ed)', border: '1px solid var(--warn-200, #fed7aa)', borderRadius: 8, padding: 10, marginBottom: 12 }}>
                  <div style={{ fontSize: 12, color: 'var(--warn-700, #b07d12)' }}>
                    <Icon name="info" size={13} style={{ verticalAlign: 'middle', marginRight: 6 }} />
                    Falta cargar el valor de IPC para calcular el ajuste de este contrato.
                  </div>
                </div>
              )}

              <div className="detail-block">
                <h3>Datos del contrato</h3>
                <dl className="def-list">
                  <dt>Inquilino</dt><dd>{contract.tenant_name || '—'}</dd>
                  <dt>Propietario</dt><dd>{contract.owner_name || '—'}</dd>
                  <dt>Vigencia</dt><dd>{fmtDate(contract.start_date)} → {contract.end_date ? fmtDate(contract.end_date) : '—'}</dd>
                  <dt>Alquiler base</dt><dd className="tabular">{money(contract.base_rent, cur)}</dd>
                  <dt>Alquiler vigente</dt><dd className="tabular">{money(contract.current_rent, cur)}</dd>
                  <dt>Ajuste</dt><dd>{adjDescription(contract)}</dd>
                  <dt>Vencimiento</dt><dd>día {contract.payment_due_day} · punitorio {contract.punitorio_daily_pct || 0}%/día</dd>
                  <dt>Saldo pendiente</dt><dd className="tabular" style={{ color: contract.balance ? 'var(--danger-600)' : undefined }}>{money(contract.balance, cur)}</dd>
                </dl>
              </div>

              <div className="detail-block">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3 style={{ margin: 0 }}>Cobros ({contract.charges?.length ?? 0})</h3>
                  <Button kind="secondary" size="sm" icon="refresh" onClick={handleGenerate} disabled={generateMut.isPending}>
                    {generateMut.isPending ? 'Generando…' : 'Generar cobros'}
                  </Button>
                </div>
                <div className="tbl-scroll" style={{ marginTop: 8 }}>
                  <table className="tbl">
                    <thead><tr>
                      <th>Período</th><th>Vence</th><th>Alquiler</th><th>Gastos</th><th>Punit.</th><th>Total</th><th>Estado</th><th></th>
                    </tr></thead>
                    <tbody>
                      {(contract.charges ?? []).map(ch => (
                        <ChargeRow key={ch.id} ch={ch} contract={contract}
                                   onPay={handlePay} onRemind={handleRemind} onEditAmount={handleEditAmount}
                                   busy={payMut.isPending} />
                      ))}
                      {(!contract.charges || contract.charges.length === 0) && (
                        <tr><td colSpan="8" className="tbl-empty">Sin cobros. Usá "Generar cobros".</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="detail-block">
                <h3>Gastos y servicios</h3>
                {(contract.expenses ?? []).map(e => (
                  <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: 13 }}>
                    <span style={{ flex: 1 }}>{e.description} {e.recurring && <span className="client-tag" style={{ fontSize: 10 }}>mensual</span>}</span>
                    <span className="muted" style={{ fontSize: 11 }}>{e.category}</span>
                    <span className="tabular">{money(e.amount, cur)}</span>
                    <IconButton name="trash" title="Eliminar gasto" onClick={() => deleteExpenseMut.mutate(e.id)} />
                  </div>
                ))}
                <div className="field-row" style={{ marginTop: 10, alignItems: 'flex-end' }}>
                  <div className="field" style={{ flex: 2 }}>
                    <label>Descripción</label>
                    <input value={exp.description} onChange={e => setExp(s => ({ ...s, description: e.target.value }))} placeholder="Ej: ABL, expensas..." />
                  </div>
                  <div className="field">
                    <label>Monto</label>
                    <input type="number" value={exp.amount} onChange={e => setExp(s => ({ ...s, amount: e.target.value }))} placeholder="0" />
                  </div>
                  <div className="field">
                    <label>Tipo</label>
                    <select value={exp.category} onChange={e => setExp(s => ({ ...s, category: e.target.value }))}>
                      <option value="servicio">Servicio</option>
                      <option value="expensas">Expensas</option>
                      <option value="reparacion">Reparación</option>
                      <option value="otro">Otro</option>
                    </select>
                  </div>
                  <label className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingBottom: 8 }}>
                    <input type="checkbox" checked={exp.recurring} onChange={e => setExp(s => ({ ...s, recurring: e.target.checked }))} style={{ width: 'auto' }} />
                    <span style={{ fontSize: 12 }}>Mensual</span>
                  </label>
                  <Button kind="secondary" size="sm" icon="plus" onClick={handleAddExpense} disabled={createExpenseMut.isPending}>Agregar</Button>
                </div>
              </div>

              <DocumentsPanel contractId={contract.id} title="Documentos del contrato" />
            </Fragment>
          )}
        </div>
      </div>
    </Fragment>
  );
}

// ─── Modal de índices IPC ─────────────────────────────────────────────────────

function IndicesModal({ onClose }) {
  const { data: indices = [] } = useIndices('IPC');
  const upsertMut = useUpsertIndex();
  const [form, setForm] = useState({ period: '', index_level: '' });

  const trapRef = useFocusTrap(onClose);

  const save = () => {
    if (!form.period || !form.index_level) { pushToast({ text: 'Completá mes y nivel.', kind: 'danger' }); return; }
    const period = form.period.length === 7 ? `${form.period}-01` : form.period; // YYYY-MM → YYYY-MM-01
    upsertMut.mutate({ code: 'IPC', period, index_level: Number(form.index_level), source: 'manual' }, {
      onSuccess: () => { setForm({ period: '', index_level: '' }); pushToast({ text: 'Índice IPC guardado.' }); },
      onError:   () => pushToast({ text: 'Error al guardar el índice.', kind: 'danger' }),
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose} aria-hidden="true">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="indices-modal-title" ref={trapRef} onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <div className="modal-head">
          <h3 id="indices-modal-title">Índices IPC (INDEC)</h3>
          <span className="close"><IconButton name="x" title="Cerrar" onClick={onClose} /></span>
        </div>
        <div className="modal-body">
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
            Cargá el número índice (nivel general) publicado por INDEC para cada mes. Los aumentos se calculan como el cociente entre el nivel del mes de ajuste y el del mes de inicio del contrato.
          </p>
          <div className="field-row" style={{ alignItems: 'flex-end' }}>
            <div className="field">
              <label>Mes</label>
              <input type="month" value={form.period} onChange={e => setForm(f => ({ ...f, period: e.target.value }))} />
            </div>
            <div className="field">
              <label>Nivel índice</label>
              <input type="number" step="0.01" value={form.index_level} onChange={e => setForm(f => ({ ...f, index_level: e.target.value }))} placeholder="Ej: 7864.13" />
            </div>
            <Button kind="primary" size="sm" icon="check" onClick={save} disabled={upsertMut.isPending}>Guardar</Button>
          </div>
          <div className="tbl-scroll" style={{ marginTop: 12, maxHeight: 280 }}>
            <table className="tbl">
              <thead><tr><th>Mes</th><th>Nivel</th><th>Origen</th></tr></thead>
              <tbody>
                {indices.map(ix => (
                  <tr key={ix.id}><td>{fmtPeriod(ix.period)}</td><td className="tabular">{ix.index_level}</td><td className="muted">{ix.source}</td></tr>
                ))}
                {indices.length === 0 && <tr><td colSpan="3" className="tbl-empty">Sin valores cargados.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Vista principal ──────────────────────────────────────────────────────────

export default function Cobranzas() {
  const { data: contracts = [] } = useContracts();
  const { data: summary } = useCobranzasSummary();
  const createMut = useCreateContract();
  const updateMut = useUpdateContract();
  const deleteMut = useDeleteContract();

  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [open, setOpen] = useState(null);       // contract id (drawer)
  const [editor, setEditor] = useState(null);   // { mode, contract? }
  const [showIndices, setShowIndices] = useState(false);

  const handleSave = (payload) => {
    if (editor.mode === 'create') {
      createMut.mutate(payload, {
        onSuccess: (c) => { setEditor(null); setOpen(c.id); pushToast({ text: 'Contrato creado.' }); },
        onError:   () => pushToast({ text: 'Error al crear el contrato.', kind: 'danger' }),
      });
    } else {
      updateMut.mutate({ id: editor.contract.id, ...payload }, {
        onSuccess: () => { setEditor(null); pushToast({ text: 'Contrato actualizado.' }); },
        onError:   () => pushToast({ text: 'Error al guardar los cambios.', kind: 'danger' }),
      });
    }
  };

  const handleDelete = (contract) => {
    setOpen(null);
    deleteMut.mutate(contract.id, {
      onSuccess: () => pushToast({ text: 'Contrato eliminado.' }),
      onError:   () => pushToast({ text: 'Error al eliminar el contrato.', kind: 'danger' }),
    });
  };

  const filtered = contracts.filter(c => {
    if (filter === 'overdue' && !c.overdue_count) return false;
    if (filter === 'pending' && !c.pending_count) return false;
    if (filter === 'active' && c.status !== 'active') return false;
    if (search) {
      const q = search.toLowerCase();
      const hay = `${c.property_label ?? ''} ${c.tenant_name ?? ''} ${c.owner_name ?? ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const counts = {
    all: contracts.length,
    active: contracts.filter(c => c.status === 'active').length,
    pending: contracts.filter(c => c.pending_count > 0).length,
    overdue: contracts.filter(c => c.overdue_count > 0).length,
  };

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Cobranzas</h1>
          <div className="sub">{counts.active} contratos activos · {counts.overdue} con cobros vencidos</div>
        </div>
        <div className="page-h-actions">
          <Button kind="secondary" icon="activity" onClick={() => setShowIndices(true)}>Índices IPC</Button>
          <Button kind="primary" icon="plus" onClick={() => setEditor({ mode: 'create' })}>Nuevo contrato</Button>
        </div>
      </div>

      <div className="page-kpis">
        <div className="kpi-grid">
          <div className="kpi"><span className="kpi-label">A cobrar</span><span className="kpi-value">{money(summary?.to_collect ?? 0, 'ARS')}</span><span className="kpi-delta">{summary?.pending_count ?? 0} cobros pendientes</span></div>
          <div className="kpi"><span className="kpi-label">Cobrado este mes</span><span className="kpi-value" style={{ color: 'var(--accent-500)' }}>{money(summary?.collected_this_month ?? 0, 'ARS')}</span></div>
          <div className="kpi"><span className="kpi-label">Cobros vencidos</span><span className="kpi-value" style={{ color: summary?.overdue_count ? 'var(--danger-600)' : undefined }}>{summary?.overdue_count ?? 0}</span></div>
          <div className="kpi"><span className="kpi-label">Contratos activos</span><span className="kpi-value">{summary?.active_contracts ?? counts.active}</span></div>
        </div>
      </div>

      <div className="scroll-surface surface">
        <div className="filter-bar">
          <input placeholder="Buscar por propiedad o inquilino..." value={search} onChange={e => setSearch(e.target.value)} />
          {[['all', 'Todos', counts.all], ['active', 'Activos', counts.active], ['pending', 'Con pendientes', counts.pending], ['overdue', 'Vencidos', counts.overdue]].map(([k, l, n]) => (
            <button key={k} type="button" className={`chip ${filter === k ? 'active' : ''}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}<span className="num">{n}</span></button>
          ))}
        </div>
        <div className="tbl-scroll">
          <table className="tbl">
            <thead><tr>
              <th>Propiedad</th><th>Inquilino</th><th>Alquiler vigente</th><th>Próx. vencimiento</th><th>Saldo</th><th>Estado</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.map(c => (
                <tr key={c.id} tabIndex={0} aria-label={`Ver contrato de ${c.tenant_name || c.property_label || 'contrato'}`}
                    onClick={() => setOpen(c.id)} style={{ cursor: 'pointer' }}
                    onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setOpen(c.id); } }}>
                  <td><b>{c.property_label || '— Sin propiedad —'}</b></td>
                  <td className="muted">{c.tenant_name || '—'}</td>
                  <td className="tabular">{money(c.current_rent, c.currency)}</td>
                  <td className="muted">{fmtDate(c.next_due)}</td>
                  <td className="tabular" style={{ color: c.balance ? 'var(--danger-600)' : undefined }}>{money(c.balance, c.currency)}</td>
                  <td>
                    {c.overdue_count > 0
                      ? <Pill kind="expired">{c.overdue_count} vencido{c.overdue_count > 1 ? 's' : ''}</Pill>
                      : c.pending_count > 0
                        ? <Pill kind="pending">{c.pending_count} pendiente{c.pending_count > 1 ? 's' : ''}</Pill>
                        : <Pill kind="paid">Al día</Pill>}
                  </td>
                  <td><div className="row-actions"><IconButton name="chevronRight" /></div></td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan="7" className="tbl-empty">No hay contratos que coincidan con los filtros.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {open && (
        <ContractDrawer
          contractId={open}
          onClose={() => setOpen(null)}
          onEdit={(c) => setEditor({ mode: 'edit', contract: c })}
          onDelete={handleDelete}
        />
      )}
      {editor && (
        <ContractEditor
          contract={editor.contract}
          mode={editor.mode}
          saving={createMut.isPending || updateMut.isPending}
          onClose={() => setEditor(null)}
          onSave={handleSave}
        />
      )}
      {showIndices && <IndicesModal onClose={() => setShowIndices(false)} />}
    </div>
  );
}
