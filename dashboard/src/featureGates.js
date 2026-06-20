// Mapa vista → feature requerida (único lugar de verdad para el gating frontend).
// El tier indica qué plan mínimo la tiene — solo para mostrar en el modal de upgrade.
export const VIEW_GATES = {
  cobranzas: { feature: 'cobranzas', required: 'profesional' },
  website:   { feature: 'website',   required: 'profesional' },
  documents: { feature: 'documents', required: 'enterprise'  },
  reportes:  { feature: 'exec_reports', required: 'enterprise' },
};

/**
 * Devuelve true si el account (objeto /me) tiene la feature.
 * Fail-closed: sin account o sin features → false.
 */
export function hasFeature(account, feature) {
  if (!account) return false;
  // ponytail: features viven en me.subscription.features, no en me.features
  const features = account.subscription?.features ?? [];
  return Array.isArray(features) && features.includes(feature);
}

/**
 * Emite el evento subscription:required para abrir el UpgradeModal.
 */
export function dispatchUpgradeEvent(feature, required) {
  window.dispatchEvent(
    new CustomEvent('subscription:required', { detail: { feature, required } })
  );
}
