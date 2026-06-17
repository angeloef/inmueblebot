import React, { useState, useEffect } from 'react';
import { Icon, Button, pushToast } from './Primitives';
import { useAuth } from './auth';
import {
  useBotSettings, useUpdateBotSettings,
  useTenants, useCreateTenant, useUpdateTenant, useDeleteTenant,
  useUpdateTenantSettings,
  useBillingStatus, useBillingPlans, useSubscribe,
} from './api';

// ── Section wrapper ────────────────────────────────────────────────────────────

function Section({ title, description, children }) {
  return (
    <div className="config-section">
      <div className="config-section-head">
        <h2>{title}</h2>
        {description && <p className="sub">{description}</p>}
      </div>
      <div className="config-section-body">{children}</div>
    </div>
  );
}

// ── Field wrapper ──────────────────────────────────────────────────────────────

function Field({ label, hint, children }) {
  return (
    <div className="field config-field">
      <label>{label}</label>
      {hint && <div className="config-hint">{hint}</div>}
      {children}
    </div>
  );
}

// ── Router segmented control (V1 / V2 / V3) — saves immediately ─────────────────

const ROUTER_OPTIONS = [
  { value: 'v1', label: 'V1', hint: 'Clasificador de intent + agente monolítico. Sistema clásico y estable.' },
  { value: 'v2', label: 'V2', hint: 'S1 (regex rápido) + S2 (coordinador con especialistas). Scheduling conversacional.' },
  { value: 'v3', label: 'V3', hint: 'Router multi-tenant schema-guided (en construcción). Por ahora hace fallback a V2 sin riesgo.' },
];

function RouterSegmented({ value, onChange, saving }) {
  const active = ROUTER_OPTIONS.find((o) => o.value === value) ?? ROUTER_OPTIONS[1];
  return (
    <div className="field config-field">
      <label style={{ marginBottom: 8 }}>Router del chatbot</label>
      <div className="segmented" role="radiogroup" aria-label="Router del chatbot">
        {ROUTER_OPTIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            className={`segmented-item ${value === o.value ? 'segmented-on' : ''}`}
            onClick={() => value !== o.value && onChange(o.value)}
            disabled={saving}
          >
            {o.label}
          </button>
        ))}
      </div>
      <div className="config-hint" style={{ marginTop: 8 }}>{active.hint}</div>
    </div>
  );
}

// ── Per-tenant router badge + mini switch (V3 Phase 2) ────────────────────────

const ROUTER_LABELS = { v1: 'V1', v2: 'V2', v3: 'V3', '': 'global' };

function TenantRouterSwitch({ tenantId, currentRouter }) {
  const updateMut = useUpdateTenantSettings();
  const [switching, setSwitching] = React.useState(false);
  const effective = currentRouter || 'v2';

  const handleSwitch = async (newValue) => {
    if (switching || newValue === currentRouter) return;
    setSwitching(true);
    try {
      await updateMut.mutateAsync({ id: tenantId, active_router: newValue });
      pushToast({ text: `Router ${newValue.toUpperCase()} activado para esta inmobiliaria.`, kind: 'success' });
    } catch {
      pushToast({ text: 'Error al cambiar el router.', kind: 'danger' });
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <span className="sub" style={{ fontSize: 11, marginRight: 2 }}>router:</span>
      <div className="segmented" role="radiogroup" aria-label="Router por inmobiliaria" style={{ gap: 2 }}>
        {ROUTER_OPTIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={effective === o.value}
            className={`segmented-item ${effective === o.value ? 'segmented-on' : ''}`}
            style={{ padding: '2px 7px', fontSize: 11 }}
            onClick={() => handleSwitch(o.value)}
            disabled={switching}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Tenant (inmobiliaria) provisioning ─────────────────────────────────────────

const EMPTY_TENANT = {
  slug: '', display_name: '', company_name: '', business_hours: '',
  timezone: 'America/Argentina/Cordoba', waba_id: '', phone_number_id: '',
  wa_access_token: '', plan: '', status: 'active',
};

function TenantForm({ initial, onSubmit, onCancel, busy, isEdit }) {
  const [form, setForm] = useState(initial);
  useEffect(() => { setForm(initial); }, [initial]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = () => {
    if (!form.display_name.trim() || (!isEdit && !form.slug.trim())) {
      pushToast({ text: 'Slug y nombre son obligatorios.', kind: 'danger' });
      return;
    }
    // Only send non-empty fields; an empty access token must NOT overwrite an existing one.
    const payload = {};
    Object.entries(form).forEach(([k, v]) => {
      if (v !== '' && v != null) payload[k] = typeof v === 'string' ? v.trim() : v;
    });
    if (isEdit) delete payload.slug; // slug is immutable on edit
    onSubmit(payload);
  };

  return (
    <div className="tenant-form" style={{ display: 'grid', gap: 10, marginTop: 12 }}>
      {!isEdit && (
        <Field label="Slug" hint="Identificador estable, sin espacios (ej: obera). No se puede cambiar luego.">
          <input type="text" value={form.slug} onChange={set('slug')} placeholder="obera" maxLength={60} />
        </Field>
      )}
      <Field label="Nombre visible">
        <input type="text" value={form.display_name} onChange={set('display_name')} placeholder="Inmobiliaria Oberá" maxLength={200} />
      </Field>
      {/* Datos de WhatsApp/Meta: solo al EDITAR. Al crear la inmobiliaria no se
          piden — la conexión de WhatsApp se hace después (p. ej. Embedded Signup). */}
      {isEdit && (
        <>
          <Field label="Phone Number ID (Meta)" hint="Clave de ruteo del webhook. Único por inmobiliaria.">
            <input type="text" value={form.phone_number_id} onChange={set('phone_number_id')} placeholder="1120063544518404" maxLength={64} />
          </Field>
          <Field label="WABA ID (Meta)">
            <input type="text" value={form.waba_id} onChange={set('waba_id')} placeholder="WhatsApp Business Account id" maxLength={64} />
          </Field>
          <Field
            label="WhatsApp access token (dejar vacío para no cambiar)"
            hint="Se guarda cifrado (Fernet). Nunca se muestra de vuelta."
          >
            <input type="password" value={form.wa_access_token} onChange={set('wa_access_token')} placeholder="EAAG…" autoComplete="off" />
          </Field>
        </>
      )}
      <Field label="Horario de atención">
        <input type="text" value={form.business_hours} onChange={set('business_hours')} placeholder="Lunes a sábado de 9 a 18hs" maxLength={300} />
      </Field>
      <Field label="Zona horaria">
        <input type="text" value={form.timezone} onChange={set('timezone')} placeholder="America/Argentina/Cordoba" maxLength={60} />
      </Field>
      <div className="config-actions" style={{ marginTop: 4 }}>
        <Button kind="secondary" size="sm" onClick={onCancel} disabled={busy}>Cancelar</Button>
        <Button kind="primary" size="sm" onClick={submit} disabled={busy}>
          {busy ? 'Guardando…' : (isEdit ? 'Guardar' : 'Crear inmobiliaria')}
        </Button>
      </div>
    </div>
  );
}

function TenantsSection() {
  const { data: tenants, isLoading } = useTenants();
  const createMut = useCreateTenant();
  const updateMut = useUpdateTenant();
  const deleteMut = useDeleteTenant();
  const [mode, setMode] = useState(null); // null | 'create' | editId

  const busy = createMut.isPending || updateMut.isPending || deleteMut.isPending;

  const handleCreate = async (payload) => {
    try {
      await createMut.mutateAsync(payload);
      pushToast({ text: 'Inmobiliaria creada.', kind: 'success' });
      setMode(null);
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'Error al crear.', kind: 'danger' });
    }
  };

  const handleUpdate = async (id, payload) => {
    try {
      await updateMut.mutateAsync({ id, ...payload });
      pushToast({ text: 'Inmobiliaria actualizada.', kind: 'success' });
      setMode(null);
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'Error al actualizar.', kind: 'danger' });
    }
  };

  const handleDelete = async (t) => {
    if (!window.confirm(`¿Eliminar la inmobiliaria "${t.display_name}"? Se borran sus datos.`)) return;
    try {
      await deleteMut.mutateAsync(t.id);
      pushToast({ text: 'Inmobiliaria eliminada.', kind: 'success' });
    } catch (err) {
      pushToast({ text: err?.response?.data?.detail ?? 'No se pudo eliminar.', kind: 'danger' });
    }
  };

  return (
    <Section
      title="Inmobiliarias"
      description="Cada inmobiliaria (tenant) tiene sus propios datos, número de WhatsApp y branding. El número entrante (phone_number_id) decide a qué inmobiliaria pertenece cada mensaje."
    >
      {isLoading ? (
        <p className="sub">Cargando inmobiliarias…</p>
      ) : (
        <div className="tenant-list" style={{ display: 'grid', gap: 8 }}>
          {(tenants ?? []).map((t) => (
            <div key={t.id} className="tenant-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 12px', border: '1px solid var(--border, #e5e7eb)', borderRadius: 8, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 180 }}>
                <div style={{ fontWeight: 600 }}>{t.display_name} <span className="sub">({t.slug})</span></div>
                <div className="config-hint">
                  {t.phone_number_id ? `Número: ${t.phone_number_id}` : 'Sin número asignado'}
                  {' · '}{t.has_access_token ? 'token ✓' : 'sin token'}
                  {' · '}{t.status ?? 'active'}
                </div>
              </div>
              <TenantRouterSwitch tenantId={t.id} currentRouter={t.active_router || ''} />
              <div style={{ display: 'flex', gap: 6 }}>
                <Button kind="secondary" size="sm" onClick={() => setMode(t.id)} disabled={busy}>Editar</Button>
                <Button kind="danger" size="sm" onClick={() => handleDelete(t)} disabled={busy}>Eliminar</Button>
              </div>
            </div>
          ))}
          {(tenants ?? []).length === 0 && <p className="sub">No hay inmobiliarias provisionadas todavía.</p>}
        </div>
      )}

      {mode === 'create' && (
        <TenantForm initial={EMPTY_TENANT} onSubmit={handleCreate} onCancel={() => setMode(null)} busy={busy} isEdit={false} />
      )}
      {mode && mode !== 'create' && (() => {
        const t = (tenants ?? []).find((x) => x.id === mode);
        if (!t) return null;
        const initial = { ...EMPTY_TENANT, ...t, wa_access_token: '' };
        return <TenantForm initial={initial} onSubmit={(p) => handleUpdate(t.id, p)} onCancel={() => setMode(null)} busy={busy} isEdit />;
      })()}

      {!mode && (
        <div style={{ marginTop: 12 }}>
          <Button kind="primary" size="sm" onClick={() => setMode('create')} disabled={busy}>
            <Icon name="plus" size={14} /> Nueva inmobiliaria
          </Button>
        </div>
      )}
    </Section>
  );
}

// ── Plan y suscripción ─────────────────────────────────────────────────────────

const FEATURE_LABELS = {
  cobranzas:      'Gestión de alquileres',
  website:        'Sitio web catálogo',
  weekly_report:  'Reporte semanal',
  cold_leads:     'Seguimiento leads fríos',
  visit_reminder: 'Recordatorio de visitas',
  multi_branch:   'Multi-sucursal',
  documents:      'Documentos vinculados',
  exec_reports:   'Reportes ejecutivos',
  exports:        'Exportación CSV',
  api:            'API / integraciones',
};

const STATUS_LABELS = {
  trial:     'Prueba',
  active:    'Activo',
  past_due:  'Vencido',
  paused:    'Pausado',
  cancelled: 'Cancelado',
};

function StatusPill({ status }) {
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span className={`plan-status-pill is-${status}`}>
      <span className="dot" aria-hidden="true" />
      {label}
    </span>
  );
}

function LimitBar({ label, used, max }) {
  const pct = max && used != null ? Math.min(100, Math.round((used / max) * 100)) : 0;
  const fillClass = pct > 90 ? 'is-over' : pct > 80 ? 'is-warn' : '';
  return (
    <div className="limit-bar">
      <div className="limit-bar-head">
        <span className="lbl">{label}</span>
        <span className="val">{max ? `${used ?? '—'} / ${max}` : 'Ilimitado'}</span>
      </div>
      {max != null && (
        <div className="limit-bar-track">
          <div className={`limit-bar-fill ${fillClass}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}

function PlanSection({ onGoToPlans }) {
  const { me } = useAuth();
  const { data: billing, isLoading: loadingBilling } = useBillingStatus();
  const { data: plans, isLoading: loadingPlans } = useBillingPlans();
  const subscribeMut = useSubscribe();
  const [subscribing, setSubscribing] = useState(null); // plan name being subscribed

  // Detectar retorno de MercadoPago (query params)
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
      window.location.href = init_point;
    } catch (err) {
      const msg = err?.response?.data?.detail ?? 'No se pudo iniciar el pago.';
      pushToast({ kind: 'danger', text: typeof msg === 'string' ? msg : 'No se pudo iniciar el pago.' });
      setSubscribing(null);
    }
  };

  const currentPlan = billing?.plan ?? me?.subscription?.plan ?? me?.plan ?? null;
  const currentStatus = billing?.status ?? me?.subscription?.status ?? null;
  const trialEnds = billing?.trial_ends_at ?? me?.subscription?.trial_ends_at ?? null;
  const periodEnd = billing?.current_period_end ?? null;
  const limits = billing?.limits ?? null;
  const features = billing?.features ?? me?.features ?? [];

  const daysLeft = trialEnds
    ? Math.ceil((new Date(trialEnds).getTime() - Date.now()) / 86_400_000)
    : null;

  return (
    <Section title="Plan y suscripción" description="Gestioná tu plan, revisá límites y actualizá tu suscripción.">
      {/* Estado actual */}
      {loadingBilling ? (
        <p className="sub">Cargando estado de suscripción…</p>
      ) : billing ? (
        <div className="plan-summary">
          <div className="plan-summary-top">
            <span className="plan-summary-name">
              Plan <span>{currentPlan ? currentPlan.charAt(0).toUpperCase() + currentPlan.slice(1) : <span className="muted">—</span>}</span>
            </span>
            {currentStatus && <StatusPill status={currentStatus} />}
            {currentStatus === 'trial' && daysLeft !== null && (
              <span className="plan-summary-meta">
                {daysLeft <= 0 ? 'El período de prueba venció' : <>Prueba: quedan <b>{daysLeft} día{daysLeft !== 1 ? 's' : ''}</b></>}
              </span>
            )}
            {periodEnd && currentStatus === 'active' && (
              <span className="plan-summary-meta">Renovación: <b>{new Date(periodEnd).toLocaleDateString('es-AR')}</b></span>
            )}
          </div>

          {limits && (
            <div className="plan-usage">
              <LimitBar label="Propiedades" used={limits.properties_used} max={limits.properties} />
              <LimitBar label="Conversaciones/mes" used={limits.conversations_used} max={limits.conversations_per_month} />
              <LimitBar label="Usuarios del equipo" used={limits.users_used} max={limits.users} />
            </div>
          )}
        </div>
      ) : (
        <p className="sub">Sin información de suscripción.</p>
      )}

      {/* Comparativa de tiers */}
      <div className="plan-grid-label">Planes disponibles</div>
      {loadingPlans ? (
        <p className="sub">Cargando planes…</p>
      ) : (plans ?? []).length === 0 ? (
        <p className="sub">No hay planes disponibles.</p>
      ) : (
        <div className="plan-grid">
          {(plans ?? []).map((plan) => {
            const isCurrent = plan.name === currentPlan;
            const isEnterprise = !plan.self_serve;
            const isFeatured = !!plan.recommended;
            return (
              <div key={plan.name} className={`plan-card${isCurrent ? ' is-current' : ''}${isFeatured ? ' is-featured' : ''}`}>
                {isFeatured && <span className="plan-ribbon">Recomendado</span>}
                <div className="plan-card-head">
                  <span className="plan-card-name">{plan.display_name ?? plan.name}</span>
                  {isCurrent && <span className="plan-card-tag">Tu plan</span>}
                </div>

                <div className="plan-card-price">
                  {plan.price_ars_monthly ? (
                    <>
                      <span className="amount">${Number(plan.price_ars_monthly).toLocaleString('es-AR')}</span>
                      <span className="period">/mes</span>
                    </>
                  ) : (
                    <span className="custom">{isEnterprise ? 'A consultar' : 'Gratis'}</span>
                  )}
                </div>

                <div className="plan-card-divider" />

                <ul className="plan-feats">
                  {(plan.features ?? []).map((f) => (
                    <li key={f}>
                      <Icon name="check" size={14} stroke={2.5} />
                      {FEATURE_LABELS[f] ?? f}
                    </li>
                  ))}
                </ul>

                {isCurrent ? (
                  <span className="plan-card-current-note">
                    <Icon name="check" size={14} stroke={2.5} />Plan activo
                  </span>
                ) : isEnterprise ? (
                  <a href="mailto:ventas@viviendapp.com" className="btn btn-secondary btn-sm">
                    Hablar con ventas
                  </a>
                ) : (
                  <Button
                    kind={isFeatured ? 'primary' : 'secondary'}
                    size="sm"
                    disabled={subscribing === plan.name}
                    onClick={() => handleSubscribe(plan.name)}
                  >
                    {subscribing === plan.name ? 'Redirigiendo…' : 'Suscribirse'}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Config() {
  const { data: settings, isLoading, isError } = useBotSettings();
  const updateMut = useUpdateBotSettings();

  // Local form state — mirrors the DB fields
  const [companyName,   setCompanyName]   = useState('');
  const [bizHours,      setBizHours]      = useState('');
  const [agentWA,       setAgentWA]       = useState('');
  const [activeRouter,  setActiveRouter]  = useState('v2');
  const [dirty,         setDirty]         = useState(false);
  const [saving,        setSaving]        = useState(false);
  const [switching,     setSwitching]     = useState(false);

  // Back-compat: derive active_router from the legacy use_v2_router when unset.
  const deriveRouter = (s) => {
    if (s?.active_router) return s.active_router;
    return s?.use_v2_router === 'true' ? 'v2' : 'v1';
  };

  useEffect(() => {
    if (!settings) return;
    setCompanyName(settings.company_name   ?? '');
    setBizHours(   settings.business_hours ?? '');
    setAgentWA(    settings.agent_whatsapp ?? '');
    setActiveRouter(deriveRouter(settings));
    setDirty(false);
  }, [settings]);

  const markDirty = (setter) => (e) => {
    setter(e.target.value);
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateMut.mutateAsync({
        company_name:   companyName.trim(),
        business_hours: bizHours.trim(),
        agent_whatsapp: agentWA.trim(),
      });
      pushToast({ text: 'Configuración guardada.', kind: 'success' });
      setDirty(false);
    } catch (err) {
      pushToast({ text: 'Error al guardar. Revisá la conexión.', kind: 'danger' });
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    if (!settings) return;
    setCompanyName(settings.company_name   ?? '');
    setBizHours(   settings.business_hours ?? '');
    setAgentWA(    settings.agent_whatsapp ?? '');
    setActiveRouter(deriveRouter(settings));
    setDirty(false);
  };

  const handleSwitchRouter = async (newValue) => {
    setSwitching(true);
    const prev = activeRouter;
    setActiveRouter(newValue); // optimistic
    try {
      await updateMut.mutateAsync({ active_router: newValue });
      pushToast({ text: `Router ${newValue.toUpperCase()} activado. Aplica en el próximo mensaje.`, kind: 'success' });
    } catch (err) {
      setActiveRouter(prev); // rollback
      pushToast({ text: 'Error al cambiar el router.', kind: 'danger' });
    } finally {
      setSwitching(false);
    }
  };

  if (isLoading) return (
    <div className="page-view">
      <div className="page-h"><h1>Configuración</h1></div>
      <div className="empty-state"><Icon name="settings" size={32} /><p>Cargando…</p></div>
    </div>
  );

  if (isError) return (
    <div className="page-view">
      <div className="page-h"><h1>Configuración</h1></div>
      <div className="empty-state">
        <Icon name="x" size={32} />
        <p>No se pudo cargar la configuración. Verificá la conexión al servidor.</p>
      </div>
    </div>
  );

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Configuración</h1>
          <div className="sub">Ajustes operativos del bot y la inmobiliaria</div>
        </div>
        {dirty && (
          <div className="config-actions">
            <Button kind="secondary" size="sm" onClick={handleDiscard} disabled={saving}>
              Descartar
            </Button>
            <Button kind="primary" size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar cambios'}
            </Button>
          </div>
        )}
      </div>

      <div className="page-body">
      <div className="config-body">

        {/* ── Sistema ── */}
        <Section
          title="Sistema"
          description="Control del motor del chatbot. Los cambios aplican en el próximo mensaje recibido."
        >
          <RouterSegmented value={activeRouter} onChange={handleSwitchRouter} saving={switching} />
        </Section>

        {/* ── Plan y suscripción ── */}
        <PlanSection onGoToPlans={() => {}} />

        {/* ── Inmobiliarias (tenants) ── */}
        <TenantsSection />

        {/* ── Identidad ── */}
        <Section
          title="Identidad del negocio"
          description="Estos datos aparecen en los mensajes de WhatsApp que envía el bot."
        >
          <Field
            label="Nombre de la inmobiliaria"
            hint="Aparece en el saludo inicial y en mensajes de redirección de temas."
          >
            <input
              type="text"
              value={companyName}
              onChange={markDirty(setCompanyName)}
              placeholder="ej: Inmobiliaria Norte"
              maxLength={80}
            />
          </Field>
        </Section>

        {/* ── Operación ── */}
        <Section
          title="Operación"
          description="Horarios y contacto para la atención al cliente."
        >
          <Field
            label="Horario de atención"
            hint="El bot lo menciona cuando explica disponibilidad para visitas."
          >
            <input
              type="text"
              value={bizHours}
              onChange={markDirty(setBizHours)}
              placeholder="ej: Lunes a sábado de 9 a 18hs"
              maxLength={120}
            />
          </Field>

          <Field
            label="WhatsApp del agente humano"
            hint="Número al que se transfiere la conversación cuando el cliente pide hablar con una persona. Formato: +5493764xxxxxx"
          >
            <input
              type="text"
              value={agentWA}
              onChange={markDirty(setAgentWA)}
              placeholder="ej: +549****3456"
              maxLength={20}
            />
          </Field>
        </Section>

      </div>
      </div>

      {/* Sticky save bar — visible when there are unsaved changes */}
      {dirty && (
        <div className="config-sticky-bar">
          <span className="config-sticky-msg">Hay cambios sin guardar</span>
          <div className="config-actions">
            <Button kind="secondary" size="sm" onClick={handleDiscard} disabled={saving}>
              Descartar
            </Button>
            <Button kind="primary" size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar cambios'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
