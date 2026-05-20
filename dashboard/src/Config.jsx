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

// ── Main component ─────────────────────────────────────────────────────────────

export default function Config() {
  const { data: settings, isLoading, isError } = useBotSettings();
  const updateMut = useUpdateBotSettings();

  // Local form state — mirrors the DB fields
  const [companyName,   setCompanyName]   = useState('');
  const [bizHours,      setBizHours]      = useState('');
  const [agentWA,       setAgentWA]       = useState('');
  const [dirty,         setDirty]         = useState(false);
  const [saving,        setSaving]        = useState(false);

  // Populate form from fetched settings
  useEffect(() => {
    if (!settings) return;
    setCompanyName(settings.company_name   ?? '');
    setBizHours(   settings.business_hours ?? '');
    setAgentWA(    settings.agent_whatsapp ?? '');
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
    setDirty(false);
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

      <div className="config-body">

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
              placeholder="ej: +5493764123456"
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
