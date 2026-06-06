import React from 'react';
import { useBotSettings } from './api';

const STATUS_META = {
  active:  { tone: 'success', dot: 'var(--success-500)',  label: 'Bot activo' },
  paused:  { tone: 'warning', dot: 'var(--warning-500)',  label: 'Bot pausado' },
  offline: { tone: 'danger',  dot: 'var(--danger-500)',   label: 'Bot desconectado' },
  loading: { tone: 'neutral', dot: 'var(--fg-tertiary)',  label: 'Verificando…' },
};

/**
 * Estado del bot derivado de /admin/settings (endpoint existente — sin cambios de backend).
 *
 *  - "Bot activo"        → settings cargó y el bot no está pausado globalmente
 *  - "Bot pausado"       → settings.bot_paused === true (handoff global, si el backend lo expone)
 *  - "Bot desconectado"  → la query a /admin/settings falló (backend inalcanzable)
 *
 * /admin/settings ya se consume en Configuración; TanStack Query deduplica el request.
 */
export default function BotStatusBadge() {
  const { data: settings, isLoading, isError } = useBotSettings();

  const paused = settings?.bot_paused === true || settings?.bot_paused === 'true';
  const status = isError ? 'offline' : isLoading ? 'loading' : paused ? 'paused' : 'active';
  const m = STATUS_META[status];

  return (
    <span className={`bot-status bot-status-${m.tone}`} role="status" aria-live="polite" aria-label={m.label}>
      <span className="bot-status-dot" style={{ background: m.dot }} aria-hidden="true" />
      {m.label}
    </span>
  );
}
