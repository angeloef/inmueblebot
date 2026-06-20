// Mapa vista → feature requerida (único lugar de verdad para el gating frontend).
// El tier indica qué plan mínimo la tiene — solo para mostrar en el modal de upgrade.
export const VIEW_GATES = {
  cobranzas: { feature: 'cobranzas', required: 'profesional' },
  website:   { feature: 'website',   required: 'profesional' },
  documents: { feature: 'documents', required: 'enterprise'  },
  reportes:  { feature: 'exec_reports', required: 'enterprise' },
};

// Contenido de marketing por feature para la página de preview (plan 39).
// Un solo componente <FeaturePreview> lo renderiza: agregar una feature nueva
// = agregar una entrada acá, sin tocar la UI. `icon` usa nombres de Primitives.Icon.
export const FEATURE_PREVIEWS = {
  cobranzas: {
    icon: 'money',
    title: 'Cobranzas y gestión de alquileres',
    problem: 'Dejá de perseguir pagos en planillas: seguí vencimientos, ajustes por IPC y estados de cada alquiler en un solo lugar.',
    bullets: [
      'Vencimientos y recordatorios de pago automáticos',
      'Ajuste de alquiler por IPC sin cálculos manuales',
      'Estado de cada contrato: al día, vencido o por renovar',
      'Historial de pagos por inquilino y propiedad',
    ],
  },
  website: {
    icon: 'grid',
    title: 'Tu sitio web con catálogo',
    problem: 'Publicá tus propiedades en un sitio propio que se actualiza solo y captura interesados las 24 horas.',
    bullets: [
      'Catálogo público sincronizado con tus propiedades',
      'Formulario de contacto que crea interesados en la app',
      'Diseño listo para compartir y posicionar',
      'Sin mantenimiento técnico de tu parte',
    ],
  },
  documents: {
    icon: 'folder',
    title: 'Documentos vinculados a clientes',
    problem: 'Tené contratos, garantías y comprobantes de cada cliente ordenados y a mano cuando los necesitás.',
    bullets: [
      'Adjuntá documentos a cada cliente o contrato',
      'Acceso rápido desde la ficha del cliente',
      'Todo centralizado y respaldado',
      'Menos carpetas y mails sueltos',
    ],
  },
  exec_reports: {
    icon: 'activity',
    title: 'Reportes ejecutivos',
    problem: 'Entendé cómo va tu inmobiliaria con métricas claras de gestión, ventas y rendimiento del equipo.',
    bullets: [
      'Indicadores de interesados, visitas y conversión',
      'Rendimiento por agente y por sucursal',
      'Tendencias mes a mes',
      'Datos para decidir, no solo planillas',
    ],
  },
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
