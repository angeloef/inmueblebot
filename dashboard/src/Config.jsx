import React, { useState, useEffect } from 'react';
import { Icon, Button, pushToast } from './Primitives';
import { useBotSettings, useUpdateBotSettings } from './api';

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

// ── Toggle switch (inline, saves immediately) ─────────────────────────────────

function ToggleField({ label, hint, value, onChange, saving }) {
  const isOn = value === 'true';
  return (
    <div className="field config-field">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <label style={{ marginBottom: 0 }}>{label}</label>
          {hint && <div className="config-hint">{hint}</div>}
        </div>
        <button
          type="button"
          className={`toggle-switch ${isOn ? 'toggle-on' : 'toggle-off'}`}
          onClick={() => onChange(isOn ? 'false' : 'true')}
          disabled={saving}
          title={isOn ? 'Click para desactivar' : 'Click para activar'}
        >
          <span className="toggle-knob" />
          <span className="toggle-label">{isOn ? 'V2' : 'V1'}</span>
        </button>
      </div>
    </div>
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
  const [useV2Router,   setUseV2Router]   = useState('false');
  const [dirty,         setDirty]         = useState(false);
  const [saving,        setSaving]        = useState(false);
  const [toggling,      setToggling]      = useState(false);

  // Populate form from fetched settings
  useEffect(() => {
    if (!settings) return;
    setCompanyName(settings.company_name   ?? '');
    setBizHours(   settings.business_hours ?? '');
    setAgentWA(    settings.agent_whatsapp ?? '');
    setUseV2Router(settings.use_v2_router  ?? 'false');
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
    setUseV2Router(settings.use_v2_router  ?? 'false');
    setDirty(false);
  };

  const handleToggleRouter = async (newValue) => {
    setToggling(true);
    const prev = useV2Router;
    setUseV2Router(newValue); // optimistic
    try {
      await updateMut.mutateAsync({ use_v2_router: newValue });
      pushToast({
        text: newValue === 'true'
          ? 'Router V2 activado. El bot usará el nuevo sistema S1+S2.'
          : 'Router V1 activado. El bot usará el sistema clásico.',
        kind: 'success',
      });
    } catch (err) {
      setUseV2Router(prev); // rollback
      pushToast({ text: 'Error al cambiar el router.', kind: 'danger' });
    } finally {
      setToggling(false);
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

  const v2Active = useV2Router === 'true';

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

      <div className="config-body">

        {/* ── Sistema ── */}
        <Section
          title="Sistema"
          description="Control del motor del chatbot. Los cambios aplican en el próximo mensaje recibido."
        >
          <ToggleField
            label="Router del chatbot"
            hint={
              v2Active
                ? 'V2 activo: S1 (regex rápido) + S2 (coordinador con especialistas). Respuestas más naturales, scheduling conversacional.'
                : 'V1 activo: clasificador de intent + agente monolítico. Sistema clásico y estable.'
            }
            value={useV2Router}
            onChange={handleToggleRouter}
            saving={toggling}
          />
        </Section>

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
