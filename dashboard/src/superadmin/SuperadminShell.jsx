/**
 * SuperadminShell.jsx — layout de la consola /superadmin.
 *
 * Header con marca + selector global de inmobiliaria (consumido por 05/06) + logout, y
 * navegación de pestañas. Las pestañas "Datos", "Analítica" y "Errores" son placeholders
 * que llenan los planes 05, 06 y 07 respectivamente.
 */
import React, { useState } from 'react';
import { useAuth } from '../auth';
import { useSuperadminTenant } from './TenantContext';
import GlobalExplorer from './GlobalExplorer';

const NAVY = '#164a71';

const TABS = [
  { id: 'data', label: 'Datos', hint: 'Explorador global (plan 05)' },
  { id: 'analytics', label: 'Analítica', hint: 'Análisis de plataforma (plan 06)' },
  { id: 'errors', label: 'Errores', hint: 'Triage de reportes (plan 07)' },
];

const S = {
  page: { minHeight: '100vh', background: 'var(--surface-base, #f6f8fa)', color: 'var(--fg-primary, #111)' },
  header: {
    display: 'flex', alignItems: 'center', gap: 16,
    padding: '14px 24px', background: NAVY, color: '#fff',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  brand: { display: 'flex', alignItems: 'center', gap: 10, fontWeight: 700, fontSize: 15 },
  badge: {
    fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase',
    background: 'rgba(255,255,255,0.16)', borderRadius: 999, padding: '3px 8px',
  },
  spacer: { flex: 1 },
  selectorWrap: { display: 'flex', alignItems: 'center', gap: 8 },
  selectorLabel: { fontSize: 12, color: 'rgba(255,255,255,0.75)' },
  select: {
    padding: '7px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.25)',
    background: 'rgba(255,255,255,0.10)', color: '#fff', fontSize: 13, outline: 'none',
    maxWidth: 260,
  },
  logout: {
    padding: '7px 12px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.25)',
    background: 'transparent', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  },
  tabs: {
    display: 'flex', gap: 4, padding: '0 24px',
    background: 'var(--surface-raised, #fff)', borderBottom: '1px solid var(--border-subtle, #e6e9ee)',
  },
  tab: (active) => ({
    appearance: 'none', background: 'none', border: 'none', cursor: 'pointer',
    padding: '14px 14px 12px', fontSize: 14, fontWeight: 600,
    color: active ? NAVY : 'var(--fg-tertiary, #667085)',
    borderBottom: active ? `2px solid ${NAVY}` : '2px solid transparent',
    marginBottom: -1,
  }),
  main: { padding: 24, maxWidth: 1120, margin: '0 auto' },
  placeholder: {
    border: '1px dashed var(--border-subtle, #d0d5dd)', borderRadius: 12,
    padding: '48px 24px', textAlign: 'center', color: 'var(--fg-tertiary, #667085)',
    background: 'var(--surface-raised, #fff)',
  },
  phTitle: { fontSize: 16, fontWeight: 700, color: 'var(--fg-secondary, #344054)', marginBottom: 6 },
};

function TenantSelector() {
  const { tenants, isLoading, selectedTenantId, setSelectedTenantId } = useSuperadminTenant();
  return (
    <div style={S.selectorWrap}>
      <label style={S.selectorLabel} htmlFor="sa-tenant">Inmobiliaria</label>
      <select
        id="sa-tenant"
        style={S.select}
        value={selectedTenantId ?? ''}
        onChange={(e) => setSelectedTenantId(e.target.value || null)}
        disabled={isLoading}
      >
        <option value="">Todas las inmobiliarias</option>
        {tenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.display_name || t.company_name || t.slug || t.id}
          </option>
        ))}
      </select>
    </div>
  );
}

function Placeholder({ tab, scope }) {
  return (
    <div style={S.placeholder}>
      <div style={S.phTitle}>{tab.label}</div>
      <p style={{ margin: 0 }}>{tab.hint}.</p>
      <p style={{ margin: '8px 0 0', fontSize: 13 }}>Ámbito actual: <strong>{scope}</strong>.</p>
    </div>
  );
}

export default function SuperadminShell({ account }) {
  const { logout } = useAuth();
  const { selectedTenant } = useSuperadminTenant();
  const [activeTab, setActiveTab] = useState(TABS[0].id);

  const tab = TABS.find((t) => t.id === activeTab) ?? TABS[0];
  const scope = selectedTenant
    ? (selectedTenant.display_name || selectedTenant.slug || selectedTenant.id)
    : 'Todas las inmobiliarias';

  return (
    <div style={S.page}>
      <header style={S.header}>
        <span style={S.brand}>
          ViviendApp <span style={S.badge}>Super-admin</span>
        </span>
        <span style={S.spacer} />
        <TenantSelector />
        <button type="button" style={S.logout} onClick={logout} title={account?.email}>
          Salir
        </button>
      </header>

      <div style={S.tabs} role="tablist" aria-label="Secciones de super-admin">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`sa-tab-${t.id}`}
            aria-controls={t.id === activeTab ? 'sa-tabpanel' : undefined}
            aria-selected={t.id === activeTab}
            style={S.tab(t.id === activeTab)}
            onClick={() => setActiveTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <main style={S.main}>
        <div id="sa-tabpanel" role="tabpanel" aria-labelledby={`sa-tab-${activeTab}`}>
          {activeTab === 'data' ? <GlobalExplorer /> : <Placeholder tab={tab} scope={scope} />}
        </div>
      </main>
    </div>
  );
}
