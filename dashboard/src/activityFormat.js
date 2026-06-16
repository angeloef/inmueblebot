// Formatea una fila de activity_log en texto legible en español + ícono/color,
// para el timeline unificado "Visitas y actividad". Compartido entre Properties y Clients.

const STATUS_LABEL = {
  available: 'Disponible',
  reserved: 'Reservada',
  sold: 'Vendida',
  rented: 'Alquilada',
};

const RELATION_LABEL = {
  buyer: 'comprador',
  tenant: 'inquilino',
  interested: 'interesado',
};

const FIELD_LABEL = {
  price: 'Precio',
  currency: 'Moneda',
  status: 'Estado',
  location: 'Dirección',
  title: 'Título',
};

const statusLabel = (s) => STATUS_LABEL[s] || s || '—';
const relationLabel = (r) => RELATION_LABEL[r] || r || '—';

/**
 * @param {{ action: string, payload?: object }} a
 * @returns {{ icon: string, color: string, text: string }}
 */
export function formatActivity(a) {
  const p = a.payload || {};
  switch (a.action) {
    case 'status_changed':
      return {
        icon: 'tag',
        color: 'var(--accent-500)',
        text: `Estado: ${statusLabel(p.from)} → ${statusLabel(p.to)}`,
      };
    case 'property_edited': {
      const changes = p.changes || {};
      if (changes.price) {
        return {
          icon: 'edit',
          color: 'var(--fg-tertiary)',
          text: `Precio: ${changes.price.from ?? '—'} → ${changes.price.to ?? '—'}`,
        };
      }
      const labels = Object.keys(changes).map(k => FIELD_LABEL[k] || k);
      return {
        icon: 'edit',
        color: 'var(--fg-tertiary)',
        text: labels.length ? `Editado: ${labels.join(', ')}` : 'Propiedad editada',
      };
    }
    case 'relation_linked':
      return {
        icon: 'user-plus',
        color: 'var(--success-500, var(--accent-500))',
        text: `Vinculado como ${relationLabel(p.relation)}${p.client_name ? `: ${p.client_name}` : ''}`,
      };
    case 'relation_changed':
      return {
        icon: 'user-plus',
        color: 'var(--accent-500)',
        text: `Relación → ${relationLabel(p.relation)}${p.client_name ? `: ${p.client_name}` : ''}`,
      };
    case 'relation_unlinked':
      return {
        icon: 'user',
        color: 'var(--danger-500, var(--fg-tertiary))',
        text: `Desvinculado${p.client_name ? `: ${p.client_name}` : ''}`,
      };
    case 'reassigned':
      return {
        icon: 'arrowUp',
        color: 'var(--fg-tertiary)',
        text: 'Reasignada de sucursal',
      };
    default:
      return { icon: 'calendar', color: 'var(--gray-400)', text: a.action };
  }
}
